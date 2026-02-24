"""Unit tests for the S7 address parser.

Tests cover all supported address formats (DB, M, I, Q areas)
with various data types and error cases.
"""

from __future__ import annotations

import pytest

from plc_tester.core.parser import S7Address, S7AreaCode, S7DataType, parse_s7_address

# ──────────────────────────────────────────────────────────────
# DB area tests
# ──────────────────────────────────────────────────────────────


class TestDBAddresses:
    """Tests for Data Block address parsing."""

    def test_db_bool(self):
        result = parse_s7_address("BOOL", "DB", "DB1.DBX0.0")
        assert result == S7Address(
            area_code=S7AreaCode.DB,
            db_number=1,
            start=0,
            bit=0,
            size=1,
            data_type=S7DataType.BOOL,
        )

    def test_db_bool_bit7(self):
        result = parse_s7_address("BOOL", "DB", "DB10.DBX5.7")
        assert result.db_number == 10
        assert result.start == 5
        assert result.bit == 7
        assert result.data_type == S7DataType.BOOL

    def test_db_int(self):
        result = parse_s7_address("INT", "DB", "DB1.DBW0")
        assert result == S7Address(
            area_code=S7AreaCode.DB,
            db_number=1,
            start=0,
            bit=0,
            size=2,
            data_type=S7DataType.INT,
        )

    def test_db_word(self):
        result = parse_s7_address("WORD", "DB", "DB2.DBW4")
        assert result.size == 2
        assert result.data_type == S7DataType.WORD

    def test_db_dint(self):
        result = parse_s7_address("DINT", "DB", "DB3.DBD8")
        assert result == S7Address(
            area_code=S7AreaCode.DB,
            db_number=3,
            start=8,
            bit=0,
            size=4,
            data_type=S7DataType.DINT,
        )

    def test_db_real(self):
        result = parse_s7_address("REAL", "DB", "DB1.DBD12")
        assert result.size == 4
        assert result.data_type == S7DataType.REAL

    def test_db_byte(self):
        result = parse_s7_address("INT", "DB", "DB5.DBB3")
        assert result.size == 1
        assert result.start == 3

    def test_db_case_insensitive(self):
        result = parse_s7_address("int", "db", "db1.dbw0")
        assert result.area_code == S7AreaCode.DB
        assert result.db_number == 1

    def test_db_large_number(self):
        result = parse_s7_address("INT", "DB", "DB999.DBW100")
        assert result.db_number == 999
        assert result.start == 100


# ──────────────────────────────────────────────────────────────
# M / I / Q area tests
# ──────────────────────────────────────────────────────────────


class TestMIQAddresses:
    """Tests for Merker, Input, and Output address parsing."""

    def test_merker_bit(self):
        result = parse_s7_address("BOOL", "M", "MX0.1")
        assert result == S7Address(
            area_code=S7AreaCode.MK,
            db_number=0,
            start=0,
            bit=1,
            size=1,
            data_type=S7DataType.BOOL,
        )

    def test_merker_word(self):
        result = parse_s7_address("INT", "M", "MW10")
        assert result == S7Address(
            area_code=S7AreaCode.MK,
            db_number=0,
            start=10,
            bit=0,
            size=2,
            data_type=S7DataType.INT,
        )

    def test_merker_dword(self):
        result = parse_s7_address("DINT", "M", "MD20")
        assert result.size == 4
        assert result.data_type == S7DataType.DINT

    def test_merker_byte(self):
        result = parse_s7_address("INT", "M", "MB5")
        assert result.size == 1
        assert result.start == 5

    def test_input_word(self):
        result = parse_s7_address("WORD", "I", "IW0")
        assert result == S7Address(
            area_code=S7AreaCode.PE,
            db_number=0,
            start=0,
            bit=0,
            size=2,
            data_type=S7DataType.WORD,
        )

    def test_input_bit(self):
        result = parse_s7_address("BOOL", "I", "IX0.3")
        assert result.area_code == S7AreaCode.PE
        assert result.bit == 3

    def test_output_dword(self):
        result = parse_s7_address("DINT", "Q", "QD0")
        assert result == S7Address(
            area_code=S7AreaCode.PA,
            db_number=0,
            start=0,
            bit=0,
            size=4,
            data_type=S7DataType.DINT,
        )

    def test_output_bit(self):
        result = parse_s7_address("BOOL", "Q", "QX1.5")
        assert result.area_code == S7AreaCode.PA
        assert result.start == 1
        assert result.bit == 5

    def test_m_shorthand_bit(self):
        """Test M{byte}.{bit} shorthand (without X)."""
        result = parse_s7_address("BOOL", "M", "M0.3")
        assert result.area_code == S7AreaCode.MK
        assert result.bit == 3
        assert result.data_type == S7DataType.BOOL


# ──────────────────────────────────────────────────────────────
# Error / invalid input tests
# ──────────────────────────────────────────────────────────────


class TestParserErrors:
    """Tests for invalid address formats and error handling."""

    def test_invalid_db_format(self):
        with pytest.raises(ValueError, match="Invalid DB address format"):
            parse_s7_address("INT", "DB", "DB1.INVALID")

    def test_db_bool_missing_bit(self):
        with pytest.raises(ValueError, match="BOOL address requires bit offset"):
            parse_s7_address("BOOL", "DB", "DB1.DBX0")

    def test_unknown_area(self):
        with pytest.raises(ValueError, match="Unknown area"):
            parse_s7_address("INT", "X", "XW0")

    def test_area_mismatch_word(self):
        with pytest.raises(ValueError, match="Area mismatch"):
            parse_s7_address("INT", "M", "IW0")

    def test_area_mismatch_bit(self):
        with pytest.raises(ValueError, match="Area mismatch"):
            parse_s7_address("BOOL", "Q", "MX0.1")

    def test_invalid_merker_format(self):
        with pytest.raises(ValueError, match="Invalid M address format"):
            parse_s7_address("INT", "M", "MFOO")

    def test_empty_address(self):
        with pytest.raises(ValueError):
            parse_s7_address("INT", "DB", "")

    def test_whitespace_handling(self):
        """Whitespace around the address should be stripped."""
        result = parse_s7_address("INT", "DB", "  DB1.DBW0  ")
        assert result.db_number == 1


# ──────────────────────────────────────────────────────────────
# Data type enum tests
# ──────────────────────────────────────────────────────────────


class TestS7DataType:
    """Tests for the S7DataType enum values."""

    def test_bool_size(self):
        assert S7DataType.BOOL == 1

    def test_int_size(self):
        assert S7DataType.INT == 2

    def test_word_size(self):
        assert S7DataType.WORD == 2

    def test_dint_size(self):
        assert S7DataType.DINT == 4

    def test_real_size(self):
        assert S7DataType.REAL == 4
