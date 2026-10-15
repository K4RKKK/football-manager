"""Inventaire des sections : chaque section listée, lecteurs mesurés, aucune donnée de carrière."""

import json

from clubdirector.game.inventory import CLUBDIRECTOR_USAGE, build_inventory, render_markdown

from .conftest import SCORED


def test_inventory_lists_every_section_and_reader():
    inv = build_inventory(SCORED)
    names = {s.name for s in inv.sections}
    assert {"game_db", "game_info"} <= names
    readers = {r.name: r for r in inv.readers}
    assert readers["players"].status == "ok" and "game_db" in readers["players"].sections
    # contrats : décodage partagé avec les joueurs, rattaché quand même à game_db
    assert "game_db" in readers["contracts"].sections
    assert readers["players"].clubdirector.startswith(CLUBDIRECTOR_USAGE["players"])
    assert readers["staff"].clubdirector == "miroir complet fm_staff"
    game_info = next(s for s in inv.sections if s.name == "game_info")
    assert game_info.state != "non décodée"


def test_inventory_report_has_no_career_values():
    inv = build_inventory(SCORED)
    text = render_markdown(inv) + json.dumps(inv.as_dict(), ensure_ascii=False)
    for secret in ("Northbridge", "Alex Example", "Sam Sample"):
        assert secret not in text
