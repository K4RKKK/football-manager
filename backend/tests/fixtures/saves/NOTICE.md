# Sauvegardes synthétiques de test

`synthetic-career.fm` et `synthetic-career-scored.fm` sont des fichiers **synthétiques** au format
conteneur réel de Football Manager 26 (en-tête, trames Zstandard, répertoire), générés par le
constructeur de tests de [fmsave](https://github.com/rhiever/fmsave) (`tests/fixtures/career.py`,
licence MIT, © 2026 Randal S. Olson) avec `scripts/generate_synthetic_saves.py`.

- Tous les noms sont fictifs (Northbridge FC, Alex Example…). Aucune donnée de carrière réelle.
- Ils valident la chaîne *fichier .fm → fmsave → normalisation → SQLite → outils → réponses*.
- Ils **ne** valident **pas** la lecture d'une vraie carrière FM26 : ce test doit être fait sur le
  PC de l'utilisateur (voir `docs/TEST_PLAN.md`, test R-1).

Licence MIT de fmsave :

```
MIT License

Copyright (c) 2026 Randal S. Olson

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT
OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```
