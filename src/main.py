"""
FX Option Pricer - Main entry point.

A desktop application for pricing FX vanilla options using the
Garman-Kohlhagen model with market data from Bloomberg.
"""

import sys
import logging
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from src.gui.main_window import FXOptionPricer


def setup_logging():
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )


def main():
    """Main entry point for the application."""
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting FX Option Pricer")

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("FX Option Pricer")
    app.setOrganizationName("FXO")

    # Enable high DPI scaling
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create and show main window
    window = FXOptionPricer()
    window.show()

    # Run event loop
    logger.info("Application started")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
