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
    assert "DOSSIER DU CLUB" in p.system and "Northbridge FC" in p.system.split("DOSSIER DU CLUB")[1]
    assert "N'invente jamais" in p.system
    assert "PRISE DE POSTE" not in p.system


def test_first_llm_conversation_is_the_taking_of_office(engine, registry, tctx, tmp_path):
    store = PreferenceStore(tmp_path / "preferences.json")
    p = ScriptedProvider([StepResult("Bonjour Coach, je prends mes fonctions."), StepResult("Réponse suivante.")])
    orch = Orchestrator(engine, registry, [p], prefs_store=store)
    orch.ask(tctx, "Que penses-tu de notre saison ?")
    assert "PRISE DE POSTE" in p.system
    assert tctx.ctx.career_id in store.load().office_taken
    orch.ask(tctx, "Et maintenant ?")
    assert "PRISE DE POSTE" not in p.system  # une seule prise de poste par carrière


def test_take_office_command(engine, registry, tctx):
    p = ScriptedProvider([StepResult("Je prends mes fonctions.")])
    a = Orchestrator(engine, registry, [p]).take_office(tctx)
    assert a.route == "niveau1" and "PRISE DE POSTE" in p.system


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
    orch.ask(tctx, "Que penses-tu de la saison ?")
    assert "Tu es **Jordan Example**" in p.system and "PRISE DE POSTE" in p.system
    orch.ask(tctx, "Bienvenue au club !")
    assert "PRISE DE POSTE" not in p.system
    _staff(engine, tctx.ctx.career_id, club, [(15, "Robin Nouveau", 0, 10, "2026-01-02")])  # nouveau directeur recruté
    orch.ask(tctx, "Bonjour")
    assert "Tu es **Robin Nouveau**" in p.system and "PRISE DE POSTE" in p.system
