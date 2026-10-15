"""Téléphone : apps Mercato / Calendrier / Effectif, réactions, recherche par nom, et parcours de bout en bout.

Toutes les données viennent de la sauvegarde SYNTHÉTIQUE des fixtures (aucune carrière réelle) ; les offres,
joueurs et messages ajoutés ici le sont uniquement pour les tests.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from sqlalchemy import insert, text, update

from clubdirector.ai.providers.base import StepResult
from clubdirector.api.app import create_app
from clubdirector.config import Settings
from clubdirector.database import schema as s
from clubdirector.database.mirror import MirrorTable, write_mirror
from clubdirector.database.repositories import Repository
from clubdirector.memory.store import ConversationStore

from .conftest import SCORED
from .test_ai import ScriptedProvider
from .test_transfers import ATHLETIC, OFFER_COLS, OUR, SAM, SOUTHPORT

ALEX = 900001
QUESTION = "Bonjour Coach.\n\nOn lance la prolongation de Sam Sample ?"


@pytest.fixture
def client(settings):
    app = create_app(settings)
    c = TestClient(app)
    c.headers["X-ClubDirector-Token"] = app.state.cd.token
    return c


def _sync(client, game_dir) -> int:
    return client.post("/api/sync", json={"path": str(game_dir / SCORED.name)}).json()["career_id"]


def _seed_market(engine, career_id: int) -> None:
    """Offres et finances au format du miroir de la sauvegarde (transfer_man, finances)."""
    with engine.begin() as c:
        write_mirror(c, career_id, 1, [
            MirrorTable("transfer_offers", OFFER_COLS, [
                (0, "transfer", None, SAM, "Sam Sample", ATHLETIC, "Example Athletic", OUR, "Northbridge FC",
                 1_500_000, "2031-02-20", "2031-02-20", "2031-03-20", None),
                (2, "transfer", 0x13, ALEX, "Alex Example", OUR, "Northbridge FC", SOUTHPORT, "Southport Example",
                 3_000_000, "2031-02-25", "2031-07-01", "2031-03-25", "2031-02-25"),
            ]),
            MirrorTable("finances", ["club_uid", "club_name", "month", "transfer_budget_allocated", "transfer_budget_remaining",
                                     "wage_budget_weekly", "wage_payroll_weekly", "balance"], [
                (OUR, "Northbridge FC", "2031-02-01", 1_000_000, 500_000, 50_000, 40_000, 100_000),
                (ATHLETIC, "Example Athletic", "2031-02-01", 1_000_000, 900_000, 20_000, 19_000, 0),
            ]),
        ])
        c.execute(text("UPDATE players_current SET transfer_value = 2000000, contract_end = '2034-06-30' "
                       "WHERE career_id = :k AND uid = :u"), {"k": career_id, "u": SAM})


SQUAD_SPEC = [("Gardien Test", {"gk": 20}), ("Latéral Droit Test", {"dr": 20, "wbr": 18}), ("Central Un Test", {"dc": 20}),
              ("Central Deux Test", {"dc": 20}), ("Latéral Gauche Test", {"dl": 20, "wbl": 18}),
              ("Sentinelle Test", {"dm": 20, "mc": 18}), ("Relayeur Un Test", {"mc": 20, "dm": 15}),
              ("Relayeur Deux Test", {"mc": 20}), ("Ailier Droit Test", {"amr": 20, "mr": 18}),
              ("Ailier Gauche Test", {"aml": 20, "ml": 18}), ("Buteur Test", {"stc": 20}), ("Remplaçant Test", {"stc": 16, "amc": 17})]


def _seed_squad(engine, career_id: int) -> None:
    """Douze joueurs de test dans l'équipe première (notes de poste au format de la sauvegarde)."""
    repo = Repository(engine)
    ctx = repo.context(career_id)
    with engine.begin() as c:
        for i, (name, ratings) in enumerate(SQUAD_SPEC):
            c.execute(insert(s.players_current).values(
                career_id=career_id, uid=990_000 + i, snapshot_id=ctx.snapshot_id, name=name,
                name_search=name.lower(), club_uid=ctx.club_uid, club_name=ctx.club_name, team_slot=0,
                position_ratings=ratings, transfer_value=1_000_000 + i, condition=9500, age=25))


def _seed_thread(engine, career_id: int, text_: str = QUESTION) -> tuple[int, int]:
    store = ConversationStore(engine)
    conv = store.thread(career_id, "directeur_sportif", 0)
    return conv, store.add_message(conv, "assistant", text_)


# ----------------------------------------------------------------------------------------- API
def test_mercato_lists_offers_received_and_made_with_budgets(client, game_dir):
    k = _sync(client, game_dir)
    empty = client.get("/api/phone/mercato").json()
    assert empty["recues"] == [] and empty["faites"] == []  # rien d'inventé sans offres dans la sauvegarde
    _seed_market(client.app.state.cd.engine, k)
    mk = client.get("/api/phone/mercato").json()
    (recue,), (faite,) = mk["recues"], mk["faites"]
    assert recue["joueur"] == "Sam Sample" and recue["acheteur"] == "Example Athletic" and recue["etat"] == "en cours"
    assert recue["notre_joueur"] is True and recue["montant"] and recue["date"] == "2031-02-20"
    assert faite["joueur"] == "Alex Example" and faite["vendeur"] == "Southport Example" and faite["notre_joueur"] is False
    assert faite["etat"] == "accord pour plus tard" and faite["effet"] == "2031-07-01"
    # Budgets : ceux de la sauvegarde, tels que les donnent les outils du directeur sportif.
    assert mk["budget_transferts"] == client.post("/api/tools/get_transfer_budget", json={"args": {}}).json()["data"]
    assert mk["budget_salaires"] == client.post("/api/tools/get_wage_budget", json={"args": {}}).json()["data"]
    assert mk["limitations"]
    sale = client.get(f"/api/phone/sale/{SAM}").json()
    assert sale["plan"]["strategie"]["prix_affiche"] and sale["plan"]["offres_recues"][0]["acheteur"] == "Example Athletic"
    assert any("rien n'est envoyé dans FM26" in x for x in sale["limitations"])


def test_lineup_is_computed_from_position_ratings(client, game_dir):
    k = _sync(client, game_dir)
    short = client.get("/api/phone/lineup")
    assert short.status_code == 400 and "joueurs disponibles" in short.json()["detail"]  # pas de onze inventé
    _seed_squad(client.app.state.cd.engine, k)
    lu = client.get("/api/phone/lineup", params={"systeme": "4-3-3"}).json()
    assert lu["systeme"] == "4-3-3" and len(lu["onze"]) == 11 and lu["banc"]
    by_slot = {p["poste"]: p["joueur"] for p in lu["onze"]}
    assert by_slot["GK"] == "Gardien Test" and by_slot["STC"] == "Buteur Test"
    assert all(p["note_poste"] >= 15 for p in lu["onze"]) and all({"photo", "notre_joueur"} <= set(p) for p in lu["onze"])
    assert client.get("/api/phone/lineup", params={"systeme": "9-9-9"}).status_code == 400
    squad = client.get("/api/phone/squad").json()
    gk = next(p for p in squad if p["nom"] == "Gardien Test")
    assert gk["notes_postes"] == {"gk": 20} and gk["condition"] == 95


def test_calendar_returns_upcoming_and_recent_matches(client, game_dir):
    _sync(client, game_dir)
    fx = client.get("/api/phone/fixtures").json()
    assert fx["recent"] and all(m["joue"] for m in fx["recent"]) and not any(m["joue"] for m in fx["upcoming"])


def test_reactions_are_stored_with_the_thread(client, game_dir):
    k = _sync(client, game_dir)
    engine = client.app.state.cd.engine
    _, mid = _seed_thread(engine, k)
    url = f"/api/contacts/directeur_sportif/messages/{mid}/reaction"
    assert client.put(url, json={"reaction": "love"}).json() == {"id": mid, "reaction": "love"}
    assert client.get("/api/contacts/directeur_sportif/messages").json()[-1]["reaction"] == "love"
    client.put(url, json={"reaction": "like"})  # une seule réaction par message : elle est remplacée
    assert client.get("/api/contacts/directeur_sportif/messages").json()[-1]["reaction"] == "like"
    client.put(url, json={"reaction": None})
    assert client.get("/api/contacts/directeur_sportif/messages").json()[-1]["reaction"] is None
    assert client.put(url, json={"reaction": "bisou"}).status_code == 422
    other = ConversationStore(engine).thread(k, "entraineur_adjoint", 77)
    foreign = ConversationStore(engine).add_message(other, "assistant", "Autre fil.")
    assert client.put(f"/api/contacts/directeur_sportif/messages/{foreign}/reaction", json={"reaction": "love"}).status_code == 404
    assert client.put("/api/contacts/inconnu/messages/1/reaction", json={"reaction": "love"}).status_code == 404


# ----------------------------------------------------------------------------------------- recherche par nom
def test_name_index_matches_like_and_follows_each_sync(engine, synced):
    repo = Repository(engine)
    ctx = repo.context(synced.career_id)

    def like(needle):
        with engine.connect() as c:
            return [r[0] for r in c.execute(text(
                "SELECT uid FROM players_current WHERE career_id = :k AND name_search LIKE :p ORDER BY uid"),
                {"k": ctx.career_id, "p": f"%{needle}%"})]

    for needle in ("sam", "Exa", "ample", "zzz", "a", "ÉXAMPLE"):
        got = sorted(r["uid"] for r in repo.find_players_by_name(ctx, needle, limit=50))
        assert got == like(needle.lower().replace("é", "e")), needle
    assert repo.name_condition(ctx, "sample")[1] is True and repo.name_condition(ctx, "sa")[1] is False
    total, rows = repo.search_players(ctx, name="sample", order_by="age")
    assert total == len(like("sample")) and rows
    # Nouvelle synchronisation : l'index est reconstruit à la recherche suivante.
    with engine.begin() as c:
        c.execute(insert(s.players_current).values(career_id=ctx.career_id, uid=999_999, snapshot_id=ctx.snapshot_id,
                                                   name="Zinedine Nouveau", name_search="zinedine nouveau"))
        c.execute(update(s.careers).where(s.careers.c.id == ctx.career_id).values(last_sync_at=datetime.now(UTC)))
    assert [r["name"] for r in repo.find_players_by_name(ctx, "nouveau")] == ["Zinedine Nouveau"]


def test_name_search_falls_back_to_like_without_the_index(engine, synced):
    repo = Repository(engine)
    ctx = repo.context(synced.career_id)
    with engine.begin() as c:
        c.exec_driver_sql("DROP TABLE player_names_fts")
    assert repo.ensure_name_index(ctx) is False
    assert "Sam Sample" in [r["name"] for r in repo.find_players_by_name(ctx, "sample")]


# ----------------------------------------------------------------------------------------- de bout en bout
HARNESS = r"""<!doctype html><meta charset="utf-8"><title>e2e</title>
<iframe id="phone" src="/overlay" style="width:365px;height:860px;border:0"></iframe><pre id="result">en cours</pre>
<script>
const out = {};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, ms = 15000, what = "") {
  const t0 = Date.now();
  for (;;) { try { const v = await fn(); if (v) return v; } catch (e) { /* pas encore */ }
    if (Date.now() - t0 > ms) throw new Error("délai dépassé : " + (what || fn)); await sleep(60); }
}
// Attente en temps réel : le temps virtuel du navigateur sans fenêtre ne s'arrête que pendant une requête ;
// une réponse diffusée (SSE) déjà commencée ne le retient pas. Chaque tour fait donc une vraie requête.
async function untilServer(fn, what, rounds = 5000) {
  for (let i = 0; i < rounds; i++) {
    try { const v = await fn(); if (v) return v; } catch (e) { /* pas encore */ }
    await fetch("/api/health", { cache: "no-store" });
  }
  throw new Error("délai dépassé : " + what);
}
(async () => {
  const f = document.getElementById("phone");
  // L'état du téléphone est une constante de premier niveau : lisible par eval dans la page, pas par window.S.
  const w = await until(() => f.contentWindow && f.contentWindow.eval && f.contentWindow.eval("typeof S") === "object" && f.contentWindow, 15000, "page");
  const d = w.document, $ = (id) => d.getElementById(id), S = w.eval("S");
  await until(() => S.contacts.length && S.home, 15000, "données");
  out.locked = S.locked && !$("lock").hidden;
  out.lockWidget = $("lk-widget").hidden ? "" : $("lk-widget").textContent.replace(/\s+/g, " ").trim();
  out.lockNotes = [...d.querySelectorAll("#lk-notes .note b")].map((e) => e.textContent);
  $("lock").dispatchEvent(new w.PointerEvent("pointerdown", { bubbles: true, clientY: 500 }));
  $("lock").dispatchEvent(new w.PointerEvent("pointerup", { bubbles: true, clientY: 500 }));
  out.unlocked = !S.locked;

  w.openApp("mercato");
  await until(() => d.querySelector("#mk-body .pl"), 15000, "mercato");
  out.received = [...d.querySelectorAll("#mk-body .pl .pn")].map((e) => e.textContent);
  out.receivedStates = [...d.querySelectorAll("#mk-body .state")].map((e) => e.textContent);
  out.mercatoBadge = $("badge-mercato").hidden ? 0 : Number($("badge-mercato").textContent);
  d.querySelector("#mk-body .pl").click();
  await untilServer(() => $("sheet-body").textContent.includes("Prix affiché"), "plan de vente");
  out.salePlan = true;
  w.closeSheet();
  d.querySelector('#mk-seg [data-side="faites"]').click();
  await until(() => d.querySelector("#mk-body .pl"), 15000, "offres faites");
  out.made = [...d.querySelectorAll("#mk-body .pl .pn")].map((e) => e.textContent);

  w.show("home"); await sleep(500); w.openApp("calendar");
  await until(() => d.querySelector("#cal-body .fx"), 15000, "calendrier");
  out.calendarGrid = !!d.querySelector("#cal-body .mgrid");
  out.calendarRows = d.querySelectorAll("#cal-body .fx").length;

  w.show("home"); await sleep(500); w.openApp("squad");
  await until(() => S.data.squad, 15000, "effectif");
  d.querySelector('#sq-seg [data-sort="onze"]').click();
  await until(() => d.querySelector(".pitch .tok"), 15000, "onze");
  out.onze = d.querySelectorAll(".pitch .tok").length;
  d.querySelector(".pitch .tok").click();
  await until(() => $("sheet-body").querySelector(".rpitch"), 15000, "notes de poste");
  out.ratingDots = d.querySelectorAll("#sheet-body .rdot").length;
  w.closeSheet();

  w.show("home"); await sleep(500); w.openChat("directeur_sportif", "messages");
  await until(() => d.querySelector("#thread .msg.them .bubble"), 15000, "fil");
  out.quickReplies = [...d.querySelectorAll("#chips .chip.quick")].map((e) => e.textContent);
  out.chipsVisible = !$("chips").hidden;
  const bubbles = d.querySelectorAll("#thread .msg.them .bubble");
  bubbles[bubbles.length - 1].dispatchEvent(new w.MouseEvent("dblclick", { bubbles: true }));
  out.tapbar = $("tapbar").classList.contains("show");
  $("tapbar").querySelector('[data-k="like"]').click();
  out.reactionSaved = await until(async () => (await w.api("/api/contacts/directeur_sportif/messages")).at(-1).reaction, 15000, "réaction");
  out.reactionBadge = (await until(() => d.querySelector("#thread .react"), 5000, "badge")).textContent;

  d.querySelector("#chips .chip.quick").click();
  try {
    await untilServer(() => !Object.keys(S.live).length && S.threads.directeur_sportif.length >= 3
      && S.threads.directeur_sportif.at(-1).from === "them", "réponse");
  } catch (e) {
    out.debug = { thread: S.threads.directeur_sportif.map((m) => [m.from, m.text, !!m.failed]), toast: $("toast").textContent };
    throw e;
  }
  out.afterReply = S.threads.directeur_sportif.slice(-2).map((m) => [m.from, m.text]);
  out.toolNarration = /consult|outil|get_/i.test(d.getElementById("thread").innerText);

  w.show("home"); await sleep(500); w.openApp("settings");
  d.querySelector('#set-body [data-key="cd-quick"]').click();
  out.quickPref = w.localStorage.getItem("cd-quick");
  $("set-lock-now").click();
  out.relocked = S.locked;
})().catch((e) => { out.error = String(e && e.message || e); })
  .finally(() => { document.getElementById("result").textContent = JSON.stringify(out); });
</script>"""


def _browser() -> str | None:
    candidates = [os.environ.get("CLUBDIRECTOR_E2E_BROWSER"),
                  r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                  r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                  r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  shutil.which("msedge"), shutil.which("google-chrome"), shutil.which("chromium")]
    return next((c for c in candidates if c and Path(c).is_file()), None)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.skipif(_browser() is None, reason="navigateur Chromium (Edge ou Chrome) introuvable")
def test_phone_end_to_end_in_a_real_browser(tmp_path, game_dir):
    """Le vrai téléphone (phone.html) dans Edge/Chrome sans fenêtre, servi par le vrai service HTTP."""
    import uvicorn

    port = _free_port()
    settings = Settings(home=tmp_path / "home", save_dirs=[game_dir], auto_sync=False, port=port)
    settings.ensure_dirs()
    app = create_app(settings)
    state = app.state.cd
    k = state.sync_and_activate(game_dir / SCORED.name)["career_id"]
    _seed_market(state.engine, k)
    _seed_squad(state.engine, k)
    _seed_thread(state.engine, k)
    state.orchestrator.providers = [ScriptedProvider([StepResult("Parfait, je m'en occupe.")] * 3)]
    app.get("/__e2e__", response_class=HTMLResponse)(lambda: HARNESS)  # page de pilotage, uniquement dans ce test

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    try:
        for _ in range(200):
            if server.started:
                break
            time.sleep(0.05)
        proc = subprocess.run(
            [_browser(), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
             "--disable-extensions", f"--user-data-dir={tmp_path / 'profil'}", "--virtual-time-budget=90000",
             "--window-size=420,900", "--dump-dom", f"http://127.0.0.1:{port}/__e2e__"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    finally:
        server.should_exit = True
        th.join(10)
    m = re.search(r'<pre id="result">(.*?)</pre>', proc.stdout, re.S)
    assert m, proc.stdout[-2000:] + proc.stderr[-2000:]
    res = json.loads(m.group(1).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    assert "error" not in res, (res.get("error"), res.get("debug"))
    # Écran verrouillé : prochain match de la sauvegarde et message non lu du directeur sportif.
    assert res["locked"] and res["unlocked"] and res["lockNotes"] == ["Directeur sportif"]
    # Mercato : offres réelles du miroir, plan de vente, pastille pour l'offre en cours.
    assert res["received"] == ["Sam Sample"] and res["receivedStates"] == ["En cours"] and res["mercatoBadge"] == 1
    assert res["salePlan"] and res["made"] == ["Alex Example"]
    assert res["calendarGrid"] and res["calendarRows"] >= 1
    assert res["onze"] == 11 and res["ratingDots"] == 15
    # Messagerie : réponses rapides à la question, réaction enregistrée, réponse diffusée.
    assert res["quickReplies"] == ["Oui, vas-y", "Non", "Dis-m'en plus"] and res["chipsVisible"]
    assert res["tapbar"] and res["reactionSaved"] == "like" and res["reactionBadge"] == "👍"
    assert res["afterReply"] == [["me", "Oui, vas-y"], ["them", "Parfait, je m'en occupe."]]
    assert res["toolNarration"] is False
    assert res["quickPref"] == "off" and res["relocked"]
