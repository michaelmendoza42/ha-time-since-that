# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from custom_components.time_since_that.model import (
    ChoreConfigError,
    CompletionEvent,
    definition_from_dict,
    definition_to_dict,
    build_snapshot,
    format_duration,
    validate_chore_definitions,
)


class TestChoreModel(unittest.TestCase):
    def test_definition_defaults(self) -> None:
        definition = definition_from_dict({"id": "scoop_cat_litter", "name": "Scoop cat litter"})

        self.assertEqual(definition.id, "scoop_cat_litter")
        self.assertEqual(definition.elapsed_display.unit, "days")
        self.assertEqual(definition.elapsed_display.rounding, "floor")
        self.assertIsNone(definition.recommended_every)

    def test_definition_full_config(self) -> None:
        definition = definition_from_dict(
            {
                "id": "move_laundry",
                "name": "Move laundry",
                "category": "laundry",
                "area": "Basement",
                "recommended_every": {"value": 45, "unit": "minutes"},
                "elapsed_display": {"unit": "minutes", "rounding": "nearest"},
            }
        )

        self.assertIsNotNone(definition.recommended_every)
        recommended = definition.recommended_every
        assert recommended is not None
        self.assertEqual(recommended.seconds, 45 * 60)
        self.assertEqual(definition.elapsed_display.unit, "minutes")
        self.assertEqual(definition.elapsed_display.rounding, "nearest")

    def test_tags_are_normalized_and_exposed_on_snapshot(self) -> None:
        definition = definition_from_dict(
            {
                "id": "scoop_cat_litter",
                "name": "Scoop cat litter",
                "tags": [" Pets ", "Daily"],
            }
        )

        self.assertEqual(definition.tags, ("pets", "daily"))
        self.assertEqual(definition_to_dict(definition)["tags"], ["pets", "daily"])
        snapshot = build_snapshot(definition, [], datetime(2026, 6, 30, tzinfo=timezone.utc))
        self.assertEqual(snapshot.attributes["tags"], ["pets", "daily"])

    def test_duplicate_tags_rejected(self) -> None:
        with self.assertRaises(ChoreConfigError):
            definition_from_dict(
                {
                    "id": "vacuum",
                    "name": "Vacuum",
                    "tags": ["home", " Home "],
                }
            )

    def test_duplicate_ids_rejected(self) -> None:
        first = definition_from_dict({"id": "vacuum", "name": "Vacuum"})
        second = definition_from_dict({"id": "vacuum", "name": "Vacuum again"})

        with self.assertRaises(ChoreConfigError):
            validate_chore_definitions([first, second])

    def test_bad_slug_rejected(self) -> None:
        with self.assertRaises(ChoreConfigError):
            definition_from_dict({"id": "Scoop-Cat-Litter", "name": "Scoop cat litter"})

    def test_format_duration_rounding(self) -> None:
        self.assertEqual(format_duration(90 * 60, "hours", "floor"), ("1 hour", 1))
        self.assertEqual(format_duration(90 * 60, "hours", "ceil"), ("2 hours", 2))
        self.assertEqual(format_duration(90 * 60, "hours", "nearest"), ("2 hours", 2))

    def test_never_done_snapshot(self) -> None:
        definition = definition_from_dict({"id": "vacuum", "name": "Vacuum"})
        snapshot = build_snapshot(definition, [], datetime(2026, 6, 30, tzinfo=timezone.utc))

        self.assertEqual(snapshot.state, "never")
        self.assertEqual(snapshot.attributes["completion_count"], 0)
        self.assertIsNone(snapshot.attributes["last_done_at"])

    def test_single_completion_snapshot(self) -> None:
        definition = definition_from_dict(
            {
                "id": "scoop_cat_litter",
                "name": "Scoop cat litter",
                "recommended_every": {"value": 2, "unit": "days"},
                "elapsed_display": {"unit": "days", "rounding": "floor"},
            }
        )
        now = datetime(2026, 6, 30, 12, tzinfo=timezone.utc)
        event = CompletionEvent(
            event_id="one",
            chore_id="scoop_cat_litter",
            done_at=now - timedelta(days=3, hours=2),
            user_id="user-1",
            user_name="Example User",
        )

        snapshot = build_snapshot(definition, [event], now)

        self.assertEqual(snapshot.state, "3 days since")
        self.assertEqual(snapshot.attributes["elapsed_value"], 3)
        self.assertTrue(snapshot.attributes["over_recommended"])
        self.assertEqual(snapshot.attributes["over_by"], "1 day")
        self.assertEqual(snapshot.attributes["last_done_by_name"], "Example User")
        self.assertIsNone(snapshot.attributes["average_interval"])

    def test_household_stats_snapshot(self) -> None:
        definition = definition_from_dict(
            {
                "id": "refill_humidifier",
                "name": "Refill humidifier",
                "elapsed_display": {"unit": "hours", "rounding": "nearest"},
            }
        )
        base = datetime(2026, 6, 30, 12, tzinfo=timezone.utc)
        events = [
            CompletionEvent("one", "refill_humidifier", base - timedelta(hours=12)),
            CompletionEvent("two", "refill_humidifier", base - timedelta(hours=7)),
            CompletionEvent("three", "refill_humidifier", base - timedelta(hours=1)),
        ]

        snapshot = build_snapshot(definition, events, base)

        self.assertEqual(snapshot.state, "1 hour since")
        self.assertEqual(snapshot.attributes["completion_count"], 3)
        self.assertEqual(snapshot.attributes["average_interval"], "6 hours")
        self.assertEqual(snapshot.attributes["median_interval"], "6 hours")
        self.assertEqual(snapshot.attributes["shortest_interval"], "5 hours")
        self.assertEqual(snapshot.attributes["longest_interval"], "6 hours")


if __name__ == "__main__":
    unittest.main()
