# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import sys
from types import ModuleType, SimpleNamespace
import unittest
from typing import Any, Callable, Coroutine
from unittest.mock import patch

from custom_components.time_since_that import _register_services
from custom_components.time_since_that.const import (
    DATA_MANAGER,
    DOMAIN,
    SERVICE_MARK_DONE,
    SERVICE_RECORD_COMPLETION,
    SOURCE_RECORDED_COMPLETION,
)


class _Invalid(ValueError):
    pass


class _Services:
    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[Any], Coroutine[Any, Any, None]]] = {}
        self.schemas: dict[str, object] = {}

    def has_service(self, domain: str, service: str) -> bool:
        return service in self.handlers

    def async_register(
        self,
        domain: str,
        service: str,
        handler: Callable[[Any], Coroutine[Any, Any, None]],
        **kwargs: object,
    ) -> None:
        self.handlers[service] = handler
        self.schemas[service] = kwargs.get("schema")


class _Manager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, str, datetime | None]] = []

    def chore_id_for_entity_id(self, entity_id: str) -> str | None:
        if entity_id == "sensor.time_since_that_scoop_cat_litter":
            return "scoop_cat_litter"
        return None

    async def async_mark_done(
        self,
        chore_id: str,
        context: object,
        *,
        source: str,
        done_at: datetime | None = None,
    ) -> None:
        self.calls.append((chore_id, context, source, done_at))


class TestCompletionServices(unittest.TestCase):
    def _modules(self, now: datetime) -> dict[str, ModuleType]:
        voluptuous = ModuleType("voluptuous")
        setattr(voluptuous, "Invalid", _Invalid)
        setattr(voluptuous, "Optional", lambda key: key)
        setattr(voluptuous, "Required", lambda key: key)
        setattr(voluptuous, "Schema", lambda schema: schema)

        homeassistant = ModuleType("homeassistant")
        const = ModuleType("homeassistant.const")
        setattr(const, "ATTR_ENTITY_ID", "entity_id")
        helpers = ModuleType("homeassistant.helpers")
        config_validation = ModuleType("homeassistant.helpers.config_validation")
        setattr(config_validation, "entity_ids", lambda value: value)
        setattr(config_validation, "string", str)
        setattr(helpers, "config_validation", config_validation)
        util = ModuleType("homeassistant.util")
        dt_util = ModuleType("homeassistant.util.dt")
        setattr(dt_util, "DEFAULT_TIME_ZONE", timezone.utc)
        setattr(dt_util, "now", lambda: now)
        setattr(
            dt_util,
            "parse_datetime",
            lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
        )
        setattr(util, "dt", dt_util)

        return {
            "voluptuous": voluptuous,
            "homeassistant": homeassistant,
            "homeassistant.const": const,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.config_validation": config_validation,
            "homeassistant.util": util,
            "homeassistant.util.dt": dt_util,
        }

    def test_dated_service_appends_normalized_completion_and_preserves_mark_done(self) -> None:
        now = datetime(2026, 7, 26, 14, 45, tzinfo=timezone.utc)
        manager = _Manager()
        services = _Services()
        hass = SimpleNamespace(services=services, data={DOMAIN: {DATA_MANAGER: manager}})
        context = object()

        with patch.dict(sys.modules, self._modules(now)):
            _register_services(hass)
            record = services.handlers[SERVICE_RECORD_COMPLETION]
            mark_done = services.handlers[SERVICE_MARK_DONE]
            asyncio.run(record(SimpleNamespace(
                data={
                    "entity_id": ["sensor.time_since_that_scoop_cat_litter"],
                    "completed_at": "2026-07-20T10:30:00-04:00",
                },
                context=context,
            )))
            asyncio.run(mark_done(SimpleNamespace(
                data={"chore_id": "scoop_cat_litter"},
                context=context,
            )))

        record_schema = services.schemas[SERVICE_RECORD_COMPLETION]
        self.assertIsInstance(record_schema, dict)
        assert isinstance(record_schema, dict)
        self.assertIn("completed_at", record_schema)
        self.assertEqual(manager.calls[0][0:3], (
            "scoop_cat_litter",
            context,
            SOURCE_RECORDED_COMPLETION,
        ))
        completed_at = manager.calls[0][3]
        assert completed_at is not None
        self.assertEqual(completed_at.isoformat(), "2026-07-20T10:30:00-04:00")
        self.assertEqual(manager.calls[1], ("scoop_cat_litter", context, "service", None))

    def test_dated_service_rejects_future_completion(self) -> None:
        now = datetime(2026, 7, 26, 14, 45, tzinfo=timezone.utc)
        manager = _Manager()
        services = _Services()
        hass = SimpleNamespace(services=services, data={DOMAIN: {DATA_MANAGER: manager}})

        with patch.dict(sys.modules, self._modules(now)):
            _register_services(hass)
            record = services.handlers[SERVICE_RECORD_COMPLETION]
            with self.assertRaisesRegex(_Invalid, "not in the future"):
                asyncio.run(record(SimpleNamespace(
                    data={"chore_id": "vacuum", "completed_at": "2026-07-27T10:30:00Z"},
                    context=None,
                )))

        self.assertEqual(manager.calls, [])


if __name__ == "__main__":
    unittest.main()
