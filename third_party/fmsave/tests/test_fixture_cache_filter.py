from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

import fmsave
from fmsave.readers._common import GAME_DB_SECTION
from fmsave.readers.fixtures import build_fixtures_with_offsets, largest_cluster
from fmsave.readers.span import RawFixtureContinuation, SpanRecords
from tests.test_fixtures import FIXTURE_LAYOUT


def build(save: fmsave.Save, span: SpanRecords, layout=FIXTURE_LAYOUT):
    context = save._context
    with context.section(GAME_DB_SECTION):
        clubs = context.club_index()
        stages = context.stage_index()
        competitions = context.competition_index()
        stadiums = context.stadium_index()
    return build_fixtures_with_offsets(span, stages, competitions, clubs, stadiums, layout)


def test_proven_cache_positions_cannot_win_calendar_cluster(career_save_path: Path) -> None:
    with fmsave.open(career_save_path) as save:
        span = save._context.span_records()
        expected, old_stats, expected_offsets = build(save, span)
        anchor = largest_cluster(span.fixtures, FIXTURE_LAYOUT.cluster_gap_bytes)[0]
        start = span.fixtures[-1].span_offset + 3 * FIXTURE_LAYOUT.cluster_gap_bytes
        copies = tuple(
            dataclasses.replace(anchor, span_offset=start + index * 100) for index in range(10)
        )
        fake = dataclasses.replace(
            span,
            fixtures=(*span.fixtures, *copies),
            fixture_cache_offsets=tuple(row.span_offset for row in copies),
        )
        assert largest_cluster(fake.fixtures, FIXTURE_LAYOUT.cluster_gap_bytes) == copies
        actual, stats, offsets = build(save, fake)
        assert actual == expected and offsets == expected_offsets
        assert len(fake.fixtures) == len(span.fixtures) + 10  # Raw audit retains each cache copy.
        assert stats == dataclasses.replace(old_stats, cache_records_excluded=10)


def test_same_key_at_other_physical_positions_is_retained(career_save_path: Path) -> None:
    with fmsave.open(career_save_path) as save:
        span = save._context.span_records()
        expected, _, _ = build(save, span)
        left = largest_cluster(span.fixtures, FIXTURE_LAYOUT.cluster_gap_bytes)[0]
        copies = tuple(
            dataclasses.replace(left, span_offset=left.span_offset + index) for index in (1, 2, 3)
        )
        raw = tuple(sorted((*span.fixtures, *copies), key=lambda row: row.span_offset))
        fake = dataclasses.replace(
            span, fixtures=raw, fixture_cache_offsets=(copies[1].span_offset,)
        )
        rows, stats, offsets = build(save, fake)
        assert len(rows) == len(expected) + 2
        assert copies[0].span_offset in offsets and copies[2].span_offset in offsets
        assert copies[1].span_offset not in offsets
        assert stats.cache_records_excluded == 1


@pytest.mark.parametrize("competing_count", (1, 2, 3))
def test_cache_bridges_preserve_physical_runs_without_voting(
    career_save_path: Path, competing_count: int
) -> None:
    with fmsave.open(career_save_path) as save:
        span = save._context.span_records()
        anchor = span.fixtures[0]
        main = tuple(
            dataclasses.replace(anchor, span_offset=offset) for offset in (0, 90, 180, 270)
        )
        competing = tuple(
            dataclasses.replace(anchor, span_offset=600 + 10 * index)
            for index in range(competing_count)
        )
        fake = dataclasses.replace(
            span,
            fixtures=(*main, *competing),
            fixture_cache_offsets=(90, 180),
            fixture_continuations=(),
        )
        layout = dataclasses.replace(FIXTURE_LAYOUT, cluster_gap_bytes=100)
        rows, stats, offsets = build(save, fake, layout)
        # The caches bridge physical gaps but contribute no votes. The earlier
        # two-anchor run wins a tie; three eligible competitors win outright.
        expected = (
            (0, 270) if competing_count <= 2 else tuple(record.span_offset for record in competing)
        )
        assert offsets == expected
        assert len(rows) == len(expected)
        assert stats.span_records == 2 + competing_count
        assert stats.cluster_records == len(expected)
        assert stats.clusters == 2
        assert stats.cache_records_excluded == 2


def test_cache_cannot_reenter_as_continuation_middle(career_save_path: Path) -> None:
    with fmsave.open(career_save_path) as save:
        span = save._context.span_records()
        expected, _, _ = build(save, span)
        selected = largest_cluster(span.fixtures, FIXTURE_LAYOUT.cluster_gap_bytes)
        left, right = selected[0], selected[-1]
        cached = dataclasses.replace(left, span_offset=left.span_offset + 1)
        genuine = dataclasses.replace(left, span_offset=left.span_offset + 2)
        proposal = RawFixtureContinuation(left.span_offset, right.span_offset, (cached, genuine))
        fake = dataclasses.replace(
            span, fixture_continuations=(proposal,), fixture_cache_offsets=(cached.span_offset,)
        )
        rows, stats, offsets = build(save, fake)
        assert len(rows) == len(expected) + 1
        assert genuine.span_offset in offsets and cached.span_offset not in offsets
        assert stats.cache_records_excluded == 0  # Counter covers strict raw admissions only.


def test_cache_endpoint_cannot_authorize_a_continuation(career_save_path: Path) -> None:
    with fmsave.open(career_save_path) as save:
        span = save._context.span_records()
        selected = largest_cluster(span.fixtures, FIXTURE_LAYOUT.cluster_gap_bytes)
        left, right = selected[0], selected[-1]
        middle = dataclasses.replace(left, span_offset=left.span_offset + 1)
        proposal = RawFixtureContinuation(left.span_offset, right.span_offset, (middle,))
        fake = dataclasses.replace(
            span, fixture_continuations=(proposal,), fixture_cache_offsets=(right.span_offset,)
        )
        expected = dataclasses.replace(fake, fixture_continuations=())
        rows, stats, offsets = build(save, fake)
        assert (rows, stats, offsets) == build(save, expected)
        assert right.span_offset not in offsets and middle.span_offset not in offsets
