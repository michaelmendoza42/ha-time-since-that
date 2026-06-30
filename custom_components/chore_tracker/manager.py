# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Runtime manager and storage coordination for Chore Tracker."""

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

from .const import STORAGE_KEY, STORAGE_VERSION
from .model import ChoreDefinition, ChoreSnapshot, CompletionEvent, build_snapshot

_LOGGER = logging.getLogger(__name__)

Listener = Callable[[], None]


class ChoreTrackerManager:
    """Own chore definitions, history, mutations, and derived state."""

    def __init__(self, hass: HomeAssistant, definitions: list[ChoreDefinition]) -> None:
        """Initialize the manager."""
        self.hass = hass
        self.definitions = {definition.id: definition for definition in definitions}
        self._events: dict[str, list[CompletionEvent]] = {
            definition.id: [] for definition in definitions
        }
        self._listeners: list[Listener] = []
        self._entity_to_chore_id: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    @property
    def chore_ids(self) -> list[str]:
        """Return configured chore ids."""
        return list(self.definitions)

    async def async_load(self) -> None:
        """Load persisted completion history."""
        data = await self._store.async_load()
        if data is None:
            return
        if not isinstance(data, dict) or data.get("version") != STORAGE_VERSION:
            raise ValueError("Unsupported Chore Tracker storage payload.")

        chores = data.get("chores", {})
        if not isinstance(chores, dict):
            raise ValueError("Invalid Chore Tracker storage payload: chores must be an object.")

        for chore_id, chore_data in chores.items():
            if not isinstance(chore_data, dict):
                continue
            raw_events = chore_data.get("events", [])
            if not isinstance(raw_events, list):
                continue
            try:
                events = [CompletionEvent.from_storage(chore_id, event) for event in raw_events]
            except (KeyError, TypeError, ValueError) as err:
                raise ValueError(f"Invalid stored events for chore '{chore_id}'.") from err
            if chore_id in self.definitions:
                self._events[chore_id] = events

    async def async_mark_done(
        self,
        chore_id: str,
        context: Context | None = None,
        *,
        source: str = "service",
        done_at: datetime | None = None,
    ) -> CompletionEvent:
        """Record a chore completion and notify entities."""
        if chore_id not in self.definitions:
            raise ValueError(f"Unknown chore id '{chore_id}'.")

        async with self._lock:
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
            self._events.setdefault(chore_id, []).append(event)
            await self._async_save()

        self._notify_listeners()
        return event

    def snapshot(self, chore_id: str, now: datetime | None = None) -> ChoreSnapshot:
        """Return calculated current state for a chore."""
        definition = self.definitions[chore_id]
        events = self._events.get(chore_id, [])
        current_time = now or dt_util.now()
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        return build_snapshot(definition, events, current_time)

    def register_listener(self, listener: Listener) -> Callable[[], None]:
        """Register a listener called after manager state changes."""
        self._listeners.append(listener)

        def remove_listener() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove_listener

    def register_entity(self, entity_id: str, chore_id: str) -> None:
        """Map an HA entity id back to its chore id for service targeting."""
        self._entity_to_chore_id[entity_id] = chore_id

    def chore_id_for_entity_id(self, entity_id: str) -> str | None:
        """Return the chore id associated with an entity id, if known."""
        return self._entity_to_chore_id.get(entity_id)

    async def _async_save(self) -> None:
        """Persist current completion history."""
        payload = {
            "version": STORAGE_VERSION,
            "chores": {
                chore_id: {"events": [event.as_storage() for event in events]}
                for chore_id, events in self._events.items()
            },
        }
        await self._store.async_save(payload)

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
