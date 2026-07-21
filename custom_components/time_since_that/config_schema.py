"""Temporary no-op YAML compatibility schema for the clean v1 reset."""

from __future__ import annotations

import voluptuous as vol

from .const import DOMAIN

# Accept an existing root so the reset release starts cleanly, but do not parse
# or instantiate YAML chores. UI config entries are the only runtime source.
CONFIG_SCHEMA = vol.Schema(
    {vol.Optional(DOMAIN): object},
    extra=vol.ALLOW_EXTRA,
)
