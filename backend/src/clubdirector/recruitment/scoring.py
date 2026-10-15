"""Score de compatibilité tactique explicable (0-100).

score = 85 % × moyenne pondérée des attributs du rôle (1-20 ramenée à 0-100)
      + 15 % × familiarité au poste (note de poste FM 1-20 ramenée à 0-100)

Chaque composant est renvoyé : l'IA cite ces chiffres, elle ne les invente pas.
"""

from __future__ import annotations

from dataclasses import dataclass

from clubdirector.database.repositories import ATTRIBUTE_FR, HIDDEN_ATTRIBUTES
from clubdirector.recruitment.roles import ROLES, RoleProfile

ATTRIBUTE_WEIGHT = 0.85
POSITION_WEIGHT = 0.15
METHOD = (
    "Score = 85 % moyenne pondérée des attributs du rôle (échelle 1-20 → 0-100) "
    "+ 15 % meilleure note de poste parmi les postes du rôle (1-20 → 0-100). "
    "Attributs cachés exclus. Poids : clubdirector/recruitment/roles.py."
)


@dataclass
class FitResult:
    role: str
    role_label: str
    score: float | None
    attribute_score: float | None
    position_score: float | None
    best_position: str | None
    contributions: list[dict]
    missing: list[str]
    strengths: list[str]
    weaknesses: list[str]

    def as_dict(self) -> dict:
        return {
            "role": self.role,
            "role_label": self.role_label,
            "score": self.score,
            "attribute_score": self.attribute_score,
            "position_score": self.position_score,
            "best_position": self.best_position,
            "contributions": self.contributions,
            "missing_attributes": self.missing,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "method": METHOD,
        }


def role_with_adjustments(role_key: str, extra_weights: dict[str, float] | None) -> RoleProfile:
    if role_key not in ROLES:
        raise ValueError(f"Rôle inconnu : {role_key}. Rôles : {', '.join(ROLES)}")
    base = ROLES[role_key]
    if not extra_weights:
        return base
    weights = dict(base.weights)
    for attr, w in extra_weights.items():
        if attr not in ATTRIBUTE_FR:
            raise ValueError(f"Attribut inconnu : {attr}")
        if attr in HIDDEN_ATTRIBUTES:
            raise ValueError(f"Attribut caché non utilisable dans un score : {attr}")
        if not 0 <= w <= 10:
            raise ValueError("Les poids doivent être compris entre 0 et 10.")
        weights[attr] = w
    return RoleProfile(base.key, base.label + " (ajusté)", base.positions, weights, base.description)


def score_player(player: dict, role: RoleProfile) -> FitResult:
    attrs = player.get("attributes") or {}
    contributions, missing = [], []
    total_w = 0.0
    acc = 0.0
    for attr, w in role.weights.items():
        v = attrs.get(attr)
        if v is None:
            missing.append(attr)
            continue
        total_w += w
        acc += w * v
        contributions.append({"attribute": attr, "label": ATTRIBUTE_FR.get(attr, attr), "value": v, "weight": w})
    attribute_score = None
    if total_w > 0 and len(missing) <= len(role.weights) // 3:
        attribute_score = round((acc / total_w - 1) / 19 * 100, 1)
    ratings = player.get("position_ratings") or {}
    pos_vals = [(p, ratings.get(p.lower())) for p in role.positions]
    pos_vals = [(p, v) for p, v in pos_vals if v is not None]
    best_pos, best_val = (max(pos_vals, key=lambda x: x[1]) if pos_vals else (None, None))
    position_score = round((best_val - 1) / 19 * 100, 1) if best_val is not None else None
    score = None
    if attribute_score is not None and position_score is not None:
        score = round(ATTRIBUTE_WEIGHT * attribute_score + POSITION_WEIGHT * position_score, 1)
    ranked = sorted(contributions, key=lambda c: (c["value"], c["weight"]), reverse=True)
    strengths = [f"{c['label']} {c['value']}" for c in ranked if c["value"] >= 15][:4]
    weaknesses = [f"{c['label']} {c['value']}" for c in sorted(contributions, key=lambda c: c["value"]) if c["value"] <= 10 and c["weight"] >= 3][:4]
    return FitResult(role.key, role.label, score, attribute_score, position_score, best_pos,
                     contributions, missing, strengths, weaknesses)
