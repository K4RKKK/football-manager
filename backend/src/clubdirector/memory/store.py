"""Mémoire persistante par carrière (préférences, objectifs, décisions) et conversations.

La mémoire ne remplace JAMAIS une donnée vivante du jeu : elle décrit des intentions de
l'utilisateur, pas l'état de la partie.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Engine, desc, func, insert, select, update

from clubdirector.database import schema as s


class MemoryStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def add(self, career_id: int, kind: str, text: str, *, key: str | None = None,
            value: dict | None = None, game_date: date | None = None) -> int:
        with self.engine.begin() as c:
            if key:
                # Une préférence structurée remplace la précédente de même clé.
                c.execute(update(s.memories).where(s.memories.c.career_id == career_id, s.memories.c.key == key)
                          .values(active=False))
            return c.execute(insert(s.memories).values(
                career_id=career_id, kind=kind, key=key, value=value or {}, text=text,
                created_at=datetime.now(UTC), game_date=game_date, active=True,
            )).inserted_primary_key[0]

    def list(self, career_id: int, active_only: bool = True) -> list[dict]:
        q = select(s.memories).where(s.memories.c.career_id == career_id)
        if active_only:
            q = q.where(s.memories.c.active.is_(True))
        with self.engine.connect() as c:
            return [
                {"id": r.id, "type": r.kind, "cle": r.key, "texte": r.text, "valeur": r.value,
                 "date_jeu": r.game_date.isoformat() if r.game_date else None}
                for r in c.execute(q.order_by(s.memories.c.id))
            ]

    def deactivate(self, career_id: int, memory_id: int) -> bool:
        with self.engine.begin() as c:
            res = c.execute(update(s.memories).where(s.memories.c.career_id == career_id, s.memories.c.id == memory_id)
                            .values(active=False))
            return bool(res.rowcount)


class ConversationStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(self, career_id: int, title: str | None = None) -> int:
        with self.engine.begin() as c:
            return c.execute(insert(s.conversations).values(
                career_id=career_id, title=title, created_at=datetime.now(UTC))).inserted_primary_key[0]

    def find_thread(self, career_id: int, contact_role: str, staff_uid: int) -> int | None:
        """Fil de messages d'un contact (rôle + personne) dans une carrière, s'il existe."""
        c_ = s.conversations.c
        with self.engine.connect() as c:
            return c.execute(select(c_.id).where(c_.career_id == career_id, c_.contact_role == contact_role,
                                                 c_.staff_uid == staff_uid).order_by(desc(c_.id)).limit(1)).scalar()

    def thread(self, career_id: int, contact_role: str, staff_uid: int, title: str | None = None) -> int:
        """Fil de messages d'un contact, créé au premier besoin. Un nouveau titulaire du poste a son propre fil."""
        found = self.find_thread(career_id, contact_role, staff_uid)
        if found is not None:
            return found
        with self.engine.begin() as c:
            return c.execute(insert(s.conversations).values(
                career_id=career_id, title=title, created_at=datetime.now(UTC), contact_role=contact_role,
                staff_uid=staff_uid, last_read_id=0)).inserted_primary_key[0]

    def count(self, conversation_id: int) -> int:
        with self.engine.connect() as c:
            return c.execute(select(func.count()).select_from(s.messages)
                             .where(s.messages.c.conversation_id == conversation_id)).scalar_one()

    def unread(self, conversation_id: int) -> int:
        """Messages du contact pas encore lus par l'entraîneur."""
        with self.engine.connect() as c:
            last = c.execute(select(s.conversations.c.last_read_id).where(s.conversations.c.id == conversation_id)).scalar()
            return c.execute(select(func.count()).select_from(s.messages).where(
                s.messages.c.conversation_id == conversation_id, s.messages.c.role == "assistant",
                s.messages.c.id > (last or 0))).scalar_one()

    def mark_read(self, conversation_id: int) -> None:
        with self.engine.begin() as c:
            last = c.execute(select(func.max(s.messages.c.id)).where(s.messages.c.conversation_id == conversation_id)).scalar()
            c.execute(update(s.conversations).where(s.conversations.c.id == conversation_id).values(last_read_id=last or 0))

    def add_message(self, conversation_id: int, role: str, content: str, *, game_date: date | None = None,
                    route: str | None = None, tool_trace: list | None = None) -> int:
        with self.engine.begin() as c:
            return c.execute(insert(s.messages).values(
                conversation_id=conversation_id, role=role, content=content, created_at=datetime.now(UTC),
                game_date=game_date, route=route, tool_trace=tool_trace)).inserted_primary_key[0]

    def messages(self, conversation_id: int, limit: int = 50) -> list[dict]:
        with self.engine.connect() as c:
            rows = c.execute(select(s.messages).where(s.messages.c.conversation_id == conversation_id)
                             .order_by(desc(s.messages.c.id)).limit(limit))
            return [dict(r._mapping) for r in reversed(list(rows))]

    def list(self, career_id: int) -> list[dict]:
        with self.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(
                select(s.conversations).where(s.conversations.c.career_id == career_id).order_by(desc(s.conversations.c.id)))]

    def search(self, career_id: int, text: str, limit: int = 20) -> list[dict]:
        with self.engine.connect() as c:
            rows = c.execute(
                select(s.messages, s.conversations.c.title).join(s.conversations)
                .where(s.conversations.c.career_id == career_id, s.messages.c.content.like(f"%{text}%"))
                .order_by(desc(s.messages.c.id)).limit(limit))
            return [dict(r._mapping) for r in rows]

    def delete_all(self, career_id: int) -> int:
        from sqlalchemy import delete

        with self.engine.begin() as c:
            return c.execute(delete(s.conversations).where(s.conversations.c.career_id == career_id)).rowcount
