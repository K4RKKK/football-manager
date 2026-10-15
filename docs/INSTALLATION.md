# Installation (Windows 11) — version de développement

> Aucune étape ne modifie le jeu, sauf l'installation optionnelle de BepInEx (étape 4).

## 1. Prérequis
- Python 3.12+ et [uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`)
- Git ; pour le plugin : SDK .NET 8 (`winget install Microsoft.DotNet.SDK.8`)

## 2. Service local
```powershell
git clone <ce dépôt> ClubDirectorAI
cd ClubDirectorAI\backend
uv sync                      # ajouter --extra anthropic pour Claude, --extra keyring pour le trousseau
uv run clubdirector saves    # liste les sauvegardes trouvées
uv run clubdirector sync "C:\Users\<vous>\Documents\Sports Interactive\Football Manager 26\games\<carriere>.fm"
uv run clubdirector serve    # puis ouvrir http://127.0.0.1:8765
```
Données : `%LOCALAPPDATA%\ClubDirectorAI` (base, copies de sauvegarde, jeton, préférences).

## 3. IA locale (installée et testée en session 2)
- Moteur : llama.cpp b11658 Vulkan — `C:\AI\llama.cpp-b11658-vulkan\` (empreinte SHA-256 vérifiée).
- Modèle : Gemma 4 26B-A4B (unsloth UD-IQ4_XS, Apache 2.0) — `C:\AI\models\gemma-4-26B-A4B-it\`.
- Chemins modifiables : variables `CLUBDIRECTOR_LLM_SERVER`, `CLUBDIRECTOR_LLM_MODEL`, `CLUBDIRECTOR_LLM_DEVICE`.
- Démarrer seule : `powershell -ExecutionPolicy Bypass -File scripts\start_llm.ps1 [-ModeJeu] [-CoucheCpu N]`
  (127.0.0.1:8080, carte dédiée `Vulkan0`, contexte 32k).

| Mode | VRAM | Génération | Usage |
|---|---:|---:|---|
| pleine puissance | 14,9 Go | ~116 tokens/s | FM26 fermé |
| `-ModeJeu` (12 couches d'experts en RAM, défaut du lanceur) | 11,4 Go | ~41 tokens/s | FM26 ouvert |
| `-ModeJeu -CoucheCpu 20` | 8,7 Go | ~29 tokens/s | si FM26 manque de mémoire vidéo |

Config ClubDirector : `%LOCALAPPDATA%\ClubDirectorAI\config.toml` (fournisseur `llama.cpp local`,
modèle `clubdirector-local`). Clés API éventuelles : variable `CLUBDIRECTOR_SECRET_<REF>` ou trousseau.

## 3 bis. Tout lancer d'un clic
Double-cliquer **`Lancer ClubDirector.cmd`** (racine du projet) : l'IA démarre en mode jeu dans une
fenêtre réduite « ClubDirector IA », puis le service sur http://127.0.0.1:8765.
Options : `scripts\start_clubdirector.ps1 -PleinePuissance` (jeu fermé) ou `-SansIA`.
Le directeur sportif fait sa **prise de poste** à la première conversation IA d'une carrière
(ou à la demande : `uv run clubdirector prise-de-poste`).

## 3 ter. Fenêtre ClubDirector au-dessus du jeu
- Lancée par `Lancer ClubDirector.cmd` (compilée au premier lancement : `dotnet build overlay\ClubDirector.Overlay -c Release`).
- **Ctrl+Alt+D** : afficher / masquer (même quand FM26 a le focus) ; Échap : masquer ; icône « DS » dans la zone de notification.
- FM26 doit être en **fenêtré sans bordure** (Préférences → Interface → mode d'affichage).
- Réglages : `%LOCALAPPDATA%\ClubDirectorAI\overlay.json` (raccourci, largeur, côté, opacité).
- La synchronisation est automatique à chaque sauvegarde du jeu ; bouton ⟳ pour forcer la lecture de la dernière sauvegarde.

### Le téléphone
La fenêtre ClubDirector est un téléphone (mode par défaut). Saisir la barre d'état (l'heure en haut)
pour le déplacer ; la position est retenue. Taille : app **Réglages → Taille du téléphone**, ou clic droit
sur l'icône de la zone de notification → « Taille du téléphone » (Petit, Normal, Grand). Réglages dans
`overlay.json` : `Mode` (`telephone` ou `panneau` pour l'ancien panneau latéral), `PhoneHeight`, `PhoneX`, `PhoneY`.
Les photos du staff et des joueurs viennent du pack de visages FM26 s'il est installé.

Apps (données de la dernière sauvegarde uniquement, montants en euros) :
- **Messages / Contacts** : les trois membres du staff ; toucher un contact ouvre la discussion. Réponses
  rapides (« Oui, vas-y », « Non », « Dis-m'en plus ») quand un contact pose une question ; réaction à une
  bulle par double-clic ou clic droit (❤️ 👍 👎 😂 ‼️ ❓), enregistrée avec la conversation.
- **Mercato** : offres reçues et faites (joueur, club, montant, état, dates), budgets ; la fiche d'une offre
  reçue pour un joueur du club affiche le plan de vente (prix affiché, plancher, acheteurs possibles).
- **Calendrier** : vue du mois et liste des matchs à venir / résultats ; la fiche d'un match propose de le
  préparer ou de le débriefer avec l'entraîneur adjoint (message prérempli, jamais envoyé seul).
- **Effectif** : joueurs par poste, buts, note, valeur ; **onze type** calculé sur les notes de poste FM26
  (9 systèmes, rotation) ; la fiche d'un joueur montre ses notes par poste sur un terrain.
- **Classement**, **Réglages** (apparence, taille du texte et du téléphone, sons, bannières, aperçu, pastilles,
  verrouillage automatique, suggestions et réponses rapides).
- **Écran verrouillé** : à l'ouverture et après 5 min sans activité (réglable, « Jamais » possible) ; il montre
  le prochain match et les messages non lus regroupés par contact ; toucher un message ouvre la discussion.

## 3 quater. Installation Windows (raccourcis et démarrage automatique)
Pour l'utilisateur courant, sans droits administrateur :
```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1            # menu Démarrer seulement
powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1 -Demarrage # + lancement à l'ouverture de session
powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1 -Simulation # montre ce qui serait fait
```
L'installateur vérifie uv, le SDK .NET 8 et le runtime WebView2 (sans rien télécharger : il indique quoi
installer), lance `uv sync`, compile le téléphone (fermer d'abord la fenêtre ClubDirector), crée
`%LOCALAPPDATA%\ClubDirectorAI\config.toml` s'il manque, puis le dossier « ClubDirector AI » du menu Démarrer
(lancer, désinstaller). Avec `-Demarrage`, un raccourci dans le dossier Démarrage de Windows lance
`scripts\start_clubdirector.ps1` (IA, téléphone, service ; fenêtre réduite) ; un second lancement ne crée
pas de doublon. Tout ce qui est créé est listé dans `%LOCALAPPDATA%\ClubDirectorAI\install.json`.

Désinstaller : menu Démarrer → ClubDirector AI → Désinstaller, ou
`powershell -ExecutionPolicy Bypass -File scripts\uninstall_windows.ps1 [-SupprimerDonnees] [-SansArret] [-Simulation]`.
Le téléphone et le service sont arrêtés, les raccourcis retirés ; les données restent sauf avec
`-SupprimerDonnees` (confirmation « SUPPRIMER »). Les sauvegardes FM26 et le dossier du projet ne sont jamais touchés.

## 3 quinquies. Publier le dépôt sur GitHub
Dépôt distant configuré : `origin` → `https://github.com/K4RKKK/football-manager.git` (branche
`claude/clubdirector-phase0-1`). Avant chaque envoi :
1. `cd backend && uv run pytest -q && uv run ruff check src tests` ; `cd overlay && dotnet test ClubDirector.Overlay.Tests`.
2. `git status --ignored` : base SQLite, `plugin.token`, `preferences.json`, `config.toml`, `snapshots/`,
   fichiers `.fm` (hors fixtures synthétiques), `bin/`, `obj/` et `.venv/` doivent rester ignorés.
3. Aucun secret ni donnée personnelle suivis : `git grep -I -E "sk-|ghp_|api[_-]?key\s*="` ne doit rien trouver.
4. `git push origin claude/clubdirector-phase0-1` (l'intégration continue `.github/workflows/tests.yml`
   relance tests et lint sous Windows et Linux).

## 4. Plugin FM26 (expérimental — bloqué par la protection du jeu, voir KNOWN_LIMITATIONS 14)
1. Fermer FM26. Installer BepInEx 6 Bleeding Edge IL2CPP ≥ build 738 (pack Thunderstore FM26 conseillé).
2. Dans `doorstop_config.ini` : `ignore_disable_switch = true`.
3. Lancer FM26 une fois (génération de `BepInEx\interop`), le fermer.
4. `cd plugin && dotnet build src\ClubDirector.Plugin -c Release /p:FMPath="<dossier FM26>"`
5. Copier `ClubDirector.Plugin.dll` et `ClubDirector.Core.dll` dans `<FM26>\BepInEx\plugins\ClubDirectorAI\`.
6. Lancer `clubdirector serve`, puis FM26 ; **F10** ouvre le panneau, **Maj+F10** relève l'arbre UI.
Désinstallation : supprimer le dossier `BepInEx\plugins\ClubDirectorAI`.
