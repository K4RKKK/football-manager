"""Rapidité : les demandes courantes sur un joueur nommé sont préparées avant le modèle (un seul tour)."""

from types import SimpleNamespace

import pytest

from clubdirector.ai.orchestrator import Orchestrator
from clubdirector.ai.prefetch import amount_in, prefetch_brief, prefetch_calls
from clubdirector.ai.providers.base import StepResult

from .test_ai import ScriptedProvider


class _Repo:
    def squad(self, ctx, team_slot=0):
        return [
            {"uid": 1, "name": "Paulo Dybala", "team_slot": 0, "transfer_value": 30_000_000},
            {"uid": 2, "name": "Lorenzo Pellegrini", "team_slot": 0, "transfer_value": 25_000_000},
            {"uid": 3, "name": "Marco Pellegrini", "team_slot": 1, "transfer_value": 500_000},  # réserve : homonyme
        ]


TCTX = SimpleNamespace(repo=_Repo(), ctx=None)


@pytest.mark.parametrize("message,expected", [
    ("Combien vaut Dybala aujourd'hui ?", [("evaluate_transfer_value", {"player_uid": 1})]),
    ("Prépare la vente de Pellegrini", [("prepare_sale", {"player_uid": 2})]),  # équipe première d'abord
    ("Il faut prolonger Paulo Dybala, tu proposes quoi ?", [("prepare_contract_proposal", {"player_uid": 1})]),
    ("On a reçu une contre-offre pour Dybala ?", [("prepare_counter_offer", {"player_uid": 1})]),
    ("Si on reçoit 15,5 M€ pour Dybala, prépare une contre-offre",
     [("prepare_counter_offer", {"player_uid": 1, "montant_recu": 15_500_000})]),
    ("Quels clubs s'intéressent à Lorenzo Pellegrini ?", [("find_buyers", {"player_uid": 2})]),
    ("On a reçu des offres ?", [("get_transfer_offers", {})]),
    ("Fais une offre pour Lautaro", []),  # une offre à faire : plan d'achat, pas ici
    ("Prépare-moi une offre pour Juanlu", []),
    ("Prépare aussi une offre pour Lewis Thomas, le gardien sans club", []),
    ("On peut recruter Dybala ?", []),
    ("Vends Dybala : trouve un club qui peut payer et prépare l'offre", [("prepare_sale", {"player_uid": 1})]),
    ("Et Marco Pellegrini, il vaut combien ?", [("evaluate_transfer_value", {"player_uid": 3})]),  # nom complet d'abord
    ("Combien vaut Lautaro ?", []),  # pas un joueur du club : le modèle cherche lui-même
    ("Comment ça va ?", []),
])
def test_prefetch_calls_for_common_director_requests(message, expected):
    assert prefetch_calls("directeur_sportif", message, TCTX, None) == expected


def test_prefetch_only_for_the_director_and_its_tools():
    assert prefetch_calls("entraineur_adjoint", "Combien vaut Dybala ?", TCTX, None) == []
    assert prefetch_calls("directeur_sportif", "Combien vaut Dybala ?", TCTX, {"get_club_squad"}) == []


def test_prefetch_brief_is_compact_and_bounded():
    brief = prefetch_brief("evaluate_transfer_value", {"joueur": "Paulo Dybala", "notes": ["x" * 9000]})
    assert '"joueur":"Paulo Dybala"' in brief and len(brief) < 5300 and "sans reconsulter" in brief


def test_director_answers_in_one_round_with_prefetched_data(engine, registry, tctx):
    p = ScriptedProvider([StepResult("Il vaut à peu près ce que dit l'estimation.")])
    a = Orchestrator(engine, registry, [p]).send(tctx, "directeur_sportif", "Combien vaut Sam Sample ?", lambda e: None)
    assert [t["tool"] for t in a.tools] == ["evaluate_transfer_value"] and a.tools[0]["ok"]
    assert "Données déjà consultées pour toi (evaluate_transfer_value)" in p.history[-1]["content"]
    assert not p.steps  # une seule étape du modèle


@pytest.mark.parametrize("text,amount", [
    ("15 M€", 15_000_000), ("12,5 millions d'euros", 12_500_000), ("800 k€", 800_000), ("800 000 €", 800_000),
    ("1.500.000 €", 1_500_000), ("Dybala est notre meilleur joueur", None),
])
def test_amount_in_message(text, amount):
    assert amount_in(text) == amount
