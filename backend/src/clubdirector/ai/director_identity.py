"""Identité du directeur sportif EN POSTE dans la carrière (staff du club géré, sauvegarde FM26).

Le directeur sportif IA prend l'identité réelle de la personne que l'entraîneur a recrutée à ce poste.

Détection (mesurée session 2, build 26.3.0) : dans `fm_staff`, la fonction de directeur sportif est
le code `unknown_r4 = 10` porté par une personne HORS des trois listes de département du club
(médical, entraînement, recrutement). Vérifié sur 11 directeurs sportifs réels de la base (Hughes,
Berta, Viana, Deco, Ausilio, Manna, Tare, Campos, Alemany, Eberl, Mitchell : tous code 10, hors
listes) et confirmé par l'utilisateur sur sa carrière (AS Roma : Francis Cagigao). Le même code
porté par quelqu'un d'une liste de département ne désigne pas un directeur sportif (45 cas).
Préférence manuelle prioritaire : `Preferences.director_staff_uid`.

Les deux autres contacts du téléphone (même table, session 3) :
- directeur technique : code 88 (vérifié : Freund au Bayern, Lange à Tottenham, Moncada à Milan,
  Maldini à la Roma) ; plusieurs par club possibles (équipes féminines, jeunes) : celui de
  l'équipe première le mieux payé ;
- entraîneur adjoint : code 20 dans la liste « entraînement » (index 1) ; le code couvre aussi des
  entraîneurs adjoints de second rang : on retient celui de l'équipe première le mieux payé
  (vérifié : Stuivenberg, Hulshoff, Sorg, Kolarov, Lijnders ; ex aequo au Bayern Danks / N'Galula).
  Méthode heuristique : l'entraîneur peut corriger depuis le téléphone (`staff_overrides`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text

DIRECTOR_JOB_CODE = 10
TECHNICAL_DIRECTOR_JOB_CODE = 88
ASSISTANT_JOB_CODE = 20


@dataclass(frozen=True)
class StaffRole:
    key: str
    label: str
    code: int
    where: str  # conditions SQL supplémentaires (sur fm_staff)
    order: str
    method: str


STAFF_ROLES: dict[str, StaffRole] = {
    "directeur_sportif": StaffRole(
        "directeur_sportif", "Directeur sportif", DIRECTOR_JOB_CODE, "AND coalesce(in_club_lists, 0) = 0 ",
        "coalesce(team_slot, 0), contract_start DESC", "sauvegarde FM26 : fonction de directeur sportif"),
    "directeur_technique": StaffRole(
        "directeur_technique", "Directeur technique", TECHNICAL_DIRECTOR_JOB_CODE, "",
        "coalesce(team_slot, 0), coalesce(wage, 0) DESC", "sauvegarde FM26 : fonction de directeur technique"),
    "entraineur_adjoint": StaffRole(
        "entraineur_adjoint", "Entraîneur adjoint", ASSISTANT_JOB_CODE, "AND coalesce(list_indexes, '') LIKE '%1%' ",
        "coalesce(team_slot, 0), coalesce(wage, 0) DESC",
        "sauvegarde FM26 : adjoint de l'équipe première le mieux payé (heuristique, corrigeable)"),
}

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
    role: str = "directeur_sportif"
    unique_id: int | None = None
    wage: int | None = None

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
                "traits": self.traits, "method": self.method, "role": self.role, "unique_id": self.unique_id}


def find_director(engine, career_id: int, club_uid: int | None, override_uid: int | None = None) -> DirectorIdentity | None:
    """Le directeur sportif en poste au club géré, ou None si la sauvegarde n'en désigne aucun."""
    return find_staff(engine, career_id, club_uid, "directeur_sportif", override_uid)


def find_staff(engine, career_id: int, club_uid: int | None, role: str,
               override_uid: int | None = None) -> DirectorIdentity | None:
    """La personne qui occupe `role` (clé de STAFF_ROLES) au club géré, ou None (poste vacant)."""
    spec = STAFF_ROLES[role]
    if club_uid is None:
        return None
    pref_cols = ", ".join(f"preferences_{k}" for k in PREFERENCE_LABELS)
    base = (f"SELECT uid, unique_id, name, first_name, last_name, age, nation_id, contract_start, contract_end, wage, "
            f"{pref_cols} FROM fm_staff WHERE career_id = :k AND club_uid = :club AND coalesce(is_human_manager, 0) = 0 ")
    with engine.connect() as c:
        try:
            if override_uid is not None:
                row = c.execute(text(base + "AND uid = :uid"), {"k": career_id, "club": club_uid, "uid": override_uid}).mappings().first()
                method = "choisi par l'entraîneur"
            else:
                row = c.execute(text(base + f"AND unknown_r4 = :code {spec.where}ORDER BY {spec.order} LIMIT 1"),
                                {"k": career_id, "club": club_uid, "code": spec.code}).mappings().first()
                method = spec.method
        except Exception:  # noqa: BLE001 — miroir du staff absent avant la première synchronisation
            return None
    if row is None:
        return None
    prefs = {k: row[f"preferences_{k}"] for k in PREFERENCE_LABELS if row[f"preferences_{k}"] is not None}
    return DirectorIdentity(row["uid"], row["name"], row["first_name"], row["last_name"], row["age"], row["nation_id"],
                            row["contract_start"], row["contract_end"], prefs, method, role, row["unique_id"], row["wage"])


def staff_candidates(engine, career_id: int, club_uid: int | None, role: str) -> list[dict]:
    """Membres du staff du club pour corriger un contact : même fonction d'abord, puis tous les autres."""
    if club_uid is None:
        return []
    spec = STAFF_ROLES[role]
    with engine.connect() as c:
        try:
            rows = c.execute(text(
                "SELECT uid, unique_id, name, age, team_slot, unknown_r4 AS code, wage FROM fm_staff "
                "WHERE career_id = :k AND club_uid = :club AND coalesce(is_human_manager, 0) = 0 "
                "ORDER BY (unknown_r4 = :code) DESC, coalesce(team_slot, 0), coalesce(wage, 0) DESC, name"),
                {"k": career_id, "club": club_uid, "code": spec.code}).mappings().all()
        except Exception:  # noqa: BLE001
            return []
    return [{"uid": r["uid"], "unique_id": r["unique_id"], "name": r["name"], "age": r["age"],
             "team_slot": r["team_slot"], "same_function": r["code"] == spec.code} for r in rows]
