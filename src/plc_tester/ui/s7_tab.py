"""S7Comm tab widget for the PLC Tester application.

Provides connection configuration, variable table (10 rows),
cyclic read controls, and status display for Snap7 communication.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from plc_tester.core.s7_client import S7Worker

# Column indices
COL_TYPE = 0
COL_AREA = 1
COL_ADDR = 2
COL_VALUE = 3
COL_STATUS = 4

DATA_TYPES = ["BOOL", "INT", "REAL", "DINT", "WORD"]
AREAS = ["DB", "I", "Q", "M"]
NUM_ROWS = 10


class S7Tab(QWidget):
    """Tab widget for S7Comm (Snap7) protocol."""

    def __init__(self, log_callback, parent=None):
        """Initialize the S7 tab.

        Args:
            log_callback: Callable to send log messages to the main window.
            parent: Parent widget.
        """
        super().__init__(parent)
        self._log = log_callback
        self._worker = S7Worker()
        self._is_connected = False
        self._init_ui()
        self._init_worker()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Connection group ──
        conn_group = QGroupBox("🔗 Connection Settings")
        conn_layout = QHBoxLayout(conn_group)

        conn_layout.addWidget(QLabel("IP:"))
        self._ip_edit = QLineEdit("192.168.0.1")
        self._ip_edit.setMinimumWidth(140)
        conn_layout.addWidget(self._ip_edit)

        conn_layout.addWidget(QLabel("Rack:"))
        self._rack_spin = QSpinBox()
        self._rack_spin.setRange(0, 7)
        self._rack_spin.setValue(0)
        conn_layout.addWidget(self._rack_spin)

        conn_layout.addWidget(QLabel("Slot:"))
        self._slot_spin = QSpinBox()
        self._slot_spin.setRange(0, 31)
        self._slot_spin.setValue(1)
        conn_layout.addWidget(self._slot_spin)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setObjectName("connectBtn")
        self._connect_btn.clicked.connect(self._on_connect)
        conn_layout.addWidget(self._connect_btn)

        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setObjectName("disconnectBtn")
        self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        conn_layout.addWidget(self._disconnect_btn)

        self._status_label = QLabel("⚪ Disconnected")
        self._status_label.setObjectName("statusLabel")
        conn_layout.addWidget(self._status_label)
        conn_layout.addStretch()

        layout.addWidget(conn_group)

        # ── Cyclic read controls ──
        cycle_group = QGroupBox("🔄 Cyclic Read")
        cycle_layout = QHBoxLayout(cycle_group)

        self._cyclic_cb = QCheckBox("Active")
        self._cyclic_cb.toggled.connect(self._on_cyclic_changed)
        cycle_layout.addWidget(self._cyclic_cb)

        cycle_layout.addWidget(QLabel("Interval (ms):"))
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(250, 5000)
        self._interval_spin.setSingleStep(250)
        self._interval_spin.setValue(1000)
        self._interval_spin.valueChanged.connect(self._on_cyclic_changed)
        cycle_layout.addWidget(self._interval_spin)

        self._read_once_btn = QPushButton("📖 Read Once")
        self._read_once_btn.clicked.connect(self._on_read_once)
        cycle_layout.addWidget(self._read_once_btn)

        cycle_layout.addStretch()
        layout.addWidget(cycle_group)

        # ── Variable table ──
        table_group = QGroupBox("📋 Variables")
        table_layout = QVBoxLayout(table_group)

        self._table = QTableWidget(NUM_ROWS, 5)
        self._table.setHorizontalHeaderLabels(["Type", "Area", "Address", "Value", "Status"])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(COL_ADDR, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_VALUE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_TYPE, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_AREA, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(COL_TYPE, 90)
        self._table.setColumnWidth(COL_AREA, 70)

        for row in range(NUM_ROWS):
            # Type dropdown
            type_combo = QComboBox()
            type_combo.addItems(DATA_TYPES)
            self._table.setCellWidget(row, COL_TYPE, type_combo)

            # Area dropdown
            area_combo = QComboBox()
            area_combo.addItems(AREAS)
            self._table.setCellWidget(row, COL_AREA, area_combo)

            # Address input
            addr_item = QTableWidgetItem("DB1.DBW0")
            self._table.setItem(row, COL_ADDR, addr_item)

            # Value (read-only)
            val_item = QTableWidgetItem("")
            val_item.setFlags(val_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, COL_VALUE, val_item)

            # Status (read-only)
            status_item = QTableWidgetItem("")
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, COL_STATUS, status_item)

        table_layout.addWidget(self._table)
        layout.addWidget(table_group)

    def _init_worker(self) -> None:
        """Set up worker signals."""
        self._worker.connected.connect(self._on_worker_connected)
        self._worker.disconnected.connect(self._on_worker_disconnected)
        self._worker.values_read.connect(self._on_values_read)
        self._worker.log_message.connect(lambda msg: self._log(f"[S7] {msg}"))
        self._worker.start()

    # ── Slot handlers ──

    @Slot()
    def _on_connect(self) -> None:
        ip = self._ip_edit.text().strip()
        rack = self._rack_spin.value()
        slot = self._slot_spin.value()
        if not ip:
            self._log("[S7] ⚠️ IP address is empty.")
            return
        self._worker.set_variables(self._collect_variables())
        self._worker.request_connect(ip, rack, slot)
        self._status_label.setText("🟡 Connecting...")

    @Slot()
    def _on_disconnect(self) -> None:
        self._worker.request_disconnect()

    @Slot()
    def _on_cyclic_changed(self) -> None:
        active = self._cyclic_cb.isChecked()
        interval = self._interval_spin.value()
        self._worker.set_variables(self._collect_variables())
        self._worker.set_cyclic(active, interval)

    @Slot()
    def _on_read_once(self) -> None:
        """Trigger a single read by briefly enabling cyclic."""
        if not self._is_connected:
            self._log("[S7] ⚠️ Not connected.")
            return
        self._worker.set_variables(self._collect_variables())
        # Temporarily enable cyclic for one pass
        self._worker.set_cyclic(True, 100)
        # Disable after a short delay
        from PySide6.QtCore import QTimer

        QTimer.singleShot(500, lambda: self._worker.set_cyclic(
            self._cyclic_cb.isChecked(), self._interval_spin.value()
        ))

    @Slot()
    def _on_worker_connected(self) -> None:
        self._is_connected = True
        self._status_label.setText("🟢 Connected")
        self._status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        self._connect_btn.setEnabled(False)
        self._disconnect_btn.setEnabled(True)

    @Slot()
    def _on_worker_disconnected(self) -> None:
        self._is_connected = False
        self._status_label.setText("🔴 Disconnected")
        self._status_label.setStyleSheet("color: #f44336; font-weight: bold;")
        self._connect_btn.setEnabled(True)
        self._disconnect_btn.setEnabled(False)

    @Slot(list)
    def _on_values_read(self, results: list[tuple[int, str, str]]) -> None:
        """Update the table with read results."""
        for row_idx, value, error in results:
            if row_idx >= self._table.rowCount():
                continue

            val_item = self._table.item(row_idx, COL_VALUE)
            status_item = self._table.item(row_idx, COL_STATUS)

            if error:
                val_item.setText("")
                status_item.setText(error)
                status_item.setForeground(QColor("#f44336"))
            elif value:
                val_item.setText(value)
                status_item.setText("OK")
                status_item.setForeground(QColor("#4CAF50"))
            else:
                val_item.setText("")
                status_item.setText("")

    # ── Helpers ──

    def _collect_variables(self) -> list[dict[str, str]]:
        """Collect variable definitions from the table."""
        variables = []
        for row in range(NUM_ROWS):
            type_combo = self._table.cellWidget(row, COL_TYPE)
            area_combo = self._table.cellWidget(row, COL_AREA)
            addr_item = self._table.item(row, COL_ADDR)
            variables.append({
                "type": type_combo.currentText() if type_combo else "INT",
                "area": area_combo.currentText() if area_combo else "DB",
                "address": addr_item.text() if addr_item else "",
            })
        return variables

    def get_config(self) -> dict:
        """Return current tab configuration for persistence."""
        return {
            "ip": self._ip_edit.text(),
            "rack": self._rack_spin.value(),
            "slot": self._slot_spin.value(),
            "interval_ms": self._interval_spin.value(),
            "cyclic_active": self._cyclic_cb.isChecked(),
            "variables": self._collect_variables(),
        }

    def load_config(self, cfg: dict) -> None:
        """Load configuration into the tab."""
        self._ip_edit.setText(cfg.get("ip", "192.168.0.1"))
        self._rack_spin.setValue(cfg.get("rack", 0))
        self._slot_spin.setValue(cfg.get("slot", 1))
        self._interval_spin.setValue(cfg.get("interval_ms", 1000))
        self._cyclic_cb.setChecked(cfg.get("cyclic_active", False))

        variables = cfg.get("variables", [])
        for row in range(min(NUM_ROWS, len(variables))):
            var = variables[row]
            type_combo = self._table.cellWidget(row, COL_TYPE)
            area_combo = self._table.cellWidget(row, COL_AREA)
            addr_item = self._table.item(row, COL_ADDR)

            if type_combo and var.get("type"):
                idx = type_combo.findText(var["type"])
                if idx >= 0:
                    type_combo.setCurrentIndex(idx)
            if area_combo and var.get("area"):
                idx = area_combo.findText(var["area"])
                if idx >= 0:
                    area_combo.setCurrentIndex(idx)
            if addr_item:
                addr_item.setText(var.get("address", ""))

    def shutdown(self) -> None:
        """Stop the worker thread."""
        self._worker.set_cyclic(False, 1000)
        self._worker.stop()
