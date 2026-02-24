"""S7 address parser for Snap7 communication.

Parses S7 address strings (e.g. DB1.DBX0.0, MW10, IW2, QD4) into structured
objects that can be used for read/write operations with snap7.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum


class S7AreaCode(IntEnum):
    """Snap7-compatible area codes."""

    PE = 0x81  # Process inputs
    PA = 0x82  # Process outputs
    MK = 0x83  # Merkers (flags)
    DB = 0x84  # Data blocks
    CT = 0x1C  # Counters
    TM = 0x1D  # Timers


class S7DataType(IntEnum):
    """Data type sizes in bytes (for read length calculation)."""

    BOOL = 1
    INT = 2
    WORD = 2
    DINT = 4
    REAL = 4


@dataclass(frozen=True, slots=True)
class S7Address:
    """Parsed S7 address ready for snap7 read operations.

    Attributes:
        area_code: Snap7 area code (DB, MK, PE, PA).
        db_number: Data block number (0 for non-DB areas).
        start: Byte offset.
        bit: Bit offset (0-7, only meaningful for BOOL).
        size: Number of bytes to read.
        data_type: The data type to decode.
    """

    area_code: S7AreaCode
    db_number: int
    start: int
    bit: int
    size: int
    data_type: S7DataType


# ---------------------------------------------------------------------------
# Regex patterns for different S7 addressing modes
# ---------------------------------------------------------------------------

# DB area: DB{n}.DBX{byte}.{bit} | DB{n}.DBB{byte} | DB{n}.DBW{byte} | DB{n}.DBD{byte}
_RE_DB = re.compile(
    r"^DB(\d+)\.DB([XBWD])(\d+)(?:\.(\d))?$",
    re.IGNORECASE,
)

# Merker / Input / Output bit:  MX{byte}.{bit} | IX{byte}.{bit} | QX{byte}.{bit}
_RE_BIT = re.compile(
    r"^([MIQ])X?(\d+)\.(\d)$",
    re.IGNORECASE,
)

# Merker / Input / Output byte/word/dword: MB{b} | MW{b} | MD{b} | IB | IW | ID | QB | QW | QD
_RE_WORD = re.compile(
    r"^([MIQ])([BWD])(\d+)$",
    re.IGNORECASE,
)

# Mapping from area letter to snap7 area code
_AREA_MAP: dict[str, S7AreaCode] = {
    "M": S7AreaCode.MK,
    "I": S7AreaCode.PE,
    "Q": S7AreaCode.PA,
}

# Mapping from size char to (size_bytes, data_type)
_SIZE_MAP: dict[str, tuple[int, S7DataType]] = {
    "X": (1, S7DataType.BOOL),
    "B": (1, S7DataType.INT),  # Byte – read 1 byte, interpret as INT
    "W": (2, S7DataType.WORD),
    "D": (4, S7DataType.DINT),
}


def parse_s7_address(data_type_name: str, area_name: str, address_str: str) -> S7Address:
    """Parse an S7 address string into an S7Address object.

    Args:
        data_type_name: Data type label (BOOL, INT, REAL, DINT, WORD).
        area_name: Area label (DB, I, Q, M).
        address_str: Address string, e.g. ``DB1.DBX0.0``, ``MW10``, ``IW2``.

    Returns:
        Parsed ``S7Address`` ready for snap7 read operations.

    Raises:
        ValueError: When the address format is invalid.
    """
    address_str = address_str.strip()
    data_type = S7DataType[data_type_name.upper()]

    # ----- DB area -----
    if area_name.upper() == "DB":
        return _parse_db_address(data_type, address_str)

    # ----- M / I / Q areas -----
    return _parse_miq_address(data_type, area_name.upper(), address_str)


def _parse_db_address(data_type: S7DataType, address_str: str) -> S7Address:
    """Parse a Data Block address like ``DB1.DBX0.0`` or ``DB1.DBW4``."""
    match = _RE_DB.match(address_str)
    if not match:
        raise ValueError(
            f"Invalid DB address format: '{address_str}'. "
            f"Expected DB{{n}}.DBX{{b}}.{{bit}}, DB{{n}}.DBW{{b}}, DB{{n}}.DBB{{b}}, "
            f"or DB{{n}}.DBD{{b}}."
        )

    db_number = int(match.group(1))
    size_char = match.group(2).upper()
    byte_offset = int(match.group(3))
    bit_offset = int(match.group(4)) if match.group(4) is not None else 0

    if size_char == "X" and match.group(4) is None:
        raise ValueError(
            f"BOOL address requires bit offset: '{address_str}'. "
            f"Expected format: DB{{n}}.DBX{{b}}.{{bit}}."
        )

    if size_char == "X" and not (0 <= bit_offset <= 7):
        raise ValueError(f"Bit offset must be 0-7, got {bit_offset} in '{address_str}'.")

    size_bytes = _SIZE_MAP[size_char][0]

    # For REAL data type on DBD addresses, override size to 4
    if data_type == S7DataType.REAL:
        size_bytes = 4

    return S7Address(
        area_code=S7AreaCode.DB,
        db_number=db_number,
        start=byte_offset,
        bit=bit_offset,
        size=size_bytes,
        data_type=data_type,
    )


def _parse_miq_address(data_type: S7DataType, area_name: str, address_str: str) -> S7Address:
    """Parse Merker / Input / Output addresses like ``MW10``, ``IW2``, ``QD4``, ``MX0.1``."""
    area_code = _AREA_MAP.get(area_name)
    if area_code is None:
        raise ValueError(f"Unknown area: '{area_name}'. Expected one of: DB, M, I, Q.")

    # Try bit pattern first (MX0.1, IX0.3, etc. or shorthand M0.1)
    match = _RE_BIT.match(address_str)
    if match:
        letter = match.group(1).upper()
        if letter != area_name:
            raise ValueError(
                f"Area mismatch: area='{area_name}' but address starts with '{letter}'."
            )
        byte_offset = int(match.group(2))
        bit_offset = int(match.group(3))
        if not (0 <= bit_offset <= 7):
            raise ValueError(f"Bit offset must be 0-7, got {bit_offset} in '{address_str}'.")
        return S7Address(
            area_code=area_code,
            db_number=0,
            start=byte_offset,
            bit=bit_offset,
            size=1,
            data_type=S7DataType.BOOL,
        )

    # Try word/byte/dword pattern (MW10, IW2, QD4, etc.)
    match = _RE_WORD.match(address_str)
    if match:
        letter = match.group(1).upper()
        if letter != area_name:
            raise ValueError(
                f"Area mismatch: area='{area_name}' but address starts with '{letter}'."
            )
        size_char = match.group(2).upper()
        byte_offset = int(match.group(3))
        size_bytes, default_type = _SIZE_MAP[size_char]

        # If user explicitly set REAL as data type, override size
        if data_type == S7DataType.REAL:
            size_bytes = 4

        effective_type = data_type if data_type != default_type else default_type

        return S7Address(
            area_code=area_code,
            db_number=0,
            start=byte_offset,
            bit=0,
            size=size_bytes,
            data_type=effective_type,
        )

    raise ValueError(
        f"Invalid {area_name} address format: '{address_str}'. "
        f"Expected {area_name}X{{b}}.{{bit}}, {area_name}B{{b}}, "
        f"{area_name}W{{b}}, or {area_name}D{{b}}."
    )
