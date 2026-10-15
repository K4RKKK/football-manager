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

## 4. Plugin FM26 (expérimental, non validé)
1. Fermer FM26. Installer BepInEx 6 Bleeding Edge IL2CPP ≥ build 738 (pack Thunderstore FM26 conseillé).
2. Dans `doorstop_config.ini` : `ignore_disable_switch = true`.
3. Lancer FM26 une fois (génération de `BepInEx\interop`), le fermer.
4. `cd plugin && dotnet build src\ClubDirector.Plugin -c Release /p:FMPath="<dossier FM26>"`
5. Copier `ClubDirector.Plugin.dll` et `ClubDirector.Core.dll` dans `<FM26>\BepInEx\plugins\ClubDirectorAI\`.
6. Lancer `clubdirector serve`, puis FM26 ; **F10** ouvre le panneau, **Maj+F10** relève l'arbre UI.
Désinstallation : supprimer le dossier `BepInEx\plugins\ClubDirectorAI`.
