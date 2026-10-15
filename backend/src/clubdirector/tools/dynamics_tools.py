"""Outil de lecture de la dynamique du vestiaire (hiérarchie calculée par le jeu)."""

from __future__ import annotations

from pydantic import Field

from clubdirector.game.dynamics import LIMITATIONS, squad_hierarchy
from clubdirector.tools.registry import ToolArgs, ToolContext, ToolRegistry, ToolResult


class HierarchyArgs(ToolArgs):
    equipe_slot: int = Field(0, ge=0, le=9, description="Équipe du club : 0 = équipe première, 1 et 2 = équipes de jeunes.")


def register_dynamics_tools(reg: ToolRegistry) -> None:
    T = reg.tool

    @T("get_squad_hierarchy", "Hiérarchie du vestiaire de notre club calculée par le jeu : leaders, très influents, "
       "influents, autres (avec l'influence de chacun), et qui est monté ou descendu depuis la liste précédente.",
       "lecture", HierarchyArgs)
    def get_squad_hierarchy(t: ToolContext, a: HierarchyArgs):
        if t.ctx.club_uid is None:
            raise LookupError("Club géré inconnu.")
        data = squad_hierarchy(t.engine, t.ctx.career_id, t.ctx.club_uid, a.equipe_slot)
        if data is None:
            raise LookupError("La sauvegarde ne contient pas de hiérarchie pour cette équipe (resynchroniser, "
                              "ou le jeu ne l'a pas encore calculée).")
        return ToolResult("", True, data={"club": t.ctx.club_name, **data}, limitations=list(LIMITATIONS))
