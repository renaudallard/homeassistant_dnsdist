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

"""Tests for services utility functions."""

from custom_components.dnsdist.services import _encode_backend_segment


class TestEncodeBackendSegment:
    def test_valid_ip_port(self):
        result = _encode_backend_segment("192.168.1.1:53")
        assert result is not None
        assert result != ""

    def test_none_returns_none(self):
        assert _encode_backend_segment(None) is None

    def test_empty_string_returns_none(self):
        assert _encode_backend_segment("") is None

    def test_whitespace_only_returns_none(self):
        assert _encode_backend_segment("   ") is None

    def test_non_string_returns_none(self):
        assert _encode_backend_segment(12345) is None  # type: ignore[arg-type]
        assert _encode_backend_segment([]) is None  # type: ignore[arg-type]

    def test_control_character_rejected(self):
        assert _encode_backend_segment("192.168.1.1\x00:53") is None
        assert _encode_backend_segment("\x01bad") is None
        assert _encode_backend_segment("ba\x02d") is None

    def test_del_character_rejected(self):
        assert _encode_backend_segment("bad\x7f") is None

    def test_colon_is_percent_encoded(self):
        result = _encode_backend_segment("192.168.1.1:53")
        assert result is not None
        assert ":" not in result
        assert "%3A" in result or "%3a" in result

    def test_slash_is_percent_encoded(self):
        result = _encode_backend_segment("192.168.1.0/24")
        assert result is not None
        assert "/" not in result
        assert "%2F" in result or "%2f" in result

    def test_plain_hostname_passthrough(self):
        result = _encode_backend_segment("mybackend")
        assert result == "mybackend"

    def test_whitespace_stripped_before_validation(self):
        # Leading/trailing whitespace is stripped — valid backend passes
        result = _encode_backend_segment("  192.168.1.1:53  ")
        assert result is not None
        assert result != ""
