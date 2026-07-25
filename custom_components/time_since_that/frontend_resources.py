"""Persistent Lovelace resource reconciliation for the bundled card."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit


async def async_reconcile_module_resource(
    resources: Any,
    desired_url: str,
    logger: logging.Logger,
) -> str:
    """Create or normalize this integration's storage-backed card resource.

    Returns a stable outcome for setup logging. A resource collection without
    create/update methods is read-only (for example, YAML resources), so the
    caller can use its non-persistent fallback instead.
    """
    if not all(
        callable(getattr(resources, method, None))
        for method in ("async_create_item", "async_update_item")
    ):
        return "read_only"

    get_info = getattr(resources, "async_get_info", None)
    if callable(get_info):
        load_result = get_info()
        if inspect.isawaitable(load_result):
            await load_result

    items = list(resources.async_items())
    resource_path = urlsplit(desired_url).path
    owned = [
        item
        for item in items
        if urlsplit(str(item.get("url", ""))).path == resource_path
    ]
    if not owned:
        await resources.async_create_item({"res_type": "module", "url": desired_url})
        return "created"

    canonical = owned[0]
    if len(owned) > 1:
        logger.warning(
            "Found %s Time Since That Lovelace resources for %s; leaving "
            "duplicates untouched until explicitly cleaned up.",
            len(owned),
            resource_path,
        )

    current_type = canonical.get("type", canonical.get("res_type"))
    if canonical.get("url") == desired_url and current_type == "module":
        return "current" if len(owned) == 1 else "duplicate_current"

    await resources.async_update_item(
        canonical["id"],
        {"res_type": "module", "url": desired_url},
    )
    return "updated" if len(owned) == 1 else "duplicate_updated"


def lovelace_resources(hass: Any) -> Any | None:
    """Return the resources collection across supported Lovelace data shapes."""
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        return None
    if isinstance(lovelace, Mapping):
        return lovelace.get("resources")
    return getattr(lovelace, "resources", None)
