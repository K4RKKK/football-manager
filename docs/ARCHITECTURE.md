# Architecture

```
FM26 (Unity 6 IL2CPP)                         Service local ClubDirector (Python, 127.0.0.1:8765)
┌──────────────────────────────┐   HTTP+jeton  ┌──────────────────────────────────────────────────┐
│ ClubDirector.Plugin (BepInEx)│ ────────────▶ │ api/app.py  (FastAPI, garde Host, jeton)         │
│  · Overlay UI Toolkit (F10)  │  battement,   │   ├─ ai/orchestrator ─ router (niveau 0)         │
│  · Relevé arbre UI (Maj+F10) │  chat         │   │      └─ providers (llama.cpp/Ollama/OpenAI,  │
│  · GameProbe (écran courant) │               │   │                    Anthropic SDK)            │
│ ClubDirector.Core (testable) │               │   ├─ tools/registry ─ catalog (lecture, analyse, │
└──────────────────────────────┘               │   │                    mémoire, actions bloquées)│
                                               │   ├─ database/repositories (SQLite, par carrière)│
Sauvegardes .fm (lecture seule) ──copie──▶     │   └─ sync/service ◀─ game/fmsave_reader          │
Documents\…\Football Manager 26\games          │        game/snapshot (copie sûre)                │
                                               │ web/index.html (interface diagnostique)          │
                                               └──────────────────────────────────────────────────┘
```

## Interfaces (cahier des charges §4.4)

| Interface demandée | Implémentation |
|---|---|
| IGameConnection | `game/interfaces.py` → `api/live.py: PluginBridge` |
| ISaveReader | `game/interfaces.py` → `game/fmsave_reader.py` |
| IPlayerRepository, IMatchRepository, ITacticRepository, IFinanceRepository, ITransferRepository | `database/repositories.py: Repository` (méthodes par domaine, filtrées par carrière) |
| IGameActionExecutor | `game/interfaces.py: UnavailableActionExecutor` (refuse tout) |
| IAIProvider | `ai/providers/base.py` |
| IConversationMemory | `memory/store.py` |
| IApprovalService | prévu phase 6 (table `operations`) |

## Flux d'une question
1. `router.classify` reconnaît une question factuelle → outils → gabarit (aucun LLM).
2. Sinon : choix du fournisseur selon le mode (local/hybride/premium), le niveau et le budget.
3. Prompt système : règles anti-invention, date du jeu, personnalité, souvenirs.
4. Boucle d'outils (≤ 6 tours) ; chaque appel validé (Pydantic, champs inconnus refusés) et journalisé.
5. Réponse + trace d'outils + limitations remontées à l'UI.

## Provenance
Chaque résultat d'outil porte `provenance` : source (`save`/`live_plugin`/`user`/`computed`),
date de collecte, date de jeu, snapshot, confiance (`verified`/`unconfirmed`/`unknown`).
