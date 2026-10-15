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
    tctx.prefs.office_taken.append(tctx.ctx.career_id)  # pas de prise de poste ici
    Orchestrator(engine, registry, [p]).ask(tctx, "Que penses-tu de notre saison ?")
    assert "directeur sportif de Northbridge FC" in p.system
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
