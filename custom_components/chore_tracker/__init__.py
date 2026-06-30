# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Home Assistant setup for Chore Tracker."""

from __future__ import annotations

import logging
from typing import Any

from .const import CONF_CHORE_ID, CONF_CHORES, DATA_MANAGER, DOMAIN, SERVICE_MARK_DONE
from .model import definition_from_dict

try:
    from .config_schema import CONFIG_SCHEMA
except ModuleNotFoundError:  # pragma: no cover - Home Assistant deps absent in pure tests
    CONFIG_SCHEMA = None  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: Any, config: dict[str, Any]) -> bool:
    """Set up Chore Tracker from YAML."""
    from homeassistant.helpers import discovery

    from .manager import ChoreTrackerManager

    if DOMAIN not in config:
        return True

    chore_config = config[DOMAIN][CONF_CHORES]
    definitions = [definition_from_dict(item) for item in chore_config]
    manager = ChoreTrackerManager(hass, definitions)
    await manager.async_load()

    hass.data.setdefault(DOMAIN, {})[DATA_MANAGER] = manager
    _register_services(hass, manager)

    await discovery.async_load_platform(hass, "sensor", DOMAIN, {}, config)
    return True


def _register_services(hass: Any, manager: Any) -> None:
    """Register Chore Tracker services."""
    import voluptuous as vol
    from homeassistant.const import ATTR_ENTITY_ID
    from homeassistant.helpers import config_validation as cv

    mark_done_schema = vol.Schema(
        {
            vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
            vol.Optional(CONF_CHORE_ID): cv.string,
        }
    )

    async def async_mark_done(call: Any) -> None:
        for chore_id in _chore_ids_from_call(call.data, manager):
            await manager.async_mark_done(chore_id, call.context, source="service")

    hass.services.async_register(
        DOMAIN,
        SERVICE_MARK_DONE,
        async_mark_done,
        schema=mark_done_schema,
    )


def _chore_ids_from_call(data: dict[str, Any], manager: Any) -> list[str]:
    """Resolve one or more chore ids from service data."""
    import voluptuous as vol
    from homeassistant.const import ATTR_ENTITY_ID

    chore_id = data.get(CONF_CHORE_ID)
    if chore_id:
        return [str(chore_id)]

    entity_ids = data.get(ATTR_ENTITY_ID)
    if entity_ids:
        raw_entity_ids = entity_ids if isinstance(entity_ids, list) else [entity_ids]
        resolved_ids: list[str] = []
        for entity_id in raw_entity_ids:
            resolved = manager.chore_id_for_entity_id(str(entity_id))
            if resolved and resolved not in resolved_ids:
                resolved_ids.append(resolved)
        if resolved_ids:
            return resolved_ids

    raise vol.Invalid(f"Provide either {CONF_CHORE_ID} or {ATTR_ENTITY_ID}.")


__all__ = ["CONFIG_SCHEMA", "async_setup"]
