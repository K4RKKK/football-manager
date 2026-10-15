"""Résumés des fils de messages : ce qui sort de la fenêtre d'historique reste connu du contact.

Le modèle ne reçoit que les derniers messages d'un fil (`history_messages`). Quand au moins
`MIN_NEW` messages plus anciens ne sont couverts par aucun résumé, le modèle local les résume
(décisions, demandes en cours, chiffres cités, joueurs concernés) ; le résumé est enregistré dans
`conversations.summary` (jusqu'au message `summary_upto`) et placé dans le dossier du contact. Un
résumé ne remplace jamais une donnée du jeu : il rappelle ce qui s'est DIT.
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine, select, update

from clubdirector.database import schema as s

log = logging.getLogger(__name__)
MIN_NEW = 8
MAX_CHARS = 1500
SYSTEM = (
    "Tu tiens le carnet de suivi d'un club de football (carrière Football Manager 26). On te donne un résumé "
    "précédent (éventuel) et de nouveaux échanges entre l'entraîneur et un membre de son staff. Rédige en français "
    "un résumé à jour, en 10 lignes au plus, sous forme de tirets courts : décisions de l'entraîneur, demandes en "
    "cours ou promises, joueurs et clubs concernés, chiffres cités (montants, dates), désaccords. N'invente rien, "
    "n'ajoute aucun conseil, aucune phrase d'introduction."
)


def summary(engine: Engine, conversation_id: int) -> tuple[str | None, int]:
    c_ = s.conversations.c
    with engine.connect() as c:
        row = c.execute(select(c_.summary, c_.summary_upto).where(c_.id == conversation_id)).first()
    return (row.summary, row.summary_upto or 0) if row else (None, 0)


def pending(engine: Engine, conversation_id: int, window: int) -> list[dict]:
    """Messages sortis de la fenêtre et pas encore résumés ([] s'il y en a moins de MIN_NEW)."""
    m = s.messages.c
    _text, upto = summary(engine, conversation_id)
    with engine.connect() as c:
        recent = c.execute(select(m.id).where(m.conversation_id == conversation_id).order_by(m.id.desc())
                           .limit(window)).scalars().all()
        if len(recent) < window:
            return []
        rows = c.execute(select(s.messages).where(m.conversation_id == conversation_id, m.id > upto,
                                                  m.id < min(recent)).order_by(m.id)).all()
    rows = [dict(r._mapping) for r in rows if r.role in ("user", "assistant")]
    return rows if len(rows) >= MIN_NEW else []


def summarize(engine: Engine, provider, conversation_id: int, contact_label: str, window: int) -> str | None:
    """Met à jour le résumé du fil avec le modèle `provider` ; None s'il n'y a rien à résumer."""
    msgs = pending(engine, conversation_id, window)
    if not msgs:
        return None
    old, _upto = summary(engine, conversation_id)
    lines = []
    for x in msgs:
        who = "Entraîneur" if x["role"] == "user" else contact_label
        when = f" ({x['game_date'].strftime('%d/%m/%Y')})" if x.get("game_date") else ""
        lines.append(f"{who}{when} : {x['content'][:1200]}")
    prompt = (f"Résumé précédent :\n{old}\n\n" if old else "") + "Nouveaux échanges :\n" + "\n".join(lines) + \
        "\n\nRésumé à jour :"
    session = provider.start(SYSTEM, [{"role": "user", "content": prompt}], [])
    if hasattr(session, "thinking"):
        session.thinking = False
    text = (session.step().text or "").strip()
    if not text:
        return None
    text = text[:MAX_CHARS]
    with engine.begin() as c:
        c.execute(update(s.conversations).where(s.conversations.c.id == conversation_id)
                  .values(summary=text, summary_upto=msgs[-1]["id"]))
    return text


def summary_block(engine: Engine, conversation_id: int | None) -> str:
    """Bloc ajouté au dossier du contact ('' sans résumé)."""
    if not conversation_id:
        return ""
    text, _upto = summary(engine, conversation_id)
    if not text:
        return ""
    return ("\n\nNOS ÉCHANGES PLUS ANCIENS (résumé, hors des derniers messages) — ce qui a été dit, pas l'état du "
            f"jeu :\n{text}")


__all__ = ["MIN_NEW", "pending", "summarize", "summary", "summary_block"]
