"""Config and options flows for UI-managed Time Since That chores."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AREA,
    CONF_CATEGORY,
    CONF_CHORES,
    CONF_ELAPSED_DISPLAY,
    CONF_LAST_COMPLETED,
    CONF_NAME,
    CONF_RECOMMENDED_EVERY,
    CONF_ROUNDING,
    CONF_TAGS,
    CONF_UNIT,
    CONF_VALUE,
    DATA_MANAGER,
    DEFAULT_DISPLAY_ROUNDING,
    DEFAULT_DISPLAY_UNIT,
    DOMAIN,
    ROUNDING_MODES,
    SOURCE_INITIAL,
    UNITS,
)
from .model import ChoreConfigError, definition_from_dict, definition_to_dict

CONF_RECOMMENDED_VALUE = "recommended_value"
CONF_RECOMMENDED_UNIT = "recommended_unit"
CONF_SELECTED_CHORE = "selected_chore"
MENU_ADD = "add"
MENU_EDIT = "edit"
MENU_ADJUST = "adjust_last_completed"
MENU_REMOVE = "remove"


class TimeSinceThatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle first-time setup by creating the household and first chore."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Create the singleton entry with its first chore."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                chore = _chore_from_form(user_input, existing_ids=set())
                initial = _initial_datetime(user_input.get(CONF_LAST_COMPLETED))
            except ChoreConfigError:
                errors["base"] = "invalid_chore"
            except ValueError:
                errors[CONF_LAST_COMPLETED] = "invalid_last_completed"
            else:
                stored_chore = definition_to_dict(chore)
                if initial is not None:
                    stored_chore[CONF_LAST_COMPLETED] = initial.isoformat()
                return self.async_create_entry(
                    title="Time Since That",
                    data={},
                    options={CONF_CHORES: [stored_chore]},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_chore_form_schema(include_initial=True),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> config_entries.OptionsFlow:
        """Return the singleton chore-management options flow."""
        return TimeSinceThatOptionsFlow()


class TimeSinceThatOptionsFlow(config_entries.OptionsFlow):
    """Manage the chore list stored in the singleton entry options.

    This documented base class ensures Home Assistant recognizes the options
    flow and renders the integration's Configure action.
    """

    def __init__(self) -> None:
        """Initialize selection state for multi-step chore actions."""
        super().__init__()
        self._selected_chore_id: str | None = None

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Show chores-management actions."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[MENU_ADD, MENU_EDIT, MENU_ADJUST, MENU_REMOVE],
        )

    async def async_step_add(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Add one UI-managed chore."""
        errors: dict[str, str] = {}
        if user_input is not None:
            chores = _stored_chores(self.config_entry.options)
            try:
                chore = _chore_from_form(user_input, {item["id"] for item in chores})
                initial = _initial_datetime(user_input.get(CONF_LAST_COMPLETED))
            except ChoreConfigError:
                errors["base"] = "invalid_chore"
            except ValueError:
                errors[CONF_LAST_COMPLETED] = "invalid_last_completed"
            else:
                stored_chore = definition_to_dict(chore)
                if initial is not None:
                    stored_chore[CONF_LAST_COMPLETED] = initial.isoformat()
                chores.append(stored_chore)
                return self.async_create_entry(data={**self.config_entry.options, CONF_CHORES: chores})

        return self.async_show_form(
            step_id=MENU_ADD,
            data_schema=_chore_form_schema(include_initial=True),
            errors=errors,
        )

    async def async_step_edit(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Select a chore to edit or show its edit fields."""
        if self._selected_chore_id is None:
            if user_input is not None:
                self._selected_chore_id = str(user_input[CONF_SELECTED_CHORE])
                return await self.async_step_edit()
            return self.async_show_form(
                step_id="edit_select",
                data_schema=_chore_selector_schema(_stored_chores(self.config_entry.options)),
            )

        chores = _stored_chores(self.config_entry.options)
        current = _find_chore(chores, self._selected_chore_id)
        if current is None:
            self._selected_chore_id = None
            return self.async_abort(reason="chore_not_found")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                replacement = _chore_from_form(
                    user_input,
                    {item["id"] for item in chores if item["id"] != current["id"]},
                    fixed_id=current["id"],
                )
            except ChoreConfigError:
                errors["base"] = "invalid_chore"
            else:
                replacement_data = definition_to_dict(replacement)
                if current.get(CONF_LAST_COMPLETED):
                    replacement_data[CONF_LAST_COMPLETED] = current[CONF_LAST_COMPLETED]
                _replace_chore(chores, current["id"], replacement_data)
                return self.async_create_entry(data={**self.config_entry.options, CONF_CHORES: chores})

        return self.async_show_form(
            step_id=MENU_EDIT,
            data_schema=_chore_form_schema(current, include_initial=False),
            errors=errors,
        )

    async def async_step_adjust_last_completed(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Select a chore then correct its latest completion timestamp."""
        if self._selected_chore_id is None:
            if user_input is not None:
                self._selected_chore_id = str(user_input[CONF_SELECTED_CHORE])
                return await self.async_step_adjust_last_completed()
            return self.async_show_form(
                step_id="adjust_select",
                data_schema=_chore_selector_schema(_stored_chores(self.config_entry.options)),
            )

        manager = self.hass.data.get(DOMAIN, {}).get(DATA_MANAGER)
        if manager is None:
            return self.async_abort(reason="not_configured")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                corrected = _required_past_datetime(user_input[CONF_LAST_COMPLETED])
                await manager.async_adjust_last_completed(self._selected_chore_id, corrected)
            except ValueError:
                errors[CONF_LAST_COMPLETED] = "invalid_last_completed"
            else:
                return self.async_create_entry(data=dict(self.config_entry.options))

        return self.async_show_form(
            step_id=MENU_ADJUST,
            data_schema=vol.Schema(
                {vol.Required(CONF_LAST_COMPLETED): selector.DateTimeSelector()}
            ),
            errors=errors,
        )

    async def async_step_remove(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.FlowResult:
        """Select and confirm removal of one chore definition."""
        if self._selected_chore_id is None:
            if user_input is not None:
                self._selected_chore_id = str(user_input[CONF_SELECTED_CHORE])
                return await self.async_step_remove()
            return self.async_show_form(
                step_id="remove_select",
                data_schema=_chore_selector_schema(_stored_chores(self.config_entry.options)),
            )

        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input["confirm"]:
                errors["base"] = "removal_not_confirmed"
            else:
                await _async_remove_chore_entities(
                    self.hass,
                    self.config_entry.entry_id,
                    self._selected_chore_id,
                )
                chores = [
                    chore
                    for chore in _stored_chores(self.config_entry.options)
                    if chore["id"] != self._selected_chore_id
                ]
                return self.async_create_entry(data={**self.config_entry.options, CONF_CHORES: chores})

        return self.async_show_form(
            step_id=MENU_REMOVE,
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
            errors=errors,
        )


def _chore_form_schema(
    current: dict[str, Any] | None = None,
    *,
    include_initial: bool,
) -> vol.Schema:
    """Build reusable add/edit form schema with JSON-serializable results."""
    current = current or {}
    recommended = current.get(CONF_RECOMMENDED_EVERY) or {}
    display = current.get(CONF_ELAPSED_DISPLAY) or {}
    schema: dict[Any, Any] = {
        vol.Required(CONF_NAME, default=current.get(CONF_NAME, "")): str,
        vol.Optional(CONF_CATEGORY, default=current.get(CONF_CATEGORY, "")): str,
        vol.Optional(CONF_AREA, default=current.get(CONF_AREA, "")): str,
        vol.Optional(CONF_TAGS, default=", ".join(current.get(CONF_TAGS, []))): str,
        vol.Optional(
            CONF_RECOMMENDED_VALUE,
            default=str(recommended.get(CONF_VALUE, "")),
        ): str,
        vol.Required(
            CONF_RECOMMENDED_UNIT,
            default=recommended.get(CONF_UNIT, "days"),
        ): vol.In(UNITS),
        vol.Required(
            CONF_UNIT,
            default=display.get(CONF_UNIT, DEFAULT_DISPLAY_UNIT),
        ): vol.In(UNITS),
        vol.Required(
            CONF_ROUNDING,
            default=display.get(CONF_ROUNDING, DEFAULT_DISPLAY_ROUNDING),
        ): vol.In(ROUNDING_MODES),
    }
    if include_initial:
        schema[vol.Optional(CONF_LAST_COMPLETED)] = selector.DateTimeSelector()
    return vol.Schema(schema)


def _chore_selector_schema(chores: list[dict[str, Any]]) -> vol.Schema:
    """Select one existing chore by stable UI identity."""
    options = {chore["id"]: chore["name"] for chore in chores}
    return vol.Schema({vol.Required(CONF_SELECTED_CHORE): vol.In(options)})


def _chore_from_form(
    user_input: dict[str, Any],
    existing_ids: set[str],
    *,
    fixed_id: str | None = None,
):
    """Normalize one flow form into a validated definition."""
    name = str(user_input[CONF_NAME]).strip()
    chore_id = fixed_id or _new_chore_id(name, existing_ids)
    tags = _parse_tags(user_input.get(CONF_TAGS, ""))
    data: dict[str, Any] = {
        "id": chore_id,
        "name": name,
        "tags": tags,
        "elapsed_display": {
            "unit": user_input[CONF_UNIT],
            "rounding": user_input[CONF_ROUNDING],
        },
    }
    if str(user_input.get(CONF_CATEGORY, "")).strip():
        data[CONF_CATEGORY] = str(user_input[CONF_CATEGORY]).strip()
    if str(user_input.get(CONF_AREA, "")).strip():
        data[CONF_AREA] = str(user_input[CONF_AREA]).strip()

    raw_cadence = str(user_input.get(CONF_RECOMMENDED_VALUE, "")).strip()
    if raw_cadence:
        try:
            value = float(raw_cadence)
        except ValueError as err:
            raise ChoreConfigError("recommended cadence must be numeric.") from err
        data[CONF_RECOMMENDED_EVERY] = {
            CONF_VALUE: value,
            CONF_UNIT: user_input[CONF_RECOMMENDED_UNIT],
        }
    return definition_from_dict(data)


def _parse_tags(raw_tags: Any) -> list[str]:
    """Parse comma-separated form input to normalized tag list."""
    if not str(raw_tags).strip():
        return []
    tags = [tag.strip().lower() for tag in str(raw_tags).split(",")]
    if not all(tags) or len(set(tags)) != len(tags):
        raise ChoreConfigError("tags must be unique non-empty values.")
    return tags


def _new_chore_id(name: str, existing_ids: set[str]) -> str:
    """Generate a stable slug and reject ambiguous duplicate identities."""
    slug = re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", name.lower())).strip("_")
    if not slug or not slug[0].isalpha():
        raise ChoreConfigError("name must begin with a letter.")
    if slug in existing_ids:
        raise ChoreConfigError("a chore with this name already exists.")
    return slug


def _initial_datetime(value: Any) -> datetime | None:
    """Return an optional valid past initial completion timestamp."""
    if value in (None, ""):
        return None
    return _required_past_datetime(value)


def _required_past_datetime(value: Any) -> datetime:
    """Parse a date-time selector result and reject future timestamps."""
    parsed = dt_util.parse_datetime(str(value))
    if parsed is None:
        raise ValueError("invalid datetime")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    if parsed > dt_util.now():
        raise ValueError("future datetime")
    return parsed


def _stored_chores(options: dict[str, Any]) -> list[dict[str, Any]]:
    """Copy JSON chore definitions before a flow mutation."""
    return deepcopy(list(options.get(CONF_CHORES, [])))


def _find_chore(chores: list[dict[str, Any]], chore_id: str) -> dict[str, Any] | None:
    """Find a stored chore by immutable ID."""
    return next((chore for chore in chores if chore["id"] == chore_id), None)


async def _async_remove_chore_entities(
    hass: HomeAssistant,
    entry_id: str,
    chore_id: str,
) -> None:
    """Remove stale registry rows when a UI chore is removed."""
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    unique_ids = {
        f"time_since_that_{chore_id}",
        f"time_since_that_{chore_id}_mark_done",
    }
    for entry in er.async_entries_for_config_entry(registry, entry_id):
        if entry.unique_id in unique_ids:
            registry.async_remove(entry.entity_id)


def _replace_chore(
    chores: list[dict[str, Any]],
    chore_id: str,
    replacement: dict[str, Any],
) -> None:
    """Replace one stored chore without changing list order."""
    for index, chore in enumerate(chores):
        if chore["id"] == chore_id:
            chores[index] = replacement
            return
    raise ValueError(f"Unknown chore '{chore_id}'.")
