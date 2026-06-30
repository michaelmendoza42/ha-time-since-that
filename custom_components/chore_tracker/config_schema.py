# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""YAML configuration schema for Chore Tracker."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.const import CONF_ID, CONF_NAME
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_AREA,
    CONF_CATEGORY,
    CONF_CHORES,
    CONF_ELAPSED_DISPLAY,
    CONF_RECOMMENDED_EVERY,
    CONF_ROUNDING,
    CONF_UNIT,
    CONF_VALUE,
    DEFAULT_DISPLAY_ROUNDING,
    DEFAULT_DISPLAY_UNIT,
    DOMAIN,
    ROUNDING_MODES,
    UNITS,
)
from .model import ChoreConfigError, definition_from_dict, validate_chore_definitions

INTERVAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VALUE): vol.All(vol.Coerce(float), vol.Range(min=0, min_included=False)),
        vol.Required(CONF_UNIT): vol.In(UNITS),
    }
)

DISPLAY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_UNIT, default=DEFAULT_DISPLAY_UNIT): vol.In(UNITS),
        vol.Optional(CONF_ROUNDING, default=DEFAULT_DISPLAY_ROUNDING): vol.In(ROUNDING_MODES),
    }
)

CHORE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ID): str,
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_CATEGORY): cv.string,
        vol.Optional(CONF_AREA): cv.string,
        vol.Optional(CONF_RECOMMENDED_EVERY): INTERVAL_SCHEMA,
        vol.Optional(CONF_ELAPSED_DISPLAY, default={}): DISPLAY_SCHEMA,
    }
)


def validate_chores(value: list[dict]) -> list[dict]:
    """Validate cross-chore invariants such as unique IDs."""
    try:
        validate_chore_definitions([definition_from_dict(item) for item in value])
    except ChoreConfigError as err:
        raise vol.Invalid(str(err)) from err
    return value


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_CHORES): vol.All(
                    cv.ensure_list,
                    [CHORE_SCHEMA],
                    vol.Length(min=1),
                    validate_chores,
                )
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)
