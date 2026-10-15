"""Secrets (clés API) : jamais dans le code ni dans config.toml.

Ordre : variable d'environnement CLUBDIRECTOR_SECRET_<REF> → trousseau système (keyring,
Gestionnaire d'identification Windows) si installé.
"""

from __future__ import annotations

import os
import re
import secrets as _secrets
from pathlib import Path

SERVICE = "ClubDirectorAI"


def _env_name(ref: str) -> str:
    return "CLUBDIRECTOR_SECRET_" + re.sub(r"[^A-Z0-9]", "_", ref.upper())


def get_secret(ref: str | None) -> str | None:
    if not ref:
        return None
    val = os.environ.get(_env_name(ref))
    if val:
        return val
    try:
        import keyring  # type: ignore[import-not-found]
    except ImportError:
        return None
    return keyring.get_password(SERVICE, ref)


def set_secret(ref: str, value: str) -> None:
    try:
        import keyring  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            f"Trousseau indisponible : installez l'extra 'keyring' ou définissez {_env_name(ref)}."
        ) from exc
    keyring.set_password(SERVICE, ref, value)


def load_or_create_token(path: Path) -> str:
    """Jeton partagé entre le plugin FM26 et le service local (authentification du plugin)."""
    path = Path(path)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = _secrets.token_urlsafe(32)
    path.write_text(token, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return token


SECRET_PATTERN = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|sk-ant-[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9._\-]{8,})")


def redact(text: str) -> str:
    """Nettoie les secrets éventuels avant journalisation."""
    return SECRET_PATTERN.sub("[SECRET]", text)
