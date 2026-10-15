# Décisions d'architecture

| # | Date | Décision | Justification | Alternatives écartées |
|---|---|---|---|---|
| D1 | 15/10/2026 | Données via la **sauvegarde** (fmsave) d'abord, plugin ensuite | Format confirmé, lecture seule, MIT, statut de vérification par champ ; même choix que The Director | Lecture mémoire par offsets (FMSuperScout) : casse à chaque patch, licence ambiguë |
| D2 | 15/10/2026 | Épingler `fmsave==0.5.10` | Les layouts dépendent du build FM ; mise à jour volontaire et testée | Version flottante |
| D3 | 15/10/2026 | SQLite + SQLAlchemy Core, migrations maison ordonnées | Une base locale, sans serveur ; Alembic surdimensionné pour l'instant | PostgreSQL, ORM complet |
| D4 | 15/10/2026 | `players_current` remplacée + `player_history` en différentiel ; upsert des matchs/stats/finances | 100 000 joueurs × N synchros serait trop volumineux ; l'historique utile est conservé | Copie intégrale par synchronisation |
| D5 | 15/10/2026 | Empreinte de carrière = manager + version de base + nom du fichier | Ne jamais mélanger deux carrières ; la fusion est une action explicite | Empreinte sur le seul manager (risque de collision) |
| D6 | 15/10/2026 | Devise étalonnée par l'utilisateur | fmsave n'expose pas la conversion ; jamais d'estimation | Facteur supposé |
| D7 | 15/10/2026 | Routage niveau 0 par règles déterministes | Coût nul, exactitude, testable | Classifieur LLM |
| D8 | 15/10/2026 | Historique de boucle d'outils **natif** par fournisseur | Préserve tool_use/réflexion (Anthropic) et tool_calls (OpenAI) sans conversion | Format pivot unique |
| D9 | 15/10/2026 | Anthropic via le **SDK officiel** (extra optionnel), Haiku 5.5 niveau 2, Opus 5.5 niveau 3 avec `fallbacks: "default"` | Recommandation officielle ; coût minimal au niveau 2 | HTTP brut |
| D10 | 15/10/2026 | Interface diagnostique en HTML/JS sans build | Zéro chaîne de compilation, servie par le service ; l'UI de production est dans le jeu | React + bundler dès maintenant |
| D11 | 15/10/2026 | Overlay **UI Toolkit natif** dans FM26, pas de navigateur embarqué | Technique prouvée (FM26Access), coût mémoire faible | CEF/WebView dans le processus du jeu |
| D12 | 15/10/2026 | Plugin scindé : `Core` (testable) / `Plugin` (dépend du jeu) | Tester hors jeu tout ce qui peut l'être | Projet unique |
| D13 | 15/10/2026 | Raccourci F10 (configurable) | F7 utilisé par The Director, F9 par FMSuperScout / Player Export | — |
| D14 | 15/10/2026 | Actions enregistrées mais indisponibles et absentes de la liste envoyée au LLM | Le modèle ne peut ni les appeler avec succès ni prétendre les avoir faites | Simulation |
| D15 | 15/10/2026 | Projet à la racine du dépôt `football-manager` (au lieu d'un sous-dossier `ClubDirectorAI/`) | Le dépôt est dédié au projet | — |
