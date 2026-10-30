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

import asyncio
import time
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from homeassistant.helpers.json import prepare_save_json

from custom_components.dnsdist.coordinator import DnsdistCoordinator
from custom_components.dnsdist.utils import compute_window_total
from custom_components.dnsdist.const import (
    ATTR_CACHE_HITS,
    ATTR_CACHE_HITRATE,
    ATTR_CACHE_MISSES,
    ATTR_CPU,
    ATTR_DOWNSTREAM_ERRORS,
    ATTR_DROPS,
    ATTR_QUERIES,
    ATTR_RESPONSES,
    ATTR_RULE_DROP,
    ATTR_SECURITY_STATUS,
    ATTR_UPTIME,
    STORAGE_KEY_HISTORY,
    STORAGE_KEY_LAST_RAW,
    STORAGE_KEY_SOURCE,
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


class FakeResponse:
    """Stand-in for an aiohttp response used as an async context manager."""

    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, response):
        self._response = response

    def get(self, *args, **kwargs):
        return self._response


class RoutedSession:
    """Serves the statistics response and 404s the optional endpoints."""

    def __init__(self, stats_payload):
        self._stats = stats_payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(kwargs)
        if url.endswith("/statistics"):
            return FakeResponse(200, self._stats)
        return FakeResponse(404, None)


class DeadSession:
    """A host that never answers."""

    def get(self, url, **kwargs):
        raise TimeoutError


def poll_dead(coord):
    """Run one update against a host that does not answer."""
    coord._history_loaded = True
    with (
        patch("custom_components.dnsdist.coordinator.async_get_clientsession", return_value=DeadSession()),
        patch.object(coord, "_async_save_history"),
    ):
        coord.data = asyncio.run(coord._async_update_data())

    return coord.data


def poll(coord, stats_payload, elapsed=None):
    """Run one full update, storing the result the way the coordinator does.

    ``elapsed`` fakes the wall clock moving on by that many seconds since the
    last reading, which is what the CPU percentage divides by.
    """
    coord._history_loaded = True
    contexts = [
        patch(
            "custom_components.dnsdist.coordinator.async_get_clientsession",
            return_value=RoutedSession(stats_payload),
        ),
        patch.object(coord, "_async_save_history"),
    ]
    if elapsed is not None:
        contexts.append(
            patch("custom_components.dnsdist.coordinator.monotonic", side_effect=[coord._last_update_ts + elapsed])
        )

    with ExitStack() as stack:
        for context in contexts:
            stack.enter_context(context)
        coord.data = asyncio.run(coord._async_update_data())

    return coord.data


def fetch_dynamic(payload, status=200):
    """Run the dynblock fetch against a canned response."""
    coord = make_coordinator()
    session = FakeSession(FakeResponse(status, payload))
    return coord, asyncio.run(coord._async_fetch_dynamic_rules(session, {}))


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
            "cpu_sys_msec",
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


class TestReachable:
    def test_unknown_before_the_first_poll(self):
        assert make_coordinator().reachable is None

    def test_true_once_a_poll_lands(self):
        coord = make_coordinator()
        poll(coord, [{"name": "queries", "value": 1.0}])
        assert coord.reachable is True

    def test_false_when_a_poll_gets_no_answer(self):
        coord = make_coordinator()
        poll_dead(coord)
        assert coord.reachable is False


class TestUnanswered:
    """A falling TOTAL_INCREASING counter is a meter reset to the statistics."""

    def test_nothing_before_the_first_reading(self):
        # Zeros here would be a fall from what was recorded before a restart
        coord = make_coordinator()
        assert poll_dead(coord) == {}

    def test_last_reading_carries_forward(self):
        coord = make_coordinator()
        poll(coord, [{"name": "queries", "value": 500.0}])
        assert poll_dead(coord)[ATTR_QUERIES] == 500

    def test_a_payload_that_is_not_statistics_is_no_answer(self):
        coord = make_coordinator()
        poll(coord, [{"name": "queries", "value": 500.0}])
        for payload in ({"error": "x"}, None, [], [{"name": "uptime", "value": 5.0}]):
            assert poll(coord, payload)[ATTR_QUERIES] == 500
            assert coord.reachable is False
            assert coord._last_raw == 500

    def test_the_dict_form_is_still_read(self):
        coord = make_coordinator()
        poll(coord, {"statistics": [{"name": "queries", "value": 42.0}]})
        assert coord.data[ATTR_QUERIES] == 42
        assert coord.reachable is True


class TestCpuUsage:
    def stats(self, cpu_user, cpu_sys=0):
        return [
            {"name": "queries", "value": 100.0},
            {"name": "cpu-user-msec", "value": float(cpu_user)},
            {"name": "cpu-sys-msec", "value": float(cpu_sys)},
        ]

    def test_the_first_poll_has_no_delta_to_report(self):
        assert poll(make_coordinator(), self.stats(500_000))[ATTR_CPU] == 0.0

    def test_counts_user_and_system_time(self):
        coord = make_coordinator()
        poll(coord, self.stats(500_000, 100_000))
        # 900ms of user plus 300ms of system, over 30 seconds
        assert poll(coord, self.stats(500_900, 100_300), elapsed=30)[ATTR_CPU] == 4.0

    def test_a_thread_per_core_may_pass_100(self):
        coord = make_coordinator()
        poll(coord, self.stats(1_000))
        assert poll(coord, self.stats(61_000), elapsed=30)[ATTR_CPU] == 200.0

    def test_a_dnsdist_restart_reports_no_percentage_rather_than_a_negative(self):
        coord = make_coordinator()
        poll(coord, self.stats(500_000))
        assert poll(coord, self.stats(100), elapsed=30)[ATTR_CPU] == 0.0

    def test_a_reading_without_the_counters_does_not_spike_the_next_one(self):
        coord = make_coordinator()
        poll(coord, self.stats(500_000))
        poll(coord, [{"name": "queries", "value": 200.0}], elapsed=30)
        assert poll(coord, self.stats(500_900), elapsed=30)[ATTR_CPU] == 3.0


class TestHistoryAndRates:
    """The history holds traffic watched go past, not the counter dnsdist reports."""

    def feed(self, coord, samples):
        """Push (timestamp, raw dnsdist counter) samples through the real path."""
        for ts, raw in samples:
            coord._update_history(ts, raw)
        return coord

    def test_no_history_is_no_rate(self):
        assert make_coordinator()._compute_rates(1000.0) == (0, 0)

    def test_a_single_sample_is_no_rate(self):
        coord = self.feed(make_coordinator(), [(1000.0, 500)])
        assert coord._compute_rates(1000.0) == (0, 0)

    def test_the_first_sample_carries_no_traffic(self):
        """There is nothing yet to measure it against."""
        coord = self.feed(make_coordinator(), [(1000.0, 999_999)])
        assert list(coord._history) == [(1000.0, 0)]

    def test_short_history_is_scaled_up_to_the_window(self):
        # 100 queries in the last minute
        coord = self.feed(make_coordinator(), [(940.0, 0), (1000.0, 100)])
        assert coord._compute_rates(1000.0) == (6000, 144000)

    def test_an_hour_of_history_is_measured_not_scaled(self):
        coord = self.feed(make_coordinator(), [(1000.0 - 3600, 0), (1000.0, 720)])
        assert coord._compute_rates(1000.0)[0] == 720

    def test_a_day_of_history_lands_on_the_measured_count(self):
        coord = self.feed(make_coordinator(), [(1000.0 - 86400, 0), (1000.0, 5000)])
        assert coord._compute_rates(1000.0)[1] == 5000

    def test_a_dnsdist_restart_costs_one_interval_not_the_window(self):
        coord = self.feed(make_coordinator(), [(0.0, 0), (1800.0, 1000), (3600.0, 2000)])
        coord._update_history(5400.0, 5)
        assert len(coord._history) == 4, "nothing may be thrown away"
        assert coord._history[-1][1] == 2005, "2000 watched before the restart, 5 since"

    def test_rates_survive_a_restart(self):
        coord = self.feed(make_coordinator(), [(0.0, 0), (3600.0, 3600)])
        coord._update_history(7200.0, 100)
        # 3600 watched over the first hour, then 100 more
        assert coord._compute_rates(7200.0)[0] == compute_window_total(coord._history, 7200.0, 3600, 3700)

    def test_the_series_never_goes_backwards(self):
        coord = self.feed(make_coordinator(), [(0.0, 500), (30.0, 400), (60.0, 10), (90.0, 60)])
        totals = [total for _, total in coord._history]
        assert totals == sorted(totals)
        assert all(rate >= 0 for rate in coord._compute_rates(90.0))

    def test_samples_older_than_a_day_are_trimmed(self):
        coord = self.feed(make_coordinator(), [(0.0, 0), (100.0, 10)])
        coord._update_history(86400.0 + 200.0, 20)
        assert [ts for ts, _ in coord._history] == [86600.0]


class TestHistoryPersistence:
    """The store round trip, which nothing covered until now."""

    def load(self, coord, stored):
        """Load a canned store payload through the real loader."""
        coord._history_loaded = False
        coord._history_store = MagicMock()

        async def _load():
            return stored

        coord._history_store.async_load = _load
        asyncio.run(coord._async_ensure_history_loaded())
        return coord

    def test_the_payload_holds_the_history_and_the_last_counter(self):
        coord = make_coordinator()
        coord._update_history(1000.0, 50)
        coord._update_history(1030.0, 150)
        payload = coord._history_payload()
        assert payload[STORAGE_KEY_HISTORY] == [(1000.0, 0), (1030.0, 100)]
        assert payload[STORAGE_KEY_LAST_RAW] == 150

    def test_the_payload_is_what_the_store_can_write(self):
        """A tuple per sample, which the old code hid a failure of at debug level."""
        coord = make_coordinator()
        coord._update_history(1000.0, 50)
        prepare_save_json({"version": 1, "minor_version": 1, "key": "k", "data": coord._history_payload()})

    def test_a_saved_payload_loads_back_unchanged(self):
        now = time.time()
        source = make_coordinator()
        source._update_history(now - 60, 1000)
        source._update_history(now - 30, 1100)
        loaded = self.load(make_coordinator(), source._history_payload())
        assert list(loaded._history) == list(source._history)
        assert loaded._last_raw == 1100

    def test_traffic_served_while_home_assistant_was_down_is_counted(self):
        now = time.time()
        source = make_coordinator()
        source._update_history(now - 60, 1000)
        source._update_history(now - 30, 1100)
        loaded = self.load(make_coordinator(), source._history_payload())
        loaded._update_history(now, 1400)
        assert loaded._history[-1][1] - loaded._history[-2][1] == 300

    def test_a_store_written_before_last_raw_existed_still_loads(self):
        now = time.time()
        legacy = {STORAGE_KEY_HISTORY: [[now - 60, 500_000], [now - 30, 500_100]]}
        loaded = self.load(make_coordinator(), legacy)
        assert len(loaded._history) == 2
        assert loaded._last_raw is None
        loaded._update_history(now, 500_200)
        assert loaded._history[-1][1] - loaded._history[-2][1] == 0, "one interval given up, once"
        loaded._update_history(now + 30, 500_300)
        assert loaded._history[-1][1] - loaded._history[-2][1] == 100

    def test_the_payload_names_the_host_it_came_from(self):
        coord = make_coordinator()
        coord._update_history(1000.0, 50)
        assert coord._history_payload()[STORAGE_KEY_SOURCE] == "192.168.1.1:8083"

    def test_history_from_another_host_is_dropped(self):
        """Reconfiguring the entry keeps the store, but not the counter it held."""
        now = time.time()
        source = make_coordinator()
        source._update_history(now - 60, 8_000_000)
        source._update_history(now - 30, 8_000_100)
        stored = source._history_payload()
        stored[STORAGE_KEY_SOURCE] = "10.9.9.9:8083"
        loaded = self.load(make_coordinator(), stored)
        assert list(loaded._history) == []
        assert loaded._last_raw is None

    def test_a_new_host_does_not_spike_the_rates(self):
        now = time.time()
        source = make_coordinator()
        for i in range(120):
            source._update_history(now - 3600 + i * 30, 8_000_000 + i * 100)
        stored = source._history_payload()
        stored[STORAGE_KEY_SOURCE] = "10.9.9.9:8083"
        loaded = self.load(make_coordinator(), stored)
        loaded._update_history(now, 5_000_000)
        assert loaded._compute_rates(now) == (0, 0), "starts over rather than counting 5M in one poll"

    def test_history_from_the_same_host_is_kept(self):
        now = time.time()
        source = make_coordinator()
        source._update_history(now - 60, 1000)
        source._update_history(now - 30, 1100)
        loaded = self.load(make_coordinator(), source._history_payload())
        assert len(loaded._history) == 2
        assert loaded._last_raw == 1100

    def test_a_store_from_before_the_source_field_still_loads(self):
        """The shape 1.5.1 wrote: a last counter, but nothing saying whose."""
        now = time.time()
        stored = {
            STORAGE_KEY_HISTORY: [[now - 60, 1000], [now - 30, 1100]],
            STORAGE_KEY_LAST_RAW: 1100,
        }
        loaded = self.load(make_coordinator(), stored)
        assert len(loaded._history) == 2
        assert loaded._last_raw == 1100
        loaded._update_history(now, 1400)
        assert loaded._history[-1][1] - loaded._history[-2][1] == 300, "the gap is still counted"

    def test_samples_older_than_a_day_are_dropped_on_load(self):
        now = time.time()
        stored = {STORAGE_KEY_HISTORY: [[now - 90_000, 1], [now - 60, 2]]}
        assert len(self.load(make_coordinator(), stored)._history) == 1

    def test_junk_in_the_store_is_skipped(self):
        now = time.time()
        stored = {STORAGE_KEY_HISTORY: ["nope", [1], [now - 60, "x"], [now - 30, 5]]}
        assert list(self.load(make_coordinator(), stored)._history) == [(now - 30, 5)]

    def test_an_unreadable_store_leaves_the_history_empty(self):
        for stored in (None, [], "nope", {}, {STORAGE_KEY_HISTORY: "nope"}):
            assert list(self.load(make_coordinator(), stored)._history) == [], stored

    def test_the_store_is_read_once(self):
        coord = self.load(make_coordinator(), {STORAGE_KEY_HISTORY: [[time.time() - 30, 5]]})
        calls = []

        async def _load():
            calls.append(1)
            return {}

        coord._history_store.async_load = _load
        asyncio.run(coord._async_ensure_history_loaded())
        assert calls == []


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
            ("cpu-sys-msec", 20000),
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
        assert result["cpu_sys_msec"] == 20000
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
            ("cpu_sys_msec", 6789),
            ("security_status", 2),
        )
        result = self.coord._normalize(stats)
        assert result[ATTR_RULE_DROP] == 7
        assert result[ATTR_DOWNSTREAM_ERRORS] == 2
        assert result[ATTR_CACHE_HITS] == 80
        assert result[ATTR_CACHE_MISSES] == 20
        assert result["cpu_user_msec"] == 12345
        assert result["cpu_sys_msec"] == 6789
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

    def test_one_unreadable_statistic_does_not_lose_the_rest(self):
        stats = self._stats(
            ("queries", 1000),
            ("acl-drops", None),
            ("cache-hits", 80),
            ("cache-misses", 20),
            ("cpu-user-msec", 900),
        )
        result = self.coord._normalize(stats)
        assert result[ATTR_QUERIES] == 1000
        assert result[ATTR_CACHE_HITS] == 80
        assert result["cpu_user_msec"] == 900
        assert result[ATTR_DROPS] == 0

    def test_an_unreadable_value_counts_as_zero(self):
        stats = self._stats(("acl-drops", "wat"), ("rule-drop", 5))
        result = self.coord._normalize(stats)
        assert result[ATTR_DROPS] == 5
        assert result[ATTR_RULE_DROP] == 5

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


class TestFetchDynamicRules:
    def test_reads_the_dynblock_mapping(self):
        payload = {"10.0.0.1/32": {"blocks": 3, "reason": "rate", "seconds": 30}}
        _, rules = fetch_dynamic(payload)
        assert list(rules) == ["10-0-0-1-32"]
        assert rules["10-0-0-1-32"]["blocks"] == 3

    def test_empty_mapping_means_no_dynblocks(self):
        assert fetch_dynamic({})[1] == {}

    def test_unreadable_payload_is_not_an_empty_one(self):
        """An empty mapping deletes every dynblock sensor, so do not fake one."""
        for payload in ([], "nope", 42, None):
            assert fetch_dynamic(payload)[1] is None, payload

    def test_a_404_latches_the_endpoint_off(self):
        coord, rules = fetch_dynamic({}, status=404)
        assert rules is None
        assert coord._dynamic_rules_supported is False

    def test_an_unreadable_payload_does_not_latch_the_endpoint(self):
        coord, _ = fetch_dynamic([])
        assert coord._dynamic_rules_supported is None


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


class TestBackends:
    def parse(self, servers):
        return make_coordinator()._parse_backends({"servers": servers})

    def test_backends_sharing_a_name_each_get_one(self):
        backends = self.parse(
            [
                {"name": "quad9", "address": "9.9.9.9:53", "state": "down"},
                {"name": "quad9", "address": "149.112.112.112:53", "state": "up"},
            ]
        )
        assert backends["quad9"]["address"] == "9.9.9.9:53"
        assert backends["quad9-149-112-112-112-53"]["state"] == "up"

    def test_a_unique_name_keeps_its_slug(self):
        backends = self.parse([{"name": "Quad 9", "address": "9.9.9.9:53"}, {"address": "1.1.1.1:53"}])
        assert sorted(backends) == ["1-1-1-1-53", "quad-9"]


class TestRedirects:
    def test_no_request_carrying_the_key_follows_a_redirect(self):
        """aiohttp keeps X-API-Key on a redirect to another host."""
        coord = make_coordinator()
        coord._api_key = "secret"
        coord._history_loaded = True
        session = RoutedSession([{"name": "queries", "value": 1.0}])
        with (
            patch("custom_components.dnsdist.coordinator.async_get_clientsession", return_value=session),
            patch.object(coord, "_async_save_history"),
        ):
            asyncio.run(coord._async_update_data())
        assert len(session.calls) == 3
        assert all(call["allow_redirects"] is False for call in session.calls)


class TestDynblockSlugs:
    def test_ipv6_networks_that_slug_alike_stay_apart(self):
        _, rules = fetch_dynamic({"2001:db8::1/128": {"blocks": 1}, "2001:db8:1::/128": {"blocks": 2}})
        assert len(rules) == 2
        assert {r["network"] for r in rules.values()} == {"2001:db8::1/128", "2001:db8:1::/128"}

    def test_ipv4_and_suffixes_keep_their_slugs(self):
        _, rules = fetch_dynamic({"10.0.0.1/32": {"blocks": 1}, "example.com.": {"blocks": 1}})
        assert sorted(rules) == ["10-0-0-1-32", "example-com"]


class TestRuleSlugs:
    def parse(self, rules):
        return make_coordinator()._parse_filtering_rules({"rules": rules})

    def test_different_names_that_slug_alike_stay_apart(self):
        rules = self.parse([{"name": "правило 1", "matches": 3}, {"name": "блок 1", "matches": 4}])
        assert rules["1"]["name"] == "правило 1"
        assert rules["1"]["matches"] == 3
        others = [slug for slug in rules if slug != "1"]
        assert len(others) == 1 and rules[others[0]]["matches"] == 4

    def test_the_same_name_twice_is_still_counted_together(self):
        rules = self.parse([{"name": "Block", "matches": 3}, {"name": "Block", "matches": 4}])
        assert rules == {"block": {**rules["block"], "matches": 7}}

    def test_a_suffixed_name_twice_is_counted_together(self):
        rules = self.parse(
            [{"name": "a 1", "matches": 1}, {"name": "a-1", "matches": 2}, {"name": "a-1", "matches": 5}]
        )
        assert sorted(r["matches"] for r in rules.values()) == [1, 7]
