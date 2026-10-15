# API du service local

Base : `http://127.0.0.1:8765`. En-tête obligatoire (sauf `/api/health`) : `X-ClubDirector-Token: <contenu de %LOCALAPPDATA%\ClubDirectorAI\plugin.token>`.
Les requêtes dont l'en-tête `Host` n'est pas `127.0.0.1`/`localhost` sont refusées (403).

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/` | Interface diagnostique (jeton injecté) |
| GET | `/api/health` | Santé (public) |
| GET | `/api/status` | Carrières, carrière active, plugin, IA, dossiers |
| GET | `/api/saves` | Sauvegardes `.fm` trouvées |
| POST | `/api/sync` `{path}` | Copie sûre + lecture + archivage (`.fm` uniquement) |
| POST | `/api/careers/{id}/activate` | Changer de carrière active |
| GET | `/api/dashboard` | Agrégat tableau de bord |
| GET | `/api/squad` · `/api/players/{uid}` · `/api/players?position=&min_age=&max_age=&name=&limit=&offset=` | Effectif, fiche, recherche paginée |
| GET | `/api/tools` · POST `/api/tools/{name}` `{args}` | Registre d'outils (diagnostic) |
| POST | `/api/chat` `{question, conversation_id?, force_tier?}` | Directeur sportif |
| GET | `/api/conversations` · `/api/conversations/{id}` | Historique |
| GET/PUT | `/api/preferences` | Personnalité, mode de connaissance, limites, devise |
| POST | `/api/currency/calibrate` `{player_uid, displayed_value, symbol}` | Étalonnage devise |
| POST | `/api/ai/test` | Test des moteurs IA |
| POST | `/api/plugin/heartbeat` · GET `/api/plugin/status` | Plugin FM26 |
