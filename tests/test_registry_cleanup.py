# Copyright (c) 2025, Renaud Allard <renaud@allard.it>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

"""Tests for orphaned entity and device cleanup."""

import subprocess
import sys
from unittest.mock import MagicMock, patch

from custom_components.dnsdist.const import (
    ATTR_BACKENDS,
    ATTR_DYNAMIC_RULES,
    ATTR_FILTERING_RULES,
    DOMAIN,
)
from custom_components.dnsdist.utils import (
    async_prune_orphaned_devices,
    async_prune_orphaned_entities,
    async_register_slug_platform,
    async_remove_retired_entities,
    device_identifier,
    filtering_rule_aliases,
    slugify_rule,
    split_dynamic_unique_id,
)

ENTRY_ID = "entry-1"


class FakeRegistryEntry:
    """Stand-in for a Home Assistant entity registry entry."""

    def __init__(self, entity_id, unique_id):
        self.entity_id = entity_id
        self.unique_id = unique_id
        self.domain = entity_id.split(".")[0]
        self.platform = DOMAIN


class FakeEntityRegistry:
    """Minimal entity registry recording what was removed or renamed."""

    def __init__(self, entries=()):
        self.entries = list(entries)
        self.removed = []
        self.renamed = {}

    def async_get_entity_id(self, domain, platform, unique_id):
        for entry in self.entries:
            if entry.unique_id == unique_id and entry.domain == domain and entry.platform == platform:
                return entry.entity_id
        return None

    def async_remove(self, entity_id):
        self.removed.append(entity_id)
        self.entries = [e for e in self.entries if e.entity_id != entity_id]

    def async_update_entity(self, entity_id, new_unique_id=None):
        self.renamed[entity_id] = new_unique_id
        for entry in self.entries:
            if entry.entity_id == entity_id:
                entry.unique_id = new_unique_id

    def async_get(self, entity_id):
        for entry in self.entries:
            if entry.entity_id == entity_id:
                return entry
        return None


def prune_entities(entries, data):
    """Run the entity pruner against a fake registry and return it."""
    registry = FakeEntityRegistry(entries)
    with patch("custom_components.dnsdist.utils.er") as er_mock:
        er_mock.async_get.return_value = registry
        er_mock.async_entries_for_config_entry.side_effect = lambda reg, entry_id: list(reg.entries)
        async_prune_orphaned_entities(MagicMock(), ENTRY_ID, data)
    return registry


# ---------------------------------------------------------------------------
# slugify_rule determinism
# ---------------------------------------------------------------------------


class TestSlugifyDeterminism:
    def test_fallback_is_stable_across_processes(self):
        """A hash based slug would change with every PYTHONHASHSEED."""
        code = "from custom_components.dnsdist.utils import slugify_rule; print(slugify_rule('!!!'))"
        slugs = set()
        for seed in ("0", "1", "2"):
            out = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                check=True,
                env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            )
            slugs.add(out.stdout.strip())
        assert len(slugs) == 1
        assert slugs.pop() == slugify_rule("!!!")

    def test_fallback_distinguishes_different_values(self):
        assert slugify_rule("!!!") != slugify_rule("???")

    def test_falsy_values_do_not_collide(self):
        assert slugify_rule(0) != slugify_rule("")


# ---------------------------------------------------------------------------
# split_dynamic_unique_id
# ---------------------------------------------------------------------------


class TestSplitDynamicUniqueId:
    def test_recognises_every_dynamic_prefix(self):
        cases = {
            "filtering_rule:block-ads": ("filtering_rule:", "block-ads"),
            "dynamic_rule:192-0-2-1-32": ("dynamic_rule:", "192-0-2-1-32"),
            "backend:resolver": ("backend:", "resolver"),
            "backend_queries:resolver": ("backend_queries:", "resolver"),
        }
        for tail, expected in cases.items():
            assert split_dynamic_unique_id(f"{ENTRY_ID}:{tail}", ENTRY_ID) == expected

    def test_fixed_entities_are_not_dynamic(self):
        for tail in ("queries", "security_status", "btn_clear_cache"):
            assert split_dynamic_unique_id(f"{ENTRY_ID}:{tail}", ENTRY_ID) == (None, "")

    def test_other_entry_is_ignored(self):
        assert split_dynamic_unique_id("other:dynamic_rule:x", ENTRY_ID) == (None, "")


# ---------------------------------------------------------------------------
# filtering_rule_aliases
# ---------------------------------------------------------------------------


class TestFilteringRuleAliases:
    def test_maps_uuid_onto_the_name_slug(self):
        data = {
            ATTR_FILTERING_RULES: {
                "block-ads": {"name": "Block Ads", "uuid": "dead-beef", "id": 3},
            }
        }
        assert filtering_rule_aliases(data) == {"dead-beef": "block-ads"}

    def test_chain_position_is_not_aliased(self):
        # "id" is the rule's position, which points at whichever rule sits
        # there now rather than the one the orphaned entity belonged to
        data = {ATTR_FILTERING_RULES: {"block-ads": {"name": "Block Ads", "uuid": "dead-beef", "id": 3}}}
        assert "3" not in filtering_rule_aliases(data)

    def test_missing_rules_give_no_aliases(self):
        assert filtering_rule_aliases({}) == {}
        assert filtering_rule_aliases({ATTR_FILTERING_RULES: None}) == {}

    def test_absent_uuid_is_skipped(self):
        data = {ATTR_FILTERING_RULES: {"block-ads": {"name": "Block Ads", "uuid": None, "id": 3}}}
        assert filtering_rule_aliases(data) == {}


# ---------------------------------------------------------------------------
# async_prune_orphaned_entities
# ---------------------------------------------------------------------------


class TestPruneOrphanedEntities:
    def test_removes_expired_dynblock(self):
        entries = [
            FakeRegistryEntry("sensor.gone", f"{ENTRY_ID}:dynamic_rule:10-0-0-1-32"),
            FakeRegistryEntry("sensor.live", f"{ENTRY_ID}:dynamic_rule:10-0-0-2-32"),
        ]
        registry = prune_entities(entries, {ATTR_DYNAMIC_RULES: {"10-0-0-2-32": {}}})
        assert registry.removed == ["sensor.gone"]

    def test_removes_deleted_backend_from_both_platforms(self):
        entries = [
            FakeRegistryEntry("sensor.q", f"{ENTRY_ID}:backend_queries:old"),
            FakeRegistryEntry("binary_sensor.h", f"{ENTRY_ID}:backend:old"),
        ]
        registry = prune_entities(entries, {ATTR_BACKENDS: {"new": {}}})
        assert sorted(registry.removed) == ["binary_sensor.h", "sensor.q"]

    def test_keeps_fixed_entities(self):
        entries = [
            FakeRegistryEntry("sensor.queries", f"{ENTRY_ID}:queries"),
            FakeRegistryEntry("button.clear", f"{ENTRY_ID}:btn_clear_cache"),
        ]
        registry = prune_entities(entries, {ATTR_BACKENDS: {}})
        assert registry.removed == []

    def test_missing_data_key_removes_nothing(self):
        """An unreadable endpoint must not be mistaken for an empty one."""
        entries = [FakeRegistryEntry("sensor.gone", f"{ENTRY_ID}:dynamic_rule:10-0-0-1-32")]
        registry = prune_entities(entries, {ATTR_BACKENDS: {}})
        assert registry.removed == []

    def test_non_dict_data_removes_nothing(self):
        entries = [FakeRegistryEntry("sensor.gone", f"{ENTRY_ID}:dynamic_rule:x")]
        registry = prune_entities(entries, None)
        assert registry.removed == []

    def test_legacy_uuid_slug_is_migrated_not_removed(self):
        entries = [FakeRegistryEntry("sensor.rule", f"{ENTRY_ID}:filtering_rule:dead-beef")]
        data = {ATTR_FILTERING_RULES: {"block-ads": {"name": "Block Ads", "uuid": "dead-beef", "id": 3}}}
        registry = prune_entities(entries, data)
        assert registry.removed == []
        assert registry.renamed == {"sensor.rule": f"{ENTRY_ID}:filtering_rule:block-ads"}

    def test_legacy_slug_removed_when_target_already_exists(self):
        entries = [
            FakeRegistryEntry("sensor.rule_old", f"{ENTRY_ID}:filtering_rule:dead-beef"),
            FakeRegistryEntry("sensor.rule", f"{ENTRY_ID}:filtering_rule:block-ads"),
        ]
        data = {ATTR_FILTERING_RULES: {"block-ads": {"name": "Block Ads", "uuid": "dead-beef", "id": 3}}}
        registry = prune_entities(entries, data)
        assert registry.removed == ["sensor.rule_old"]
        assert registry.renamed == {}

    def test_unmappable_filtering_rule_is_removed(self):
        entries = [FakeRegistryEntry("sensor.rule", f"{ENTRY_ID}:filtering_rule:long-gone")]
        data = {ATTR_FILTERING_RULES: {"block-ads": {"name": "Block Ads", "uuid": "abc", "id": 1}}}
        registry = prune_entities(entries, data)
        assert registry.removed == ["sensor.rule"]


# ---------------------------------------------------------------------------
# async_remove_retired_entities
# ---------------------------------------------------------------------------


def remove_retired(entries):
    """Run the retired entity sweep against a fake registry and return it."""
    registry = FakeEntityRegistry(entries)
    with patch("custom_components.dnsdist.utils.er") as er_mock:
        er_mock.async_get.return_value = registry
        er_mock.async_entries_for_config_entry.side_effect = lambda reg, entry_id: list(reg.entries)
        async_remove_retired_entities(MagicMock(), ENTRY_ID)
    return registry


class TestRemoveRetiredEntities:
    def test_removes_the_backend_switch(self):
        entries = [FakeRegistryEntry("switch.s", f"{ENTRY_ID}:backend_switch:resolver")]
        assert remove_retired(entries).removed == ["switch.s"]

    def test_keeps_the_live_backend_entities(self):
        entries = [
            FakeRegistryEntry("sensor.q", f"{ENTRY_ID}:backend_queries:resolver"),
            FakeRegistryEntry("binary_sensor.h", f"{ENTRY_ID}:backend:resolver"),
            FakeRegistryEntry("button.clear", f"{ENTRY_ID}:btn_clear_cache"),
        ]
        assert remove_retired(entries).removed == []

    def test_other_entry_is_ignored(self):
        entries = [FakeRegistryEntry("switch.s", "other:backend_switch:resolver")]
        assert remove_retired(entries).removed == []


# ---------------------------------------------------------------------------
# async_prune_orphaned_devices
# ---------------------------------------------------------------------------


def make_device(device_id, identifier, entities, config_entries=None):
    device = MagicMock()
    device.id = device_id
    device.identifiers = {(DOMAIN, identifier)}
    device.config_entries = {ENTRY_ID} if config_entries is None else config_entries
    device.name = identifier
    device._entities = entities
    return device


def prune_devices(devices, identifier):
    removed = []
    dev_reg = MagicMock()
    dev_reg.async_remove_device.side_effect = removed.append
    lookup = {d.id: d._entities for d in devices}

    with (
        patch("custom_components.dnsdist.utils.dr") as dr_mock,
        patch("custom_components.dnsdist.utils.er") as er_mock,
    ):
        dr_mock.async_get.return_value = dev_reg
        dr_mock.async_entries_for_config_entry.return_value = devices
        er_mock.async_entries_for_device.side_effect = lambda reg, dev_id, **kw: lookup[dev_id]
        async_prune_orphaned_devices(MagicMock(), ENTRY_ID, identifier)

    return removed


class TestPruneOrphanedDevices:
    def test_removes_empty_device_from_a_previous_name(self):
        devices = [
            make_device("old", device_identifier("dns1", False), []),
            make_device("new", device_identifier("dns2", False), ["sensor.queries"]),
        ]
        assert prune_devices(devices, device_identifier("dns2", False)) == ["old"]

    def test_keeps_current_device_even_when_empty(self):
        devices = [make_device("cur", device_identifier("dns1", False), [])]
        assert prune_devices(devices, device_identifier("dns1", False)) == []

    def test_keeps_stale_device_that_still_holds_entities(self):
        devices = [make_device("old", device_identifier("dns1", False), ["sensor.queries"])]
        assert prune_devices(devices, device_identifier("dns2", False)) == []

    def test_keeps_device_shared_with_another_entry(self):
        devices = [make_device("old", device_identifier("dns1", False), [], {ENTRY_ID, "entry-2"})]
        assert prune_devices(devices, device_identifier("dns2", False)) == []

    def test_group_and_host_identifiers_differ(self):
        assert device_identifier("dns1", True) != device_identifier("dns1", False)


# ---------------------------------------------------------------------------
# async_register_slug_platform
# ---------------------------------------------------------------------------


class FakeEntity:
    def __init__(self, slug):
        self.slug = slug
        self.entity_id = f"sensor.{slug}"
        self.unique_id = slug


class TestRegisterSlugPlatform:
    def _setup(self, initial):
        coordinator = MagicMock()
        coordinator.data = {ATTR_BACKENDS: initial}
        registry = FakeEntityRegistry()
        added = []
        entry = MagicMock()
        with patch("custom_components.dnsdist.utils.er") as er_mock:
            er_mock.async_get.return_value = registry
            async_register_slug_platform(
                MagicMock(),
                entry,
                coordinator,
                added.extend,
                data_key=ATTR_BACKENDS,
                factory=FakeEntity,
            )
        sync = coordinator.async_add_listener.call_args[0][0]
        return coordinator, registry, added, sync

    def _resync(self, sync, registry):
        with patch("custom_components.dnsdist.utils.er") as er_mock:
            er_mock.async_get.return_value = registry
            sync()

    def test_adds_entities_for_current_slugs(self):
        _, _, added, _ = self._setup({"a": {}, "b": {}})
        assert sorted(e.slug for e in added) == ["a", "b"]

    def test_removes_entity_when_slug_disappears(self):
        coordinator, registry, added, sync = self._setup({"a": {}, "b": {}})
        registry.entries = [FakeRegistryEntry(e.entity_id, e.unique_id) for e in added]

        coordinator.data = {ATTR_BACKENDS: {"a": {}}}
        self._resync(sync, registry)

        assert registry.removed == ["sensor.b"]

    def test_entity_still_being_added_is_kept_for_later(self):
        """An entity with no entity_id yet has no hass to remove itself with."""
        coordinator, registry, added, sync = self._setup({"a": {}})
        added[0].entity_id = None

        coordinator.data = {ATTR_BACKENDS: {}}
        self._resync(sync, registry)
        assert registry.removed == []

        added[0].entity_id = "sensor.a"
        registry.entries = [FakeRegistryEntry("sensor.a", "a")]
        self._resync(sync, registry)
        assert registry.removed == ["sensor.a"]

    def test_does_not_add_duplicates_on_resync(self):
        coordinator, registry, added, sync = self._setup({"a": {}})
        self._resync(sync, registry)
        assert len(added) == 1

    def test_reappearing_slug_is_added_again(self):
        coordinator, registry, added, sync = self._setup({"a": {}})
        registry.entries = [FakeRegistryEntry(e.entity_id, e.unique_id) for e in added]

        coordinator.data = {ATTR_BACKENDS: {}}
        self._resync(sync, registry)
        coordinator.data = {ATTR_BACKENDS: {"a": {}}}
        self._resync(sync, registry)

        assert [e.slug for e in added] == ["a", "a"]

    def test_missing_data_key_leaves_entities_alone(self):
        coordinator, registry, added, sync = self._setup({"a": {}})
        registry.entries = [FakeRegistryEntry(e.entity_id, e.unique_id) for e in added]

        coordinator.data = {}
        self._resync(sync, registry)

        assert registry.removed == []
        assert len(added) == 1
