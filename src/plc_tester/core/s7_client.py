"""Snap7 client wrapper running in a dedicated QThread.

Provides connection management, cyclic reading, and automatic reconnection
for S7Comm communication with Siemens S7-1200/1500 PLCs.
"""

from __future__ import annotations

import contextlib
import logging
import struct
import time
from typing import Any

import snap7
from PySide6.QtCore import QMutex, QThread, Signal
from snap7.util import get_bool, get_dint, get_int, get_real

from plc_tester.core.parser import S7Address, S7AreaCode, S7DataType, parse_s7_address

logger = logging.getLogger(__name__)

# Reconnect interval in seconds
_RECONNECT_INTERVAL = 5.0


class S7Worker(QThread):
    """Worker thread for S7Comm (Snap7) communication.

    Signals:
        connected: Emitted when connection is established.
        disconnected: Emitted when connection is lost.
        values_read: Emitted with list of (row_index, value_str, error_str) tuples.
        log_message: Emitted with log text for the UI log panel.
    """

    connected = Signal()
    disconnected = Signal()
    values_read = Signal(list)  # list[tuple[int, str, str]]
    log_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._client = snap7.client.Client()
        self._mutex = QMutex()
        self._running = False
        self._cyclic = False
        self._interval_ms = 1000
        self._ip = ""
        self._rack = 0
        self._slot = 1
        self._variables: list[dict[str, str]] = []
        self._should_connect = False
        self._should_disconnect = False

    # ---- Public API (called from GUI thread) ----

    def request_connect(self, ip: str, rack: int, slot: int) -> None:
        """Request connection to PLC."""
        self._mutex.lock()
        self._ip = ip
        self._rack = rack
        self._slot = slot
        self._should_connect = True
        self._mutex.unlock()

    def request_disconnect(self) -> None:
        """Request disconnection from PLC."""
        self._mutex.lock()
        self._should_disconnect = True
        self._mutex.unlock()

    def set_cyclic(self, active: bool, interval_ms: int) -> None:
        """Enable or disable cyclic reading."""
        self._mutex.lock()
        self._cyclic = active
        self._interval_ms = max(250, min(5000, interval_ms))
        self._mutex.unlock()

    def set_variables(self, variables: list[dict[str, str]]) -> None:
        """Update variable definitions from the UI table."""
        self._mutex.lock()
        self._variables = list(variables)
        self._mutex.unlock()

    def stop(self) -> None:
        """Stop the worker thread gracefully."""
        self._mutex.lock()
        self._running = False
        self._mutex.unlock()
        self.wait(3000)

    # ---- Thread run loop ----

    def run(self) -> None:  # noqa: C901
        """Main worker loop – handles connect/disconnect/read requests."""
        self._running = True
        is_connected = False
        last_reconnect = 0.0

        while self._running:
            self._mutex.lock()
            should_connect = self._should_connect
            should_disconnect = self._should_disconnect
            cyclic = self._cyclic
            interval_ms = self._interval_ms
            variables = list(self._variables)
            ip = self._ip
            rack = self._rack
            slot = self._slot
            self._should_connect = False
            self._should_disconnect = False
            self._mutex.unlock()

            # Handle disconnect request
            if should_disconnect and is_connected:
                with contextlib.suppress(Exception):
                    self._client.disconnect()
                is_connected = False
                self.disconnected.emit()
                self.log_message.emit("🔌 Disconnected from PLC.")

            # Handle connect request
            if should_connect:
                is_connected = self._do_connect(ip, rack, slot)
                if is_connected:
                    last_reconnect = 0.0

            # Auto-reconnect on connection loss
            if not is_connected and not should_connect and cyclic:
                now = time.monotonic()
                if now - last_reconnect >= _RECONNECT_INTERVAL:
                    last_reconnect = now
                    self.log_message.emit("🔄 Attempting auto-reconnect...")
                    is_connected = self._do_connect(ip, rack, slot)

            # Cyclic read
            if is_connected and cyclic and variables:
                results = self._read_all(variables)
                self.values_read.emit(results)

                # Check if connection was lost during read
                if not self._client.get_connected():
                    is_connected = False
                    self.disconnected.emit()
                    self.log_message.emit("❌ Connection lost during read.")

            # Sleep for interval (or shorter poll if not cyclic)
            sleep_ms = interval_ms if cyclic else 200
            self.msleep(sleep_ms)

        # Cleanup
        if is_connected:
            with contextlib.suppress(Exception):
                self._client.disconnect()

    def _do_connect(self, ip: str, rack: int, slot: int) -> bool:
        """Attempt connection to the PLC."""
        try:
            self._client.connect(ip, rack, slot)
            if self._client.get_connected():
                self.connected.emit()
                self.log_message.emit(f"✅ Connected to {ip} (rack={rack}, slot={slot}).")
                return True
            self.log_message.emit(f"⚠️ Connection to {ip} failed – no error but not connected.")
            return False
        except Exception as exc:
            self.disconnected.emit()
            self.log_message.emit(f"❌ Connection error: {exc}")
            return False

    def _read_all(self, variables: list[dict[str, str]]) -> list[tuple[int, str, str]]:
        """Read all configured variables, returning per-row results."""
        results: list[tuple[int, str, str]] = []

        for idx, var in enumerate(variables):
            dtype = var.get("type", "INT")
            area = var.get("area", "DB")
            addr_str = var.get("address", "")

            if not addr_str.strip():
                results.append((idx, "", ""))
                continue

            try:
                parsed = parse_s7_address(dtype, area, addr_str)
                value = self._read_single(parsed)
                results.append((idx, str(value), ""))
            except Exception as exc:
                results.append((idx, "", str(exc)))

        return results

    def _read_single(self, addr: S7Address) -> Any:
        """Read and decode a single S7 variable."""
        area_map = {
            S7AreaCode.DB: snap7.type.Areas.DB,
            S7AreaCode.MK: snap7.type.Areas.MK,
            S7AreaCode.PE: snap7.type.Areas.PE,
            S7AreaCode.PA: snap7.type.Areas.PA,
        }
        snap7_area = area_map[addr.area_code]

        raw = self._client.read_area(snap7_area, addr.db_number, addr.start, addr.size)

        return _decode_value(raw, addr)


def _decode_value(data: bytearray, addr: S7Address) -> Any:
    """Decode raw bytes into Python value based on S7 data type.

    Args:
        data: Raw byte data read from PLC.
        addr: Parsed address with type information.

    Returns:
        Decoded Python value (bool, int, or float).
    """
    if addr.data_type == S7DataType.BOOL:
        return get_bool(data, 0, addr.bit)

    if addr.data_type == S7DataType.INT:
        return get_int(data, 0)

    if addr.data_type == S7DataType.WORD:
        # WORD is unsigned 16-bit
        return struct.unpack(">H", data[:2])[0]

    if addr.data_type == S7DataType.DINT:
        return get_dint(data, 0)

    if addr.data_type == S7DataType.REAL:
        return round(get_real(data, 0), 6)

    return data.hex()
