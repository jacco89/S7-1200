"""PLC Tester application entry point.

Launches the PySide6 application with the main window.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from plc_tester.ui.main_window import _STYLESHEET, MainWindow


def main() -> None:
    """Application entry point."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)-30s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    app = QApplication(sys.argv)
    app.setApplicationName("PLC Tester")
    app.setOrganizationName("PLCTester")

    # Apply dark stylesheet
    app.setStyleSheet(_STYLESHEET)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
