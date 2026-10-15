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

## Téléphone (`/overlay`)
| Méthode | Route | Rôle |
|---|---|---|
| GET | `/overlay` | Page du téléphone (jeton injecté) |
| GET | `/api/contacts` | Les trois contacts du staff (personne, photo, non lus, dernier message) |
| GET · POST | `/api/contacts/{role}/messages` `{text}` | Fil d'un contact ; envoi avec réponse diffusée (SSE : `delta`, `break`, `tool`, `status`, `done`, `error`) |
| PUT | `/api/contacts/{role}/messages/{id}/reaction` `{reaction}` | Réaction de l'entraîneur : `love`, `like`, `dislike`, `laugh`, `emphasize`, `question`, ou `null` pour la retirer (une par message) |
| POST | `/api/contacts/{role}/intro` · `/read` | Premier message du contact ; marquer lu |
| GET · PUT | `/api/contacts/{role}/candidates` · `/person` `{uid}` | Choisir qui occupe le poste (`null` : détection automatique) |
| GET | `/api/photos/{unique_id}` | Photo du pack de visages (404 sinon) |
| GET | `/api/phone/home` | Widgets : date du jeu, prochain et dernier match, classement |
| GET | `/api/phone/table` · `/api/phone/fixtures` | Classement ; matchs à venir et récents (30 au plus) |
| GET | `/api/phone/squad` | Équipe première : saison, valeur, notes de poste (`notes_postes`), condition |
| GET | `/api/phone/mercato` | Offres reçues / faites (`get_transfer_offers`), budgets transferts et salaires, limitations |
| GET | `/api/phone/sale/{uid}` | Plan de vente d'un de nos joueurs (`prepare_sale`, préparation uniquement) |
| GET | `/api/phone/lineup?systeme=4-2-3-1&rotation=false` | Onze type (`propose_lineup`) : onze, banc, alertes ; 400 si l'effectif ne suffit pas |
