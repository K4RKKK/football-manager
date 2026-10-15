"""Régénère les sauvegardes SYNTHÉTIQUES de test à partir d'un clone de fmsave (MIT).

Usage :
  git clone --depth 1 https://github.com/rhiever/fmsave /chemin/fmsave
  uv run --project backend python scripts/generate_synthetic_saves.py /chemin/fmsave
"""

from __future__ import annotations

import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "backend" / "tests" / "fixtures" / "saves"


def main() -> None:
    fmsave_repo = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(fmsave_repo))
    from tests.fixtures.career import career_fragment  # type: ignore[import-not-found]
    from tests.test_competition_rules import EXAMPLE_SCORES  # type: ignore[import-not-found]

    career_fragment().write(OUT / "synthetic-career.fm")
    career_fragment(span_results=EXAMPLE_SCORES).write(OUT / "synthetic-career-scored.fm")
    print("Écrit dans", OUT)


if __name__ == "__main__":
    main()
