# ClubDirector AI — règles permanentes

Directeur sportif IA pour Football Manager 26 (Windows 11, carrière solo locale).
Lire au début de chaque session : `docs/DEVELOPMENT_STATUS.md`, `docs/KNOWN_LIMITATIONS.md`,
`docs/TECHNICAL_FEASIBILITY.md`, puis `docs/ROADMAP.md`.

## Règles non négociables
- Les données de carrière viennent de FM26 (sauvegarde via fmsave, ou plugin). Jamais inventées :
  une valeur inconnue reste `None` et l'utilisateur en est informé.
- Une fonctionnalité n'est « terminée » que si un test représentatif le prouve. Distinguer
  ✅ testé / 🟡 non validé dans FM26 / 🧪 expérimental dans la doc.
- Sauvegardes : lecture seule, toujours via `game/snapshot.take_snapshot` (copie). Jamais
  d'écriture à côté des sauvegardes du jeu.
- Actions dans FM26 : indisponibles (`available=False`) tant que leur exécution ET leur
  confirmation dans le jeu ne sont pas prouvées. Ne jamais simuler un succès.
- L'IA n'accède qu'aux outils du registre ; pas d'exécution de code arbitraire. Les questions
  factuelles passent par le niveau 0 (sans LLM).
- Service local sur 127.0.0.1 uniquement, jeton obligatoire, aucun secret dans le code/config.
- Données fictives : uniquement dans les tests / bancs « mode développement », jamais présentées
  comme réelles.

## Structure
- `backend/` (Python 3.12+, uv) : `src/clubdirector/{game,sync,database,tools,ai,recruitment,proactive,memory,security,api,web}`
- `plugin/` (C#) : `ClubDirector.Core` (testable hors jeu), `ClubDirector.Plugin` (BepInEx 6 IL2CPP, nécessite les interop FM26)
- `docs/`, `scripts/`, `config/`

## Commandes
- Tests backend : `cd backend && uv run pytest -q` ; lint : `uv run ruff check src tests`
- Tests plugin : `cd plugin && dotnet test tests/ClubDirector.Core.Tests`
- Bout en bout : `scripts/e2e_plugin_backend.sh`
- Service : `cd backend && uv run clubdirector serve` (http://127.0.0.1:8765)

## Conventions
- Code et messages utilisateur en français ; identifiants en anglais.
- fmsave est épinglé (`fmsave==0.5.10`) : toute mise à jour = relancer les tests + vérifier `field_status`.
- Techniques IL2CPP : `TryCast<T>()` (pas `is`), délégués via `DelegateSupport.ConvertDelegate`,
  API Unity sur le thread principal uniquement (passer par `MainThreadDispatcher`).
- Mettre à jour `docs/DEVELOPMENT_STATUS.md` et `docs/TEST_REPORT.md` à chaque étape validée.
