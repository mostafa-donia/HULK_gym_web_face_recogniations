#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
 SYSTEMIZE — Professional WhatsApp Bulk Sender & Smart Scheduler
 Standalone Edition (Desktop Native PySide6)
=============================================================================
 Features:
  - Excel (.xlsx/.xls), CSV & Google Contacts Import with Category Filters
  - Rich Text Personalization ({الاسم}, {الهاتف}, {التصنيف}, etc.)
  - Images, PDFs & Document Attachments
  - Anti-Ban Timing: Human-like mouse curvature, typing delays, randomized pause
  - Instant Dispatch or Scheduled Date & Time Sending
  - Native Top-Left Windows Mini HUD Overlay (Pure PySide6, Non-Web, HWND_TOPMOST)
  - Emergency Physical Kill Switch (Ctrl + K)
=============================================================================
"""

import sys
import os

# Ensure project root is in sys.path
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QFont
from PySide6.QtCore import Qt

from gui.main_window import MainWindow


def main():
    # Enable High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Systemize WhatsApp Pro")
    app.setApplicationDisplayName("Systemize WhatsApp Pro")
    app.setOrganizationName("Systemize")

    # Set Application Icon
    icon_path = os.path.join(PROJECT_DIR, "assets", "icon.ico")
    if not os.path.exists(icon_path):
        icon_path = os.path.join(PROJECT_DIR, "assets", "logo.png")

    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Set Default Font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Launch Main Window
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
