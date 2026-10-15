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

## 3. IA locale (optionnel, recommandé)
llama.cpp (build Vulkan pour la RX 9070 XT) :
`llama-server -m <modele.gguf> --jinja -ngl 99 --port 8080` — le paramètre `--jinja` est requis
pour les appels d'outils. Ollama : configurer `base_url = "http://127.0.0.1:11434/v1"`.
Voir `config/clubdirector.example.toml` (copier en `%LOCALAPPDATA%\ClubDirectorAI\config.toml`).
Clés API : variable `CLUBDIRECTOR_SECRET_<REF>` ou trousseau Windows — jamais dans le fichier.

## 4. Plugin FM26 (expérimental, non validé)
1. Fermer FM26. Installer BepInEx 6 Bleeding Edge IL2CPP ≥ build 738 (pack Thunderstore FM26 conseillé).
2. Dans `doorstop_config.ini` : `ignore_disable_switch = true`.
3. Lancer FM26 une fois (génération de `BepInEx\interop`), le fermer.
4. `cd plugin && dotnet build src\ClubDirector.Plugin -c Release /p:FMPath="<dossier FM26>"`
5. Copier `ClubDirector.Plugin.dll` et `ClubDirector.Core.dll` dans `<FM26>\BepInEx\plugins\ClubDirectorAI\`.
6. Lancer `clubdirector serve`, puis FM26 ; **F10** ouvre le panneau, **Maj+F10** relève l'arbre UI.
Désinstallation : supprimer le dossier `BepInEx\plugins\ClubDirectorAI`.
