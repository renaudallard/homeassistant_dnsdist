"""Tests for input validation functions."""

import pytest
import voluptuous as vol

from custom_components.dnsdist.config_flow import validate_host


class TestValidateHost:
    """Tests for validate_host function."""

    # Valid hostnames
    def test_simple_hostname(self):
        assert validate_host("localhost") == "localhost"
        assert validate_host("myserver") == "myserver"

    def test_fqdn(self):
        assert validate_host("server.example.com") == "server.example.com"
        assert validate_host("dns.google.com") == "dns.google.com"

    def test_hostname_with_numbers(self):
        assert validate_host("server1") == "server1"
        assert validate_host("ns1.example.com") == "ns1.example.com"

    def test_hostname_with_hyphens(self):
        assert validate_host("my-server") == "my-server"
        assert validate_host("my-dns-server.example.com") == "my-dns-server.example.com"

    def test_hostname_strips_whitespace(self):
        assert validate_host("  server.example.com  ") == "server.example.com"

    # Valid IPv4 addresses
    def test_ipv4_valid(self):
        assert validate_host("192.168.1.1") == "192.168.1.1"
        assert validate_host("10.0.0.1") == "10.0.0.1"
        assert validate_host("255.255.255.255") == "255.255.255.255"
        assert validate_host("0.0.0.0") == "0.0.0.0"

    def test_ipv4_edge_cases(self):
        assert validate_host("1.2.3.4") == "1.2.3.4"
        assert validate_host("127.0.0.1") == "127.0.0.1"

    # Valid IPv6 addresses
    def test_ipv6_full(self):
        assert validate_host("2001:0db8:85a3:0000:0000:8a2e:0370:7334") == "2001:0db8:85a3:0000:0000:8a2e:0370:7334"

    def test_ipv6_compressed(self):
        assert validate_host("::1") == "::1"
        assert validate_host("::") == "::"

    def test_ipv6_with_brackets(self):
        assert validate_host("[::1]") == "[::1]"
        assert validate_host("[2001:db8::1]") == "[2001:db8::1]"

    # Invalid inputs - empty/None
    def test_empty_string_raises(self):
        with pytest.raises(vol.Invalid, match="non-empty string"):
            validate_host("")

    def test_none_raises(self):
        with pytest.raises(vol.Invalid, match="non-empty string"):
            validate_host(None)

    def test_whitespace_only_raises(self):
        # After strip(), becomes empty string which fails hostname validation
        with pytest.raises(vol.Invalid, match="Invalid host format"):
            validate_host("   ")

    # Invalid IPv4 addresses
    def test_ipv4_out_of_range(self):
        with pytest.raises(vol.Invalid, match="Invalid IPv4"):
            validate_host("256.1.1.1")
        with pytest.raises(vol.Invalid, match="Invalid IPv4"):
            validate_host("192.168.1.256")

    def test_ipv4_too_few_octets(self):
        with pytest.raises(vol.Invalid, match="Invalid IPv4"):
            validate_host("192.168.1")
        with pytest.raises(vol.Invalid, match="Invalid IPv4"):
            validate_host("192.168")

    def test_ipv4_too_many_octets(self):
        with pytest.raises(vol.Invalid, match="Invalid IPv4"):
            validate_host("192.168.1.1.1")

    def test_ipv4_with_leading_zeros_style(self):
        # These should work as they're valid
        assert validate_host("192.168.01.01") == "192.168.01.01"

    # Invalid hostnames
    def test_hostname_starting_with_hyphen(self):
        with pytest.raises(vol.Invalid, match="Invalid host format"):
            validate_host("-invalid.com")

    def test_hostname_ending_with_hyphen(self):
        with pytest.raises(vol.Invalid, match="Invalid host format"):
            validate_host("invalid-.com")

    def test_hostname_with_invalid_chars(self):
        with pytest.raises(vol.Invalid, match="Invalid host format"):
            validate_host("server@domain.com")
        with pytest.raises(vol.Invalid, match="Invalid host format"):
            validate_host("server:8080")

    def test_hostname_label_too_long(self):
        # Labels must be <= 63 characters
        long_label = "a" * 64
        with pytest.raises(vol.Invalid, match="Invalid host format"):
            validate_host(f"{long_label}.example.com")

    def test_hostname_too_long(self):
        # Total hostname must be <= 253 characters
        # Create a hostname that's too long
        long_hostname = ".".join(["a" * 60] * 5)  # 5 * 60 + 4 dots = 304 chars
        with pytest.raises(vol.Invalid, match="Invalid host format"):
            validate_host(long_hostname)

    # Edge cases
    def test_single_char_hostname(self):
        assert validate_host("a") == "a"

    def test_single_digit_rejected_as_invalid_ip(self):
        # Single digit is treated as malformed IPv4, not a hostname
        with pytest.raises(vol.Invalid, match="Invalid IPv4"):
            validate_host("1")

    def test_numeric_hostname_not_ip(self):
        # A string like "12345" that's all numeric but not a valid IP
        with pytest.raises(vol.Invalid, match="Invalid IPv4"):
            validate_host("12345")

    def test_partial_ip_like_string(self):
        with pytest.raises(vol.Invalid, match="Invalid IPv4"):
            validate_host("192.168")
