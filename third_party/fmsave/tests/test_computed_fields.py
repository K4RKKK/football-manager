"""Computed fields: read-only properties a record lists in COMPUTED_FIELDS.

They cost no memory per record, and every export form writes them after the stored fields.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import pytest

import fmsave
from fmsave import Table, _status
from fmsave._status import register_field_statuses
from fmsave.export import column_names


@dataclass(frozen=True, slots=True)
class ComputedExampleLine:
    """A fictional record with one computed rate."""

    name: str
    minutes: int
    goals: int

    COMPUTED_FIELDS: ClassVar[tuple[str, ...]] = ("goals_per_90",)

    @property
    def goals_per_90(self) -> float | None:
        """Goals per 90 minutes, or None without minutes."""
        return self.goals * 90 / self.minutes if self.minutes else None


@pytest.fixture(autouse=True)
def registered_example_statuses() -> Iterator[None]:
    """Register the fictional record's statuses for one test, then restore the registry."""
    saved_statuses = {
        model_class: dict(statuses) for model_class, statuses in _status._statuses_by_class.items()
    }
    register_field_statuses(
        ComputedExampleLine, verified=("name", "minutes", "goals"), unconfirmed=("goals_per_90",)
    )
    yield
    _status._statuses_by_class.clear()
    _status._statuses_by_class.update(saved_statuses)


@dataclass(frozen=True, slots=True)
class ComputedNotAProperty:
    name: str

    COMPUTED_FIELDS: ClassVar[tuple[str, ...]] = ("name_length",)

    def name_length(self) -> int:
        return len(self.name)


def example_table() -> Table[ComputedExampleLine]:
    return Table(
        (
            ComputedExampleLine("Alex Example", 180, 3),
            ComputedExampleLine("Sam Sample", 0, 0),
        ),
        ComputedExampleLine,
    )


def test_a_computed_field_is_a_column_after_the_stored_fields() -> None:
    assert column_names(ComputedExampleLine) == ("name", "minutes", "goals", "goals_per_90")


def test_every_export_form_writes_the_computed_value(tmp_path: Path) -> None:
    table = example_table()
    assert [row["goals_per_90"] for row in table.to_dicts()] == [1.5, None]
    assert table.to_columns()["goals_per_90"] == [1.5, None]
    csv_path = tmp_path / "lines.csv"
    table.write_csv(csv_path)
    with csv_path.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    assert [row["goals_per_90"] for row in rows] == ["1.5", ""]


def test_coverage_and_where_see_the_computed_field() -> None:
    table = example_table()
    assert table.coverage["goals_per_90"] == 0.5
    assert [row.name for row in table.where(goals_per_90=1.5)] == ["Alex Example"]


def test_a_computed_field_carries_its_registered_status() -> None:
    assert fmsave.field_status(ComputedExampleLine, "goals_per_90") == "unconfirmed"


def test_a_computed_name_that_is_not_a_property_is_refused() -> None:
    with pytest.raises(TypeError, match="name_length"):
        column_names(ComputedNotAProperty)
