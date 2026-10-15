"""Surveillance de l'IA locale (llama-server) : un serveur figé ou arrêté est relancé.

Constat du 15/10/2026 : llama-server s'est figé une fois — `/health` répondait « ok », aucune
activité CPU/GPU, les demandes restaient sans réponse plus de 3 minutes. `/health` est servi hors
de la boucle de calcul du serveur ; `/slots` passe par elle et décrit la demande en cours (jetons
du prompt traités, jetons générés) : c'est la requête de test courte de la surveillance. Elle ne
touche pas au cache du prompt (préchauffage des contacts), contrairement à une vraie génération.

Diagnostic toutes les `interval_s` secondes :
- « arrete » : le port ne répond plus à deux relevés de suite, alors que le serveur a déjà
  répondu depuis le démarrage du service. Un serveur jamais vu n'est pas lancé d'office :
  ClubDirector peut être lancé sans IA ;
- « fige » : `/slots` ne répond plus, ou la demande en cours n'avance plus (aucun jeton lu ni
  généré), ou une demande du service attend sans être traitée, pendant `stall_s` secondes ;
- « occupe » : une demande avance. Jamais relancé, quelle que soit sa durée.

Relance : arrêt du processus qui écoute sur le port (seulement s'il porte le nom attendu,
llama-server.exe), puis `scripts/start_llm.ps1` avec les paramètres relevés sur la ligne de
commande du serveur (mode jeu, couches MoE sur le CPU, contexte, port). Le serveur écrit son
journal dans `llm.log` (l'ancien est archivé : il garde la trace du blocage) ; la surveillance
note ses relevés et décisions dans `llm-watchdog.log`. Au plus `max_restarts` relances par heure,
ensuite « echec » : l'entraîneur reçoit un message clair au lieu d'un silence.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import logging
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)

START_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "start_llm.ps1"
LOCAL_HOSTS = ("127.0.0.1", "localhost")
_UNSUPPORTED = "non disponible"  # /slots désactivé (--no-slots)


@dataclass(frozen=True)
class LaunchParams:
    """Paramètres de scripts/start_llm.ps1 : ceux du serveur observé, pour le relancer à l'identique."""

    port: int = 8080
    ctx: int = 32768
    mode_jeu: bool = True
    couche_cpu: int = 12

    @classmethod
    def from_command_line(cls, cmdline: str, default_port: int = 8080) -> LaunchParams:
        def opt(*names: str) -> int | None:
            for name in names:
                m = re.search(rf'(?:^|\s){re.escape(name)}(?:\s+|=)"?(\d+)', cmdline)
                if m:
                    return int(m.group(1))
            return None

        moe = opt("--n-cpu-moe", "-ncmoe")
        return cls(port=opt("--port") or default_port, ctx=opt("-c", "--ctx-size") or 32768,
                   mode_jeu=bool(moe), couche_cpu=moe or 12)

    def script_args(self, journal: Path | None = None) -> list[str]:
        args = ["-Port", str(self.port), "-Ctx", str(self.ctx)]
        if self.mode_jeu:
            args += ["-ModeJeu", "-CoucheCpu", str(self.couche_cpu)]
        if journal is not None:
            args += ["-Journal", str(journal)]
        return args


class ServerControl(Protocol):
    def describe(self, port: int) -> tuple[int | None, str | None, str | None]:
        """(pid, nom de l'exécutable, ligne de commande) du processus qui écoute sur le port."""

    def stop(self, port: int) -> str:
        """Arrête le serveur qui écoute sur le port ; renvoie ce qui a été fait."""

    def start(self, params: LaunchParams) -> None: ...


class WindowsServerControl:
    """Arrêt et lancement de llama-server sous Windows (PowerShell, taskkill, start_llm.ps1).

    `image` : seul un processus de ce nom est arrêté (jamais un autre programme sur le port).
    `command` : commande de lancement (défaut : start_llm.ps1 avec les paramètres relevés).
    La fenêtre du serveur s'ouvre réduite, sans prendre le focus (FM26 reste au premier plan)."""

    def __init__(self, script: Path = START_SCRIPT, *, image: str = "llama-server.exe",
                 journal: Path | None = None, command: Callable[[LaunchParams], list[str]] | None = None,
                 window: str = "minimized") -> None:
        self.script = Path(script)
        self.image = image.lower()
        self.journal = journal
        self.command = command
        self.window = window

    @staticmethod
    def _run(args: list[str], timeout: float = 30.0) -> str:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=flags, check=False)
        return out.stdout.decode("utf-8", errors="replace")

    def describe(self, port: int) -> tuple[int | None, str | None, str | None]:
        script = (
            "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
            f"$c = Get-NetTCPConnection -LocalPort {int(port)} -State Listen -ErrorAction SilentlyContinue "
            "| Select-Object -First 1; "
            "if ($c) { $p = Get-CimInstance Win32_Process -Filter \"ProcessId=$($c.OwningProcess)\"; "
            "[pscustomobject]@{pid=$c.OwningProcess; name=$p.Name; cmd=$p.CommandLine} | ConvertTo-Json -Compress }"
        )
        raw = self._run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script]).strip()
        if not raw:
            return None, None, None
        data = json.loads(raw)
        return data.get("pid"), data.get("name"), data.get("cmd")

    def stop(self, port: int) -> str:
        pid, name, _cmd = self.describe(port)
        if pid is None:
            return "aucun processus n'écoute plus sur le port"
        if (name or "").lower() != self.image:
            raise RuntimeError(f"le port {port} est tenu par {name} (pid {pid}), pas par {self.image} : rien n'est arrêté")
        self._run(["taskkill", "/PID", str(pid), "/F"])
        for _ in range(40):  # le port se libère en général en moins d'une seconde
            if self.describe(port)[0] is None:
                return f"{name} (pid {pid}) arrêté"
            time.sleep(0.25)
        raise RuntimeError(f"{name} (pid {pid}) ne s'arrête pas")

    def start(self, params: LaunchParams) -> None:
        cmd = self.command(params) if self.command else [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.script),
            *params.script_args(self.journal)]
        # Aucune sortie héritée du service : le serveur vit plus longtemps que lui, et une sortie vers un
        # tube que plus personne ne lit finirait par bloquer ses écritures de journal (serveur figé).
        kwargs: dict[str, Any] = {"close_fds": True}
        if sys.platform != "win32" or self.window == "hidden":
            kwargs["stdin"] = kwargs["stdout"] = kwargs["stderr"] = subprocess.DEVNULL
        if sys.platform == "win32":
            if self.window == "hidden":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                # Sa propre console (réduite) : aucun descripteur passé, il écrit dans sa fenêtre.
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 7  # SW_SHOWMINNOACTIVE : réduite, sans voler le focus au jeu
                kwargs["startupinfo"] = si
                kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(cmd, **kwargs)  # noqa: S603 — commande fixe (script du dépôt), sans shell


@dataclass
class WatchdogStatus:
    state: str = "inconnu"  # inconnu, absent, demarrage, pret, occupe, suspect, arrete, fige, relance, echec
    detail: str | None = None
    last_check_at: str | None = None
    restarts: int = 0
    last_restart_at: str | None = None
    last_restart_reason: str | None = None
    params: dict | None = None


def _now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class LlmWatchdog:
    def __init__(self, base_url: str, control: ServerControl | None, *, log_path: Path | None = None,
                 interval_s: float = 10.0, stall_s: float = 60.0, probe_timeout_s: float = 8.0,
                 ready_timeout_s: float = 240.0, max_restarts: int = 3, restart_window_s: float = 3600.0,
                 transport: httpx.BaseTransport | None = None, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        u = urlsplit(base_url)
        self.root = f"{u.scheme}://{u.netloc}"
        self.port = u.port or (443 if u.scheme == "https" else 80)
        self.control = control
        self.log_path = Path(log_path) if log_path else None
        self.interval_s = interval_s
        self.stall_s = stall_s
        self.ready_timeout_s = ready_timeout_s
        self.max_restarts = max_restarts
        self.restart_window_s = restart_window_s
        self.clock = clock
        self.sleep = sleep
        self.http = httpx.Client(timeout=httpx.Timeout(probe_timeout_s, connect=3.0), transport=transport)
        self.status = WatchdogStatus()
        self.generation = 0  # +1 à chaque relance : une demande sait si le serveur a été relancé entre-temps
        self.params: LaunchParams | None = None
        self.last_slots: Any = None
        self._ready = threading.Event()
        self._ready.set()
        self._lock = threading.RLock()  # un relevé (et une relance) à la fois
        self._requests: dict[int, list[float]] = {}  # demandes du service en cours : [début, dernier progrès]
        self._ids = itertools.count()
        self._seen = False
        self._down = 0
        self._loading_since: float | None = None
        self._silent_since: float | None = None
        self._signature: tuple | None = None
        self._progress_at = clock()
        self._restart_times: list[float] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ demandes du service
    def covers(self, base_url: str) -> bool:
        u = urlsplit(base_url)
        return f"{u.scheme}://{u.netloc}" == self.root

    @contextlib.contextmanager
    def track(self) -> Iterator[Callable[[], None]]:
        """Déclare une demande en cours ; la fonction rendue signale un progrès (octets reçus)."""
        key = next(self._ids)
        now = self.clock()
        entry = [now, now]
        self._requests[key] = entry

        def progress() -> None:
            entry[1] = self.clock()

        try:
            yield progress
        finally:
            self._requests.pop(key, None)

    def _longest_wait(self, now: float) -> float | None:
        waits = [now - last for _start, last in list(self._requests.values())]
        return max(waits) if waits else None

    def after_failure(self, generation: int, timeout: float | None = None) -> bool:
        """Après une erreur réseau d'une demande : True si le serveur a été relancé depuis
        `generation` et répond de nouveau (la demande peut être refaite). Sans la boucle de
        surveillance (tests, commandes ponctuelles), aucune relance n'est tentée."""
        if self._thread is None:
            return False
        if self.generation == generation and self._ready.is_set():
            self.check(urgent=True)  # serveur arrêté : relance immédiate, sans attendre le relevé suivant
        if self.generation == generation:
            return False
        return self.wait_ready(timeout if timeout is not None else self.ready_timeout_s + 30)

    def wait_ready(self, timeout: float) -> bool:
        self._ready.wait(timeout)
        return self._ready.is_set() and self.status.state in ("pret", "occupe")

    @property
    def restarting(self) -> bool:
        return not self._ready.is_set()

    # ------------------------------------------------------------------ relevé
    def _health(self) -> str:
        try:
            r = self.http.get(self.root + "/health", timeout=5.0)
        except httpx.ConnectError:
            return "ferme"
        except httpx.HTTPError:
            return "muet"
        if r.status_code == 503:
            return "chargement"
        return "ok" if r.status_code < 400 else "muet"

    def _slots(self) -> Any:
        try:
            r = self.http.get(self.root + "/slots")
        except httpx.HTTPError:
            return None
        if r.status_code in (404, 501):
            return _UNSUPPORTED
        if r.status_code >= 400:
            return None
        data = r.json()
        return data if isinstance(data, list) else _UNSUPPORTED

    @staticmethod
    def _progress_signature(slots: list) -> tuple:
        return tuple(
            (s.get("id"), s.get("id_task"), s.get("n_prompt_tokens_processed"),
             tuple(t.get("n_decoded") for t in s.get("next_token") or [] if isinstance(t, dict)))
            for s in slots if isinstance(s, dict) and s.get("is_processing")
        )

    def _diagnose(self, now: float, urgent: bool) -> tuple[str, str | None]:
        health = self._health()
        if health == "ferme":
            self._signature = None
            if not self._seen:
                return "absent", f"IA locale non démarrée (rien n'écoute sur le port {self.port})"
            self._down += 1
            if self._down >= 2 or urgent:
                return "arrete", f"serveur arrêté : le port {self.port} ne répond plus"
            return "suspect", "le port ne répond plus (vérification au prochain relevé)"
        self._down = 0
        if health == "chargement":
            self._seen = True
            self._loading_since = self._loading_since if self._loading_since is not None else now
            if now - self._loading_since >= self.ready_timeout_s:
                return "fige", f"chargement du modèle bloqué depuis {now - self._loading_since:.0f} s"
            return "demarrage", "chargement du modèle"
        self._loading_since = None
        if not self._seen:
            self._seen = True
            self._capture()
        slots = self._slots() if health == "ok" else None
        self.last_slots = slots
        if slots is None:
            self._silent_since = self._silent_since if self._silent_since is not None else now
            silent = now - self._silent_since
            if silent >= self.stall_s:
                return "fige", f"figé : la requête de test reste sans réponse depuis {silent:.0f} s"
            return "suspect", "la requête de test reste sans réponse (vérification au prochain relevé)"
        self._silent_since = None
        waiting = self._longest_wait(now)
        if slots is _UNSUPPORTED:  # sans /slots : seules les demandes du service renseignent
            if waiting is not None and waiting >= 3 * self.stall_s:
                return "fige", f"figé : une demande n'a rien reçu depuis {waiting:.0f} s"
            return "pret", None
        signature = self._progress_signature(slots)
        if signature != self._signature:
            self._signature = signature
            self._progress_at = now
        if signature:
            stalled = now - self._progress_at
            if stalled >= self.stall_s:
                return "fige", f"figé : la demande en cours n'avance plus depuis {stalled:.0f} s (aucun jeton lu ni généré)"
            return "occupe", None
        if waiting is not None and waiting >= self.stall_s:
            return "fige", f"figé : une demande attend depuis {waiting:.0f} s sans être traitée"
        return "pret", None

    def check(self, *, urgent: bool = False, act: bool = True) -> str:
        """Un relevé ; relance le serveur s'il est arrêté ou figé (sauf `act=False`)."""
        with self._lock:
            state, detail = self._diagnose(self.clock(), urgent)
            self.status.state, self.status.detail = state, detail
            self.status.last_check_at = _now_text()
            if state in ("arrete", "fige") and act:
                self._recover(detail or state)
            elif state in ("suspect", "arrete", "fige"):
                log.info("IA locale : %s", detail)
            return self.status.state

    def _capture(self) -> None:
        """Relève la ligne de commande du serveur (paramètres de relance)."""
        if self.control is None:
            return
        try:
            pid, name, cmd = self.control.describe(self.port)
        except Exception as exc:  # noqa: BLE001 — sans relevé, la relance prend les réglages du lanceur
            self.note(f"ligne de commande du serveur illisible : {exc}")
            return
        if cmd:
            self.params = LaunchParams.from_command_line(cmd, self.port)
            self.status.params = asdict(self.params)
            self.note(f"serveur observé : {name} (pid {pid}) {cmd.strip()}", logging.INFO)

    # ------------------------------------------------------------------ relance
    def _recover(self, reason: str) -> bool:
        now = self.clock()
        self._restart_times = [t for t in self._restart_times if now - t < self.restart_window_s]
        if self.control is None:
            self.status.state = "echec"
            self.status.detail = f"{reason} ; relance automatique indisponible sur ce système"
            self.note(self.status.detail)
            return False
        if len(self._restart_times) >= self.max_restarts:
            self.status.state = "echec"
            self.status.detail = (f"{reason} ; relance automatique suspendue ({self.max_restarts} relances en moins "
                                  f"d'une heure) : relancer « Lancer ClubDirector.cmd »")
            self.note(self.status.detail)
            return False
        self._restart_times.append(now)
        self._ready.clear()
        self.generation += 1
        self.status.state = "relance"
        self.status.detail = reason
        slots = json.dumps(self.last_slots, ensure_ascii=False)[:2000] if self.last_slots is not None else "aucun"
        self.note(f"{reason}. Relance n° {len(self._restart_times)} (dernier état /slots : {slots})")
        ok = False
        try:
            if self.params is None:
                self._capture()
            params = self.params or LaunchParams(port=self.port)
            self.note(self.control.stop(self.port))
            self.control.start(params)
            self.note(f"lancement : start_llm.ps1 {' '.join(params.script_args())}")
            ok = self._wait_up()
        except Exception as exc:  # noqa: BLE001 — l'échec est signalé à l'entraîneur, la surveillance continue
            self.note(f"relance impossible : {type(exc).__name__}: {exc}")
        self._signature = None
        self._silent_since = self._loading_since = None
        self._down = 0
        self._progress_at = self.clock()
        self.status.restarts += 1
        self.status.last_restart_at = _now_text()
        self.status.last_restart_reason = reason
        if ok:
            self.status.state, self.status.detail = "pret", f"relancé automatiquement ({reason})"
            self.note("IA locale de nouveau prête")
        else:
            self.status.state = "echec"
            self.status.detail = f"{reason} ; la relance n'a pas abouti (voir llm-watchdog.log et llm.log)"
            self.note(self.status.detail)
        self._ready.set()
        return ok

    def _wait_up(self) -> bool:
        deadline = self.clock() + self.ready_timeout_s
        while self.clock() < deadline:
            if self._health() == "ok":
                return True
            self.sleep(1.0)
        return False

    # ------------------------------------------------------------------ journal, boucle
    def note(self, message: str, level: int = logging.WARNING) -> None:
        log.log(level, "Surveillance IA locale : %s", message)
        if self.log_path is None:
            return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(f"{_now_text()} {message}\n")
        except OSError:
            pass

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="llm-watchdog", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.check()
            except Exception as exc:  # noqa: BLE001 — la surveillance ne s'arrête jamais sur une erreur
                log.warning("Surveillance IA locale : %s", exc)
            self._stop.wait(self.interval_s)

    def stop(self) -> None:
        self._stop.set()

    def as_dict(self) -> dict:
        return asdict(self.status) | {"generation": self.generation, "url": self.root}


def build_watchdog(settings: Any, providers: list) -> LlmWatchdog | None:
    """Surveillance du premier fournisseur local (127.0.0.1) ; les fournisseurs du même serveur y sont reliés."""
    cfg = settings.ai.watchdog
    local = [p for p in providers if urlsplit(getattr(p, "base_url", "") or "").hostname in LOCAL_HOSTS]
    if not cfg.enabled or not local:
        return None
    control = None
    if sys.platform == "win32":
        control = WindowsServerControl(Path(cfg.start_script) if cfg.start_script else START_SCRIPT,
                                       journal=settings.home / "llm.log")
    wd = LlmWatchdog(local[0].base_url, control, log_path=settings.home / "llm-watchdog.log",
                     interval_s=cfg.interval_s, stall_s=cfg.stall_s, ready_timeout_s=cfg.ready_timeout_s,
                     max_restarts=cfg.max_restarts_per_hour)
    for p in local:
        if wd.covers(p.base_url):
            p.watchdog = wd
    return wd
