"""Tests for utility functions."""


from custom_components.dnsdist.utils import (
    coerce_int,
    compute_window_total,
    slugify,
    slugify_rule,
)


class TestCoerceInt:
    """Tests for coerce_int function."""

    def test_integer_input(self):
        assert coerce_int(42) == 42
        assert coerce_int(0) == 0
        assert coerce_int(-5) == -5

    def test_float_input(self):
        assert coerce_int(3.14) == 3
        assert coerce_int(9.99) == 9
        assert coerce_int(-2.5) == -2

    def test_string_input(self):
        assert coerce_int("123") == 123
        assert coerce_int("45.67") == 45
        assert coerce_int("-10") == -10

    def test_bool_input(self):
        assert coerce_int(True) == 1
        assert coerce_int(False) == 0

    def test_invalid_input_returns_zero(self):
        assert coerce_int(None) == 0
        assert coerce_int("not a number") == 0
        assert coerce_int("") == 0
        assert coerce_int([]) == 0
        assert coerce_int({}) == 0


class TestSlugify:
    """Tests for slugify function."""

    def test_basic_slugify(self):
        assert slugify("Hello World") == "hello-world"
        assert slugify("Test") == "test"

    def test_special_characters(self):
        assert slugify("Test@123!") == "test-123"
        assert slugify("foo_bar_baz") == "foo-bar-baz"
        assert slugify("a.b.c") == "a-b-c"

    def test_multiple_spaces_and_symbols(self):
        assert slugify("  multiple   spaces  ") == "multiple-spaces"
        assert slugify("---dashes---") == "dashes"

    def test_empty_and_none(self):
        assert slugify("") == "unknown"
        assert slugify(None) == "unknown"
        assert slugify("   ") == "unknown"

    def test_custom_fallback(self):
        assert slugify("", fallback="default") == "default"
        assert slugify(None, fallback="custom") == "custom"

    def test_unicode(self):
        # Unicode gets stripped, leaving fallback
        assert slugify("日本語") == "unknown"

    def test_mixed_case(self):
        assert slugify("CamelCase") == "camelcase"
        assert slugify("UPPERCASE") == "uppercase"


class TestSlugifyRule:
    """Tests for slugify_rule function."""

    def test_basic_rule_names(self):
        assert slugify_rule("Block Ads") == "block-ads"
        assert slugify_rule("allow-list") == "allow-list"

    def test_empty_generates_hash(self):
        result = slugify_rule("")
        assert result.startswith("rule-")
        assert len(result) > 5

    def test_none_generates_hash(self):
        result = slugify_rule(None)
        assert result.startswith("rule-")

    def test_whitespace_only_generates_hash(self):
        result = slugify_rule("   ")
        assert result.startswith("rule-")

    def test_special_characters(self):
        assert slugify_rule("Rule #1 (main)") == "rule-1-main"


class TestComputeWindowTotal:
    """Tests for compute_window_total function."""

    def test_empty_history(self):
        assert compute_window_total([], 1000.0, 3600, 100) == 0

    def test_single_entry_within_window(self):
        history = [(900.0, 50)]
        # now=1000, window=3600, so horizon=1000-3600=-2600
        # Entry at 900 is after horizon, baseline=50
        # delta = 100 - 50 = 50
        assert compute_window_total(history, 1000.0, 3600, 100) == 50

    def test_all_entries_within_window(self):
        history = [
            (100.0, 10),
            (200.0, 20),
            (300.0, 30),
        ]
        # horizon = 1000 - 3600 = -2600, all entries after horizon
        # baseline = first entry = 10
        # delta = 100 - 10 = 90
        assert compute_window_total(history, 1000.0, 3600, 100) == 90

    def test_entries_before_and_after_horizon(self):
        # horizon = 1000 - 100 = 900
        history = [
            (800.0, 40),  # before horizon
            (950.0, 60),  # after horizon
        ]
        # Interpolation between (800, 40) and (950, 60) at t=900
        # span = 950 - 800 = 150
        # fraction = (900 - 800) / 150 = 100/150 = 0.6667
        # baseline = 40 + (60 - 40) * 0.6667 = 40 + 13.33 = 53.33
        # delta = 100 - 53 = 47
        result = compute_window_total(history, 1000.0, 100, 100)
        assert result == 47

    def test_exact_horizon_match(self):
        history = [
            (800.0, 30),
            (900.0, 50),  # exactly at horizon
            (950.0, 70),
        ]
        # horizon = 1000 - 100 = 900
        # Entry at 900 exactly matches horizon, baseline = 50
        # delta = 100 - 50 = 50
        assert compute_window_total(history, 1000.0, 100, 100) == 50

    def test_all_entries_before_horizon(self):
        history = [
            (100.0, 10),
            (200.0, 20),
        ]
        # horizon = 1000 - 100 = 900, all entries before
        # Uses last entry as baseline = 20
        # delta = 100 - 20 = 80
        assert compute_window_total(history, 1000.0, 100, 100) == 80

    def test_negative_delta_returns_zero(self):
        history = [(900.0, 150)]
        # current_total (100) < baseline (150)
        # delta would be negative, should return 0
        assert compute_window_total(history, 1000.0, 3600, 100) == 0

    def test_large_window(self):
        history = [(0.0, 0)]
        # 24 hour window
        assert compute_window_total(history, 86400.0, 86400, 1000) == 1000
