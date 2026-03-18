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

"""Tests for DnsdistGroupCoordinator aggregation logic."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.dnsdist.group_coordinator import DnsdistGroupCoordinator
from custom_components.dnsdist.const import (
    ATTR_CACHE_HITS,
    ATTR_CACHE_HITRATE,
    ATTR_CACHE_MISSES,
    ATTR_CPU,
    ATTR_DOWNSTREAM_ERRORS,
    ATTR_DROPS,
    ATTR_DYNAMIC_RULES,
    ATTR_FILTERING_RULES,
    ATTR_QUERIES,
    ATTR_RESPONSES,
    ATTR_RULE_DROP,
    ATTR_SECURITY_STATUS,
    ATTR_UPTIME,
    DOMAIN,
)


def make_group_coordinator(members=None):
    hass = MagicMock()
    hass.data = {}
    with (
        patch("homeassistant.helpers.frame.report_usage"),
        patch(
            "custom_components.dnsdist.group_coordinator.async_dispatcher_connect",
            return_value=MagicMock(),
        ),
    ):
        coord = DnsdistGroupCoordinator(
            hass,
            entry_id="test-group",
            name="testgroup",
            members=members or ["host1", "host2"],
            update_interval=30,
        )
    return coord, hass


def make_member(name, data, success=True):
    c = MagicMock()
    c._name = name
    c.last_update_success = success
    c.data = data
    return c


def base_data(**overrides):
    """Return a minimal member data dict with all expected keys."""
    d = {
        ATTR_QUERIES: 0,
        ATTR_RESPONSES: 0,
        ATTR_DROPS: 0,
        ATTR_RULE_DROP: 0,
        ATTR_DOWNSTREAM_ERRORS: 0,
        ATTR_CACHE_HITS: 0,
        ATTR_CACHE_MISSES: 0,
        ATTR_CPU: 0.0,
        ATTR_UPTIME: 0,
        ATTR_SECURITY_STATUS: "ok",
    }
    d.update(overrides)
    return d


def run_aggregation(coord, hass, members_map):
    """Set hass.data and run _async_update_data, patching HA storage calls."""
    hass.data[DOMAIN] = members_map
    with (
        patch.object(coord, "_async_ensure_history_loaded", new_callable=AsyncMock),
        patch.object(coord, "_async_save_history", new_callable=AsyncMock),
    ):
        return asyncio.run(coord._async_update_data())


class TestGroupAggregationCounters:
    def test_sums_all_counters(self):
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        d1 = base_data(
            queries=100, responses=90, drops=5, rule_drop=2, downstream_errors=1, cache_hits=40, cache_misses=10
        )
        d2 = base_data(
            queries=200, responses=180, drops=10, rule_drop=4, downstream_errors=2, cache_hits=80, cache_misses=20
        )
        c1 = make_member("h1", d1)
        c2 = make_member("h2", d2)
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        assert result[ATTR_QUERIES] == 300
        assert result[ATTR_RESPONSES] == 270
        assert result[ATTR_DROPS] == 15
        assert result[ATTR_RULE_DROP] == 6
        assert result[ATTR_DOWNSTREAM_ERRORS] == 3
        assert result[ATTR_CACHE_HITS] == 120
        assert result[ATTR_CACHE_MISSES] == 30

    def test_deque_maxlen_at_30s_interval(self):
        coord, _ = make_group_coordinator()
        assert coord._history.maxlen == (86400 // 30) + 1


class TestGroupAggregationCPU:
    def test_averages_cpu(self):
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        c1 = make_member("h1", base_data(cpu=20.0))
        c2 = make_member("h2", base_data(cpu=40.0))
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        assert result[ATTR_CPU] == 30.0

    def test_cpu_zero_when_no_members_report_cpu(self):
        coord, hass = make_group_coordinator(members=["h1"])
        # cpu key absent from data
        c1 = make_member("h1", base_data())
        del c1.data[ATTR_CPU]
        result = run_aggregation(coord, hass, {"e1": c1})
        assert result[ATTR_CPU] == 0.0

    def test_skips_invalid_cpu_values(self):
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        c1 = make_member("h1", base_data(cpu="not-a-number"))
        c2 = make_member("h2", base_data(cpu=50.0))
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        # Only c2 contributes
        assert result[ATTR_CPU] == 50.0


class TestGroupAggregationUptime:
    def test_takes_max_uptime(self):
        coord, hass = make_group_coordinator(members=["h1", "h2", "h3"])
        c1 = make_member("h1", base_data(uptime=1000))
        c2 = make_member("h2", base_data(uptime=5000))
        c3 = make_member("h3", base_data(uptime=3000))
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2, "e3": c3})
        assert result[ATTR_UPTIME] == 5000

    def test_uptime_zero_when_no_members(self):
        coord, hass = make_group_coordinator(members=["h1"])
        c1 = make_member("h1", base_data())
        del c1.data[ATTR_UPTIME]
        result = run_aggregation(coord, hass, {"e1": c1})
        assert result[ATTR_UPTIME] == 0


class TestGroupAggregationSecurityStatus:
    def test_critical_wins_over_warning(self):
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        c1 = make_member("h1", base_data(security_status="critical"))
        c2 = make_member("h2", base_data(security_status="warning"))
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        assert result[ATTR_SECURITY_STATUS] == "critical"

    def test_warning_wins_over_ok(self):
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        c1 = make_member("h1", base_data(security_status="ok"))
        c2 = make_member("h2", base_data(security_status="warning"))
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        assert result[ATTR_SECURITY_STATUS] == "warning"

    def test_ok_wins_over_unknown(self):
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        c1 = make_member("h1", base_data(security_status="unknown"))
        c2 = make_member("h2", base_data(security_status="ok"))
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        assert result[ATTR_SECURITY_STATUS] == "ok"


class TestGroupAggregationCacheHitrate:
    def test_hitrate_computed_from_totals(self):
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        c1 = make_member("h1", base_data(cache_hits=60, cache_misses=40))
        c2 = make_member("h2", base_data(cache_hits=40, cache_misses=60))
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        # 100 hits / 200 total = 50%
        assert result[ATTR_CACHE_HITRATE] == 50.0

    def test_hitrate_zero_when_no_cache_traffic(self):
        coord, hass = make_group_coordinator(members=["h1"])
        c1 = make_member("h1", base_data(cache_hits=0, cache_misses=0))
        result = run_aggregation(coord, hass, {"e1": c1})
        assert result[ATTR_CACHE_HITRATE] == 0.0


class TestGroupAggregationMemberFiltering:
    def test_no_active_members_returns_last_data(self):
        coord, hass = make_group_coordinator(members=["h1"])
        # No coordinators in hass.data
        result = run_aggregation(coord, hass, {})
        # Returns _last_data which is zero_data()
        assert result[ATTR_QUERIES] == 0

    def test_skips_non_member_coordinator(self):
        coord, hass = make_group_coordinator(members=["h1"])
        c_other = make_member("other", base_data(queries=999))
        c1 = make_member("h1", base_data(queries=100))
        result = run_aggregation(coord, hass, {"e1": c_other, "e2": c1})
        assert result[ATTR_QUERIES] == 100

    def test_skips_failed_coordinator(self):
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        c1 = make_member("h1", base_data(queries=100), success=True)
        c2 = make_member("h2", base_data(queries=200), success=False)
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        assert result[ATTR_QUERIES] == 100

    def test_skips_coordinator_without_name(self):
        coord, hass = make_group_coordinator(members=["h1"])
        c_no_name = MagicMock(spec=[])  # no attributes at all
        c1 = make_member("h1", base_data(queries=50))
        result = run_aggregation(coord, hass, {"e1": c_no_name, "e2": c1})
        assert result[ATTR_QUERIES] == 50


class TestGroupAggregationFilteringRules:
    def test_rule_matches_summed_across_members(self):
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        rules_h1 = {"block-ads": {"name": "Block Ads", "matches": 100}}
        rules_h2 = {"block-ads": {"name": "Block Ads", "matches": 200}}
        c1 = make_member("h1", base_data(**{ATTR_FILTERING_RULES: rules_h1}))
        c2 = make_member("h2", base_data(**{ATTR_FILTERING_RULES: rules_h2}))
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        rules = result[ATTR_FILTERING_RULES]
        assert "block-ads" in rules
        assert rules["block-ads"]["matches"] == 300

    def test_rule_sources_tracked_per_member(self):
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        rules_h1 = {"block-ads": {"name": "Block Ads", "matches": 10}}
        rules_h2 = {"block-ads": {"name": "Block Ads", "matches": 20}}
        c1 = make_member("h1", base_data(**{ATTR_FILTERING_RULES: rules_h1}))
        c2 = make_member("h2", base_data(**{ATTR_FILTERING_RULES: rules_h2}))
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        sources = result[ATTR_FILTERING_RULES]["block-ads"]["sources"]
        assert sources["h1"] == 10
        assert sources["h2"] == 20

    def test_different_rules_stay_separate(self):
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        rules_h1 = {"allow-microsoft": {"name": "Allow Microsoft", "matches": 50}}
        rules_h2 = {"block-home": {"name": "Block Home", "matches": 30}}
        c1 = make_member("h1", base_data(**{ATTR_FILTERING_RULES: rules_h1}))
        c2 = make_member("h2", base_data(**{ATTR_FILTERING_RULES: rules_h2}))
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        rules = result[ATTR_FILTERING_RULES]
        assert "allow-microsoft" in rules
        assert "block-home" in rules


class TestGroupAggregationDynamicRules:
    def test_blocks_summed_across_members(self):
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        dyn_h1 = {"192-168-1-0-24": {"network": "192.168.1.0/24", "blocks": 5}}
        dyn_h2 = {"192-168-1-0-24": {"network": "192.168.1.0/24", "blocks": 10}}
        c1 = make_member("h1", base_data(**{ATTR_DYNAMIC_RULES: dyn_h1}))
        c2 = make_member("h2", base_data(**{ATTR_DYNAMIC_RULES: dyn_h2}))
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        slug = list(result[ATTR_DYNAMIC_RULES].keys())[0]
        assert result[ATTR_DYNAMIC_RULES][slug]["blocks"] == 15

    def test_dynamic_rule_sources_tracked(self):
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        dyn_h1 = {"10-0-0-1-32": {"network": "10.0.0.1/32", "blocks": 3}}
        dyn_h2 = {"10-0-0-1-32": {"network": "10.0.0.1/32", "blocks": 7}}
        c1 = make_member("h1", base_data(**{ATTR_DYNAMIC_RULES: dyn_h1}))
        c2 = make_member("h2", base_data(**{ATTR_DYNAMIC_RULES: dyn_h2}))
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        slug = list(result[ATTR_DYNAMIC_RULES].keys())[0]
        sources = result[ATTR_DYNAMIC_RULES][slug]["sources"]
        assert sources["h1"] == 3
        assert sources["h2"] == 7
