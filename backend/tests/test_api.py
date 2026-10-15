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


def test_amounts_use_the_save_currency_table_unless_calibrated_by_hand(client, game_dir):
    from sqlalchemy import text

    career = client.post("/api/sync", json={"path": str(game_dir / SCORED.name)}).json()["career_id"]
    assert client.get("/api/status").json()["currency"]["factor"] is None  # fixture : pas de table des devises
    with client.app.state.cd.engine.begin() as c:
        c.execute(text("CREATE TABLE IF NOT EXISTS fm_currencies (career_id INTEGER, snapshot_id INTEGER, "
                       "name TEXT, short_name TEXT, symbol TEXT, rate REAL)"))
        c.execute(text("INSERT INTO fm_currencies (career_id, snapshot_id, name, short_name, symbol, rate) "
                       "VALUES (:k, 0, 'European Euro', 'Euro', '€', 1.15713)"), {"k": career})
    cur = client.get("/api/status").json()["currency"]
    assert cur["source"] == "sauvegarde" and cur["factor"] == 1.15713 and cur["symbol"] == "€"
    client.post("/api/currency/calibrate", json={"player_uid": 900001, "displayed_value": 9_000_000})
    cur = client.get("/api/status").json()["currency"]
    assert cur["source"] == "manuel" and cur["factor"] == 2.0


def test_plugin_heartbeat_updates_live_status(client):
    assert client.get("/api/plugin/status").json()["state"] == "absent"
    r = client.post("/api/plugin/heartbeat", json={"plugin_version": "0.1.0", "game_version": "26.3.2",
                                                   "state": "carriere_chargee", "in_match": True})
    assert r.json()["silent"] is True
    st = client.get("/api/plugin/status").json()
    assert st["state"] == "carriere_chargee" and st["plugin_version"] == "0.1.0"


def test_overlay_page_injects_token_and_loads_offline(client):
    html = client.get("/overlay").text
    assert client.app.state.cd.token in html and "Téléphone du coach" in html
    assert "<script src=" not in html and "https://" not in html  # autonome, hors ligne
    old = client.get("/overlay/panneau").text
    assert client.app.state.cd.token in old and "Directeur sportif IA" in old


def test_phone_contacts_threads_and_streamed_replies(client, game_dir):
    import json as _json

    from clubdirector.ai.providers.base import StepResult

    from .test_ai import ScriptedProvider

    client.post("/api/sync", json={"path": str(game_dir / SCORED.name)})
    contacts = client.get("/api/contacts").json()
    assert [c["role"] for c in contacts] == ["directeur_sportif", "directeur_technique", "entraineur_adjoint"]
    ds = contacts[0]
    assert ds["can_chat"] and ds["intro_pending"] and ds["unread"] == 0
    for c in contacts[1:]:  # poste vacant dans la sauvegarde : personne à qui écrire
        assert c["can_chat"] == (c["person"] is not None)
        if not c["can_chat"]:
            assert client.post(f"/api/contacts/{c['role']}/messages", json={"text": "Salut"}).status_code == 409
    client.app.state.cd.orchestrator.providers = [
        ScriptedProvider([StepResult("Bonjour Coach.\n\nJe prends mes fonctions."), StepResult("Ça va bien, Coach.")])]
    r = client.post("/api/contacts/directeur_sportif/intro")
    events = [_json.loads(line[5:]) for line in r.text.splitlines() if line.startswith("data:")]
    assert [e["type"] for e in events] == ["delta", "done"] and events[-1]["message"]["from"] == "them"
    assert client.get("/api/contacts").json()[0]["unread"] == 1
    client.post("/api/contacts/directeur_sportif/read")
    assert client.get("/api/contacts").json()[0]["unread"] == 0
    r = client.post("/api/contacts/directeur_sportif/messages", json={"text": "Comment ça va ?"})
    assert "Ça va bien" in r.text
    thread = client.get("/api/contacts/directeur_sportif/messages").json()
    assert [m["from"] for m in thread] == ["them", "me", "them"] and thread[1]["text"] == "Comment ça va ?"
    assert client.get("/api/staff/123/photo").status_code == 404
    assert client.get("/api/phone/home").json()["club"] == "Northbridge FC"


def test_status_reports_director_and_office(client, game_dir):
    client.post("/api/sync", json={"path": str(game_dir / SCORED.name)})
    d = client.get("/api/status").json()["director"]
    assert d["office_taken"] is False and d["name"]


def test_sync_latest_picks_the_newest_save(client, game_dir):
    import os
    import time
    newest = game_dir / SCORED.name
    os.utime(newest, (time.time() + 60, time.time() + 60))
    r = client.post("/api/sync/latest")
    assert r.status_code == 200 and r.json()["source"] == SCORED.name


def test_status_is_exposed_by_the_api(client):
    st = client.get("/api/status").json()["auto_sync"]
    assert st["enabled"] is False and st["syncs"] == 0
