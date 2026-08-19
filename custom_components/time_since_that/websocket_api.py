"""Authenticated WebSocket commands for the dashboard completion-history view."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.auth.permissions.const import POLICY_CONTROL, POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import DATA_MANAGER, DOMAIN
from .model import required_past_datetime

WS_GET_COMPLETION_HISTORY = f"{DOMAIN}/completion_history"
WS_UPDATE_COMPLETION = f"{DOMAIN}/update_completion"


def _manager_for_entity(hass: HomeAssistant, entity_id: str) -> Any:
    """Resolve the active manager and chore ID from a sensor entity."""
    manager = hass.data.get(DOMAIN, {}).get(DATA_MANAGER)
    if manager is None:
        raise ValueError("Time Since That is not configured.")
    chore_id = manager.chore_id_for_entity_id(entity_id)
    if chore_id is None:
        raise ValueError("Entity is not a Time Since That chore.")
    return manager, chore_id


def _require_entity_permission(connection: websocket_api.ActiveConnection, entity_id: str, permission: str) -> None:
    """Enforce the same entity read/control policy used by Home Assistant services."""
    if not connection.user.permissions.check_entity(entity_id, permission):
        raise Unauthorized(
            user_id=connection.user.id,
            entity_id=entity_id,
            permission=permission,
        )


def _history_payload(events: list[Any]) -> list[dict[str, str]]:
    """Return only the fields required by the dashboard card."""
    return [
        {"event_id": event.event_id, "completed_at": event.done_at.isoformat()}
        for event in events
    ]


@websocket_api.websocket_command(
    {vol.Required("type"): WS_GET_COMPLETION_HISTORY, vol.Required("entity_id"): cv.entity_id}
)
@callback
def websocket_get_completion_history(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return one chore's completion history without adding it to sensor state."""
    try:
        _require_entity_permission(connection, msg["entity_id"], POLICY_READ)
        manager, chore_id = _manager_for_entity(hass, msg["entity_id"])
    except ValueError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    connection.send_result(msg["id"], {"events": _history_payload(manager.completion_history(chore_id))})


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_UPDATE_COMPLETION,
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("event_id"): cv.string,
        vol.Required("completed_at"): cv.string,
    }
)
@websocket_api.async_response
async def websocket_update_completion(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Correct one completion timestamp selected from the card history view."""
    try:
        _require_entity_permission(connection, msg["entity_id"], POLICY_CONTROL)
        completed_at = required_past_datetime(
            dt_util.parse_datetime(msg["completed_at"]),
            default_timezone=dt_util.DEFAULT_TIME_ZONE,
            now=dt_util.now(),
        )
        manager, chore_id = _manager_for_entity(hass, msg["entity_id"])
        event = await manager.async_adjust_completion(
            chore_id, msg["event_id"], completed_at
        )
    except (TypeError, ValueError) as err:
        connection.send_error(msg["id"], "invalid_completion", str(err))
        return
    connection.send_result(
        msg["id"], {"event_id": event.event_id, "completed_at": event.done_at.isoformat()}
    )


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register the authenticated commands used by the bundled dashboard card."""
    websocket_api.async_register_command(hass, websocket_get_completion_history)
    websocket_api.async_register_command(hass, websocket_update_completion)
