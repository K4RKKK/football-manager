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

## Téléphone (`web/phone.html`)
Style iPhone iOS, sombre par défaut, clair au choix ou selon Windows (« Auto »). Jetons iOS dans `:root`
(`--bg`, `--bg-elev`, `--sep`, `--text`, `--text2`, `--blue`, `--green`, `--red`, `--orange`) redéfinis sous
`[data-theme="light"]`. Fond d'écran aux couleurs de la Roma (dégradés), partagé par l'accueil et l'écran verrouillé.

Règles de comportement :
- Sobre et réaliste : jamais de « X consulte… » ni de liste d'outils ; pendant une réponse, seulement les trois points.
- Toucher un contact ouvre la discussion ; la fiche s'ouvre depuis l'en-tête du fil.
- Les boutons « En parler à… », « Préparer ce match… » préremplissent un message : rien n'est envoyé sans l'entraîneur.
- Réponses rapides seulement quand le dernier message du contact finit par une question ; sinon, suggestions du rôle.
- Réaction (tapback) : une par message, pastille bleue sur sa dernière bulle ; double-clic, clic droit ou toucher la pastille.
- Notifications : une bannière par contact ; plusieurs messages → « N messages » et carte empilée ; plusieurs contacts →
  bannière « Messages ». Écran verrouillé : une carte par contact non lu (empilée au-delà d'un message).
- États d'offre : conclue (vert), échouée (rouge), en cours (orange), accord pour plus tard (bleu), sans suite (gris).
- Notes de poste : 18-20 vert (naturel), 15-17 jaune (compétent), 10-14 orange (dépannage), < 10 gris (inadapté).
- Montants : texte déjà formaté par le service (devise étalonnée, euros) ; dates du jeu au format français.
