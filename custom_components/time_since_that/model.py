"""Pure domain model and stats helpers for Time Since That."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re
from statistics import mean, median
from typing import Any

from .const import (
    DEFAULT_DISPLAY_ROUNDING,
    DEFAULT_DISPLAY_UNIT,
    ROUNDING_MODES,
    UNITS,
)

UNIT_SECONDS: dict[str, int] = {
    "minutes": 60,
    "hours": 60 * 60,
    "days": 24 * 60 * 60,
}

SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class ChoreConfigError(ValueError):
    """Raised when a chore definition is invalid."""


@dataclass(frozen=True, slots=True)
class RecommendedEvery:
    """Recommended cadence for a chore."""

    value: float
    unit: str

    @property
    def seconds(self) -> float:
        """Return the cadence in seconds."""
        return self.value * UNIT_SECONDS[self.unit]


@dataclass(frozen=True, slots=True)
class ElapsedDisplay:
    """Human display choices for elapsed intervals."""

    unit: str = DEFAULT_DISPLAY_UNIT
    rounding: str = DEFAULT_DISPLAY_ROUNDING


@dataclass(frozen=True, slots=True)
class ChoreDefinition:
    """Static YAML-defined chore metadata."""

    id: str
    name: str
    category: str | None = None
    area: str | None = None
    recommended_every: RecommendedEvery | None = None
    elapsed_display: ElapsedDisplay = ElapsedDisplay()


@dataclass(frozen=True, slots=True)
class CompletionEvent:
    """A single household completion event."""

    event_id: str
    chore_id: str
    done_at: datetime
    user_id: str | None = None
    user_name: str | None = None
    context_id: str | None = None
    context_parent_id: str | None = None
    source: str = "service"

    def as_storage(self) -> dict[str, Any]:
        """Serialize the event for Home Assistant storage."""
        return {
            "event_id": self.event_id,
            "done_at": self.done_at.isoformat(),
            "user_id": self.user_id,
            "user_name": self.user_name,
            "context_id": self.context_id,
            "context_parent_id": self.context_parent_id,
            "source": self.source,
        }

    @classmethod
    def from_storage(cls, chore_id: str, data: dict[str, Any]) -> "CompletionEvent":
        """Deserialize an event from Home Assistant storage."""
        done_at = parse_datetime(data["done_at"])
        return cls(
            event_id=str(data["event_id"]),
            chore_id=chore_id,
            done_at=done_at,
            user_id=data.get("user_id"),
            user_name=data.get("user_name"),
            context_id=data.get("context_id"),
            context_parent_id=data.get("context_parent_id"),
            source=data.get("source") or "service",
        )


@dataclass(frozen=True, slots=True)
class ChoreSnapshot:
    """Calculated current state for a chore."""

    state: str
    attributes: dict[str, Any]


def parse_datetime(value: str) -> datetime:
    """Parse an ISO datetime and ensure it is timezone-aware."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def validate_chore_definitions(definitions: list[ChoreDefinition]) -> list[ChoreDefinition]:
    """Validate normalized chore definitions."""
    seen: set[str] = set()
    for definition in definitions:
        if not SLUG_RE.match(definition.id):
            raise ChoreConfigError(
                f"Invalid chore id '{definition.id}'. Use lowercase snake_case."
            )
        if definition.id in seen:
            raise ChoreConfigError(f"Duplicate chore id '{definition.id}'.")
        seen.add(definition.id)
        if not definition.name.strip():
            raise ChoreConfigError(f"Chore '{definition.id}' must have a non-empty name.")
        if definition.recommended_every is not None:
            _validate_positive_value(definition.recommended_every.value, "recommended_every.value")
            _validate_unit(definition.recommended_every.unit)
        _validate_unit(definition.elapsed_display.unit)
        if definition.elapsed_display.rounding not in ROUNDING_MODES:
            raise ChoreConfigError(
                f"Invalid rounding '{definition.elapsed_display.rounding}'."
            )
    return definitions


def definition_from_dict(data: dict[str, Any]) -> ChoreDefinition:
    """Build a normalized chore definition from a config dictionary."""
    recommended = data.get("recommended_every")
    display = data.get("elapsed_display") or {}
    definition = ChoreDefinition(
        id=str(data["id"]),
        name=str(data["name"]),
        category=data.get("category"),
        area=data.get("area"),
        recommended_every=(
            _recommended_from_dict(recommended)
            if recommended
            else None
        ),
        elapsed_display=ElapsedDisplay(
            unit=str(display.get("unit", DEFAULT_DISPLAY_UNIT)),
            rounding=str(display.get("rounding", DEFAULT_DISPLAY_ROUNDING)),
        ),
    )
    return validate_chore_definitions([definition])[0]


def format_duration(
    seconds: float | int | None,
    unit: str,
    rounding: str = DEFAULT_DISPLAY_ROUNDING,
) -> tuple[str | None, int | None]:
    """Format seconds into a rounded human duration and numeric value."""
    if seconds is None:
        return None, None
    _validate_unit(unit)
    if rounding not in ROUNDING_MODES:
        raise ChoreConfigError(f"Invalid rounding '{rounding}'.")

    try:
        raw_value = max(0.0, float(seconds)) / UNIT_SECONDS[unit]
    except (TypeError, ValueError) as err:
        raise ChoreConfigError("Duration seconds must be numeric.") from err
    if rounding == "ceil":
        value = math.ceil(raw_value)
    elif rounding == "nearest":
        value = math.floor(raw_value + 0.5)
    else:
        value = math.floor(raw_value)

    return f"{value} {_plural(unit, value)}", value


def build_snapshot(
    definition: ChoreDefinition,
    events: list[CompletionEvent],
    now: datetime,
) -> ChoreSnapshot:
    """Calculate current state and attributes for one chore."""
    ordered = sorted(events, key=lambda event: event.done_at)
    display_unit = definition.elapsed_display.unit
    rounding = definition.elapsed_display.rounding
    attrs: dict[str, Any] = {
        "chore_id": definition.id,
        "friendly_chore_name": definition.name,
        "completion_count": len(ordered),
        "elapsed_unit": display_unit,
        "category": definition.category,
        "area": definition.area,
    }

    if definition.recommended_every is not None:
        rec_text, _ = format_duration(
            definition.recommended_every.seconds,
            definition.recommended_every.unit,
            "nearest",
        )
        attrs.update(
            {
                "recommended_every": rec_text,
                "recommended_every_value": _preserve_number(definition.recommended_every.value),
                "recommended_every_unit": definition.recommended_every.unit,
            }
        )
    else:
        attrs.update(
            {
                "recommended_every": None,
                "recommended_every_value": None,
                "recommended_every_unit": None,
            }
        )

    if not ordered:
        attrs.update(
            {
                "last_done_at": None,
                "last_done_by_name": None,
                "last_done_by_user_id": None,
                "elapsed": None,
                "elapsed_value": None,
                "over_recommended": None,
                "over_by": None,
                "over_by_value": None,
                "average_interval": None,
                "average_interval_seconds": None,
                "median_interval": None,
                "median_interval_seconds": None,
                "shortest_interval": None,
                "longest_interval": None,
            }
        )
        return ChoreSnapshot("never", attrs)

    last_event = ordered[-1]
    elapsed_seconds = max(0.0, (now - last_event.done_at).total_seconds())
    elapsed_text, elapsed_value = format_duration(elapsed_seconds, display_unit, rounding)
    attrs.update(
        {
            "last_done_at": last_event.done_at.isoformat(),
            "last_done_by_name": last_event.user_name,
            "last_done_by_user_id": last_event.user_id,
            "elapsed": elapsed_text,
            "elapsed_value": elapsed_value,
        }
    )

    if definition.recommended_every is None:
        attrs.update({"over_recommended": None, "over_by": None, "over_by_value": None})
    else:
        over_seconds = elapsed_seconds - definition.recommended_every.seconds
        over_recommended = over_seconds > 0
        over_text, over_value = format_duration(max(0.0, over_seconds), display_unit, rounding)
        attrs.update(
            {
                "over_recommended": over_recommended,
                "over_by": over_text if over_recommended else None,
                "over_by_value": over_value if over_recommended else None,
            }
        )

    intervals = [
        (current.done_at - previous.done_at).total_seconds()
        for previous, current in zip(ordered, ordered[1:])
    ]
    if intervals:
        average_seconds = mean(intervals)
        median_seconds = median(intervals)
        attrs.update(
            {
                "average_interval": format_duration(average_seconds, display_unit, rounding)[0],
                "average_interval_seconds": average_seconds,
                "median_interval": format_duration(median_seconds, display_unit, rounding)[0],
                "median_interval_seconds": median_seconds,
                "shortest_interval": format_duration(min(intervals), display_unit, rounding)[0],
                "longest_interval": format_duration(max(intervals), display_unit, rounding)[0],
            }
        )
    else:
        attrs.update(
            {
                "average_interval": None,
                "average_interval_seconds": None,
                "median_interval": None,
                "median_interval_seconds": None,
                "shortest_interval": None,
                "longest_interval": None,
            }
        )

    return ChoreSnapshot(f"{elapsed_text} since", attrs)


def _recommended_from_dict(data: dict[str, Any]) -> RecommendedEvery:
    """Build a recommended cadence from config data with clear errors."""
    try:
        value = float(data["value"])
        unit = str(data["unit"])
    except (KeyError, TypeError, ValueError) as err:
        raise ChoreConfigError("recommended_every requires numeric value and unit.") from err
    return RecommendedEvery(value, unit)


def _validate_positive_value(value: float, field_name: str) -> None:
    if value <= 0:
        raise ChoreConfigError(f"{field_name} must be greater than zero.")


def _validate_unit(unit: str) -> None:
    if unit not in UNITS:
        raise ChoreConfigError(f"Invalid unit '{unit}'. Supported units: {', '.join(UNITS)}.")


def _plural(unit: str, value: int) -> str:
    if value == 1:
        return unit[:-1]
    return unit


def _preserve_number(value: float) -> int | float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return value
    if numeric.is_integer():
        try:
            return int(numeric)
        except (OverflowError, ValueError):
            return value
    return value
