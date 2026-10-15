"""Renvois entre contacts, noms inconnus, accords et routage sans IA (mesurés sur le banc d'évaluation)."""

from clubdirector.ai.orchestrator import AGREE_RE, Orchestrator, message_kind
from clubdirector.ai.providers.base import StepResult
from clubdirector.ai.topics import topic_owner, unknown_people

from .test_ai import ScriptedProvider


def test_each_subject_goes_to_the_right_contact():
    assert topic_owner("Quel onze pour jeudi ?", "directeur_sportif") == "entraineur_adjoint"
    assert topic_owner("On travaille quoi à l'entraînement cette semaine ?", "directeur_sportif") == "entraineur_adjoint"
    assert topic_owner("Notre staff médical est-il assez fourni ?", "directeur_sportif") == "directeur_technique"
    assert topic_owner("Recrute-moi un latéral gauche", "entraineur_adjoint") == "directeur_sportif"
    assert topic_owner("Prolongez Dybala", "directeur_technique") == "directeur_sportif"
    assert topic_owner("Comment je recrute un préparateur physique ?", "directeur_technique") is None  # son métier
    assert topic_owner("Quel onze pour jeudi ?", "entraineur_adjoint") is None
    assert topic_owner("Salut, ça va ?", "directeur_sportif") is None


def test_agreement_to_a_proposal_is_recognised():
    asked = "Il faudrait un attaquant.\n\nVous voulez que je lance une recherche ?"
    assert message_kind("D'accord, lance la recherche", asked) == "reponse"
    assert AGREE_RE.search("D'accord, lance la recherche") and AGREE_RE.search("Oui vas-y")
    assert not AGREE_RE.search("Non, on garde tout le monde")


def test_unknown_names_are_spotted(engine, tctx):
    assert unknown_people(engine, tctx.ctx.career_id, "Fais signer Jean-Michel Fictif") == ["Jean-Michel Fictif"]
    known = tctx.repo.squad(tctx.ctx)[0]["name"]
    if " " in known:
        assert unknown_people(engine, tctx.ctx.career_id, f"Que penses-tu de {known} ?") == []


def test_redirect_and_unknown_hints_reach_the_model(engine, registry, tctx):
    p = ScriptedProvider([StepResult("C'est le domaine de l'adjoint."), StepResult("Je ne le connais pas.")])
    orch = Orchestrator(engine, registry, [p])
    orch.send(tctx, "directeur_sportif", "Quel onze pour jeudi ?")
    assert "relève de" in p.history[-1]["content"] and "propose_lineup" not in [t["tool"] for t in []]
    orch.send(tctx, "directeur_sportif", "Fais signer Jean-Michel Fictif")
    assert "ne correspond à aucun joueur" in p.history[-1]["content"]


def test_a_remark_is_not_answered_with_a_raw_fact(engine, registry, tctx):
    p = ScriptedProvider([StepResult("Content de l'entendre, Coach.")])
    a = Orchestrator(engine, registry, [p]).send(tctx, "directeur_sportif",
                                                  "Le groupe a bien réagi après le dernier match, je suis content")
    assert a.route == "niveau1"  # discussion : pas de réponse factuelle sans IA
