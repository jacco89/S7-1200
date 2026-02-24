"""OPC UA tab widget for the PLC Tester application.

Provides connection configuration, node table (10 rows),
cyclic read controls, node browser dialog, and status display
for OPC UA communication.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from plc_tester.core.opcua_client import BrowseWorker, OpcuaWorker

# Column indices
COL_NODE_ID = 0
COL_VALUE = 1
COL_STATUS = 2

NUM_ROWS = 10


# ──────────────────────────────────────────────────────────────────
# Node Browser Dialog
# ──────────────────────────────────────────────────────────────────


class NodeBrowserDialog(QDialog):
    """Modal dialog that browses the OPC UA server address space.

    Shows a tree of nodes; double-clicking a variable node accepts
    and returns its Node ID to the caller.
    """

    def __init__(self, url: str, username: str, password: str, log_callback, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🌳 OPC UA Node Browser")
        self.setMinimumSize(650, 500)
        self.resize(750, 550)
        self._log = log_callback
        self._selected_node_id: str = ""
        self._worker: BrowseWorker | None = None

        self._init_ui()
        self._start_browse(url, username, password)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Info label
        info = QLabel("Double-click a variable (📊) to select its Node ID.")
        info.setStyleSheet("color: #89b4fa; font-weight: bold; padding: 4px;")
        layout.addWidget(info)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setTextVisible(True)
        self._progress.setFormat("Browsing server address space...")
        layout.addWidget(self._progress)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name", "Node ID"])
        self._tree.setColumnWidth(0, 350)
        self._tree.setAlternatingRowColors(True)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.setFont(QFont("Segoe UI", 11))
        layout.addWidget(self._tree)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._select_btn = QPushButton("✅ Select")
        self._select_btn.setEnabled(False)
        self._select_btn.clicked.connect(self._on_select)
        btn_layout.addWidget(self._select_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _start_browse(self, url: str, username: str, password: str) -> None:
        """Launch the BrowseWorker thread."""
        self._worker = BrowseWorker(url, username, password, parent=self)
        self._worker.browse_done.connect(self._on_browse_done)
        self._worker.browse_error.connect(self._on_browse_error)
        self._worker.log_message.connect(lambda msg: self._log(f"[Browse] {msg}"))
        self._worker.start()

    @Slot(list)
    def _on_browse_done(self, tree: list[dict]) -> None:
        """Populate the tree widget with browsed nodes."""
        self._progress.hide()
        self._populate_tree(self._tree.invisibleRootItem(), tree)
        self._tree.expandToDepth(1)
        self._select_btn.setEnabled(True)

    @Slot(str)
    def _on_browse_error(self, error: str) -> None:
        """Show error in the tree widget."""
        self._progress.hide()
        item = QTreeWidgetItem(["❌ " + error, ""])
        item.setForeground(0, QColor("#f44336"))
        self._tree.addTopLevelItem(item)

    def _populate_tree(self, parent_item: QTreeWidgetItem, nodes: list[dict]) -> None:
        """Recursively add nodes to the tree."""
        for node in nodes:
            name = node.get("name", "?")
            node_id = node.get("node_id", "")
            children = node.get("children", [])
            is_variable = node.get("is_variable", False)

            # Prefix with icon
            if is_variable:
                display_name = f"📊 {name}"
            elif children:
                display_name = f"📁 {name}"
            else:
                display_name = f"📄 {name}"

            item = QTreeWidgetItem([display_name, node_id])
            item.setData(0, Qt.ItemDataRole.UserRole, node_id)
            item.setData(1, Qt.ItemDataRole.UserRole, is_variable)

            if is_variable:
                item.setForeground(0, QColor("#a6e3a1"))
                item.setForeground(1, QColor("#89b4fa"))

            parent_item.addChild(item)

            if children:
                self._populate_tree(item, children)

    @Slot(QTreeWidgetItem, int)
    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Double-click on a variable node selects it and closes the dialog."""
        is_variable = item.data(1, Qt.ItemDataRole.UserRole)
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        if is_variable and node_id:
            self._selected_node_id = node_id
            self.accept()

    @Slot()
    def _on_select(self) -> None:
        """Use the currently selected tree item."""
        item = self._tree.currentItem()
        if item:
            is_variable = item.data(1, Qt.ItemDataRole.UserRole)
            node_id = item.data(0, Qt.ItemDataRole.UserRole)
            if is_variable and node_id:
                self._selected_node_id = node_id
                self.accept()

    @property
    def selected_node_id(self) -> str:
        """The Node ID selected by the user, or empty string."""
        return self._selected_node_id

    def closeEvent(self, event) -> None:  # noqa: N802
        """Ensure worker is stopped on close."""
        if self._worker and self._worker.isRunning():
            self._worker.wait(2000)
        super().closeEvent(event)


# ──────────────────────────────────────────────────────────────────
# OPC UA Tab
# ──────────────────────────────────────────────────────────────────


class OpcuaTab(QWidget):
    """Tab widget for OPC UA (AsyncUA) protocol."""

    def __init__(self, log_callback, parent=None):
        """Initialize the OPC UA tab.

        Args:
            log_callback: Callable to send log messages to the main window.
            parent: Parent widget.
        """
        super().__init__(parent)
        self._log = log_callback
        self._worker = OpcuaWorker()
        self._is_connected = False
        self._init_ui()
        self._init_worker()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Connection group ──
        conn_group = QGroupBox("🔗 Connection Settings")
        conn_layout = QVBoxLayout(conn_group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Server URL:"))
        self._url_edit = QLineEdit("opc.tcp://192.168.0.1:4840")
        self._url_edit.setMinimumWidth(300)
        row1.addWidget(self._url_edit)
        row1.addStretch()
        conn_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Username:"))
        self._user_edit = QLineEdit()
        self._user_edit.setPlaceholderText("(optional)")
        self._user_edit.setMinimumWidth(140)
        row2.addWidget(self._user_edit)

        row2.addWidget(QLabel("Password:"))
        self._pass_edit = QLineEdit()
        self._pass_edit.setPlaceholderText("(optional)")
        self._pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pass_edit.setMinimumWidth(140)
        row2.addWidget(self._pass_edit)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setObjectName("connectBtn")
        self._connect_btn.clicked.connect(self._on_connect)
        row2.addWidget(self._connect_btn)

        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setObjectName("disconnectBtn")
        self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        row2.addWidget(self._disconnect_btn)

        self._status_label = QLabel("⚪ Disconnected")
        self._status_label.setObjectName("statusLabel")
        row2.addWidget(self._status_label)
        row2.addStretch()
        conn_layout.addLayout(row2)

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

        self._browse_btn = QPushButton("🌳 Browse Nodes")
        self._browse_btn.setStyleSheet(
            "background: #cba6f7; color: #1e1e2e; font-weight: bold;"
        )
        self._browse_btn.clicked.connect(self._on_browse)
        cycle_layout.addWidget(self._browse_btn)

        cycle_layout.addStretch()
        layout.addWidget(cycle_group)

        # ── Node table ──
        table_group = QGroupBox("📋 OPC UA Nodes")
        table_layout = QVBoxLayout(table_group)

        self._table = QTableWidget(NUM_ROWS, 3)
        self._table.setHorizontalHeaderLabels(["Node ID", "Value", "Status"])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(COL_NODE_ID, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_VALUE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.Stretch)

        for row in range(NUM_ROWS):
            # Node ID input
            node_item = QTableWidgetItem("")
            self._table.setItem(row, COL_NODE_ID, node_item)

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
        self._worker.log_message.connect(lambda msg: self._log(f"[OPC UA] {msg}"))
        self._worker.start()

    # ── Slot handlers ──

    @Slot()
    def _on_connect(self) -> None:
        url = self._url_edit.text().strip()
        if not url:
            self._log("[OPC UA] ⚠️ Server URL is empty.")
            return
        self._worker.set_nodes(self._collect_nodes())
        self._worker.request_connect(
            url,
            self._user_edit.text().strip(),
            self._pass_edit.text(),
        )
        self._status_label.setText("🟡 Connecting...")

    @Slot()
    def _on_disconnect(self) -> None:
        self._worker.request_disconnect()

    @Slot()
    def _on_cyclic_changed(self) -> None:
        active = self._cyclic_cb.isChecked()
        interval = self._interval_spin.value()
        self._worker.set_nodes(self._collect_nodes())
        self._worker.set_cyclic(active, interval)

    @Slot()
    def _on_read_once(self) -> None:
        if not self._is_connected:
            self._log("[OPC UA] ⚠️ Not connected.")
            return
        self._worker.set_nodes(self._collect_nodes())
        self._worker.set_cyclic(True, 100)
        from PySide6.QtCore import QTimer

        QTimer.singleShot(500, lambda: self._worker.set_cyclic(
            self._cyclic_cb.isChecked(), self._interval_spin.value()
        ))

    @Slot()
    def _on_browse(self) -> None:
        """Open the Node Browser dialog to select Node IDs from the server."""
        url = self._url_edit.text().strip()
        if not url:
            self._log("[OPC UA] ⚠️ Server URL is empty – cannot browse.")
            return

        self._log("[OPC UA] 🌳 Opening Node Browser...")

        dialog = NodeBrowserDialog(
            url=url,
            username=self._user_edit.text().strip(),
            password=self._pass_edit.text(),
            log_callback=self._log,
            parent=self,
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:
            node_id = dialog.selected_node_id
            if node_id:
                self._insert_node_id(node_id)
                self._log(f"[OPC UA] ✅ Selected node: {node_id}")

    def _insert_node_id(self, node_id: str) -> None:
        """Insert a Node ID into the first empty row, or the selected row."""
        # Use the currently selected row if it exists
        current_row = self._table.currentRow()
        if 0 <= current_row < NUM_ROWS:
            node_item = self._table.item(current_row, COL_NODE_ID)
            if node_item:
                node_item.setText(node_id)
                return

        # Otherwise, find the first empty row
        for row in range(NUM_ROWS):
            node_item = self._table.item(row, COL_NODE_ID)
            if node_item and not node_item.text().strip():
                node_item.setText(node_id)
                return

        # All rows full – replace the last one
        node_item = self._table.item(NUM_ROWS - 1, COL_NODE_ID)
        if node_item:
            node_item.setText(node_id)

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

    def _collect_nodes(self) -> list[dict[str, str]]:
        """Collect node definitions from the table."""
        nodes = []
        for row in range(NUM_ROWS):
            node_item = self._table.item(row, COL_NODE_ID)
            nodes.append({
                "node_id": node_item.text() if node_item else "",
            })
        return nodes

    def get_config(self) -> dict:
        """Return current tab configuration for persistence."""
        return {
            "url": self._url_edit.text(),
            "username": self._user_edit.text(),
            "password": self._pass_edit.text(),
            "interval_ms": self._interval_spin.value(),
            "cyclic_active": self._cyclic_cb.isChecked(),
            "nodes": self._collect_nodes(),
        }

    def load_config(self, cfg: dict) -> None:
        """Load configuration into the tab."""
        self._url_edit.setText(cfg.get("url", "opc.tcp://192.168.0.1:4840"))
        self._user_edit.setText(cfg.get("username", ""))
        self._pass_edit.setText(cfg.get("password", ""))
        self._interval_spin.setValue(cfg.get("interval_ms", 1000))
        self._cyclic_cb.setChecked(cfg.get("cyclic_active", False))

        nodes = cfg.get("nodes", [])
        for row in range(min(NUM_ROWS, len(nodes))):
            node = nodes[row]
            node_item = self._table.item(row, COL_NODE_ID)
            if node_item:
                node_item.setText(node.get("node_id", ""))

    def shutdown(self) -> None:
        """Stop the worker thread."""
        self._worker.set_cyclic(False, 1000)
        self._worker.stop()
