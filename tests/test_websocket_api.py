from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import importlib
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from custom_components.time_since_that.const import DATA_MANAGER, DOMAIN


class _Connection:
    def __init__(self) -> None:
        self.user = SimpleNamespace(
            id="user-id",
            permissions=SimpleNamespace(check_entity=lambda entity_id, permission: True),
        )
        self.results: list[tuple[int, object]] = []
        self.errors: list[tuple[int, str, str]] = []

    def send_result(self, message_id: int, result: object) -> None:
        self.results.append((message_id, result))

    def send_error(self, message_id: int, code: str, message: str) -> None:
        self.errors.append((message_id, code, message))


class _Manager:
    def __init__(self) -> None:
        self.updated: tuple[str, str, datetime] | None = None

    def chore_id_for_entity_id(self, entity_id: str) -> str | None:
        return "scoop_cat_litter" if entity_id == "sensor.time_since_that_scoop_cat_litter" else None

    def completion_history(self, chore_id: str) -> list[SimpleNamespace]:
        assert chore_id == "scoop_cat_litter"
        return [SimpleNamespace(event_id="event-2", done_at=datetime(2026, 7, 24, 14, 45, tzinfo=timezone.utc))]

    async def async_adjust_completion(
        self, chore_id: str, event_id: str, completed_at: datetime
    ) -> SimpleNamespace:
        self.updated = (chore_id, event_id, completed_at)
        return SimpleNamespace(event_id=event_id, done_at=completed_at)

    async def async_delete_completion(
        self, chore_id: str, event_id: str
    ) -> SimpleNamespace:
        self.deleted = (chore_id, event_id)
        return SimpleNamespace(event_id=event_id)


class TestCompletionHistoryWebSocket(unittest.TestCase):
    def _modules(self, now: datetime) -> dict[str, ModuleType]:
        websocket_api = ModuleType("homeassistant.components.websocket_api")
        setattr(websocket_api, "ActiveConnection", object)
        setattr(websocket_api, "websocket_command", lambda schema: lambda handler: handler)
        setattr(websocket_api, "async_response", lambda handler: handler)
        setattr(websocket_api, "async_register_command", lambda hass, command: None)
        components = ModuleType("homeassistant.components")
        setattr(components, "websocket_api", websocket_api)
        homeassistant = ModuleType("homeassistant")
        auth = ModuleType("homeassistant.auth")
        permissions = ModuleType("homeassistant.auth.permissions")
        permission_const = ModuleType("homeassistant.auth.permissions.const")
        setattr(permission_const, "POLICY_CONTROL", "control")
        setattr(permission_const, "POLICY_READ", "read")
        exceptions = ModuleType("homeassistant.exceptions")
        setattr(exceptions, "Unauthorized", PermissionError)
        core = ModuleType("homeassistant.core")
        setattr(core, "HomeAssistant", object)
        setattr(core, "callback", lambda handler: handler)
        helpers = ModuleType("homeassistant.helpers")
        config_validation = ModuleType("homeassistant.helpers.config_validation")
        setattr(config_validation, "entity_id", str)
        setattr(config_validation, "string", str)
        setattr(helpers, "config_validation", config_validation)
        util = ModuleType("homeassistant.util")
        dt_util = ModuleType("homeassistant.util.dt")
        setattr(dt_util, "DEFAULT_TIME_ZONE", timezone.utc)
        setattr(dt_util, "now", lambda: now)
        setattr(dt_util, "parse_datetime", lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")))
        setattr(util, "dt", dt_util)
        voluptuous = ModuleType("voluptuous")
        setattr(voluptuous, "Required", lambda key: key)
        return {
            "voluptuous": voluptuous,
            "homeassistant": homeassistant,
            "homeassistant.auth": auth,
            "homeassistant.auth.permissions": permissions,
            "homeassistant.auth.permissions.const": permission_const,
            "homeassistant.components": components,
            "homeassistant.components.websocket_api": websocket_api,
            "homeassistant.core": core,
            "homeassistant.exceptions": exceptions,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.config_validation": config_validation,
            "homeassistant.util": util,
            "homeassistant.util.dt": dt_util,
        }

    def test_history_and_update_commands_use_entity_scoped_events(self) -> None:
        now = datetime(2026, 7, 26, 14, 45, tzinfo=timezone.utc)
        manager = _Manager()
        hass = SimpleNamespace(data={DOMAIN: {DATA_MANAGER: manager}})
        connection = _Connection()
        module_name = "custom_components.time_since_that.websocket_api"
        with patch.dict(sys.modules, self._modules(now)):
            sys.modules.pop(module_name, None)
            websocket = importlib.import_module(module_name)
            websocket.websocket_get_completion_history(
                hass,
                connection,
                {"id": 1, "entity_id": "sensor.time_since_that_scoop_cat_litter"},
            )
            asyncio.run(websocket.websocket_update_completion(
                hass,
                connection,
                {
                    "id": 2,
                    "entity_id": "sensor.time_since_that_scoop_cat_litter",
                    "event_id": "event-2",
                    "completed_at": "2026-07-20T10:30:00Z",
                },
            ))
            asyncio.run(websocket.websocket_delete_completion(
                hass,
                connection,
                {
                    "id": 3,
                    "entity_id": "sensor.time_since_that_scoop_cat_litter",
                    "event_id": "event-2",
                },
            ))
        self.assertEqual(connection.errors, [])
        self.assertEqual(connection.results[0], (1, {"events": [
            {"event_id": "event-2", "completed_at": "2026-07-24T14:45:00+00:00"},
        ]}))
        self.assertEqual(manager.updated, (
            "scoop_cat_litter", "event-2", datetime(2026, 7, 20, 10, 30, tzinfo=timezone.utc),
        ))
        self.assertEqual(connection.results[1], (2, {
            "event_id": "event-2", "completed_at": "2026-07-20T10:30:00+00:00",
        }))
        self.assertEqual(manager.deleted, ("scoop_cat_litter", "event-2"))
        self.assertEqual(connection.results[2], (3, {"event_id": "event-2"}))


if __name__ == "__main__":
    unittest.main()
