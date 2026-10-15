from __future__ import annotations

import dataclasses

import pytest

from fmsave._checks import check_player_match_stats, enforce, evaluate_player_match_stats
from fmsave._layouts import GateBounds, find_layout
from fmsave._reader_stats import MatchStats

BOUNDS = find_layout(GateBounds, "game_db", 4000, "").layout
FULL_SIZE_GAME_DB_BYTES = 300 * 1024 * 1024


def confirmed_empty_stats() -> MatchStats:
    return MatchStats(
        records=0,
        with_stats=0,
        players_with_records=0,
        competition_in_stage_space=0,
        minutes_in_range=0,
        rating_in_range=0,
        stats_in_range=0,
        opponent_resolved=0,
        unowned=0,
        lists_found=0,
        lists_decoded=0,
        history_slots=12,
        history_containing_null=7,
        history_null=3,
        history_empty=2,
        history_nonempty=0,
        history_unknown=0,
    )


def test_every_player_declaring_absence_has_no_match_ratios_to_judge() -> None:
    stats = confirmed_empty_stats()
    gates = evaluate_player_match_stats(stats, BOUNDS, FULL_SIZE_GAME_DB_BYTES)
    assert all(gate.observed is None and not gate.applied and gate.passed for gate in gates)
    enforce("player_match_stats", gates, strict=True)
    check = check_player_match_stats(stats, BOUNDS, FULL_SIZE_GAME_DB_BYTES)
    assert check.record_count == 0
    assert check.anomalies["incomplete_match_lists"] == 0
    assert {key: value for key, value in check.anomalies.items() if key.startswith("history_")} == {
        "history_slots": 12,
        "history_containing_null": 7,
        "history_null": 3,
        "history_empty": 2,
        "history_nonempty": 0,
        "history_unknown": 0,
    }


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"history_null": 2, "history_unknown": 1}, id="one-unresolved-player"),
        pytest.param({"history_null": 2, "history_nonempty": 1}, id="filtered-positive-history"),
        pytest.param({"history_null": 2}, id="missing-one-player-declaration"),
        pytest.param({"history_slots": 11}, id="too-many-declarations-for-population"),
        pytest.param(
            {
                "history_slots": 0,
                "history_containing_null": 0,
                "history_null": 0,
                "history_empty": 0,
            },
            id="no-accepted-player-headers",
        ),
        pytest.param(
            {"history_containing_null": -1, "history_null": 11}, id="invalid-negative-count"
        ),
        pytest.param({"history_unknown": None}, id="missing-ownership-metadata"),
        pytest.param({"history_empty": None}, id="missing-empty-declarations"),
        pytest.param({"lists_found": 1}, id="contradictory-undecoded-positive-list"),
        pytest.param(
            {"lists_found": 1, "lists_decoded": 1}, id="contradictory-decoded-positive-list"
        ),
        pytest.param({"lists_decoded": 1}, id="inconsistent-legacy-list-counts"),
        pytest.param({"lists_found": None, "lists_decoded": None}, id="no-list-metadata"),
    ],
)
def test_empty_output_is_not_absence_when_any_declaration_is_unresolved_or_positive(
    changes: dict[str, int | None],
) -> None:
    stats = dataclasses.replace(confirmed_empty_stats(), **changes)
    gates = evaluate_player_match_stats(stats, BOUNDS, FULL_SIZE_GAME_DB_BYTES)
    competition_gate = gates[0]
    assert competition_gate.observed is None
    assert competition_gate.applied and not competition_gate.passed
    assert competition_gate.minimum == BOUNDS.per_match_competition_in_stage_space[0]


def test_absence_metadata_never_disables_checks_of_existing_match_rows() -> None:
    stats = dataclasses.replace(
        confirmed_empty_stats(),
        records=10,
        competition_in_stage_space=9,
        lists_found=2,
        lists_decoded=1,
    )
    gates = evaluate_player_match_stats(stats, BOUNDS, FULL_SIZE_GAME_DB_BYTES)
    assert [gate.name for gate in gates if gate.applied and not gate.passed] == [
        "per_match_competition_in_stage_space",
        "per_match_lists_complete",
    ]
    without_declarations = dataclasses.replace(
        stats,
        history_slots=None,
        history_containing_null=None,
        history_null=None,
        history_empty=None,
        history_nonempty=None,
        history_unknown=None,
    )
    assert gates == evaluate_player_match_stats(
        without_declarations, BOUNDS, FULL_SIZE_GAME_DB_BYTES
    )


def test_ordinary_callers_keep_their_unknown_absence_and_original_diagnostics() -> None:
    stats = MatchStats(0, 0, 0, 0, 0, 0, 0, 0, 0, lists_found=0, lists_decoded=0)
    check = check_player_match_stats(stats, BOUNDS, FULL_SIZE_GAME_DB_BYTES)
    assert check.gates[0].applied and not check.gates[0].passed
    assert check.gates[-1].applied and not check.gates[-1].passed
    assert not any(key.startswith("history_") for key in check.anomalies)
