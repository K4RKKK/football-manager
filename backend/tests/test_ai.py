"""Sections 8, 19.2 — routage économique, boucle d'outils, budget, refus d'inventer."""

import json

import httpx
import pytest

from clubdirector.ai.orchestrator import Orchestrator
from clubdirector.ai.providers.base import ProviderError, StepResult, ToolCall
from clubdirector.ai.providers.openai_compat import OpenAICompatProvider
from clubdirector.ai.router import classify


@pytest.mark.parametrize("q,intent,args", [
    ("Combien avons-nous de défenseurs centraux ?", "count_position", {"position": "DC"}),
    ("Combien de gardiens avons-nous ?", "count_position", {"position": "GK"}),
    ("Qui est notre meilleur buteur ?", "top_stat", {"stat": "goals", "relative_season": 0}),
    ("Qui a été notre meilleur buteur la saison dernière ?", "top_stat", {"stat": "goals", "relative_season": -1}),
    ("Combien Mbappé a-t-il marqué la saison dernière ?", "player_goals", {"name": "mbappe", "relative_season": -1}),
    ("Quel était notre score il y a une semaine ?", "match_days_ago", {"days_ago": 7}),
    ("Quel était notre résultat il y a 10 jours ?", "match_days_ago", {"days_ago": 10}),
    ("Quel est notre budget transferts ?", "transfer_budget", {}),
    ("Où en est-on au classement ?", "table", {}),
    ("Qui est notre joueur le mieux payé ?", "top_wage", {}),
    ("Quels sont les plus gros salaires de l'effectif ?", "top_wage", {}),
])
def test_level0_classification(q, intent, args):
    got = classify(q)
    assert got is not None and got.name == intent and got.args == args


@pytest.mark.parametrize("q", [
    "Bonjour, comment se porte notre club ?",
    "Analyse notre 4-2-3-1 et dis-moi pourquoi nous marquons peu.",
    "Trouve-moi un ailier droit pour moins de 15 millions.",
    "Quels joueurs devrions-nous vendre cet été ?",
])
def test_open_questions_go_to_llm(q):
    assert classify(q) is None


def test_level0_answers_without_any_llm(engine, registry, tctx):
    o = Orchestrator(engine, registry, [])
    a = o.ask(tctx, "Quel était notre score il y a une semaine ?")
    assert a.route == "niveau0" and "3-1" in a.text and "20 février" in a.text
    a = o.ask(tctx, "Combien avons-nous de défenseurs centraux ?")
    assert a.route == "niveau0" and a.text.startswith("Nous avons 1 joueur")
    assert "sauvegarde" not in a.text and "relevé à la date" not in a.text  # ton naturel, pas de jargon
    a = o.ask(tctx, "Combien Mbappé a-t-il marqué la saison dernière ?")
    assert a.route == "niveau0" and "non disponible" in a.text.lower()
    a = o.ask(tctx, "Qui est notre joueur le mieux payé ?")  # 384 s et 6 consultations par le modèle sur le banc
    assert a.route == "niveau0" and a.text.startswith("Le mieux payé, c'est Sam Sample") and "par semaine" in a.text


def test_no_provider_is_reported_honestly(engine, registry, tctx):
    a = Orchestrator(engine, registry, []).ask(tctx, "Fais-moi un bilan complet de notre effectif.")
    assert a.route == "indisponible" and "aucun moteur" in a.text


class ScriptedProvider:
    """Faux modèle : rejoue une liste d'étapes et enregistre ce qu'il reçoit."""

    name, model, tier = "scripted", "fake", 1
    input_cost_per_mtok = output_cost_per_mtok = 0.0

    def __init__(self, steps, tier=1, cost=0.0):
        self.steps, self.tier = list(steps), tier
        self.input_cost_per_mtok = self.output_cost_per_mtok = cost
        self.received_results = []
        self.system = None
        self.tools = None
        self.history = []

    @property
    def prompt(self) -> str:
        """Tout ce que le modèle a reçu : prompt système + messages (dont le DOSSIER)."""
        return (self.system or "") + "\n" + "\n".join(m["content"] for m in self.history)

    def start(self, system, history, tools):
        self.system, self.tools, self.history = system, tools, list(history)
        outer = self

        class S:
            def step(self):
                return outer.steps.pop(0)

            def add_tool_results(self, results):
                outer.received_results.extend(results)

        return S()

    def ping(self):
        return "ok"


def test_llm_tool_loop_uses_real_data(engine, registry, tctx):
    p = ScriptedProvider([
        StepResult("", [ToolCall("1", "get_club_squad", {})], input_tokens=100, output_tokens=10),
        StepResult("Notre effectif compte 1 joueur : Sam Sample.", input_tokens=200, output_tokens=20),
    ])
    a = Orchestrator(engine, registry, [p]).ask(tctx, "Fais-moi un bilan de l'effectif")
    assert a.route == "niveau1" and [t["tool"] for t in a.tools] == ["get_club_squad"]
    payload = json.loads(p.received_results[0][1])
    assert payload["ok"] and payload["data"][0]["nom"] == "Sam Sample"
    assert "N'invente jamais" in p.system and "01/03/2031" in p.history[0]["content"]
    assert all(t["name"] != "submit_transfer_offer" for t in p.tools)


def test_llm_cannot_execute_actions(engine, registry, tctx):
    p = ScriptedProvider([
        StepResult("", [ToolCall("1", "submit_transfer_offer", {"player_uid": 900001, "amount": 12})]),
        StepResult("Je ne peux pas envoyer l'offre : l'exécution dans FM26 n'est pas disponible."),
    ])
    a = Orchestrator(engine, registry, [p]).ask(tctx, "Envoie une offre de 12 millions")
    _call, content, is_error = p.received_results[0]
    assert is_error and "non prouvée" in json.loads(content)["error"]
    assert a.tools[0]["ok"] is False


def test_monthly_budget_blocks_paid_provider(engine, registry, tctx):
    paid = ScriptedProvider([StepResult("x", input_tokens=1_000_000, output_tokens=0)] * 3, tier=2, cost=1.0)
    o = Orchestrator(engine, registry, [paid], mode="hybride", monthly_budget_usd=0.5)
    first = o.ask(tctx, "Analyse libre numéro un")
    assert first.route == "niveau2" and first.cost_usd == pytest.approx(1.0)
    second = o.ask(tctx, "Analyse libre numéro deux")
    assert second.route == "indisponible"


def test_local_mode_never_uses_paid_tiers(engine, registry, tctx):
    paid = ScriptedProvider([StepResult("x")], tier=2, cost=1.0)
    assert Orchestrator(engine, registry, [paid], mode="local").choose_provider("question") is None


def test_provider_failure_is_explicit(engine, registry, tctx):
    class Broken(ScriptedProvider):
        def start(self, *a):
            raise ProviderError("serveur injoignable")

    a = Orchestrator(engine, registry, [Broken([])]).ask(tctx, "Analyse libre")
    assert a.route == "indisponible" and "injoignable" in a.text


def test_openai_compatible_wire_format():
    seen = {}

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        seen.setdefault("bodies", []).append(body)
        if len(seen["bodies"]) == 1:
            return httpx.Response(200, json={"model": "m", "usage": {"prompt_tokens": 5, "completion_tokens": 2},
                "choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "get_league_table", "arguments": "{}"}}]}}]})
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "1er"}}]})

    p = OpenAICompatProvider("llama.cpp", "http://127.0.0.1:8080/v1", "local", transport=httpx.MockTransport(handler))
    sess = p.start("sys", [{"role": "user", "content": "classement ?"}],
                   [{"name": "get_league_table", "description": "d", "parameters": {"type": "object", "properties": {}}}])
    step = sess.step()
    assert step.tool_calls[0].name == "get_league_table" and step.input_tokens == 5
    sess.add_tool_results([(step.tool_calls[0], '{"ok":true}', False)])
    assert sess.step().text == "1er"
    second = seen["bodies"][1]["messages"]
    assert second[0]["role"] == "system" and second[-1] == {"role": "tool", "tool_call_id": "c1", "content": '{"ok":true}'}
    assert seen["bodies"][0]["tool_choice"] == "auto"


def test_openai_compatible_unreachable_server():
    def handler(request):
        raise httpx.ConnectError("refused")

    p = OpenAICompatProvider("ollama", "http://127.0.0.1:11434/v1", "m", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match="injoignable"):
        p.start("s", [], []).step()


@pytest.mark.parametrize("q", [
    "Quel est notre prochain match et que faut-il surveiller ?",
    "Qui est notre meilleur buteur et que penses-tu de sa forme ?",
    "Quel était notre score il y a une semaine ? Analyse-le.",
])
def test_fact_plus_advice_goes_to_llm(q):
    assert classify(q) is None
