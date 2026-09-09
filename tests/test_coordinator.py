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

"""Tests for DnsdistCoordinator normalization logic."""

from unittest.mock import MagicMock, patch

from custom_components.dnsdist.coordinator import DnsdistCoordinator
from custom_components.dnsdist.const import (
    ATTR_CACHE_HITS,
    ATTR_CACHE_HITRATE,
    ATTR_CACHE_MISSES,
    ATTR_DOWNSTREAM_ERRORS,
    ATTR_DROPS,
    ATTR_QUERIES,
    ATTR_RESPONSES,
    ATTR_RULE_DROP,
    ATTR_SECURITY_STATUS,
    ATTR_UPTIME,
)


def make_coordinator(update_interval=30):
    hass = MagicMock()
    hass.data = {}
    with patch("homeassistant.helpers.frame.report_usage"):
        return DnsdistCoordinator(
            hass,
            entry_id="test-entry",
            name="testhost",
            host="192.168.1.1",
            port=8083,
            api_key=None,
            use_https=False,
            verify_ssl=True,
            update_interval=update_interval,
        )


# ---------------------------------------------------------------------------
# Zero data and deque
# ---------------------------------------------------------------------------


class TestZeroData:
    def test_has_all_expected_keys(self):
        coord = make_coordinator()
        data = coord._zero_data()
        for key in (
            ATTR_QUERIES,
            ATTR_RESPONSES,
            ATTR_DROPS,
            ATTR_RULE_DROP,
            ATTR_DOWNSTREAM_ERRORS,
            ATTR_CACHE_HITS,
            ATTR_CACHE_MISSES,
            ATTR_UPTIME,
            ATTR_SECURITY_STATUS,
            "cpu_user_msec",
        ):
            assert key in data, f"Missing key: {key}"

    def test_all_numeric_values_are_zero(self):
        coord = make_coordinator()
        data = coord._zero_data()
        for key in (ATTR_QUERIES, ATTR_RESPONSES, ATTR_DROPS, ATTR_CACHE_HITS, ATTR_CACHE_MISSES):
            assert data[key] == 0

    def test_deque_maxlen_at_30s_interval(self):
        coord = make_coordinator(update_interval=30)
        assert coord._history.maxlen == (86400 // 30) + 1

    def test_deque_maxlen_at_10s_interval(self):
        coord = make_coordinator(update_interval=10)
        assert coord._history.maxlen == (86400 // 10) + 1

    def test_deque_maxlen_at_600s_interval(self):
        coord = make_coordinator(update_interval=600)
        assert coord._history.maxlen == (86400 // 600) + 1


# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------


class TestNormalize:
    def setup_method(self):
        self.coord = make_coordinator()

    def _stats(self, *pairs):
        """Build a list-format stats payload from (name, value) pairs."""
        return [{"name": k, "value": v} for k, v in pairs]

    def test_list_format_all_keys(self):
        stats = self._stats(
            ("queries", 1000),
            ("responses", 900),
            ("acl-drops", 4),
            ("rule-drop", 5),
            ("dyn-blocked", 1),
            ("downstream-send-errors", 3),
            ("cache-hits", 400),
            ("cache-misses", 100),
            ("uptime", 3600),
            ("cpu-user-msec", 50000),
            ("security-status", 1),
        )
        result = self.coord._normalize(stats)
        assert result[ATTR_QUERIES] == 1000
        assert result[ATTR_RESPONSES] == 900
        assert result[ATTR_DROPS] == 10
        assert result[ATTR_RULE_DROP] == 5
        assert result[ATTR_DOWNSTREAM_ERRORS] == 3
        assert result[ATTR_CACHE_HITS] == 400
        assert result[ATTR_CACHE_MISSES] == 100
        assert result[ATTR_UPTIME] == 3600
        assert result["cpu_user_msec"] == 50000
        assert result[ATTR_SECURITY_STATUS] == "ok"

    def test_drops_sums_every_drop_counter(self):
        stats = self._stats(
            ("acl-drops", 1),
            ("rule-drop", 2),
            ("dyn-blocked", 4),
            ("no-policy", 8),
            ("noncompliant-queries", 16),
        )
        result = self.coord._normalize(stats)
        assert result[ATTR_DROPS] == 31
        assert result[ATTR_RULE_DROP] == 2

    def test_drops_zero_without_drop_counters(self):
        result = self.coord._normalize(self._stats(("queries", 10)))
        assert result[ATTR_DROPS] == 0

    def test_drops_ignores_the_stat_dnsdist_does_not_have(self):
        result = self.coord._normalize(self._stats(("drops", 99)))
        assert result[ATTR_DROPS] == 0

    def test_dict_format_with_statistics_key(self):
        stats = {"statistics": [{"name": "queries", "value": 42}]}
        result = self.coord._normalize(stats)
        assert result[ATTR_QUERIES] == 42

    def test_underscore_key_variants(self):
        stats = self._stats(
            ("rule_drop", 7),
            ("downstream_errors", 2),
            ("cache_hits", 80),
            ("cache_misses", 20),
            ("cpu_user_msec", 12345),
            ("security_status", 2),
        )
        result = self.coord._normalize(stats)
        assert result[ATTR_RULE_DROP] == 7
        assert result[ATTR_DOWNSTREAM_ERRORS] == 2
        assert result[ATTR_CACHE_HITS] == 80
        assert result[ATTR_CACHE_MISSES] == 20
        assert result["cpu_user_msec"] == 12345
        assert result[ATTR_SECURITY_STATUS] == "warning"

    def test_cache_hitrate_calculated(self):
        stats = self._stats(("cache-hits", 80), ("cache-misses", 20))
        result = self.coord._normalize(stats)
        assert result[ATTR_CACHE_HITRATE] == 80.0

    def test_cache_hitrate_zero_when_no_traffic(self):
        stats = self._stats(("cache-hits", 0), ("cache-misses", 0))
        result = self.coord._normalize(stats)
        assert result.get(ATTR_CACHE_HITRATE, 0.0) == 0.0

    def test_security_status_all_values(self):
        for code, expected in [(0, "unknown"), (1, "ok"), (2, "warning"), (3, "critical")]:
            stats = self._stats(("security-status", code))
            result = self.coord._normalize(stats)
            assert result[ATTR_SECURITY_STATUS] == expected, f"code={code}"

    def test_unknown_security_status_code_maps_to_unknown(self):
        stats = self._stats(("security-status", 99))
        result = self.coord._normalize(stats)
        assert result[ATTR_SECURITY_STATUS] == "unknown"

    def test_unknown_keys_are_ignored(self):
        stats = self._stats(("queries", 10), ("some-unknown-metric", 999))
        result = self.coord._normalize(stats)
        assert result[ATTR_QUERIES] == 10
        assert "some-unknown-metric" not in result

    def test_empty_list_returns_zero_data(self):
        result = self.coord._normalize([])
        assert result[ATTR_QUERIES] == 0
        assert result[ATTR_RESPONSES] == 0

    def test_string_values_are_coerced(self):
        stats = self._stats(("queries", "500"), ("responses", "450"))
        result = self.coord._normalize(stats)
        assert result[ATTR_QUERIES] == 500
        assert result[ATTR_RESPONSES] == 450


# ---------------------------------------------------------------------------
# _normalize_filtering_rule
# ---------------------------------------------------------------------------


class TestNormalizeFilteringRule:
    def setup_method(self):
        self.coord = make_coordinator()

    def test_basic_rule(self):
        item = {
            "name": "Block Ads",
            "matches": 42,
            "action": "Drop",
            "rule": "qtype==A",
            "uuid": "abc-123",
            "id": 1,
            "enabled": True,
        }
        result = self.coord._normalize_filtering_rule(item)
        assert result is not None
        assert result["name"] == "Block Ads"
        assert result["matches"] == 42
        assert result["action"] == "Drop"
        assert result["uuid"] == "abc-123"
        assert result["enabled"] is True

    def test_name_fallback_to_rule_field(self):
        item = {"rule": "qtype==AAAA", "matches": 5}
        result = self.coord._normalize_filtering_rule(item)
        assert result["name"] == "qtype==AAAA"

    def test_name_fallback_to_uuid(self):
        item = {"uuid": "dead-beef", "matches": 0}
        result = self.coord._normalize_filtering_rule(item)
        assert result["name"] == "dead-beef"

    def test_name_fallback_to_id(self):
        item = {"id": 7, "matches": 0}
        result = self.coord._normalize_filtering_rule(item)
        assert result["name"] == "7"

    def test_name_fallback_to_unnamed(self):
        result = self.coord._normalize_filtering_rule({})
        assert result["name"] == "Unnamed Rule"

    def test_matches_priority_numMatches(self):
        item = {"name": "r", "numMatches": 99}
        result = self.coord._normalize_filtering_rule(item)
        assert result["matches"] == 99

    def test_matches_priority_hits(self):
        item = {"name": "r", "hits": 77}
        result = self.coord._normalize_filtering_rule(item)
        assert result["matches"] == 77

    def test_matches_priority_count(self):
        item = {"name": "r", "count": 33}
        result = self.coord._normalize_filtering_rule(item)
        assert result["matches"] == 33

    def test_slug_ignores_uuid_and_id(self):
        # dnsdist regenerates the uuid on every config load and id is only the
        # rule position, so the slug has to come from the name
        item = {"name": "Some Rule", "uuid": "my-uuid", "id": 5}
        result = self.coord._normalize_filtering_rule(item)
        assert result["slug"] == "some-rule"

    def test_slug_survives_a_new_uuid(self):
        first = self.coord._normalize_filtering_rule({"name": "Block Ads", "uuid": "aaa", "id": 0})
        second = self.coord._normalize_filtering_rule({"name": "Block Ads", "uuid": "bbb", "id": 4})
        assert first["slug"] == second["slug"]

    def test_slug_from_name_when_no_uuid_or_id(self):
        item = {"name": "Block Home"}
        result = self.coord._normalize_filtering_rule(item)
        assert result["slug"] == "block-home"

    def test_slug_from_rule_expression_for_unnamed_rules(self):
        item = {"name": "", "rule": "qtype==AAAA", "uuid": "aaa"}
        result = self.coord._normalize_filtering_rule(item)
        assert result["slug"] == "qtype-aaaa"


# ---------------------------------------------------------------------------
# _parse_filtering_rules
# ---------------------------------------------------------------------------


class TestParseFilteringRules:
    def setup_method(self):
        self.coord = make_coordinator()

    def test_rules_keyed_by_name_slug(self):
        payload = {"rules": [{"name": "Block Ads", "matches": 3, "uuid": "aaa"}]}
        assert set(self.coord._parse_filtering_rules(payload)) == {"block-ads"}

    def test_duplicate_names_are_counted_together(self):
        payload = {
            "rules": [
                {"name": "Block Ads", "matches": 3, "uuid": "aaa"},
                {"name": "Block Ads", "matches": 4, "uuid": "bbb"},
            ]
        }
        rules = self.coord._parse_filtering_rules(payload)
        assert list(rules) == ["block-ads"]
        assert rules["block-ads"]["matches"] == 7

    def test_no_rules_gives_empty_mapping(self):
        """dnsdist with zero rules is not the same as an unreadable payload."""
        assert self.coord._parse_filtering_rules({"rules": []}) == {}

    def test_unreadable_payload_gives_none(self):
        # None keeps the caller from taking an empty mapping as proof that
        # every rule is gone, which would delete all the rule sensors
        assert self.coord._parse_filtering_rules({}) is None
        assert self.coord._parse_filtering_rules({"rules": "nonsense"}) is None

    def test_merged_rules_drop_the_single_rule_identifiers(self):
        payload = {
            "rules": [
                {"name": "Block Ads", "matches": 3, "uuid": "aaa", "id": 0},
                {"name": "Block Ads", "matches": 4, "uuid": "bbb", "id": 1},
            ]
        }
        merged = self.coord._parse_filtering_rules(payload)["block-ads"]
        assert merged["uuid"] is None
        assert merged["id"] is None


# ---------------------------------------------------------------------------
# _normalize_dynamic_rule
# ---------------------------------------------------------------------------


class TestNormalizeDynamicRule:
    def setup_method(self):
        self.coord = make_coordinator()

    def test_basic_dynblock(self):
        result = self.coord._normalize_dynamic_rule(
            "192.168.1.0/24",
            {"blocks": 15, "reason": "rate limit", "action": "drop", "seconds": 60},
        )
        assert result is not None
        assert result["network"] == "192.168.1.0/24"
        assert result["blocks"] == 15
        assert result["reason"] == "rate limit"
        assert result["action"] == "drop"
        assert result["seconds"] == 60

    def test_empty_network_returns_none(self):
        result = self.coord._normalize_dynamic_rule("", {"blocks": 1})
        assert result is None

    def test_whitespace_network_returns_none(self):
        result = self.coord._normalize_dynamic_rule("   ", {"blocks": 1})
        assert result is None

    def test_blocks_from_count_field(self):
        result = self.coord._normalize_dynamic_rule("10.0.0.1/32", {"count": 5})
        assert result["blocks"] == 5

    def test_blocks_from_hits_field(self):
        result = self.coord._normalize_dynamic_rule("10.0.0.1/32", {"hits": 3})
        assert result["blocks"] == 3

    def test_default_reason_unknown(self):
        result = self.coord._normalize_dynamic_rule("10.0.0.1/32", {"blocks": 1})
        assert result["reason"] == "Unknown"

    def test_reason_from_message_field(self):
        result = self.coord._normalize_dynamic_rule("10.0.0.1/32", {"message": "DoS detected"})
        assert result["reason"] == "DoS detected"

    def test_default_action_refused(self):
        result = self.coord._normalize_dynamic_rule("10.0.0.1/32", {})
        assert result["action"] == "refused"

    def test_ebpf_and_warning_flags(self):
        result = self.coord._normalize_dynamic_rule("10.0.0.1/32", {"ebpf": True, "warning": True, "blocks": 1})
        assert result["ebpf"] is True
        assert result["warning"] is True

    def test_slug_is_present(self):
        result = self.coord._normalize_dynamic_rule("192.168.0.0/16", {"blocks": 2})
        assert "slug" in result
        assert result["slug"] != ""
