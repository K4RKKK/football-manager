"""Section 17 — service local : authentification, hôte, synchronisation, chat, plugin."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clubdirector.api.app import create_app

from .conftest import SCORED


@pytest.fixture
def client(settings):
    app = create_app(settings)
    c = TestClient(app)
    c.headers["X-ClubDirector-Token"] = app.state.cd.token
    return c


def test_health_is_public_but_api_requires_token(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/status", headers={"X-ClubDirector-Token": "faux"}).status_code == 401


def test_foreign_host_is_rejected(client):
    assert client.get("/api/health", headers={"Host": "evil.example:8765"}).status_code == 403


def test_index_injects_token_and_is_marked_diagnostic(client):
    html = client.get("/").text
    assert client.app.state.cd.token in html and "Interface de diagnostic hors jeu" in html


def test_full_flow_sync_dashboard_chat(client, game_dir):
    assert client.get("/api/dashboard").status_code == 409  # pas encore de carrière
    assert client.post("/api/sync", json={"path": str(game_dir / "x.txt")}).status_code == 400
    assert client.post("/api/sync", json={"path": str(game_dir / "absent.fm")}).status_code == 404
    saves = client.get("/api/saves").json()
    assert {Path(s["path"]).name for s in saves} == {"synthetic-career.fm", "synthetic-career-scored.fm"}
    r = client.post("/api/sync", json={"path": str(game_dir / SCORED.name)})
    assert r.status_code == 200 and r.json()["counts"]["players"] == 4
    d = client.get("/api/dashboard").json()
    assert d["club"]["data"]["club"] == "Northbridge FC"
    assert d["last_matches"]["data"][0]["score"] == "1-2"
    squad = client.get("/api/squad").json()
    assert [p["nom"] for p in squad] == ["Sam Sample"]
    assert client.get("/api/players/900001").json()["nom"] == "Alex Example"
    assert client.get("/api/players/1").status_code == 404
    a = client.post("/api/chat", json={"question": "Quel était notre score il y a une semaine ?"}).json()
    assert a["route"] == "niveau0" and "3-1" in a["text"]
    conv = client.get(f"/api/conversations/{a['conversation_id']}").json()
    assert [m["role"] for m in conv] == ["user", "assistant"]
    assert client.post("/api/tools/submit_transfer_offer", json={"args": {}}).json()["ok"] is False


def test_currency_calibration_and_preferences(client, game_dir):
    client.post("/api/sync", json={"path": str(game_dir / SCORED.name)})
    cal = client.post("/api/currency/calibrate", json={"player_uid": 900001, "displayed_value": 9_000_000}).json()
    assert cal["factor"] == 2.0
    prefs = client.get("/api/preferences").json()
    prefs["knowledge_mode"] = "realiste"
    prefs["advanced_mode_confirmed"] = True
    assert client.put("/api/preferences", json=prefs).json()["advanced_mode_confirmed"] is False


def test_plugin_heartbeat_updates_live_status(client):
    assert client.get("/api/plugin/status").json()["state"] == "absent"
    r = client.post("/api/plugin/heartbeat", json={"plugin_version": "0.1.0", "game_version": "26.3.2",
                                                   "state": "carriere_chargee", "in_match": True})
    assert r.json()["silent"] is True
    st = client.get("/api/plugin/status").json()
    assert st["state"] == "carriere_chargee" and st["plugin_version"] == "0.1.0"
