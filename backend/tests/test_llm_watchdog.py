"""Surveillance de l'IA locale : serveur figé ou arrêté détecté, relancé, demande refaite.

Aucun vrai llama-server n'est touché : les tests unitaires simulent le serveur (transport HTTP) et
l'horloge ; le test de bout en bout lance un faux serveur (tests/fake_llama_server.py) sur un port
libre, le fige, et vérifie que la surveillance l'arrête, le relance et que la demande aboutit.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from clubdirector.ai.llm_watchdog import LaunchParams, LlmWatchdog, WindowsServerControl, build_watchdog
from clubdirector.ai.providers.base import ProviderError, status_sink
from clubdirector.ai.providers.openai_compat import OpenAICompatProvider
from clubdirector.config import Settings

REAL_CMDLINE = (
    '"C:\\AI\\llama.cpp-b11658-vulkan\\llama-server.exe" -m "C:\\AI\\models\\gemma-4-26B-A4B-it\\'
    'gemma-4-26B-A4B-it-UD-IQ4_XS.gguf" --host 127.0.0.1 --port 8080 --device Vulkan0 -ngl 999 -c 32768 '
    "-fa on -ctk q8_0 -ctv q8_0 -np 1 --jinja --alias clubdirector-local --n-cpu-moe 12 "
)
FAKE_SERVER = Path(__file__).parent / "fake_llama_server.py"


class FakeServer:
    """llama-server simulé : mode « idle », « busy » (avance), « frozen », « silent » (/slots muet),
    « down » (port fermé), « loading »."""

    def __init__(self, mode: str = "idle") -> None:
        self.mode = mode
        self.decoded = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.mode == "down":
            raise httpx.ConnectError("refusé", request=request)
        if request.url.path == "/health":
            return httpx.Response(503 if self.mode == "loading" else 200, json={"status": "ok"})
        if request.url.path == "/slots":
            if self.mode == "silent":
                raise httpx.ReadTimeout("sans réponse", request=request)
            if self.mode == "busy":
                self.decoded += 3
            processing = self.mode in ("busy", "frozen")
            return httpx.Response(200, json=[{"id": 0, "is_processing": processing, "id_task": 4515,
                                              "n_prompt_tokens_processed": 150,
                                              "next_token": [{"n_decoded": self.decoded}]}])
        return httpx.Response(404)


class FakeControl:
    def __init__(self, server: FakeServer, cmdline: str = REAL_CMDLINE) -> None:
        self.server = server
        self.cmdline = cmdline
        self.calls: list = []

    def describe(self, port: int):
        return 18144, "llama-server.exe", self.cmdline

    def stop(self, port: int) -> str:
        self.calls.append("stop")
        self.server.mode = "down"
        return "llama-server.exe (pid 18144) arrêté"

    def start(self, params: LaunchParams) -> None:
        self.calls.append(params)
        self.server.mode = "idle"


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


def make(server: FakeServer, tmp_path: Path, **kw):
    clock = Clock()
    control = FakeControl(server)
    wd = LlmWatchdog("http://127.0.0.1:8080/v1", control, log_path=tmp_path / "llm-watchdog.log",
                     transport=httpx.MockTransport(server.handler), clock=clock, sleep=clock.sleep,
                     stall_s=60, ready_timeout_s=30, **kw)
    return wd, control, clock


def run_checks(wd: LlmWatchdog, clock: Clock, seconds: float, step: float = 10.0) -> list[str]:
    states = []
    end = clock.t + seconds
    while clock.t <= end:
        states.append(wd.check())
        clock.t += step
    return states


def test_launch_params_come_from_the_running_server_command_line():
    p = LaunchParams.from_command_line(REAL_CMDLINE)
    assert (p.port, p.ctx, p.mode_jeu, p.couche_cpu) == (8080, 32768, True, 12)
    assert p.script_args() == ["-Port", "8080", "-Ctx", "32768", "-ModeJeu", "-CoucheCpu", "12"]
    full = LaunchParams.from_command_line(REAL_CMDLINE.replace("--n-cpu-moe 12", "").replace("-c 32768", "-c 16384"))
    assert (full.mode_jeu, full.ctx) == (False, 16384)
    assert "-ModeJeu" not in full.script_args(Path("llm.log")) and full.script_args(Path("llm.log"))[-2:] == ["-Journal", "llm.log"]


def test_busy_server_making_progress_is_never_restarted(tmp_path):
    server = FakeServer("busy")
    wd, control, clock = make(server, tmp_path)
    states = run_checks(wd, clock, 600)
    assert set(states) == {"occupe"} and control.calls == []


def test_frozen_request_is_detected_and_server_restarted_with_same_params(tmp_path):
    server = FakeServer("frozen")
    wd, control, clock = make(server, tmp_path)
    states = run_checks(wd, clock, 80)
    assert states[:6] == ["occupe"] * 6
    assert "pret" in states  # relancé puis de nouveau prêt
    assert control.calls[0] == "stop" and control.calls[1] == LaunchParams(8080, 32768, True, 12)
    assert wd.generation == 1 and wd.status.restarts == 1
    assert "n'avance plus" in wd.status.last_restart_reason
    journal = (tmp_path / "llm-watchdog.log").read_text(encoding="utf-8")
    assert "Relance n° 1" in journal and '"id_task": 4515' in journal and "de nouveau prête" in journal


def test_unanswered_test_request_means_frozen(tmp_path):
    server = FakeServer("idle")
    wd, control, clock = make(server, tmp_path)
    assert wd.check() == "pret"
    server.mode = "silent"
    states = run_checks(wd, clock, 70)
    assert states[0] == "suspect" and "stop" in control.calls
    assert "requête de test" in wd.status.last_restart_reason


def test_request_waiting_without_being_processed_means_frozen(tmp_path):
    server = FakeServer("idle")
    wd, control, clock = make(server, tmp_path)
    with wd.track():
        states = run_checks(wd, clock, 70)
    assert states[0] == "pret" and control.calls and "sans être traitée" in wd.status.last_restart_reason


def test_stopped_server_is_restarted_only_if_it_was_running(tmp_path):
    server = FakeServer("down")
    wd, control, clock = make(server, tmp_path)
    assert run_checks(wd, clock, 30) == ["absent"] * 4 and control.calls == []  # lancé sans IA : rien
    server.mode = "idle"
    assert wd.check() == "pret"
    server.mode = "down"
    assert wd.check() == "suspect"  # un relevé isolé ne suffit pas
    assert wd.check() == "pret" and control.calls[0] == "stop"
    assert "arrêté" in wd.status.last_restart_reason


def test_failed_request_restarts_a_stopped_server_at_once_only_when_watching(tmp_path):
    server = FakeServer("idle")
    wd, control, clock = make(server, tmp_path, interval_s=3600)
    assert wd.check() == "pret"
    server.mode = "down"
    assert wd.after_failure(0) is False and control.calls == []  # boucle non démarrée : jamais de relance
    wd.start()  # premier relevé immédiat, puis une heure d'attente
    try:
        assert wd.after_failure(0) is True  # sans attendre le relevé suivant
    finally:
        wd.stop()
    assert control.calls[0] == "stop" and wd.generation == 1 and wd.status.state == "pret"


def test_restarts_are_limited_per_hour(tmp_path):
    server = FakeServer("frozen")
    wd, control, clock = make(server, tmp_path, max_restarts=1)
    run_checks(wd, clock, 80)
    server.mode = "frozen"
    states = run_checks(wd, clock, 80)
    assert control.calls.count("stop") == 1 and states[-1] == "echec"
    assert "relance automatique suspendue" in wd.status.detail


def test_diagnostic_only_never_restarts(tmp_path):
    server = FakeServer("frozen")
    wd, control, clock = make(server, tmp_path)
    for _ in range(10):
        wd.check(act=False)
        clock.t += 10
    assert wd.status.state == "fige" and control.calls == []


@pytest.mark.skipif(sys.platform != "win32", reason="fenêtre de console Windows")
def test_relaunched_server_gets_its_own_console_not_the_service_outputs(monkeypatch):
    """Le serveur relancé ne doit pas écrire dans la sortie du service : il lui survit, et un tube que
    plus personne ne lit finirait par bloquer ses écritures de journal (constaté au premier essai)."""
    seen = {}
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: seen.update(cmd=cmd, **kw))
    WindowsServerControl(Path("start_llm.ps1"), journal=Path("llm.log")).start(LaunchParams(8080, 32768, True, 8))
    assert not {"stdin", "stdout", "stderr"} & set(seen)
    assert seen["creationflags"] & subprocess.CREATE_NEW_CONSOLE
    assert seen["startupinfo"].wShowWindow == 7  # réduite, sans prendre le focus au jeu
    assert seen["cmd"][-9:] == ["-Port", "8080", "-Ctx", "32768", "-ModeJeu", "-CoucheCpu", "8", "-Journal", "llm.log"]


def test_watchdog_is_built_for_the_local_provider_only(tmp_path):
    s = Settings(home=tmp_path, save_dirs=[], auto_sync=False)
    local = OpenAICompatProvider("llama.cpp local", "http://127.0.0.1:8080/v1", "m")
    remote = OpenAICompatProvider("OpenRouter", "https://openrouter.ai/api/v1", "m")
    wd = build_watchdog(s, [local, remote])
    assert wd is not None and local.watchdog is wd and remote.watchdog is None
    assert wd.log_path == tmp_path / "llm-watchdog.log"
    s.ai.watchdog.enabled = False
    assert build_watchdog(s, [OpenAICompatProvider("x", "http://127.0.0.1:8080/v1", "m")]) is None


# ---------------------------------------------------------------------- côté fournisseur
class StubWatchdog:
    """Surveillance simulée : la 1re demande est coupée par une relance, `after_failure` dit si elle a abouti."""

    def __init__(self, restarted_ok: bool) -> None:
        self.generation = 0
        self.restarted_ok = restarted_ok
        self.restarting = False

    def track(self):
        import contextlib

        return contextlib.nullcontext(lambda: None)

    def after_failure(self, generation: int) -> bool:
        self.generation += 1
        return self.restarted_ok


def test_request_cut_by_a_restart_is_retried_and_user_is_told(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            raise httpx.RemoteProtocolError("connexion coupée", request=request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Bonjour coach."}, "finish_reason": "stop"}]})

    p = OpenAICompatProvider("llama.cpp local", "http://127.0.0.1:8080/v1", "m", transport=httpx.MockTransport(handler))
    p.watchdog = StubWatchdog(restarted_ok=True)
    notices: list[str] = []
    token = status_sink.set(notices.append)
    try:
        step = p.start("système", [{"role": "user", "content": "Salut"}], []).step()
    finally:
        status_sink.reset(token)
    assert step.text == "Bonjour coach." and len(calls) == 2
    assert notices[0].startswith("L'IA locale ne répond pas") and notices[-1] == "IA locale relancée : la demande est refaite."


def test_failed_restart_gives_a_clear_error(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("coupé", request=request)

    p = OpenAICompatProvider("llama.cpp local", "http://127.0.0.1:8080/v1", "m", transport=httpx.MockTransport(handler))
    p.watchdog = StubWatchdog(restarted_ok=False)
    with pytest.raises(ProviderError, match="relance automatique n'a pas abouti"):
        p.start("système", [{"role": "user", "content": "Salut"}], []).step()


def test_stopped_local_server_gives_a_clear_error_without_watchdog():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refusé", request=request)

    p = OpenAICompatProvider("llama.cpp local", "http://127.0.0.1:8080/v1", "m", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match="injoignable sur 127.0.0.1:8080 : serveur arrêté"):
        p.start("système", [{"role": "user", "content": "Salut"}], []).step()


# ---------------------------------------------------------------------- bout en bout (processus réels)
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_health(port: int, timeout: float = 20.0) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise AssertionError("faux serveur non démarré")


@pytest.mark.skipif(sys.platform != "win32", reason="arrêt et lancement de processus Windows")
def test_frozen_server_process_is_killed_relaunched_and_the_reply_arrives(tmp_path):
    port = _free_port()
    cmd = [sys.executable, str(FAKE_SERVER), "--port", str(port)]
    frozen = subprocess.Popen([*cmd, "--fige"], creationflags=subprocess.CREATE_NO_WINDOW)
    # Un vrai processus python.exe joue llama-server : seul le processus de ce port (ce faux serveur) est arrêté.
    control = WindowsServerControl(image="python.exe", command=lambda _params: cmd, window="hidden")
    try:
        _wait_health(port)
        wd = LlmWatchdog(f"http://127.0.0.1:{port}/v1", control, log_path=tmp_path / "llm-watchdog.log",
                         interval_s=0.3, stall_s=2.0, ready_timeout_s=30)
        provider = OpenAICompatProvider("llama.cpp local", f"http://127.0.0.1:{port}/v1", "faux", timeout_s=60)
        provider.watchdog = wd
        notices: list[str] = []
        token = status_sink.set(notices.append)
        wd.start()
        try:
            t0 = time.monotonic()
            step = provider.start("Tu es le directeur sportif.", [{"role": "user", "content": "Salut"}], []) \
                .step_stream(lambda _d: None)
            elapsed = time.monotonic() - t0
        finally:
            status_sink.reset(token)
            wd.stop()
        assert step.text == "Bonjour coach."
        assert frozen.wait(timeout=10) is not None  # le serveur figé a été arrêté
        assert wd.status.restarts == 1 and wd.status.state == "pret"
        assert "n'avance plus" in wd.status.last_restart_reason
        assert any("relance automatique" in n for n in notices)
        journal = (tmp_path / "llm-watchdog.log").read_text(encoding="utf-8")
        assert "serveur observé" in journal and "Relance n° 1" in journal and "de nouveau prête" in journal
        assert elapsed < 30
    finally:
        if frozen.poll() is None:
            frozen.kill()
        try:
            control.stop(port)  # le faux serveur relancé
        except Exception:  # noqa: BLE001
            pass
