# Connexion en direct à FM26 — état de l'art et plan (recherche du 15/10/2026)

Objectif de l'utilisateur : que le staff réagisse **en direct** à la partie (nouveau jour, fin de
match, rapports, blessures…) au lieu d'attendre une sauvegarde, et que les réponses et actions
soient quasi immédiates.

## 1. Ce qui existe pour FM26 (sources publiques)

| Outil | Comment il se connecte | Ce qu'il lit | Remarques |
|---|---|---|---|
| [FMRTE 26](https://www.fmrte.com/) ([Windows](https://www.fmrte.com/files/file/163-fmrte-26-for-windows/)) | lit (et écrit) la mémoire du jeu en cours, depuis un programme externe | joueurs, staff, clubs, en direct | suit chaque patch (26.3.2) ; la page macOS signale que FM26 a des protections qui bloquent ce type d'outil sur Mac ; erreur connue si BepInEx est chargé |
| [FM Live Editor 26](https://www.fmscout.com/a-fm-live-editor-26.html) | programme externe : FM ouvert + partie chargée → « Load Data » | joueurs, staff, clubs (finances, installations), nations, stades | Windows 10/11, 26.3.2 Steam/Epic/Game Pass ; lecture gratuite |
| [Genie Scout 26](https://www.fmscout.com/a-genie-scout-26-now-available.html) | programme externe (recrutement) | base de joueurs de la partie | casse souvent après une mise à jour de FM26 (adresses mémoire décalées) |
| [fm-ai-assistent](https://github.com/JelmerBouma1985/fm-ai-assistent) | **assistant IA open source qui lit la partie chargée directement en mémoire vive** (Windows 11 / Linux), même utilisateur et même niveau d'administration que FM26 | joueurs, staff, clubs, compétitions, contrats, budgets ; « sonde » de la date et du processus | le plus proche de ClubDirector ; Java ; à étudier (méthode de lecture non décrite dans le README) |
| [FMSuperScout](https://github.com/mavarobli/FMSuperScout/blob/main/README.md) | plugin BepInEx 6 **dans** le jeu, lecture seule, export JSON sur touche F9 | 45 000+ joueurs et staff | installeur Steam/Epic/Game Pass ; génération des liaisons au premier lancement (1-3 min) |
| [BepInExPack FM26](https://thunderstore.io/c/football-manager-26/p/BepInEx/BepInExPack_FootballManager26/) (Thunderstore), [FM26 Camera Mod](https://github.com/torojoh/FM26-Camera-Mod/blob/main/INSTALLATION.md), [FM26 UltrawideFix](https://thunderstore.io/c/football-manager-26/), [FM26Access](https://github.com/GreenBeanGravy/FM26Access/), [FMMLoader-26](https://github.com/jal-co/FMMLoader-26) | chargeur BepInEx / MelonLoader dans le processus du jeu | accès complet aux classes du jeu (IL2CPP) | des joueurs les utilisent ; un [rapport SI](https://community.sports-interactive.com/bugtracker/1644_football-manager-26-bugs-tracker/all-other-issues/bepinex-and-melonloader-dont-work-when-loading-a-save-r34012/) signale des échecs au chargement d'une carrière sur une ancienne version |
| [Éditeur officiel FM26](https://store.epicgames.com/p/football-manager-26-football-manager-ingame-editor-24e596) (DLC payant) | dans le jeu | modification en direct | pas d'interface pour un programme tiers |

Constat : **deux familles** de connexion en direct existent et fonctionnent sur FM26 :
1. **Lecture externe de la mémoire** (FMRTE, FM Live Editor, Genie Scout, fm-ai-assistent) : aucun
   fichier du jeu modifié, rien d'injecté ; le programme ouvre le processus `fm.exe` en lecture.
2. **Plugin dans le jeu** (BepInEx/MelonLoader) : accès direct aux objets et aux événements du jeu
   (fin de match, passage au jour suivant…), mais chargeur injecté au démarrage.

## 2. Notre situation

- **BepInEx chez l'utilisateur** (session 2) : avec le chargeur Doorstop (`winhttp.dll`), FM26
  affichait « Le serveur n'est pas accessible » puis demandait une activation hors ligne (page
  `codefusion.technology` = protection anti-falsification). Sans `winhttp.dll`, le jeu démarre. Un
  [fil du forum SI](https://community.sports-interactive.com/forums/topic/599507-the-server-is-not-reachable-fm26/)
  rapporte la même erreur avec d'autres causes possibles (pack de stades, BepInEx, réseau) ; une
  [discussion BepInEx](https://github.com/BepInEx/BepInEx/discussions/553) rappelle que `winhttp.dll`
  ne contient aucun code réseau. Hypothèse à vérifier (sans contournement) : le jeu doit pouvoir
  joindre les serveurs d'activation (`srv01-03.codefusion.technology:443`) quand son environnement
  change ; un pare-feu ou un antivirus qui les bloque produirait exactement ce message.
- **Lecture des sauvegardes** (actuel) : fiable mais différée (≈ 3 min de lecture après chaque
  sauvegarde, accélérée par la session « Fiabilité de l'IA locale et synchro plus rapide »).

## 3. Options pour le direct

| Option | Direct ? | Risque protection | Effort | Verdict |
|---|---|---|---|---|
| A. **Lecteur mémoire externe en lecture seule** (comme FMRTE / fm-ai-assistent) | oui (sondage toutes les 1-2 s) | faible : rien n'est injecté ni modifié ; outils du même type utilisés publiquement sur FM26 | élevé : retrouver les structures IL2CPP (métadonnées du jeu → décalages des champs), à refaire après chaque patch (automatisable depuis les métadonnées) | **recommandée** |
| B. **Plugin BepInEx** (le plugin ClubDirector existe déjà, compile contre les interop réels) | oui, avec de vrais événements | celui constaté : message de la protection au démarrage ; à retester **avec l'accord de l'utilisateur** en vérifiant d'abord l'accès réseau aux serveurs d'activation, sans aucun contournement | moyen (plugin prêt) | à retester une fois, en parallèle |
| C. Sauvegardes automatiques fréquentes + lecture rapide | quasi (selon la fréquence) | aucun | faible | en place, amélioré en continu |
| D. Lecture de l'écran (OCR) | partiel | aucun | élevé, fragile | écartée |

## 4. Plan proposé (option A, puis B si le test réseau est concluant)

1. **Faisabilité** (une session) : avec l'accord de l'utilisateur pour le téléchargement, extraire
   les métadonnées IL2CPP de FM26 (Il2CppDumper ou Cpp2IL : fichier `global-metadata.dat` +
   `GameAssembly.dll`, lus, jamais modifiés) → noms de classes et décalages des champs ; écrire un
   petit lecteur .NET (`OpenProcess` en lecture seule + `ReadProcessMemory`) qui retrouve **la date
   du jeu** et le club de l'entraîneur. Critère : la date lue change quand on avance d'un jour.
2. **Événements en direct** : nouveau jour, résultat d'un match (score, buteurs, notes), blessures,
   messages de la boîte de réception → envoyés au service local (`POST /api/live/event`), qui
   déclenche les messages proactifs du staff (session « Intelligence du staff ») en quelques
   secondes.
3. **Données vivantes** pour les réponses (condition, moral, forme du jour) sans attendre une
   sauvegarde ; la lecture des sauvegardes reste la référence complète.
4. **Garde-fous** : lecture seule (aucune écriture en mémoire), aucun fichier du jeu modifié, aucun
   contournement de protection, carrière solo locale ; lecteur désactivable ; décalages
   régénérés automatiquement après chaque mise à jour de FM26, sinon retour au mode sauvegarde.

## 5. Limites et précautions

- L'EULA restreint la rétro-ingénierie « sauf si la loi le permet » (voir KNOWN_LIMITATIONS 13) :
  usage personnel, solo, sans redistribution de fichiers du jeu.
- Les décalages mémoire changent à chaque patch : un lecteur externe doit vérifier ce qu'il lit
  (dates plausibles, identifiants connus) et se couper proprement en cas de doute.
- Rien ne doit être téléchargé ni installé dans le dossier du jeu sans l'accord explicite de
  l'utilisateur.
