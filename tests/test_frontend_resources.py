"""Regression tests for bundled Lovelace module registration."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import unittest

from custom_components.time_since_that.frontend_resources import (
    async_reconcile_module_resource,
)

URL = "/time_since_that/time-since-that-card.js?v=1.0.4"
PATH = "/time_since_that/time-since-that-card.js"


class FakeStorageResources:
    def __init__(self, items=None) -> None:
        self.items = list(items or [])
        self.calls: list[tuple] = []
        self.loaded = False

    async def async_get_info(self) -> None:
        self.calls.append(("load",))
        self.loaded = True

    def async_items(self):
        assert self.loaded
        return self.items

    async def async_create_item(self, data):
        self.calls.append(("create", data))

    async def async_update_item(self, item_id, data):
        self.calls.append(("update", item_id, data))


class FakeYamlResources:
    def async_items(self):
        return []


class FrontendResourceTests(unittest.TestCase):
    def reconcile(self, resources):
        return asyncio.run(
            async_reconcile_module_resource(resources, URL, logging.getLogger(__name__))
        )

    def test_creates_a_module_resource_after_loading_storage(self) -> None:
        resources = FakeStorageResources()

        self.assertEqual(self.reconcile(resources), "created")
        self.assertEqual(
            resources.calls,
            [("load",), ("create", {"res_type": "module", "url": URL})],
        )

    def test_current_resource_is_idempotent(self) -> None:
        resources = FakeStorageResources([{"id": "one", "url": URL, "type": "module"}])

        self.assertEqual(self.reconcile(resources), "current")
        self.assertEqual(resources.calls, [("load",)])

    def test_stale_version_updates_in_place(self) -> None:
        resources = FakeStorageResources(
            [{"id": "one", "url": f"{PATH}?v=1.0.3", "type": "module"}]
        )

        self.assertEqual(self.reconcile(resources), "updated")
        self.assertEqual(
            resources.calls,
            [("load",), ("update", "one", {"res_type": "module", "url": URL})],
        )

    def test_wrong_type_updates_in_place(self) -> None:
        resources = FakeStorageResources([{"id": "one", "url": URL, "type": "js"}])

        self.assertEqual(self.reconcile(resources), "updated")
        self.assertEqual(
            resources.calls[-1],
            ("update", "one", {"res_type": "module", "url": URL}),
        )

    def test_unrelated_resources_are_not_changed(self) -> None:
        resources = FakeStorageResources(
            [{"id": "other", "url": "/local/other-card.js", "type": "module"}]
        )

        self.assertEqual(self.reconcile(resources), "created")
        self.assertEqual(resources.calls[-1][0], "create")

    def test_read_only_resources_are_not_mutated(self) -> None:
        self.assertEqual(self.reconcile(FakeYamlResources()), "read_only")

    def test_resource_url_version_matches_manifest(self) -> None:
        manifest_path = Path(__file__).parents[1] / "custom_components/time_since_that/manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError) as err:
            self.fail(f"Could not read manifest version: {err}")
        self.assertTrue(URL.endswith(f"?v={manifest['version']}"))


if __name__ == "__main__":
    unittest.main()
