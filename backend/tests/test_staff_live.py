"""Staff vivant : messages proactifs, suivi des dossiers, mémoire longue (décisions, résumés), outils d'analyse."""

from datetime import date

import pytest
from sqlalchemy import text

from clubdirector.ai.orchestrator import Orchestrator
from clubdirector.ai.providers.base import StepResult, ToolCall
from clubdirector.database.mirror import MirrorTable, write_mirror
from clubdirector.database.repositories import Repository
from clubdirector.memory.decisions import coach_rules, detect_decisions
from clubdirector.memory.store import MemoryStore
from clubdirector.memory.summaries import pending, summary
from clubdirector.proactive.staff_messages import NoticeStore, run_proactive
from clubdirector.tools.registry import ToolContext
from clubdirector.transfers.dossiers import DossierStore

from .test_ai import ScriptedProvider

OUR, SOUTHPORT, ATHLETIC, RICH = 5001, 5002, 5004, 5100
SAM, ALEX = 900003, 900001  # Sam Sample (notre défenseur), Alex Example (Southport)
DS, DT, ADJ = "directeur_sportif", "directeur_technique", "entraineur_adjoint"
OFFER_COLS = ["index", "kind", "status", "player_uid", "player_name", "bidding_club_uid", "bidding_club_name",
              "selling_club_uid", "selling_club_name", "amount", "offered_on", "effective_on", "deadline", "updated_on"]
STAFF_COLS = ["uid", "unique_id", "name", "first_name", "last_name", "age", "nation_id", "club_uid", "team_slot",
              "is_human_manager", "in_club_lists", "list_indexes", "unknown_r4", "wage", "has_contract", "contract_start",
              "contract_end"]
INJURY_COLS = ["kind", "player_uid", "player_name", "date", "club_uid", "type_name"]


def _mirror(engine, career_id, *tables):
    with engine.begin() as c:
        write_mirror(c, career_id, 1, list(tables))


def _offers(rows):
    return MirrorTable("transfer_offers", OFFER_COLS, [(i, *r) for i, r in enumerate(rows)])


def _career(engine, tctx):
    """Le club synthétique avec un staff (DT, adjoint), un contrat court et une offre reçue pour Sam Sample."""
    k = tctx.ctx.career_id
    with engine.begin() as c:
        c.execute(text("UPDATE players_current SET transfer_value = 2000000, wage = 2000, contract_end = '2031-06-30' "
                       "WHERE career_id = :k AND uid = :u"), {"k": k, "u": SAM})
    _mirror(engine, k, MirrorTable("staff", STAFF_COLS, [
        (21, 22, "Paola Technique", "Paola", "Technique", 45, 1, OUR, 0, 0, 1, "[2]", 88, 14000, 1, "2029-07-01", "2031-05-31"),
        (23, 24, "Tony Adjoint", "Tony", "Adjoint", 45, 1, OUR, 0, 0, 1, "[1]", 20, 7200, 1, "2029-07-01", "2033-06-30"),
    ]), _offers([
        ("transfer", None, SAM, "Sam Sample", ATHLETIC, "Example Athletic", OUR, "Northbridge FC", 1_500_000,
         "2031-02-20", "2031-02-20", "2031-03-20", None),
    ]), MirrorTable("injuries", INJURY_COLS, []))


def _next_save(engine, tctx, game_date: str) -> ToolContext:
    """Une sauvegarde plus récente de la même carrière (date du jeu avancée)."""
    with engine.begin() as c:
        c.execute(text("UPDATE careers SET last_game_date = :d WHERE id = :k"), {"d": game_date, "k": tctx.ctx.career_id})
    repo = Repository(engine)
    return ToolContext(engine, repo, repo.context(tctx.ctx.career_id), tctx.prefs)


def _thread_texts(orch, tctx, role):
    conv = orch.thread(tctx, role)
    return [m["content"] for m in orch.conversations.messages(conv) if m["role"] == "assistant"]


# --------------------------------------------------------------------------- messages proactifs
def test_each_contact_writes_once_per_new_fact(engine, registry, tctx):
    _career(engine, tctx)
    orch = Orchestrator(engine, registry, [])  # sans modèle : le message reprend les faits
    first = run_proactive(tctx, orch, registry)
    by_role = {m["role"]: m for m in first.messages}
    assert set(by_role) == {DS, DT, ADJ}
    ds = _thread_texts(orch, tctx, DS)[-1]
    assert "Offre reçue le 20/02/2031 de Example Athletic pour Sam Sample : transfert" in ds
    assert "Contrat de Sam Sample : fin le 30/06/2031, dans 4 mois" in ds
    assert "Contrat de Paola Technique (directeur technique) : fin le 31/05/2031" in _thread_texts(orch, tctx, DT)[-1]
    assert "Prochain match le 06/03/2031 : à domicile contre Example Athletic" in _thread_texts(orch, tctx, ADJ)[-1]
    assert orch.conversations.unread(orch.thread(tctx, DS)) == 1  # non lu -> pastille et notification du téléphone
    # Sauvegarde suivante sans fait nouveau : personne n'écrit, aucun doublon.
    again = run_proactive(tctx, orch, registry)
    assert again.new == 0 and again.messages == []
    assert len(_thread_texts(orch, tctx, DS)) == 1
    keys = {n["fact_key"] for n in NoticeStore(engine).recent(tctx.ctx.career_id)}
    assert any(k.startswith("offre|900003|5004|transfer|2031-02-20") for k in keys)


def test_the_model_writes_the_message_from_the_facts_without_showing_its_work(engine, registry, tctx):
    _career(engine, tctx)
    p = ScriptedProvider([StepResult("Coach, Example Athletic propose 1,5 M pour Sam.\n\nJe vous prépare une contre-offre ?")])
    orch = Orchestrator(engine, registry, [p])
    orch.conversations.add_message(orch.thread(tctx, DS), "assistant", "Bonjour Coach.")  # déjà présenté
    report = run_proactive(tctx, orch, registry, roles=(DS,))
    order = p.history[-1]["content"]
    assert order.startswith("[Message automatique") and "Offre reçue le 20/02/2031 de Example Athletic" in order
    assert "Ne parle jamais de sauvegarde lue" in order and "N'invente" not in order.split("Faits établis")[0]
    assert report.messages[0]["route"] == "niveau1"
    assert _thread_texts(orch, tctx, DS)[-1].startswith("Coach, Example Athletic propose 1,5 M")


def test_injuries_and_returns_are_announced_by_the_assistant(engine, registry, tctx):
    _career(engine, tctx)
    k = tctx.ctx.career_id
    _mirror(engine, k, MirrorTable("injuries", INJURY_COLS, [("typed", SAM, "Sam Sample", "2031-03-20", OUR, "Entorse de la cheville")]))
    orch = Orchestrator(engine, registry, [])
    run_proactive(tctx, orch, registry, roles=(ADJ,))
    text_ = _thread_texts(orch, tctx, ADJ)[-1]
    assert "Sam Sample est blessé : Entorse de la cheville, retour prévu le 20/03/2031 (dans 19 jours" in text_
    assert "Indisponibles (blessés ou suspendus) : Sam Sample" in text_
    _mirror(engine, k, MirrorTable("injuries", INJURY_COLS, []))  # sauvegarde suivante : guéri
    later = _next_save(engine, tctx, "2031-03-21")
    run_proactive(later, orch, registry, roles=(ADJ,))
    assert "Sam Sample n'est plus à l'infirmerie" in _thread_texts(orch, later, ADJ)[-1]


def test_a_vacant_post_writes_nothing(engine, registry, tctx):
    _career(engine, tctx)
    _mirror(engine, tctx.ctx.career_id, MirrorTable("staff", STAFF_COLS, []))
    report = run_proactive(tctx, Orchestrator(engine, registry, []), registry)
    assert ADJ in report.skipped_roles  # prochain match à annoncer, mais pas d'adjoint dans la sauvegarde
    assert {m["role"] for m in report.messages} == {DS}  # le directeur sportif peut toujours écrire


# --------------------------------------------------------------------------- dossiers
def test_dossiers_are_opened_then_followed_in_the_next_saves(engine, registry, tctx):
    _career(engine, tctx)
    k = tctx.ctx.career_id
    p = ScriptedProvider([
        StepResult("", [ToolCall("1", "prepare_transfer_offer", {"name": "Alex Example"}),
                        ToolCall("2", "prepare_contract_proposal", {"player_uid": SAM}),
                        ToolCall("3", "prepare_sale", {"player_uid": SAM})]),
        StepResult("Les trois dossiers sont prêts, Coach."),
    ])
    orch = Orchestrator(engine, registry, [p])
    orch.conversations.add_message(orch.thread(tctx, DS), "assistant", "Bonjour Coach.")
    orch.send(tctx, DS, "Prépare une offre pour Alex Example, la prolongation de Sam Sample et sa vente au cas où.")
    store = DossierStore(engine)
    opened = {d["kind"]: d for d in store.list(k)}
    assert set(opened) == {"achat", "contrat", "vente"} and all(d["status"] == "ouvert" for d in opened.values())
    assert opened["achat"]["club_name"] == "Southport Example" and opened["achat"]["plan"]["offre"]["cible"]
    assert opened["contrat"]["baseline"]["contract_end"] == "2031-06-30"

    # Sauvegarde 2 : notre offre pour Alex est enregistrée, Rich United fait une offre pour Sam, Sam a prolongé.
    _mirror(engine, k, _offers([
        ("transfer", None, SAM, "Sam Sample", ATHLETIC, "Example Athletic", OUR, "Northbridge FC", 1_500_000,
         "2031-02-20", "2031-02-20", "2031-03-20", None),
        ("transfer", None, ALEX, "Alex Example", OUR, "Northbridge FC", SOUTHPORT, "Southport Example", 3_000_000,
         "2031-03-05", "2031-03-05", "2031-04-05", None),
        ("transfer", None, SAM, "Sam Sample", RICH, "Rich United", OUR, "Northbridge FC", 4_000_000,
         "2031-03-06", "2031-03-06", "2031-04-06", None),
    ]))
    with engine.begin() as c:
        c.execute(text("UPDATE players_current SET contract_end = '2034-06-30', wage = 3500 WHERE career_id = :k AND uid = :u"),
                  {"k": k, "u": SAM})
    save2 = _next_save(engine, tctx, "2031-03-08")
    quiet = Orchestrator(engine, registry, [])
    run_proactive(save2, quiet, registry, roles=(DS,))
    msg = _thread_texts(quiet, save2, DS)[-1]
    assert "Dossier « achat de Alex Example » (préparé par toi) : notre offre est enregistrée dans le jeu" in msg
    assert "Dossier « prolongation de contrat de Sam Sample » (préparé par toi) : Sam Sample a prolongé jusqu'au 30/06/2034" in msg
    assert "Dossier « vente de Sam Sample » (préparé par toi) : offre reçue de Rich United" in msg
    assert msg.count("Rich United") == 1  # l'offre n'est annoncée qu'une fois (dossier et règle « offre reçue »)
    status = {d["kind"]: d["status"] for d in store.list(k)}
    assert status == {"achat": "offre_faite", "contrat": "conclu", "vente": "offre_recue"}

    # Sauvegarde 3 : l'offre pour Alex aboutit, il rejoint le club.
    _mirror(engine, k, _offers([
        ("transfer", "completed", ALEX, "Alex Example", OUR, "Northbridge FC", SOUTHPORT, "Southport Example", 3_000_000,
         "2031-03-05", "2031-03-12", "2031-04-05", "2031-03-12"),
    ]))
    with engine.begin() as c:
        c.execute(text("UPDATE players_current SET club_uid = :o, club_name = 'Northbridge FC' WHERE career_id = :k AND uid = :u"),
                  {"o": OUR, "k": k, "u": ALEX})
    save3 = _next_save(engine, tctx, "2031-03-14")
    run_proactive(save3, quiet, registry, roles=(DS,))
    assert "Alex Example a rejoint le club (transfert, " in _thread_texts(quiet, save3, DS)[-1]
    achat = next(d for d in store.list(k) if d["kind"] == "achat")
    assert achat["status"] == "conclu" and achat["closed_game_date"] == date(2031, 3, 14)
    assert [e["statut"] for e in achat["events"]] == ["ouvert", "offre_faite", "conclu"]
    before = len(_thread_texts(quiet, save3, DS))
    run_proactive(save3, quiet, registry, roles=(DS,))
    assert len(_thread_texts(quiet, save3, DS)) == before  # rien de nouveau : pas de message


def test_an_operation_asked_to_the_director_is_prepared_before_the_model_and_opens_a_dossier(engine, registry, tctx):
    from clubdirector.transfers.operations import operation_request

    _career(engine, tctx)
    k = tctx.ctx.career_id
    with engine.begin() as c:  # un homonyme gardien, sans club, plus un autre joueur du même nom
        c.execute(text("INSERT INTO players_current (career_id, uid, snapshot_id, name, name_search, age, club_uid, club_name, "
                       "positions, transfer_value) VALUES (:k, 1001, 1, 'Lewis Thomas', 'lewis thomas', 23, NULL, NULL, ',GK,', 77000),"
                       " (:k, 1002, 1, 'Lewis Thomas', 'lewis thomas', 17, :s, 'Southport Example', ',MC,DM,', 20000)"),
                  {"k": k, "s": SOUTHPORT})
    assert operation_request(tctx, "Prépare une offre pour Lewis Thomas, le gardien sans club.")[1] == {"player_uid": 1001}
    assert operation_request(tctx, "Prépare une offre pour Lewis Thomas.") is None  # ambigu : le modèle demande
    assert operation_request(tctx, "Prépare-moi une offre pour Alex Example")[0] == "prepare_transfer_offer"
    assert operation_request(tctx, "Recrute Alex Example") is not None
    assert operation_request(tctx, "Fais une offre pour Sam Sample") is None  # un des nôtres : pas un achat
    assert operation_request(tctx, "On ne vend pas Sam Sample") is None
    p = ScriptedProvider([StepResult("Voici le plan pour Lewis Thomas, Coach.")])
    orch = Orchestrator(engine, registry, [p])
    orch.conversations.add_message(orch.thread(tctx, DS), "assistant", "Bonjour Coach.")
    orch.send(tctx, DS, "Prépare aussi une offre pour Lewis Thomas, le gardien sans club.")
    brief = p.history[-1]["content"]
    assert "[Préparation calculée par l'outil prepare_transfer_offer" in brief and '"joueur": "Lewis Thomas"' in brief
    d = DossierStore(engine).list(k)
    assert [(x["kind"], x["player_uid"], x["status"]) for x in d] == [("achat", 1001, "ouvert")]
    # Une question n'est pas une demande : rien n'est préparé d'office.
    p2 = ScriptedProvider([StepResult("Non, pas encore.")])
    Orchestrator(engine, registry, [p2]).send(tctx, DS, "Sam Sample a prolongé ?")
    assert "Préparation calculée" not in p2.history[-1]["content"]


def test_a_target_who_extends_then_signs_elsewhere_is_followed(engine, registry, tctx):
    _career(engine, tctx)
    k = tctx.ctx.career_id

    def alex(**values):
        sets = ", ".join(f"{c} = :{c}" for c in values)
        with engine.begin() as c:
            c.execute(text(f"UPDATE players_current SET {sets} WHERE career_id = :k AND uid = :u"), {**values, "k": k, "u": ALEX})

    alex(contract_end="2032-06-30")
    store = DossierStore(engine)
    store.open_from_tool(tctx, "prepare_transfer_offer", {"name": "Alex Example"}, {}, role=DS)
    orch = Orchestrator(engine, registry, [])
    alex(contract_end="2035-06-30")  # il prolonge chez lui : le dossier reste ouvert, le prix change
    run_proactive(tctx, orch, registry, roles=(DS,))
    msg = _thread_texts(orch, tctx, DS)[-1]
    assert "Alex Example a prolongé à Southport Example jusqu'au 30/06/2035 (avant : 30/06/2032) ; prix cible réestimé à" in msg
    assert store.list(k)[0]["status"] == "ouvert"
    alex(club_uid=RICH, club_name="Rich United")  # puis il signe ailleurs : dossier clos
    later = _next_save(engine, tctx, "2031-03-20")
    run_proactive(later, orch, registry, roles=(DS,))
    assert "Alex Example a signé ailleurs : Rich United" in _thread_texts(orch, later, DS)[-1]
    assert store.list(k)[0]["status"] == "parti"


def test_a_dossier_change_is_kept_until_it_has_been_reported(engine, registry, tctx):
    _career(engine, tctx)
    k = tctx.ctx.career_id
    store = DossierStore(engine)
    store.open_from_tool(tctx, "prepare_contract_proposal", {"player_uid": SAM}, {}, role=DS)
    with engine.begin() as c:
        c.execute(text("UPDATE players_current SET contract_end = '2033-06-30' WHERE career_id = :k AND uid = :u"), {"k": k, "u": SAM})
    store.review(tctx)  # le changement est vu (ex. relecture interrompue) mais pas encore signalé
    run_proactive(tctx, Orchestrator(engine, registry, []), registry, roles=(DS,))
    assert "a prolongé jusqu'au 30/06/2033" in _thread_texts(Orchestrator(engine, registry, []), tctx, DS)[-1]


# --------------------------------------------------------------------------- mémoire longue
def test_decisions_are_recognised_without_the_model():
    squad = [{"uid": 1, "name": "Matías Soulé"}, {"uid": 2, "name": "Manu Koné"}, {"uid": 3, "name": "Paulo Dybala"}]
    found = detect_decisions("On ne vend pas Soulé, Koné et Dybala. Et âge max 26 ans pour les recrues.", squad, date(2025, 10, 21))
    assert [(d.key, d.value["regle"]) for d in found] == [("vente:1", "ne_pas_vendre"), ("vente:2", "ne_pas_vendre"),
                                                         ("vente:3", "ne_pas_vendre"), ("age_max_recrue", "age_max_recrue")]
    assert detect_decisions("on ne vend pas Soulé et on prolonge Koné", squad, None)[0].value["joueur"] == "Matías Soulé"
    assert len(detect_decisions("on ne vend pas Soulé et on prolonge Koné", squad, None)) == 1
    window = detect_decisions("Le mercato ferme le 2 février", squad, date(2025, 10, 21))[0]
    assert window.value == {"regle": "fin_fenetre_transferts", "value": "2026-02-02"}
    assert detect_decisions("Tu peux vendre Dybala ?", squad, None) == []
    assert detect_decisions("Combien vaut Soulé ?", squad, None) == []


def test_a_decision_told_to_one_contact_is_kept_and_applied_by_all(engine, registry, tctx):
    _career(engine, tctx)
    k = tctx.ctx.career_id
    p = ScriptedProvider([StepResult("Bien reçu Coach, Sam reste."), StepResult("Salut Coach !")])
    orch = Orchestrator(engine, registry, [p])
    orch.send(tctx, DS, "On ne vend pas Sam Sample. Et âge max 26 ans pour les recrues.")
    assert "décision de l'entraîneur retenue dans la mémoire du club" in p.history[-1]["content"]
    texts = [m["texte"] for m in MemoryStore(engine).list(k)]
    assert "Sam Sample : ne pas vendre (décision de l'entraîneur)." in texts
    assert "Recrues : 26 ans maximum (décision de l'entraîneur)." in texts
    orch.send(tctx, ADJ, "Salut")  # un autre contact connaît la décision
    assert "Sam Sample : ne pas vendre" in p.history[0]["content"]
    # Les outils l'appliquent.
    sale = registry.execute("prepare_sale", {"player_uid": SAM}, tctx)
    assert sale.data["strategie"]["alerte"] == "joueur marqué « jamais vendre » par l'entraîneur"
    counter = registry.execute("prepare_counter_offer", {"player_uid": SAM}, tctx)
    assert counter.data["decision"].startswith("refuser")
    targets = registry.execute("find_recruitment_targets", {"role": "dc_stoppeur"}, tctx)
    assert any("Âge maximum de l'entraîneur appliqué : 26 ans" in x for x in targets.limitations)
    report = run_proactive(tctx, Orchestrator(engine, registry, []), registry, roles=(DS,))
    assert report.messages and "L'entraîneur a décidé de NE PAS vendre ce joueur" in _thread_texts(orch, tctx, DS)[-1]
    # Décision contraire : elle remplace la précédente.
    orch2 = Orchestrator(engine, registry, [ScriptedProvider([StepResult("Compris.")])])
    orch2.send(tctx, DS, "Finalement Sam Sample est à vendre.")
    rules = coach_rules(engine, k)
    assert SAM not in rules.never_sell and SAM in rules.to_sell and rules.max_age == 26


def test_old_messages_are_summarised_for_the_contact(engine, registry, tctx):
    p = ScriptedProvider([StepResult("- L'entraîneur refuse de vendre Sam Sample.\n- Offre d'Example Athletic jugée trop basse."),
                          StepResult("Oui Coach.")])
    orch = Orchestrator(engine, registry, [p])
    conv = orch.thread(tctx, DS)
    for i in range(14):
        orch.conversations.add_message(conv, "user", f"Question {i}")
        orch.conversations.add_message(conv, "assistant", f"Réponse {i}")
    assert len(pending(engine, conv, orch.history_messages)) == 16  # 28 messages, 12 dans la fenêtre
    assert orch.summarize_threads(tctx, roles=(DS,)) == [DS]
    text_, upto = summary(engine, conv)
    assert "refuse de vendre Sam Sample" in text_ and upto > 0
    assert pending(engine, conv, orch.history_messages) == []
    orch.send(tctx, DS, "On en est où ?")
    assert "NOS ÉCHANGES PLUS ANCIENS" in p.history[0]["content"] and "refuse de vendre Sam Sample" in p.history[0]["content"]


# --------------------------------------------------------------------------- outils d'analyse
def test_performance_per_90_scout_report_plan_and_dossiers_tools(engine, registry, tctx):
    _career(engine, tctx)
    perf = registry.execute("analyze_player_performance", {"name": "Alex Example", "min_minutes": 0}, tctx)
    assert perf.ok and perf.data["minutes"] == 1080 and perf.data["metriques"]
    assert all(m["statistique"] for m in perf.data["metriques"]) and "percentile" in perf.data["metriques"][0]
    report = registry.execute("generate_scout_report", {"name": "Alex Example"}, tctx)
    assert report.ok and report.data["rapport"].startswith("Alex Example") and report.data["verdict"]
    assert "Marché : estimation" in report.data["rapport"]
    MemoryStore(engine).add(tctx.ctx.career_id, "preference", "Recrues : 18 ans maximum.", key="age_max_recrue",
                            value={"regle": "age_max_recrue", "value": 18})
    strict = registry.execute("generate_scout_report", {"name": "Alex Example"}, tctx)
    assert strict.data["verdict"] == "hors critères de l'entraîneur"
    plan = registry.execute("plan_transfer_window", {}, tctx)
    assert plan.ok and plan.data["priorites"] and plan.data["a_renforcer"]
    assert plan.data["offres_recues_en_cours"][0]["club"] == "Example Athletic"
    assert plan.data["criteres_entraineur"]["age_max_recrue"] == 18
    dossiers = registry.execute("list_dossiers", {}, tctx)
    assert dossiers.ok and dossiers.data["nombre"] == 0
    placeholders = {t.name for t in registry.all() if not t.available}
    assert not {"generate_scout_report", "plan_transfer_window", "analyze_player_performance"} & placeholders


# --------------------------------------------------------------------------- service
@pytest.fixture
def client(settings):
    from fastapi.testclient import TestClient

    from clubdirector.api.app import create_app

    app = create_app(settings)
    app.state.cd.orchestrator.providers = []  # jamais la vraie IA locale de la machine pendant les tests
    c = TestClient(app)
    c.headers["X-ClubDirector-Token"] = app.state.cd.token
    return c


def test_staff_routes_and_no_background_work_during_tests(client, settings, game_dir):
    from .conftest import SCORED

    assert settings.proactive_enabled is False  # suit auto_sync (coupé pendant les tests)
    client.post("/api/sync", json={"path": str(game_dir / SCORED.name)})
    assert client.get("/api/staff/notices").json() == []
    out = client.post("/api/staff/proactive").json()
    assert out["proactif"]["new"] >= 1 and out["proactif"]["messages"]
    notices = client.get("/api/staff/notices").json()
    assert notices and all(n["message_id"] for n in notices)
    assert client.get("/api/staff/dossiers").json() == []
    assert client.get("/api/staff/dossiers", headers={"X-ClubDirector-Token": "x"}).status_code == 401
