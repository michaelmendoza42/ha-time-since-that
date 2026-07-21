# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Runtime manager and isolated v1 history storage for Time Since That."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
import logging
from typing import Any
from uuid import uuid4

from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import SOURCE_INITIAL, STORAGE_KEY, STORAGE_VERSION
from .model import ChoreDefinition, ChoreSnapshot, CompletionEvent, build_snapshot

_LOGGER = logging.getLogger(__name__)

Listener = Callable[[], None]


class TimeSinceThatHistoryRepository:
    """Persist only clean-reset v1 completion history.

    This intentionally never reads or writes legacy YAML-era storage keys.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the isolated v1 history store."""
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._events: dict[str, list[CompletionEvent]] = {}
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Load all v1 event buckets without consulting legacy storage."""
        data = await self._store.async_load()
        if data is None:
            return
        if not isinstance(data, dict) or data.get("version") != STORAGE_VERSION:
            raise ValueError("Unsupported Time Since That v1 storage payload.")

        raw_chores = data.get("chores", {})
        if not isinstance(raw_chores, dict):
            raise ValueError("Invalid Time Since That v1 storage payload.")

        parsed: dict[str, list[CompletionEvent]] = {}
        for chore_id, chore_data in raw_chores.items():
            if not isinstance(chore_data, dict):
                raise ValueError(f"Invalid stored chore '{chore_id}'.")
            raw_events = chore_data.get("events", [])
            if not isinstance(raw_events, list):
                raise ValueError(f"Invalid stored events for chore '{chore_id}'.")
            try:
                parsed[str(chore_id)] = [
                    CompletionEvent.from_storage(str(chore_id), event)
                    for event in raw_events
                ]
            except (KeyError, TypeError, ValueError) as err:
                raise ValueError(f"Invalid stored events for chore '{chore_id}'.") from err
        self._events = parsed

    def events_for(self, chore_id: str) -> list[CompletionEvent]:
        """Return a copy of one chore's completion events."""
        return list(self._events.get(chore_id, []))

    async def async_append(self, event: CompletionEvent) -> None:
        """Append one event and persist all v1 buckets."""
        async with self._lock:
            self._events.setdefault(event.chore_id, []).append(event)
            await self._async_save()

    async def async_replace_latest(self, chore_id: str, done_at: datetime) -> CompletionEvent:
        """Correct the latest event while preserving its identity and attribution."""
        async with self._lock:
            events = self._events.get(chore_id, [])
            if not events:
                raise ValueError(f"Chore '{chore_id}' has no completion to adjust.")
            latest_index = max(range(len(events)), key=lambda index: events[index].done_at)
            latest = events[latest_index]
            corrected = CompletionEvent(
                event_id=latest.event_id,
                chore_id=latest.chore_id,
                done_at=done_at,
                user_id=latest.user_id,
                user_name=latest.user_name,
                context_id=latest.context_id,
                context_parent_id=latest.context_parent_id,
                source=latest.source,
            )
            events[latest_index] = corrected
            await self._async_save()
            return corrected

    async def _async_save(self) -> None:
        """Save every v1 bucket, including removed chore history."""
        payload = {
            "version": STORAGE_VERSION,
            "chores": {
                chore_id: {"events": [event.as_storage() for event in events]}
                for chore_id, events in self._events.items()
            },
        }
        await self._store.async_save(payload)


class TimeSinceThatManager:
    """Own active UI-managed chore definitions and derived entity state."""

    def __init__(
        self,
        hass: HomeAssistant,
        definitions: list[ChoreDefinition],
        history: TimeSinceThatHistoryRepository,
    ) -> None:
        """Initialize the manager for one config entry."""
        self.hass = hass
        self.definitions = {definition.id: definition for definition in definitions}
        self._history = history
        self._listeners: list[Listener] = []
        self._entity_to_chore_id: dict[str, str] = {}

    @property
    def chore_ids(self) -> list[str]:
        """Return configured chore IDs in UI-managed order."""
        return list(self.definitions)

    async def async_mark_done(
        self,
        chore_id: str,
        context: Context | None = None,
        *,
        source: str = "service",
        done_at: datetime | None = None,
    ) -> CompletionEvent:
        """Record a completion and notify entities."""
        if chore_id not in self.definitions:
            raise ValueError(f"Unknown chore id '{chore_id}'.")

        user_id = getattr(context, "user_id", None) if context else None
        event = CompletionEvent(
            event_id=uuid4().hex,
            chore_id=chore_id,
            done_at=done_at or dt_util.now(),
            user_id=user_id,
            user_name=await self._async_user_name(user_id),
            context_id=getattr(context, "id", None) if context else None,
            context_parent_id=getattr(context, "parent_id", None) if context else None,
            source=source,
        )
        await self._history.async_append(event)
        self._notify_listeners()
        return event

    async def async_adjust_last_completed(
        self,
        chore_id: str,
        done_at: datetime,
    ) -> CompletionEvent:
        """Correct one chore's latest completion timestamp."""
        if chore_id not in self.definitions:
            raise ValueError(f"Unknown chore id '{chore_id}'.")
        if not self._history.events_for(chore_id):
            return await self.async_mark_done(
                chore_id,
                source=SOURCE_INITIAL,
                done_at=done_at,
            )
        corrected = await self._history.async_replace_latest(chore_id, done_at)
        self._notify_listeners()
        return corrected

    def snapshot(self, chore_id: str, now: datetime | None = None) -> ChoreSnapshot:
        """Return calculated current state for a chore."""
        definition = self.definitions[chore_id]
        current_time = now or dt_util.now()
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        return build_snapshot(definition, self._history.events_for(chore_id), current_time)

    def register_listener(self, listener: Listener) -> Callable[[], None]:
        """Register a listener called after a completion mutation."""
        self._listeners.append(listener)

        def remove_listener() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove_listener

    def register_entity(self, entity_id: str, chore_id: str) -> None:
        """Map an entity ID back to one chore for service targeting."""
        self._entity_to_chore_id[entity_id] = chore_id

    def unregister_entity(self, entity_id: str) -> None:
        """Remove an entity-to-chore service-target mapping."""
        self._entity_to_chore_id.pop(entity_id, None)

    def chore_id_for_entity_id(self, entity_id: str) -> str | None:
        """Return the chore ID associated with an entity ID."""
        return self._entity_to_chore_id.get(entity_id)

    async def _async_user_name(self, user_id: str | None) -> str | None:
        """Resolve a Home Assistant user name when possible."""
        if not user_id:
            return None
        auth = getattr(self.hass, "auth", None)
        if auth is None or not hasattr(auth, "async_get_user"):
            return None
        try:
            user = await auth.async_get_user(user_id)
        except (AttributeError, KeyError, ValueError) as err:
            _LOGGER.debug("Could not resolve user name for %s: %s", user_id, err)
            return None
        return getattr(user, "name", None) if user is not None else None

    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            listener()
