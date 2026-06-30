# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Sensor platform for Chore Tracker."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DATA_MANAGER, DOMAIN
from .manager import ChoreTrackerManager

SCAN_INTERVAL = timedelta(minutes=1)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up Chore Tracker sensors from YAML."""
    manager: ChoreTrackerManager = hass.data[DOMAIN][DATA_MANAGER]
    async_add_entities(
        ChoreSensor(manager, chore_id) for chore_id in manager.chore_ids
    )


class ChoreSensor(SensorEntity):
    """Sensor representing freshness and household stats for one chore."""

    _attr_should_poll = False

    def __init__(self, manager: ChoreTrackerManager, chore_id: str) -> None:
        """Initialize a chore sensor."""
        self._manager = manager
        self._chore_id = chore_id
        self._definition = manager.definitions[chore_id]
        self._attr_name = f"Chore {self._definition.name}"
        self._attr_unique_id = f"chore_tracker_{chore_id}"
        self._remove_manager_listener = None
        self._remove_time_listener = None

    async def async_added_to_hass(self) -> None:
        """Register state-change listeners."""
        if self.entity_id is not None:
            self._manager.register_entity(self.entity_id, self._chore_id)
        self._remove_manager_listener = self._manager.register_listener(
            self._handle_manager_update
        )
        self._remove_time_listener = async_track_time_interval(
            self.hass,
            self._handle_time_update,
            SCAN_INTERVAL,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up listeners."""
        if self._remove_manager_listener is not None:
            self._remove_manager_listener()
        if self._remove_time_listener is not None:
            self._remove_time_listener()

    @property
    def native_value(self) -> str:
        """Return a human-readable freshness state."""
        return self._manager.snapshot(self._chore_id).state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return summary attributes for automations and dashboards."""
        return self._manager.snapshot(self._chore_id).attributes

    @callback
    def _handle_manager_update(self) -> None:
        """Push state after a mark-done mutation."""
        self.async_write_ha_state()

    @callback
    def _handle_time_update(self, _now) -> None:  # noqa: ANN001
        """Refresh elapsed display as time passes."""
        self.async_write_ha_state()
