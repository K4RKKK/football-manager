"""Profils de rôles pondérés (ajustables). Les poids sont des choix de conception explicites,
documentés et modifiables : ils ne prétendent pas reproduire le moteur de FM26.

Seuls des attributs VISIBLES dans le jeu sont utilisés (aucun attribut caché).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RoleProfile:
    key: str
    label: str
    positions: tuple[str, ...]
    weights: dict[str, float] = field(default_factory=dict)
    description: str = ""


ROLES: dict[str, RoleProfile] = {
    r.key: r
    for r in [
        RoleProfile("gardien", "Gardien classique", ("GK",), {
            "reflexes": 5, "handling": 5, "one_on_ones": 4, "positioning": 4, "aerial_reach": 4,
            "command_of_area": 3, "communication": 3, "concentration": 3, "agility": 3,
            "kicking": 2, "decisions": 2}, "Arrêts, prise de balle, autorité dans la surface."),
        RoleProfile("gardien_libero", "Gardien libéro", ("GK",), {
            "reflexes": 4, "handling": 3, "one_on_ones": 4, "rushing_out": 4, "positioning": 3,
            "passing": 3, "kicking": 3, "first_touch": 2, "composure": 3, "decisions": 3,
            "anticipation": 3, "agility": 2}, "Sorties hautes et relance au pied."),
        RoleProfile("dc_stoppeur", "Défenseur central stoppeur", ("DC",), {
            "marking": 5, "heading": 5, "positioning": 5, "tackling": 4, "jumping_reach": 4,
            "strength": 4, "bravery": 3, "anticipation": 3, "concentration": 3, "aggression": 2},
         "Duel, jeu aérien, protection de la surface."),
        RoleProfile("dc_relanceur", "Défenseur central relanceur", ("DC",), {
            "passing": 4, "composure": 4, "first_touch": 3, "vision": 2, "tackling": 4,
            "marking": 4, "positioning": 4, "heading": 3, "anticipation": 3, "decisions": 3,
            "pace": 2}, "Défend puis relance proprement."),
        RoleProfile("lateral_offensif", "Latéral / piston offensif", ("DL", "DR", "WBL", "WBR"), {
            "crossing": 4, "stamina": 5, "work_rate": 4, "acceleration": 4, "pace": 4,
            "off_the_ball": 3, "tackling": 3, "teamwork": 3, "dribbling": 2, "positioning": 2,
            "marking": 2}, "Couloir complet, apport offensif et centres."),
        RoleProfile("lateral_defensif", "Latéral défensif", ("DL", "DR"), {
            "tackling": 4, "marking": 4, "positioning": 4, "anticipation": 3, "concentration": 3,
            "pace": 3, "stamina": 3, "acceleration": 2, "teamwork": 2, "crossing": 1},
         "Priorité au repli et aux duels."),
        RoleProfile("milieu_recuperateur", "Milieu récupérateur", ("DM", "MC"), {
            "tackling": 5, "anticipation": 5, "positioning": 5, "concentration": 4, "teamwork": 4,
            "work_rate": 3, "decisions": 3, "marking": 3, "stamina": 3, "strength": 2},
         "Ratisse, coupe les lignes, protège la défense."),
        RoleProfile("regisseur", "Meneur reculé / régisseur", ("DM", "MC"), {
            "passing": 5, "vision": 5, "composure": 4, "decisions": 4, "first_touch": 4,
            "technique": 4, "teamwork": 3, "anticipation": 3, "positioning": 2},
         "Oriente le jeu depuis la base du milieu."),
        RoleProfile("box_to_box", "Milieu box-to-box", ("MC",), {
            "stamina": 5, "work_rate": 5, "passing": 3, "tackling": 3, "off_the_ball": 3,
            "teamwork": 3, "decisions": 3, "natural_fitness": 2, "strength": 2, "first_touch": 2},
         "Couvre les deux surfaces."),
        RoleProfile("meneur_offensif", "Meneur offensif (n°10)", ("AMC", "MC"), {
            "passing": 5, "vision": 5, "technique": 4, "first_touch": 4, "decisions": 4,
            "composure": 3, "flair": 3, "off_the_ball": 2, "dribbling": 2},
         "Dernière passe et création."),
        RoleProfile("ailier_centreur", "Ailier débordeur-centreur", ("AML", "AMR", "ML", "MR"), {
            "crossing": 5, "dribbling": 4, "acceleration": 4, "pace": 4, "agility": 3,
            "technique": 3, "off_the_ball": 2, "work_rate": 2, "stamina": 2, "first_touch": 2},
         "Déborde et centre ; idéal pour un jeu de centres."),
        RoleProfile("ailier_interieur", "Ailier intérieur / inversé", ("AML", "AMR"), {
            "dribbling": 4, "finishing": 4, "off_the_ball": 4, "acceleration": 4, "pace": 3,
            "technique": 3, "first_touch": 3, "composure": 3, "agility": 3, "long_shots": 2},
         "Rentre dans l'axe pour frapper ou combiner."),
        RoleProfile("buteur_surface", "Renard des surfaces", ("STC",), {
            "finishing": 5, "off_the_ball": 5, "anticipation": 4, "composure": 4,
            "acceleration": 3, "first_touch": 2, "heading": 2, "jumping_reach": 1},
         "Attaque la surface, conclut les centres et les ballons dans la boîte."),
        RoleProfile("avant_centre_complet", "Avant-centre complet", ("STC",), {
            "finishing": 4, "heading": 3, "jumping_reach": 3, "strength": 3, "first_touch": 3,
            "off_the_ball": 3, "composure": 3, "technique": 2, "passing": 2, "dribbling": 2,
            "acceleration": 2, "pace": 2}, "Polyvalent : finition, jeu dos au but, jeu aérien."),
        RoleProfile("pivot", "Pivot / point d'appui", ("STC",), {
            "heading": 5, "jumping_reach": 5, "strength": 5, "finishing": 3, "bravery": 3,
            "balance": 3, "first_touch": 2, "teamwork": 2}, "Point d'appui aérien et physique."),
    ]
}
