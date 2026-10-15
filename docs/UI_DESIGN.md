# Design system

Palette (cahier des charges §11.1), utilisée par l'interface diagnostique (`backend/src/clubdirector/web/index.html`)
et l'overlay du plugin (`DirectorOverlay.cs`) :

| Jeton | Valeur | Usage |
|---|---|---|
| `--bg` | `#0B141B` | fond |
| `--surface` | `#13212B` | cartes, menu |
| `--surface2` | `#192A34` | survol, champs |
| `--border` | `#263C45` | bordures |
| `--green` | `#29C77B` | action principale, onglet actif |
| `--green2` | `#65E5A5` | valeurs fortes (≥ 15) |
| `--text` / `--muted` | `#F2F6F8` / `#9BAEB8` | texte |
| `--warn` / `--err` | `#E6B85D` / `#E36E75` | limitations / erreurs, valeurs faibles (≤ 7) |

Règles : rayon 10 px (cartes) / 8 px (champs) ; animations d'apparition 200-250 ms uniquement ;
tout montant non étalonné est affiché en nombre brut + mention discrète ; toute limitation d'un
outil est affichée en orange sous la donnée ; aucune donnée inventée, même en exemple.

Validation visuelle session 1 : captures Chromium 1440×900 (5 écrans) et 390×844 (aucun
défilement horizontal, menu horizontal défilant).
