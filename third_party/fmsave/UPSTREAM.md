# fmsave — fork intégré à ClubDirector AI

- Origine : https://github.com/rhiever/fmsave (licence MIT, © 2026 Randal S. Olson — voir `LICENSE`).
- Base : commit `f732460719d80d74287a48b15abd22607952bee2` (0.5.10 + 1 commit de documentation), importé le 2026-10-15.
- Raison : prendre en charge les builds FM26 de l'utilisateur (26.3.0) et décoder davantage de
  sections, sans attendre les versions publiques.

## Règles conservées de l'amont
- Lecture seule ; pas de lecture mémoire, pas de réseau, pas de déchiffrement.
- Connaissance du format issue uniquement de l'observation de ses propres sauvegardes et de
  l'interface du jeu (pas de décompilation).
- Aucune donnée réelle (sauvegarde, extrait, nom, uid, valeur) dans le dépôt : tests sur
  fragments synthétiques ; analyses réelles dans `.local/` (ignoré par Git).

## Modifications locales
Chaque modification est listée ici et dans `CHANGELOG.md` (section « ClubDirector »), pour pouvoir
la reproposer à l'amont.
