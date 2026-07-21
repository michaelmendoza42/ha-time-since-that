# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Home Assistant setup for the UI-managed Time Since That integration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

from .const import (
    CONF_CHORE_ID,
    CONF_CHORES,
    CONF_LAST_COMPLETED,
    DATA_MANAGER,
    DOMAIN,
    SERVICE_MARK_DONE,
    SOURCE_INITIAL,
)
from .model import definition_from_dict, parse_datetime, validate_chore_definitions

PLATFORMS = ("sensor", "button")
CARD_FRONTEND_PATH = Path(__file__).parent / "frontend"
CARD_URL = f"/{DOMAIN}"
CARD_JS_URL = f"{CARD_URL}/time-since-that-card.js"
DATA_FRONTEND_REGISTERED = "frontend_registered"

_LOGGER = logging.getLogger(__name__)

try:
    from .config_schema import CONFIG_SCHEMA
except ModuleNotFoundError:  # pragma: no cover - Home Assistant deps absent in pure tests
    CONFIG_SCHEMA = None  # type: ignore[assignment]


async def async_setup(hass: Any, config: dict[str, Any]) -> bool:
    """Register domain-wide services and the bundled Lovelace card.

    The temporary schema accepts an old YAML root but never reads it. This is a
    clean reset, not a migration path.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    if DOMAIN in config:
        _LOGGER.warning(
            "Ignoring legacy YAML configuration for %s; manage chores through "
            "Settings > Devices & services instead.",
            DOMAIN,
        )

    _register_services(hass)
    if not domain_data.get(DATA_FRONTEND_REGISTERED):
        await _async_register_frontend(hass)
        domain_data[DATA_FRONTEND_REGISTERED] = True
    return True


async def async_setup_entry(hass: Any, entry: Any) -> bool:
    """Set up one UI-managed household config entry."""
    from .manager import TimeSinceThatHistoryRepository, TimeSinceThatManager

    domain_data = hass.data.setdefault(DOMAIN, {})
    history = TimeSinceThatHistoryRepository(hass)
    await history.async_load()

    raw_chores = entry.options.get(CONF_CHORES, [])
    definitions = validate_chore_definitions(
        [definition_from_dict(chore) for chore in raw_chores]
    )
    manager = TimeSinceThatManager(hass, definitions, history)
    for raw_chore in raw_chores:
        initial_value = raw_chore.get(CONF_LAST_COMPLETED)
        chore_id = str(raw_chore["id"])
        if initial_value and not history.events_for(chore_id):
            await manager.async_mark_done(
                chore_id,
                source=SOURCE_INITIAL,
                done_at=parse_datetime(str(initial_value)),
            )

    domain_data[DATA_MANAGER] = manager
    domain_data[entry.entry_id] = manager

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: Any, entry: Any) -> bool:
    """Unload platforms and entry-specific runtime state."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        domain_data = hass.data.get(DOMAIN, {})
        domain_data.pop(entry.entry_id, None)
        domain_data.pop(DATA_MANAGER, None)
    return unload_ok


async def _async_update_listener(hass: Any, entry: Any) -> None:
    """Reload entities after chore options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_frontend(hass: Any) -> None:
    """Serve and automatically load the bundled Lovelace card."""
    from homeassistant.components.frontend import add_extra_js_url

    if hasattr(hass.http, "async_register_static_paths"):
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(CARD_FRONTEND_PATH), True)]
        )
    else:  # Home Assistant 2024.6 compatibility
        hass.http.register_static_path(CARD_URL, str(CARD_FRONTEND_PATH), True)

    add_extra_js_url(hass, CARD_JS_URL)


def _register_services(hass: Any) -> None:
    """Register the domain service once; resolve the live entry manager per call."""
    if hass.services.has_service(DOMAIN, SERVICE_MARK_DONE):
        return

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
        manager = hass.data.get(DOMAIN, {}).get(DATA_MANAGER)
        if manager is None:
            raise vol.Invalid("Time Since That is not configured.")
        for chore_id in _chore_ids_from_call(call.data, manager):
            await manager.async_mark_done(chore_id, call.context, source="service")

    hass.services.async_register(
        DOMAIN,
        SERVICE_MARK_DONE,
        async_mark_done,
        schema=mark_done_schema,
    )


def _chore_ids_from_call(data: dict[str, Any], manager: Any) -> list[str]: 
    """Resolve one or more chore IDs from service data."""
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


__all__ = ["CONFIG_SCHEMA", "async_setup", "async_setup_entry", "async_unload_entry"]
