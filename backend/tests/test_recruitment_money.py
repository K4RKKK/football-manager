"""Sections 12.1 et 10.4 — score explicable, devise étalonnée, positions."""

import pytest

from clubdirector.money import CurrencyCalibration, UncalibratedCurrency, calibrate
from clubdirector.positions import normalize_position
from clubdirector.recruitment.roles import ROLES
from clubdirector.recruitment.scoring import role_with_adjustments, score_player


def player(**attrs):
    base = {a: 10 for r in ROLES.values() for a in r.weights}
    base.update(attrs)
    return {"attributes": base, "position_ratings": {"stc": 20, "amr": 15}}


def test_score_is_reproducible_from_its_components():
    fit = score_player(player(finishing=20, off_the_ball=18), ROLES["buteur_surface"])
    w = ROLES["buteur_surface"].weights
    expected_attr = round((sum(w[a] * player(finishing=20, off_the_ball=18)["attributes"][a] for a in w) / sum(w.values()) - 1) / 19 * 100, 1)
    assert fit.attribute_score == expected_attr
    assert fit.position_score == 100.0 and fit.best_position == "STC"
    assert fit.score == round(0.85 * expected_attr + 0.15 * 100, 1)
    assert "Finition 20" in fit.strengths


def test_better_attributes_give_better_score():
    weak = score_player(player(crossing=6, dribbling=6), ROLES["ailier_centreur"]).score
    strong = score_player(player(crossing=18, dribbling=17), ROLES["ailier_centreur"]).score
    assert strong > weak


def test_hidden_attributes_cannot_be_weighted():
    with pytest.raises(ValueError):
        role_with_adjustments("buteur_surface", {"consistency": 5})
    with pytest.raises(ValueError):
        role_with_adjustments("inconnu", None)


def test_missing_attributes_give_no_score_rather_than_a_guess():
    fit = score_player({"attributes": {}, "position_ratings": {}}, ROLES["gardien"])
    assert fit.score is None and fit.missing


def test_currency_calibration():
    c = CurrencyCalibration()
    assert not c.calibrated and "non étalonnée" in c.format(1000)
    with pytest.raises(UncalibratedCurrency):
        c.to_raw(10)
    c = calibrate(4_500_000, 9_000_000, "€", "ref")
    assert c.to_display(1000) == 2000 and c.to_raw(20_000_000) == 10_000_000
    assert c.format(6_000_000) == "12,0 M€"
    with pytest.raises(ValueError):
        calibrate(0, 10, "€", "x")


@pytest.mark.parametrize("text,code", [("DC", "DC"), ("ailier droit", "AMR"), ("BU", "STC"), ("Défenseur central", "DC"),
                                       ("gardien", "GK"), ("mdc", "DM"), ("xyz", None)])
def test_positions(text, code):
    assert normalize_position(text) == code
