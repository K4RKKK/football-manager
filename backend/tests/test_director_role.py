"""Rôle du directeur sportif : dossier du club automatique et prise de poste."""

from clubdirector.ai.club_brief import build_club_dossier
from clubdirector.ai.orchestrator import Orchestrator
from clubdirector.ai.providers.base import StepResult
from clubdirector.preferences import PreferenceStore

from .test_ai import ScriptedProvider


def test_dossier_is_built_from_the_save(registry, tctx):
    dossier = build_club_dossier(registry, tctx)
    assert "Northbridge FC" in dossier  # club géré détecté dans la sauvegarde
    assert "Meilleurs buteurs" in dossier or "Derniers matchs" in dossier
    assert "Coach" not in dossier  # données seulement, pas de style


def test_role_prompt_carries_identity_dossier_and_rules(engine, registry, tctx):
    p = ScriptedProvider([StepResult("Bien reçu, Coach.")])
    tctx.prefs.office_by_career[str(tctx.ctx.career_id)] = 0  # prise de poste déjà faite (sans identité)
    Orchestrator(engine, registry, [p]).ask(tctx, "Que penses-tu de notre saison ?")
    assert "directeur sportif de **Northbridge FC**" in p.system and "TON RÔLE EXACT" in p.system
    assert "TES LIMITES" in p.system and "c'est l'entraîneur qui clique" in p.system
    assert "N'invente jamais" in p.system and "FORMAT : MESSAGES" in p.system
    # Le dossier change à chaque sauvegarde : premier message, après le prompt système et les outils.
    dossier = p.history[0]["content"]
    assert dossier.startswith("DOSSIER") and "Northbridge FC" in dossier and "dernière sauvegarde :" not in p.system
    assert "prendre tes fonctions" not in p.prompt


def test_the_taking_of_office_is_the_directors_first_message_not_a_hijacked_question(engine, registry, tctx, tmp_path):
    store = PreferenceStore(tmp_path / "preferences.json")
    p = ScriptedProvider([StepResult("Bonjour Coach, je prends mes fonctions."), StepResult("Ça va bien, Coach.")])
    orch = Orchestrator(engine, registry, [p], prefs_store=store)
    assert orch.intro_pending(tctx, "directeur_sportif")
    first = orch.introduce(tctx, "directeur_sportif")
    assert first.route == "niveau1" and "prendre tes fonctions" in p.history[-1]["content"]
    assert tctx.ctx.career_id in store.load().office_taken
    thread = orch.thread(tctx, "directeur_sportif")
    # La consigne automatique n'est pas enregistrée : le fil commence par le message du directeur.
    assert [m["role"] for m in orch.conversations.messages(thread)] == ["assistant"]
    assert orch.introduce(tctx, "directeur_sportif") is None  # une seule présentation
    orch.send(tctx, "directeur_sportif", "Comment ça va ?")
    last = p.history[-1]["content"]
    assert "prendre tes fonctions" not in p.prompt and last.startswith("Comment ça va ?")
    assert "UNE seule bulle" in last  # politesse : réponse courte et immédiate
    assert [m["role"] for m in orch.conversations.messages(thread)] == ["assistant", "user", "assistant"]


def test_a_simple_question_is_never_turned_into_the_taking_of_office(engine, registry, tctx, tmp_path):
    p = ScriptedProvider([StepResult("Ça va, Coach !")])
    orch = Orchestrator(engine, registry, [p], prefs_store=PreferenceStore(tmp_path / "p.json"))
    assert orch.office_pending(tctx)
    orch.ask(tctx, "Comment ça va Francis ?")
    assert "prendre tes fonctions" not in p.prompt


def test_take_office_command(engine, registry, tctx):
    p = ScriptedProvider([StepResult("Je prends mes fonctions.")])
    a = Orchestrator(engine, registry, [p]).take_office(tctx)
    assert a.route == "niveau1" and "prendre tes fonctions" in p.history[-1]["content"]


def test_no_taking_of_office_without_a_model(engine, registry, tctx):
    a = Orchestrator(engine, registry, []).ask(tctx, "Que penses-tu de notre saison ?")
    assert a.route == "indisponible" and tctx.ctx.career_id not in tctx.prefs.office_taken


def test_preferences_with_a_windows_bom_still_load(tmp_path):
    p = tmp_path / "preferences.json"
    p.write_bytes(b"\xef\xbb\xbf" + b'{"office_taken": [3]}')
    assert PreferenceStore(p).load().office_taken == [3]


# ------------------------------------------------------------------ identité du directeur en poste
from clubdirector.ai.director_identity import find_director  # noqa: E402
from clubdirector.database.mirror import MirrorTable, write_mirror  # noqa: E402

STAFF_COLS = ["uid", "name", "first_name", "last_name", "age", "nation_id", "club_uid", "team_slot", "is_human_manager",
              "in_club_lists", "unknown_r4", "contract_start", "contract_end", "preferences_patience", "preferences_resources"]


def _staff(engine, career_id, club_uid, rows):
    with engine.begin() as c:
        write_mirror(c, career_id, 1, [MirrorTable("staff", STAFF_COLS, [
            (uid, name, name.split()[0], name.split()[-1], 50, 1, club_uid, 0, 0, lists, code, start, "2029-06-30", 18, 4)
            for uid, name, lists, code, start in rows])])


def test_the_director_in_office_is_detected(engine, tctx):
    club = tctx.ctx.club_uid
    _staff(engine, tctx.ctx.career_id, club, [
        (11, "Alex Coach", 1, 10, "2024-07-01"),        # code 10 mais dans un département : pas directeur
        (12, "Jordan Example", 0, 10, "2025-07-24"),     # directeur sportif
        (13, "Sam Scout", 1, 14, "2025-07-01"),
    ])
    d = find_director(engine, tctx.ctx.career_id, club)
    assert d.name == "Jordan Example" and d.first_name == "Jordan"
    assert any("patient" in x for x in d.traits) and any("économe" in x for x in d.traits)
    assert find_director(engine, tctx.ctx.career_id, club, override_uid=13).name == "Sam Scout"


def test_the_ai_takes_the_director_identity_and_a_new_one_introduces_himself(engine, registry, tctx, tmp_path):
    club = tctx.ctx.club_uid
    _staff(engine, tctx.ctx.career_id, club, [(12, "Jordan Example", 0, 10, "2025-07-24")])
    store = PreferenceStore(tmp_path / "preferences.json")
    p = ScriptedProvider([StepResult("Bonjour Coach."), StepResult("Merci."), StepResult("Bonjour Coach, je suis le nouveau.")])
    orch = Orchestrator(engine, registry, [p], prefs_store=store)
    orch.introduce(tctx, "directeur_sportif")
    assert "Tu es **Jordan Example**" in p.system and "prendre tes fonctions" in p.prompt
    orch.send(tctx, "directeur_sportif", "Bienvenue au club !")
    assert "prendre tes fonctions" not in p.prompt
    _staff(engine, tctx.ctx.career_id, club, [(15, "Robin Nouveau", 0, 10, "2026-01-02")])  # nouveau directeur recruté
    assert orch.intro_pending(tctx, "directeur_sportif")  # nouveau titulaire : nouveau fil
    orch.introduce(tctx, "directeur_sportif")
    assert "Tu es **Robin Nouveau**" in p.system and "prendre tes fonctions" in p.prompt


# ------------------------------------------------------------------ les deux autres contacts du téléphone
from clubdirector.ai.director_identity import find_staff  # noqa: E402
from clubdirector.ai.orchestrator import _alternate  # noqa: E402
from clubdirector.ai.providers.base import ToolCall  # noqa: E402

TEAM_COLS = ["uid", "unique_id", "name", "first_name", "last_name", "age", "nation_id", "club_uid", "team_slot",
             "is_human_manager", "in_club_lists", "list_indexes", "unknown_r4", "wage", "contract_start", "contract_end"]


def _team(engine, career_id, club_uid, rows):
    with engine.begin() as c:
        write_mirror(c, career_id, 1, [MirrorTable("staff", TEAM_COLS, [
            (uid, uid + 1, name, name.split()[0], name.split()[-1], 45, 1, club_uid, slot, 0, 1 if lists != "[]" else 0,
             lists, code, wage, "2025-07-01", "2029-06-30")
            for uid, name, slot, lists, code, wage in rows])])


def test_technical_director_and_assistant_are_found_in_the_save(engine, tctx):
    club = tctx.ctx.club_uid
    _team(engine, tctx.ctx.career_id, club, [
        (21, "Paola Technique", 0, "[2]", 88, 14000),   # directrice technique (équipe première, mieux payée)
        (22, "Elsa Feminine", 0, "[2]", 88, 1000),
        (23, "Tony Adjoint", 0, "[1]", 20, 7200),        # adjoint principal
        (24, "Marc Second", 0, "[1]", 20, 3000),
        (25, "Jean Reserve", 1, "[1]", 20, 9000),        # adjoint de la réserve
        (26, "Kevin Scout", 0, "[2]", 20, 9900),         # même code hors liste entraînement
    ])
    k = tctx.ctx.career_id
    assert find_staff(engine, k, club, "directeur_technique").name == "Paola Technique"
    adj = find_staff(engine, k, club, "entraineur_adjoint")
    assert adj.name == "Tony Adjoint" and adj.unique_id == 24 and adj.role == "entraineur_adjoint"
    assert find_staff(engine, k, club, "entraineur_adjoint", override_uid=24).name == "Marc Second"


def test_each_contact_has_its_own_script_thread_and_colleagues(engine, registry, tctx):
    club = tctx.ctx.club_uid
    _team(engine, tctx.ctx.career_id, club, [(21, "Paola Technique", 0, "[2]", 88, 14000),
                                             (23, "Tony Adjoint", 0, "[1]", 20, 7200)])
    p = ScriptedProvider([StepResult("Salut Coach !"), StepResult("Bonjour Coach.")])
    orch = Orchestrator(engine, registry, [p])
    orch.introduce(tctx, "entraineur_adjoint")
    assert "ENTRAÎNEUR ADJOINT" in p.system and "Tu es **Tony Adjoint**" in p.system and "tutoies" in p.system
    assert "Directeur technique : Paola Technique" in p.system
    orch.send(tctx, "directeur_technique", "Où en est l'académie ?")
    assert "DIRECTEUR TECHNIQUE" in p.system and "Entraîneur adjoint : Tony Adjoint" in p.system
    assert orch.thread(tctx, "entraineur_adjoint") != orch.thread(tctx, "directeur_technique")
    assert orch.conversations.unread(orch.thread(tctx, "entraineur_adjoint")) == 1


def test_replies_are_streamed_and_split_around_data_lookups(engine, registry, tctx):
    p = ScriptedProvider([StepResult("Je regarde ça.", [ToolCall("1", "get_club_squad", {})]),
                          StepResult("On a un seul joueur, Sam Sample.")])
    events = []
    a = Orchestrator(engine, registry, [p]).send(tctx, "directeur_sportif", "Fais-moi un point sur l'effectif", events.append)
    kinds = [e["type"] for e in events]
    assert kinds == ["delta", "break", "tool", "delta"] and events[2]["label"] == "effectif"
    assert a.text == "Je regarde ça.\n\nOn a un seul joueur, Sam Sample."


def test_thinking_only_for_real_analyses(engine, registry):
    orch = Orchestrator(engine, registry, [])
    assert not orch._wants_thinking("Comment ça va Francis ?")
    assert orch._wants_thinking("Fais-moi une analyse détaillée de l'effectif")
    assert Orchestrator(engine, registry, [], thinking="off")._wants_thinking("analyse approfondie") is False


def test_messages_alternate_for_the_model():
    out = _alternate([{"role": "user", "content": "DOSSIER"}, {"role": "user", "content": "Salut"},
                      {"role": "assistant", "content": "Salut Coach"}, {"role": "user", "content": "Ça va ?"}])
    assert [m["role"] for m in out] == ["user", "assistant", "user"] and out[0]["content"] == "DOSSIER\n\nSalut"


def test_messages_are_told_apart_question_request_reply_discussion():
    from clubdirector.ai.orchestrator import message_kind

    asked = "Pellegrini et Dybala finissent en 2026.\n\nVous voulez que je vous chiffre les deux prolongations ?"
    assert message_kind("Comment ça va Francis ?") == "politesse"
    assert message_kind("Merci, bonne journée") == "politesse"
    assert message_kind("Combien il reste sur la marge salariale ?") == "question"
    assert message_kind("Qui sont nos meilleurs buteurs") == "question"
    assert message_kind("Prépare-moi une offre pour un ailier droit") == "demande"
    assert message_kind("Je veux que tu prolonges Dybala") == "demande"
    assert message_kind("Vends Shomurodov") == "demande"
    assert message_kind("Oui vas-y", asked) == "reponse"
    assert message_kind("Seulement Dybala, Pellegrini on le laisse partir", asked) == "reponse"
    assert message_kind("Trouve-moi plutôt un défenseur central", asked) == "demande"
    assert message_kind("Le groupe a bien répondu ce week-end, je suis content") == "discussion"


def test_the_detected_message_type_guides_the_reply(engine, registry, tctx):
    p = ScriptedProvider([StepResult("Trop d'erreurs sur coups de pied arrêtés."), StepResult("Je m'en occupe.")])
    orch = Orchestrator(engine, registry, [p])
    orch.send(tctx, "directeur_sportif", "Pourquoi on prend autant de buts ?")
    assert "type de message : QUESTION" in p.history[-1]["content"]
    orch.send(tctx, "directeur_sportif", "Prépare-moi une offre pour un ailier droit")
    assert "type de message : DEMANDE" in p.history[-1]["content"]
    stored = [m["content"] for m in orch.conversations.messages(orch.thread(tctx, "directeur_sportif"))]
    assert "Consigne automatique" not in " ".join(stored)  # la consigne n'est jamais enregistrée


def test_dossier_names_the_whole_first_team_so_the_model_never_invents_players(registry, tctx):
    dossier = build_club_dossier(registry, tctx)
    roster = next(line for line in dossier.splitlines() if "Effectif COMPLET" in line)
    for player in tctx.repo.squad(tctx.ctx):
        assert player["name"] in roster
    assert "aucun autre joueur n'est à nous" in roster


def test_each_contact_only_gets_the_tools_of_its_job(engine, registry, tctx):
    from clubdirector.ai.orchestrator import Orchestrator

    orch = Orchestrator(engine, registry, [])
    dt = {t["name"] for t in orch._tools_for("directeur_technique")}
    adj = {t["name"] for t in orch._tools_for("entraineur_adjoint")}
    ds = {t["name"] for t in orch._tools_for("directeur_sportif")}
    assert "get_club_staff" in dt and not dt & {"get_club_squad", "search_players", "propose_lineup", "find_recruitment_targets"}
    assert {"propose_lineup", "get_top_players_stat", "get_club_squad"} <= adj
    assert not adj & {"find_recruitment_targets", "search_expiring_contracts", "get_transfer_budget"}
    assert ds >= adj | dt  # le directeur sportif garde tout


def test_a_tool_outside_the_role_is_refused(engine, registry, tctx):
    from clubdirector.ai.orchestrator import Orchestrator
    from clubdirector.ai.providers.base import StepResult, ToolCall

    p = ScriptedProvider([StepResult("", [ToolCall("1", "get_club_squad", {})]), StepResult("C'est le domaine de l'adjoint.")])
    a = Orchestrator(engine, registry, [p]).send(tctx, "directeur_technique", "Que vaut notre attaque ?")
    assert a.tools[0]["ok"] is False and "hors de ton rôle" in a.tools[0]["error"]


def test_the_technical_director_gets_the_staff_not_the_players(registry, tctx):
    dossier = build_club_dossier(registry, tctx, "directeur_technique")
    assert "Effectif COMPLET" not in dossier
    assert "Staff du club" in dossier or "Club :" in dossier  # sauvegarde synthétique : staff parfois absent
