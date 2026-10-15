---
name: fm26-il2cpp-plugin
description: Développer ou déboguer le plugin BepInEx 6 IL2CPP de ClubDirector dans FM26 (overlay UI Toolkit, relevé d'arbre UI, battement de cœur, futures actions UI). À utiliser pour toute modification de plugin/src/ClubDirector.Plugin ou ClubDirector.Core.
---

# Plugin FM26 (BepInEx 6 IL2CPP, Unity 6, UI Toolkit)

## Faits établis (sources : FM26Access, FMSuperScout, pack BepInEx Thunderstore)
- BepInEx 6 Bleeding Edge IL2CPP ≥ build 738 ; `ignore_disable_switch = true` dans `doorstop_config.ini`.
- UI = UI Toolkit. Document principal : UIDocument `PanelManager` (slots `Menu`, `Report`, `Card`, `Overlay`, `ModalDialog`…).
- Overlay : nouveau GameObject + `UIDocument`, `panelSettings` emprunté à un document du jeu, `sortingOrder` élevé.

## Règles IL2CPP
- Cast : `el.TryCast<T>()` (jamais `is`/`as` sur un proxy). Type réel : `el.GetIl2CppType().Name`.
- Callbacks : `DelegateSupport.ConvertDelegate<EventCallback<ClickEvent>>(new Action<ClickEvent>(...))`.
- Types injectés : `ClassInjector.RegisterTypeInIl2Cpp<T>()` + constructeur `(IntPtr ptr) : base(ptr)`.
- API Unity uniquement sur le thread principal ; réseau et calcul sur `Task.Run` ; retour via `MainThreadDispatcher`.
- Parcours d'arbre UI bornés (≤ 8000 nœuds) ; ne jamais lire `BindingExpect.Parameters` (crash natif).
- Tout accès au jeu dans un `try/catch` : une erreur ne doit jamais rendre FM26 inutilisable.

## Validation
- Logique testable → `ClubDirector.Core` + tests xUnit (`dotnet test plugin/tests/ClubDirector.Core.Tests`).
- Protocole → `scripts/e2e_plugin_backend.sh`.
- Dans le jeu → `docs/TEST_PLAN.md` P-1…P-6 sur le PC de l'utilisateur ; mettre à jour la matrice
  de `docs/TECHNICAL_FEASIBILITY.md` seulement avec des résultats observés (`BepInEx/LogOutput.log`).
- Actions (shortlist, offres) : rester `available=False` côté backend tant que l'effet n'est pas
  constaté dans FM26 et relu par le plugin.
