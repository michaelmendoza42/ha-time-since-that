# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import asyncio
import importlib
import sys
from types import ModuleType, SimpleNamespace
from typing import Any
import unittest
from unittest.mock import AsyncMock, patch


class _OptionsFlow:
    def async_show_menu(self, *, step_id: str, menu_options: list[str]) -> dict[str, Any]:
        return {"type": "menu", "step_id": step_id, "menu_options": menu_options}

    def async_show_form(self, *, step_id: str, data_schema: Any, errors: Any = None) -> dict[str, Any]:
        return {"type": "form", "step_id": step_id, "errors": errors or {}}

    def async_create_entry(self, *, data: dict[str, Any]) -> dict[str, Any]:
        return {"type": "create_entry", "data": data}

    def async_abort(self, *, reason: str) -> dict[str, Any]:
        return {"type": "abort", "reason": reason}


class _ConfigFlow:
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__()


def _modules() -> dict[str, ModuleType]:
    voluptuous = ModuleType("voluptuous")
    setattr(voluptuous, "Schema", lambda schema: schema)
    setattr(voluptuous, "Required", lambda key, default=None: key)
    setattr(voluptuous, "Optional", lambda key, default=None: key)
    setattr(voluptuous, "In", lambda options: options)

    homeassistant = ModuleType("homeassistant")
    config_entries = ModuleType("homeassistant.config_entries")
    setattr(config_entries, "ConfigFlow", _ConfigFlow)
    setattr(config_entries, "OptionsFlow", _OptionsFlow)
    setattr(config_entries, "ConfigEntry", object)
    setattr(config_entries, "FlowResult", dict)
    setattr(homeassistant, "config_entries", config_entries)
    core = ModuleType("homeassistant.core")
    setattr(core, "HomeAssistant", object)
    setattr(core, "callback", lambda func: func)
    helpers = ModuleType("homeassistant.helpers")
    selector = ModuleType("homeassistant.helpers.selector")
    setattr(selector, "DateTimeSelector", lambda: "datetime")
    setattr(helpers, "selector", selector)
    util = ModuleType("homeassistant.util")
    dt_util = ModuleType("homeassistant.util.dt")
    setattr(util, "dt", dt_util)

    return {
        "voluptuous": voluptuous,
        "homeassistant": homeassistant,
        "homeassistant.config_entries": config_entries,
        "homeassistant.core": core,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.selector": selector,
        "homeassistant.util": util,
        "homeassistant.util.dt": dt_util,
    }


CHORES = [
    {"id": "scoop_cat_litter", "name": "Scoop cat litter", "tags": ["pets"]},
    {"id": "vacuum", "name": "Vacuum", "tags": []},
]


class TestOptionsFlow(unittest.TestCase):
    """Drive the options flow the way Home Assistant does.

    Home Assistant routes a menu choice or form submission to
    ``async_step_<step_id>``, so every shown step must have that handler.
    """

    def setUp(self) -> None:
        patcher = patch.dict(sys.modules, _modules())
        patcher.start()
        self.addCleanup(patcher.stop)
        sys.modules.pop("custom_components.time_since_that.config_flow", None)
        self.config_flow = importlib.import_module("custom_components.time_since_that.config_flow")
        self.addCleanup(sys.modules.pop, "custom_components.time_since_that.config_flow", None)

    def _flow(self) -> Any:
        flow = self.config_flow.TimeSinceThatOptionsFlow()
        flow.config_entry = SimpleNamespace(
            entry_id="entry",
            data={"chores": CHORES},
            options={},
        )
        flow.hass = SimpleNamespace(data={})
        return flow

    def _step(self, flow: Any, step_id: str, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        handler = getattr(flow, f"async_step_{step_id}", None)
        self.assertIsNotNone(handler, f"no handler for step '{step_id}'")
        return asyncio.run(handler(user_input))

    def test_menu_offers_add_edit_remove_with_handlers(self) -> None:
        flow = self._flow()
        menu = self._step(flow, "init")

        self.assertEqual(menu["menu_options"], ["add", "edit_select", "remove_select"])
        for option in menu["menu_options"]:
            self.assertTrue(hasattr(flow, f"async_step_{option}"), option)

    def test_edit_selects_chore_then_saves_changes(self) -> None:
        flow = self._flow()
        picker = self._step(flow, "edit_select")
        self.assertEqual(picker["type"], "form")

        form = self._step(flow, picker["step_id"], {"selected_chore": "vacuum"})
        self.assertEqual((form["type"], form["step_id"]), ("form", "edit"))

        result = self._step(flow, form["step_id"], {
            "name": "Vacuum downstairs",
            "category": "",
            "area": "",
            "tags": "floors",
            "recommended_value": "",
            "recommended_unit": "days",
            "unit": "days",
            "rounding": "floor",
        })

        self.assertEqual(result["type"], "create_entry")
        chores = result["data"]["chores"]
        self.assertEqual([chore["id"] for chore in chores], ["scoop_cat_litter", "vacuum"])
        self.assertEqual(chores[1]["name"], "Vacuum downstairs")
        self.assertEqual(chores[1]["tags"], ["floors"])

    def test_remove_selects_chore_then_requires_confirmation(self) -> None:
        flow = self._flow()
        picker = self._step(flow, "remove_select")
        confirm = self._step(flow, picker["step_id"], {"selected_chore": "vacuum"})
        self.assertEqual((confirm["type"], confirm["step_id"]), ("form", "remove"))

        declined = self._step(flow, confirm["step_id"], {"confirm": False})
        self.assertEqual(declined["errors"], {"base": "removal_not_confirmed"})

        with patch.object(
            self.config_flow, "_async_remove_chore_entities", new_callable=AsyncMock
        ) as remove_entities:
            result = self._step(flow, confirm["step_id"], {"confirm": True})

        self.assertEqual(result["type"], "create_entry")
        self.assertEqual([chore["id"] for chore in result["data"]["chores"]], ["scoop_cat_litter"])
        remove_entities.assert_awaited_once_with(flow.hass, "entry", "vacuum")


if __name__ == "__main__":
    unittest.main()
