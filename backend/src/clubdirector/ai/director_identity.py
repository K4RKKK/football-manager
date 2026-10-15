"""Identité du directeur sportif EN POSTE dans la carrière (staff du club géré, sauvegarde FM26).

Le directeur sportif IA prend l'identité réelle de la personne que l'entraîneur a recrutée à ce poste.

Détection (mesurée session 2, build 26.3.0) : dans `fm_staff`, la fonction de directeur sportif est
le code `unknown_r4 = 10` porté par une personne HORS des trois listes de département du club
(médical, entraînement, recrutement). Vérifié sur 11 directeurs sportifs réels de la base (Hughes,
Berta, Viana, Deco, Ausilio, Manna, Tare, Campos, Alemany, Eberl, Mitchell : tous code 10, hors
listes) et confirmé par l'utilisateur sur sa carrière (AS Roma : Francis Cagigao). Le même code
porté par quelqu'un d'une liste de département ne désigne pas un directeur sportif (45 cas).
Préférence manuelle prioritaire : `Preferences.director_staff_uid`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text

DIRECTOR_JOB_CODE = 10

PREFERENCE_LABELS = {
    # préférence fmsave : (libellé si élevée, libellé si basse)
    "business": ("très orienté business et valorisation commerciale du club", "peu porté sur l'aspect commercial"),
    "buying_players": ("enclin à recruter et à investir sur le marché", "réticent à acheter, préfère faire avec l'existant"),
    "resources": ("favorable à des dépenses généreuses", "très économe avec les ressources du club"),
    "patience": ("patient : laisse le temps à un projet de mûrir", "impatient : attend des résultats rapides"),
    "interference": ("interventionniste : s'implique dans le travail des autres", "discret : laisse chacun faire son travail"),
    "flexibility": ("souple : prêt à changer d'approche", "attaché à ses principes, change rarement d'approche"),
    "attacking": ("amateur de football offensif", "attaché à la solidité défensive"),
    "directness": ("aime un jeu direct", "préfère un jeu de possession patient"),
    "trigger_press": ("veut une équipe qui presse haut", "préfère un bloc qui attend"),
    "tempo": ("aime un tempo élevé", "aime un tempo maîtrisé"),
    "width": ("aime le jeu sur les ailes", "aime le jeu dans l'axe"),
    "squad_rotation": ("partisan de la rotation de l'effectif", "préfère une équipe-type stable"),
    "hardness_of_training": ("partisan d'un entraînement exigeant", "partisan d'une charge d'entraînement mesurée"),
    "mind_games": ("aime la guerre psychologique et la communication offensive", "évite les jeux d'influence dans les médias"),
}


@dataclass
class DirectorIdentity:
    uid: int
    name: str
    first_name: str | None
    last_name: str | None
    age: int | None
    nation_id: int | None
    contract_start: str | None
    contract_end: str | None
    preferences: dict[str, int] = field(default_factory=dict)
    method: str = "sauvegarde FM26 : fonction de directeur sportif"

    @property
    def traits(self) -> list[str]:
        """Traits marqués (≥ 15 ou ≤ 6 sur 20), du plus marqué au moins marqué."""
        out = []
        for key, value in sorted(self.preferences.items(), key=lambda kv: -abs(kv[1] - 10.5)):
            if key in PREFERENCE_LABELS and value is not None and (value >= 15 or value <= 6):
                high, low = PREFERENCE_LABELS[key]
                out.append(f"{high if value >= 15 else low} ({value}/20)")
        return out

    def as_dict(self) -> dict:
        return {"uid": self.uid, "name": self.name, "first_name": self.first_name, "last_name": self.last_name,
                "age": self.age, "contract_start": self.contract_start, "contract_end": self.contract_end,
                "traits": self.traits, "method": self.method}


def find_director(engine, career_id: int, club_uid: int | None, override_uid: int | None = None) -> DirectorIdentity | None:
    """Le directeur sportif en poste au club géré, ou None si la sauvegarde n'en désigne aucun."""
    if club_uid is None:
        return None
    pref_cols = ", ".join(f"preferences_{k}" for k in PREFERENCE_LABELS)
    base = (f"SELECT uid, name, first_name, last_name, age, nation_id, contract_start, contract_end, {pref_cols} "
            "FROM fm_staff WHERE career_id = :k AND club_uid = :club AND coalesce(is_human_manager, 0) = 0 ")
    with engine.connect() as c:
        try:
            if override_uid is not None:
                row = c.execute(text(base + "AND uid = :uid"), {"k": career_id, "club": club_uid, "uid": override_uid}).mappings().first()
                method = "choisi par l'entraîneur (préférence director_staff_uid)"
            else:
                row = c.execute(text(base + "AND unknown_r4 = :code AND coalesce(in_club_lists, 0) = 0 "
                                     "ORDER BY coalesce(team_slot, 0), contract_start DESC LIMIT 1"),
                                {"k": career_id, "club": club_uid, "code": DIRECTOR_JOB_CODE}).mappings().first()
                method = "sauvegarde FM26 : fonction de directeur sportif"
        except Exception:  # noqa: BLE001 — miroir du staff absent avant la première synchronisation
            return None
    if row is None:
        return None
    prefs = {k: row[f"preferences_{k}"] for k in PREFERENCE_LABELS if row[f"preferences_{k}"] is not None}
    return DirectorIdentity(row["uid"], row["name"], row["first_name"], row["last_name"], row["age"], row["nation_id"],
                            row["contract_start"], row["contract_end"], prefs, method)
