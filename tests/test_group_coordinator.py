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
from unittest.mock import MagicMock, patch

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
    ATTR_MEMBERS,
    ATTR_QUERIES,
    ATTR_REQ_PER_DAY,
    ATTR_REQ_PER_HOUR,
    ATTR_RESPONSES,
    ATTR_RULE_DROP,
    ATTR_SECURITY_STATUS,
    ATTR_UPTIME,
    CONF_NAME,
    DOMAIN,
)


def make_host_entry(name, disabled=False):
    """Build a fake host config entry the group can count as configured."""
    entry = MagicMock()
    entry.data = {CONF_NAME: name}
    entry.title = name
    entry.disabled_by = "user" if disabled else None
    return entry


def make_group_coordinator(members=None, configured=None):
    hass = MagicMock()
    hass.data = {}
    names = members or ["host1", "host2"]
    hass.config_entries.async_entries.return_value = [
        make_host_entry(n) for n in (names if configured is None else configured)
    ]
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


def make_member(name, data, success=True, reachable=True):
    c = MagicMock()
    c._name = name
    c._host = "10.0.0.1"
    c.last_update_success = success
    c.data = data
    c.reachable = reachable
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
    """Set hass.data and run one aggregation."""
    hass.data[DOMAIN] = members_map
    return asyncio.run(coord._async_update_data())


class TestReloadSignal:
    def handle(self, registered):
        coord, hass = make_group_coordinator()
        hass.data[DOMAIN] = {"test-group": coord} if registered else {}
        with patch.object(coord, "async_request_refresh", MagicMock()):
            coord._handle_reload_signal()
        return hass.async_create_task.called

    def test_refreshes_while_the_entry_is_loaded(self):
        assert self.handle(registered=True) is True

    def test_ignores_the_signal_its_own_unload_sent(self):
        """Unload pops us from hass.data before it sends the signal."""
        assert self.handle(registered=False) is False


class TestMemberStates:
    def states(self, members, coords):
        coord, _ = make_group_coordinator(members=members)
        return coord._member_states(coords)

    def test_reports_every_configured_member(self):
        coords = {"e1": make_member("h1", {}), "e2": make_member("h2", {})}
        assert sorted(self.states(["h1", "h2"], coords)) == ["h1", "h2"]

    def test_a_member_that_answers_is_on(self):
        states = self.states(["h1"], {"e1": make_member("h1", {}, reachable=True)})
        assert states["h1"]["reachable"] is True

    def test_a_member_that_does_not_answer_is_off(self):
        states = self.states(["h1"], {"e1": make_member("h1", {}, reachable=False)})
        assert states["h1"]["reachable"] is False

    def test_a_member_that_has_not_polled_yet_reports_nothing(self):
        """A group can poll before a member has, which is not a failure."""
        states = self.states(["h1"], {"e1": make_member("h1", {}, reachable=None)})
        assert states["h1"]["reachable"] is None
        assert states["h1"]["loaded"] is True

    def test_a_member_with_no_coordinator_reports_nothing(self):
        """Unloaded, disabled or deleted is not the same as unreachable."""
        states = self.states(["h1"], {})
        assert states["h1"]["reachable"] is None
        assert states["h1"]["loaded"] is False

    def test_the_display_name_survives_the_slug(self):
        states = self.states(["DNS 1"], {"e1": make_member("DNS 1", {})})
        assert states["dns-1"]["name"] == "DNS 1"

    def test_a_group_coordinator_is_not_a_member(self):
        other_group = MagicMock(spec=["_name", "reachable"])
        other_group._name = "h1"
        assert self.states(["h1"], {"e1": other_group})["h1"]["loaded"] is False

    def test_the_aggregate_carries_the_member_states(self):
        coord, hass = make_group_coordinator(members=["h1"])
        result = run_aggregation(coord, hass, {"e1": make_member("h1", base_data())})
        assert result[ATTR_MEMBERS]["h1"]["reachable"] is True

    def test_member_states_survive_having_no_active_members(self):
        coord, hass = make_group_coordinator(members=["h1"])
        result = run_aggregation(coord, hass, {"e1": make_member("h1", base_data(), success=False)})
        assert result[ATTR_MEMBERS]["h1"]["reachable"] is True


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


class TestGroupRates:
    """The group has no history of its own, it adds up what its members report."""

    def rates(self, members):
        coord, hass = make_group_coordinator(members=[n for n, _, _ in members])
        coords = {
            f"e{i}": make_member(n, base_data(**{ATTR_REQ_PER_HOUR: h, ATTR_REQ_PER_DAY: d}))
            for i, (n, h, d) in enumerate(members)
        }
        result = run_aggregation(coord, hass, coords)
        return result[ATTR_REQ_PER_HOUR], result[ATTR_REQ_PER_DAY]

    def test_sums_the_member_rates(self):
        assert self.rates([("h1", 100, 2400), ("h2", 50, 1200)]) == (150, 3600)

    def test_a_member_that_has_no_history_yet_adds_nothing(self):
        assert self.rates([("h1", 100, 2400), ("h2", 0, 0)]) == (100, 2400)

    def test_a_member_that_dropped_out_is_simply_not_counted(self):
        """No shared counter, so nothing to mistake a smaller group for."""
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        both = {
            "e1": make_member("h1", base_data(**{ATTR_REQ_PER_HOUR: 100, ATTR_REQ_PER_DAY: 2400})),
            "e2": make_member("h2", base_data(**{ATTR_REQ_PER_HOUR: 50, ATTR_REQ_PER_DAY: 1200})),
        }
        assert run_aggregation(coord, hass, both)[ATTR_REQ_PER_HOUR] == 150
        result = run_aggregation(coord, hass, {"e1": both["e1"]})
        assert result[ATTR_REQ_PER_HOUR] == 100
        assert result[ATTR_REQ_PER_DAY] == 2400


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


# ---------------------------------------------------------------------------
# Expiry of aggregated rules
# ---------------------------------------------------------------------------


class TestGroupAggregationExpiry:
    def test_expired_dynblocks_disappear_from_the_group(self):
        """An empty aggregate from members that did report is the truth."""
        coord, hass = make_group_coordinator(members=["h1"])
        dyn = {"10-0-0-1-32": {"network": "10.0.0.1/32", "blocks": 3}}
        c1 = make_member("h1", base_data(**{ATTR_DYNAMIC_RULES: dyn}))
        run_aggregation(coord, hass, {"e1": c1})

        c1.data = base_data(**{ATTR_DYNAMIC_RULES: {}})
        result = run_aggregation(coord, hass, {"e1": c1})
        assert result[ATTR_DYNAMIC_RULES] == {}

    def test_deleted_filtering_rules_disappear_from_the_group(self):
        coord, hass = make_group_coordinator(members=["h1"])
        rules = {"block-ads": {"name": "Block Ads", "matches": 4}}
        c1 = make_member("h1", base_data(**{ATTR_FILTERING_RULES: rules}))
        run_aggregation(coord, hass, {"e1": c1})

        c1.data = base_data(**{ATTR_FILTERING_RULES: {}})
        result = run_aggregation(coord, hass, {"e1": c1})
        assert result[ATTR_FILTERING_RULES] == {}

    def test_unreported_rules_keep_the_last_known_value(self):
        """A member that could not be read must not wipe the sensors."""
        coord, hass = make_group_coordinator(members=["h1"])
        dyn = {"10-0-0-1-32": {"network": "10.0.0.1/32", "blocks": 3}}
        c1 = make_member("h1", base_data(**{ATTR_DYNAMIC_RULES: dyn}))
        run_aggregation(coord, hass, {"e1": c1})

        c1.data = base_data()
        result = run_aggregation(coord, hass, {"e1": c1})
        assert list(result[ATTR_DYNAMIC_RULES]) == ["10-0-0-1-32"]

    def test_a_member_that_is_down_does_not_delete_its_rules(self):
        """A partial aggregate is no proof that the missing member's rules are gone."""
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        rules_h1 = {"block-ads": {"name": "Block Ads", "matches": 4}}
        rules_h2 = {"block-porn": {"name": "Block Porn", "matches": 2}}
        c1 = make_member("h1", base_data(**{ATTR_FILTERING_RULES: rules_h1}))
        c2 = make_member("h2", base_data(**{ATTR_FILTERING_RULES: rules_h2}))
        run_aggregation(coord, hass, {"e1": c1, "e2": c2})

        c2.last_update_success = False
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        assert sorted(result[ATTR_FILTERING_RULES]) == ["block-ads", "block-porn"]

    def test_a_deleted_member_does_not_freeze_the_group(self):
        """A member whose host entry is gone must not hold the aggregate back."""
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        rules_h1 = {"block-ads": {"name": "Block Ads", "matches": 4}}
        rules_h2 = {"block-porn": {"name": "Block Porn", "matches": 2}}
        c1 = make_member("h1", base_data(**{ATTR_FILTERING_RULES: rules_h1}))
        c2 = make_member("h2", base_data(**{ATTR_FILTERING_RULES: rules_h2}))
        run_aggregation(coord, hass, {"e1": c1, "e2": c2})

        hass.config_entries.async_entries.return_value = [make_host_entry("h1")]
        result = run_aggregation(coord, hass, {"e1": c1})
        assert list(result[ATTR_FILTERING_RULES]) == ["block-ads"]

    def test_a_disabled_member_does_not_freeze_the_group(self):
        """A disabled host entry is never going to report, so it cannot hold on."""
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        rules_h1 = {"block-ads": {"name": "Block Ads", "matches": 4}}
        rules_h2 = {"block-porn": {"name": "Block Porn", "matches": 2}}
        c1 = make_member("h1", base_data(**{ATTR_FILTERING_RULES: rules_h1}))
        c2 = make_member("h2", base_data(**{ATTR_FILTERING_RULES: rules_h2}))
        run_aggregation(coord, hass, {"e1": c1, "e2": c2})

        hass.config_entries.async_entries.return_value = [
            make_host_entry("h1"),
            make_host_entry("h2", disabled=True),
        ]
        result = run_aggregation(coord, hass, {"e1": c1})
        assert list(result[ATTR_FILTERING_RULES]) == ["block-ads"]

    def test_partial_first_read_leaves_the_key_out(self):
        """With nothing known yet an incomplete aggregate must claim nothing."""
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        rules_h1 = {"block-ads": {"name": "Block Ads", "matches": 4}}
        c1 = make_member("h1", base_data(**{ATTR_FILTERING_RULES: rules_h1}))
        result = run_aggregation(coord, hass, {"e1": c1})
        assert ATTR_FILTERING_RULES not in result

    def test_an_active_member_reporting_no_rules_holds_the_aggregate(self):
        """A host that is down still counts as active but reports no rules key."""
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        rules_h1 = {"block-ads": {"name": "Block Ads", "matches": 4}}
        rules_h2 = {"block-porn": {"name": "Block Porn", "matches": 2}}
        c1 = make_member("h1", base_data(**{ATTR_FILTERING_RULES: rules_h1}))
        c2 = make_member("h2", base_data(**{ATTR_FILTERING_RULES: rules_h2}))
        run_aggregation(coord, hass, {"e1": c1, "e2": c2})

        # h2 stays reachable but its own fetch failed, so it carries no rules
        c2.data = base_data()
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        assert sorted(result[ATTR_FILTERING_RULES]) == ["block-ads", "block-porn"]

    def test_all_members_reporting_empty_clears_the_rules(self):
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        rules_h1 = {"block-ads": {"name": "Block Ads", "matches": 4}}
        c1 = make_member("h1", base_data(**{ATTR_FILTERING_RULES: rules_h1}))
        c2 = make_member("h2", base_data(**{ATTR_FILTERING_RULES: {}}))
        run_aggregation(coord, hass, {"e1": c1, "e2": c2})

        c1.data = base_data(**{ATTR_FILTERING_RULES: {}})
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        assert result[ATTR_FILTERING_RULES] == {}

    def test_a_member_without_the_endpoint_does_not_block_for_ever(self):
        """A 404 member will never report, so it must not freeze the aggregate."""
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        rules_h1 = {"block-ads": {"name": "Block Ads", "matches": 4}}
        c1 = make_member("h1", base_data(**{ATTR_FILTERING_RULES: rules_h1}))
        c2 = make_member("h2", base_data())
        c2._server_config_supported = False
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        assert list(result[ATTR_FILTERING_RULES]) == ["block-ads"]

        c1.data = base_data(**{ATTR_FILTERING_RULES: {}})
        result = run_aggregation(coord, hass, {"e1": c1, "e2": c2})
        assert result[ATTR_FILTERING_RULES] == {}

    def test_reloading_a_member_does_not_delete_its_rules(self):
        """Reloading a host pops it from hass.data and signals the group at once."""
        coord, hass = make_group_coordinator(members=["h1", "h2"])
        rules_h1 = {"block-ads": {"name": "Block Ads", "matches": 4}}
        rules_h2 = {"block-porn": {"name": "Block Porn", "matches": 2}}
        c1 = make_member("h1", base_data(**{ATTR_FILTERING_RULES: rules_h1}))
        c2 = make_member("h2", base_data(**{ATTR_FILTERING_RULES: rules_h2}))
        run_aggregation(coord, hass, {"e1": c1, "e2": c2})

        # h2 is mid-reload: gone from hass.data, entry still configured
        result = run_aggregation(coord, hass, {"e1": c1})
        assert sorted(result[ATTR_FILTERING_RULES]) == ["block-ads", "block-porn"]
