# Couverture des données (mode B — sauvegarde, fmsave 0.5.10)

« Statut fmsave » : `verified` = vérifié contre le jeu par fmsave ; `unconfirmed` = lu mais sens non confirmé.

| Donnée (§6) | Lue | Statut fmsave | Stockage | Remarque |
|---|---|---|---|---|
| Club géré, manager, date de jeu | oui | — | `careers` | |
| Effectif, nom, âge, naissance, nationalité (id), taille | oui | âge : unconfirmed | `players_current` | noms de pays : id seulement |
| Postes (naturels ≥18, secondaires 15-17), notes de poste | oui | verified | idem | |
| 52 attributs + 8 de personnalité | oui | verified | JSON | cachés masqués hors mode avancé |
| CA / PA | oui | unconfirmed | | mode avancé seulement |
| Valeur de transfert | oui | verified | | unité interne |
| Contrat : salaire, début, fin, statut | oui | salaire : unconfirmed ; fin : verified | | |
| Prêts, suspensions, traits, condition | oui | verified (condition brute) | | |
| Disponibilité du jour, moral | non | — | — | |
| Matchs : date, équipes, tour, score | oui (scores partiels) | verified | `fixtures` (archivés) | |
| Stats de saison (min., buts, passes D., xG, note, cartons…) | saison en cours | verified | `season_stats` (archivées par saison) | |
| Stats par match | partiel | — | non stocké (à faire) | |
| Classements | oui | — | `league_tables` (par snapshot) | |
| Finances mensuelles, budgets transferts/salaires | oui | verified | `finances` | dette non lue |
| Tactiques : nom, style, mentalité, postes | oui | — | `tactics` | instructions non décodées |
| Blessures | historique conservé | — | `injuries` | pas l'état du jour |
| Staff, installations, sponsors, affiliations | lus par fmsave | — | non stockés (à faire) | |
| Noms de compétitions | non (fichier de noms requis) | — | | `competition_names` pris en charge par fmsave |
