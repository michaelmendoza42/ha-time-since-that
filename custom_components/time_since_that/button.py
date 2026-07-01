# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Button platform for Time Since That."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DATA_MANAGER, DOMAIN, SOURCE_BUTTON
from .manager import TimeSinceThatManager


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up Time Since That mark-done buttons from YAML."""
    manager: TimeSinceThatManager = hass.data[DOMAIN][DATA_MANAGER]
    async_add_entities(
        MarkDoneButton(manager, chore_id) for chore_id in manager.chore_ids
    )


class MarkDoneButton(ButtonEntity):
    """Button that records a completion event for one tracked item."""

    _attr_should_poll = False
    _attr_icon = "mdi:check-circle-outline"

    def __init__(self, manager: TimeSinceThatManager, chore_id: str) -> None:
        """Initialize a mark-done button."""
        self._manager = manager
        self._chore_id = chore_id
        self._definition = manager.definitions[chore_id]
        self._attr_name = f"Mark {self._definition.name} done"
        self._attr_unique_id = f"time_since_that_{chore_id}_mark_done"

    async def async_added_to_hass(self) -> None:
        """Register this button entity as another target for the chore."""
        if self.entity_id is not None:
            self._manager.register_entity(self.entity_id, self._chore_id)

    async def async_press(self) -> None:
        """Record a completion event when the button is pressed."""
        await self._manager.async_mark_done(self._chore_id, source=SOURCE_BUTTON)
