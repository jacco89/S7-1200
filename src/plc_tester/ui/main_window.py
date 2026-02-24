"""Main window for the PLC Tester application.

Contains the tab widget (S7 / OPC UA) and a bottom log panel.
Applies a modern dark theme via QSS stylesheet.
"""

from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from plc_tester.core.config_manager import load_config, save_config
from plc_tester.ui.opcua_tab import OpcuaTab
from plc_tester.ui.s7_tab import S7Tab

logger = logging.getLogger(__name__)

# ── Modern dark QSS stylesheet ──
_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "Roboto", sans-serif;
    font-size: 13px;
}

QGroupBox {
    border: 1px solid #45475a;
    border-radius: 8px;
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
    font-weight: bold;
    color: #89b4fa;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

QTabWidget::pane {
    border: 1px solid #45475a;
    border-radius: 6px;
    background: #1e1e2e;
}
QTabBar::tab {
    background: #313244;
    color: #bac2de;
    padding: 8px 24px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    min-width: 140px;
}
QTabBar::tab:selected {
    background: #45475a;
    color: #89b4fa;
    font-weight: bold;
}
QTabBar::tab:hover {
    background: #585b70;
}

QLineEdit, QSpinBox, QComboBox {
    background: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #89b4fa;
}

QPushButton {
    background: #45475a;
    border: none;
    border-radius: 4px;
    padding: 6px 18px;
    color: #cdd6f4;
    font-weight: bold;
}
QPushButton:hover {
    background: #585b70;
}
QPushButton:pressed {
    background: #89b4fa;
    color: #1e1e2e;
}
QPushButton:disabled {
    background: #313244;
    color: #6c7086;
}
QPushButton#connectBtn {
    background: #a6e3a1;
    color: #1e1e2e;
}
QPushButton#connectBtn:hover {
    background: #94e2d5;
}
QPushButton#connectBtn:disabled {
    background: #313244;
    color: #6c7086;
}
QPushButton#disconnectBtn {
    background: #f38ba8;
    color: #1e1e2e;
}
QPushButton#disconnectBtn:hover {
    background: #eba0ac;
}
QPushButton#disconnectBtn:disabled {
    background: #313244;
    color: #6c7086;
}

QTableWidget {
    background: #181825;
    alternate-background-color: #1e1e2e;
    gridline-color: #45475a;
    border: 1px solid #45475a;
    border-radius: 4px;
    selection-background-color: #45475a;
}
QTableWidget::item {
    padding: 4px;
}
QHeaderView::section {
    background: #313244;
    color: #89b4fa;
    padding: 6px;
    border: none;
    border-right: 1px solid #45475a;
    border-bottom: 1px solid #45475a;
    font-weight: bold;
}

QTextEdit#logPanel {
    background: #11111b;
    color: #a6adc8;
    border: 1px solid #45475a;
    border-radius: 4px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
}

QCheckBox {
    spacing: 6px;
    color: #cdd6f4;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #45475a;
    border-radius: 3px;
    background: #313244;
}
QCheckBox::indicator:checked {
    background: #89b4fa;
    border-color: #89b4fa;
}

QSplitter::handle {
    background: #45475a;
    height: 3px;
}

QLabel#statusLabel {
    font-weight: bold;
    padding: 0 8px;
}

QLabel#titleLabel {
    font-size: 18px;
    font-weight: bold;
    color: #89b4fa;
    padding: 4px 0;
}
"""


class MainWindow(QMainWindow):
    """Application main window with tabbed interface and log panel."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PLC Tester – S7-1200/1500 Diagnostic Tool")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)

        self._init_ui()
        self._load_settings()

    def _init_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 8, 12, 8)

        # Title
        title = QLabel("🔧 PLC Tester – Siemens S7-1200/1500")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        # Splitter: tabs on top, logs on bottom
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Tab widget
        self._tabs = QTabWidget()
        self._s7_tab = S7Tab(log_callback=self._append_log)
        self._opcua_tab = OpcuaTab(log_callback=self._append_log)
        self._tabs.addTab(self._s7_tab, "⚙ S7Comm (Snap7)")
        self._tabs.addTab(self._opcua_tab, "🌐 OPC UA (AsyncUA)")
        splitter.addWidget(self._tabs)

        # Log panel
        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(0, 0, 0, 0)

        log_header = QHBoxLayout()
        log_label = QLabel("📋 Communication Log")
        log_label.setStyleSheet("font-weight: bold; color: #89b4fa; font-size: 13px;")
        log_header.addWidget(log_label)
        log_header.addStretch()
        log_layout.addLayout(log_header)

        self._log_edit = QTextEdit()
        self._log_edit.setObjectName("logPanel")
        self._log_edit.setReadOnly(True)
        self._log_edit.setFont(QFont("Cascadia Code", 10))
        self._log_edit.setMaximumHeight(200)
        log_layout.addWidget(self._log_edit)
        splitter.addWidget(log_container)

        # Set splitter proportions
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

    def _load_settings(self) -> None:
        """Load persisted configuration."""
        try:
            config = load_config()
            self._s7_tab.load_config(config.get("s7", {}))
            self._opcua_tab.load_config(config.get("opcua", {}))
            self._append_log("📁 Configuration loaded.")
        except Exception as exc:
            self._append_log(f"⚠️ Failed to load config: {exc}")

    def _save_settings(self) -> None:
        """Save current configuration."""
        try:
            config = {
                "s7": self._s7_tab.get_config(),
                "opcua": self._opcua_tab.get_config(),
            }
            save_config(config)
            self._append_log("💾 Configuration saved.")
        except Exception as exc:
            self._append_log(f"⚠️ Failed to save config: {exc}")

    @Slot(str)
    def _append_log(self, message: str) -> None:
        """Append a timestamped message to the log panel."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self._log_edit.append(f"[{timestamp}]  {message}")
        # Auto-scroll to bottom
        scrollbar = self._log_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event) -> None:  # noqa: N802
        """Save settings and stop workers on close."""
        self._save_settings()
        self._s7_tab.shutdown()
        self._opcua_tab.shutdown()
        super().closeEvent(event)
