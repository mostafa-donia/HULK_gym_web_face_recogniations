import os
import ctypes
from PySide6.QtCore import Qt, QPoint, QTimer, Signal
from PySide6.QtGui import QIcon, QFont, QColor, QPainter, QBrush, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QGraphicsDropShadowEffect, QApplication
)


class MiniOverlayWindow(QWidget):
    """
    Native Windows PySide6 Always-On-Top Mini HUD Overlay.
    - Positioned at Top-Left of the screen.
    - Pure Windows PySide6 native widget (NO WEB VIEW).
    - Enforced HWND_TOPMOST via Win32 API to ensure it never gets covered by WhatsApp Desktop.
    - Live countdown, remaining message counter, and quick action controls.
    """
    pause_requested = Signal()
    resume_requested = Signal()
    stop_requested = Signal()
    show_main_window_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.drag_position = QPoint()
        self.is_paused = False

        self._init_window()
        self._init_ui()
        self._setup_topmost_keeper()

    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(340, 195)

        # Position at Top-Left corner with comfortable margin
        self.move(24, 24)

    def _init_ui(self):
        # Outer container layout
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 10, 10, 10)

        # Card container with dark glass design
        self.card = QWidget(self)
        self.card.setObjectName("overlayCard")
        self.card.setStyleSheet("""
            QWidget#overlayCard {
                background-color: rgba(9, 14, 24, 0.95);
                border: 1.5px solid rgba(163, 230, 53, 0.5);
                border-radius: 16px;
            }
        """)

        # Drop shadow for floating HUD effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 6)
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(8)

        # Header: Logo + Title + Pin badge + Minimize
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.title_label = QLabel("⚡ Systemize WA Dispatcher")
        self.title_label.setStyleSheet("color: #a3e635; font-size: 11px; font-weight: 900; letter-spacing: 0.5px;")

        self.badge_pin = QLabel("TOPMOST")
        self.badge_pin.setStyleSheet("""
            background: rgba(163, 230, 53, 0.15);
            color: #bef264;
            border: 1px solid rgba(163, 230, 53, 0.4);
            font-size: 8px;
            font-weight: 900;
            padding: 2px 5px;
            border-radius: 6px;
        """)

        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.badge_pin)
        header_layout.addStretch()

        # Button to toggle/restore main window
        self.btn_open_main = QPushButton("🗖")
        self.btn_open_main.setToolTip("فتح لوحة التحكم الرئيسية")
        self.btn_open_main.setFixedSize(22, 22)
        self.btn_open_main.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #94a3b8; border: 1px solid #334155;
                border-radius: 6px; font-size: 10px; font-weight: bold;
            }
            QPushButton:hover { background: #334155; color: #fff; }
        """)
        self.btn_open_main.clicked.connect(self.show_main_window_requested.emit)
        header_layout.addWidget(self.btn_open_main)

        card_layout.addLayout(header_layout)

        # Counter Row: Sent / Total + Remaining
        counter_layout = QHBoxLayout()
        self.lbl_counter = QLabel("0 / 0 (0%)")
        self.lbl_counter.setStyleSheet("color: #ffffff; font-size: 15px; font-weight: 1000;")

        self.lbl_remaining = QLabel("المتبقي: 0")
        self.lbl_remaining.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 700;")

        counter_layout.addWidget(self.lbl_counter)
        counter_layout.addStretch()
        counter_layout.addWidget(self.lbl_remaining)
        card_layout.addLayout(counter_layout)

        # Sleek Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #0f172a;
                border-radius: 4px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #65a30d, stop:1 #a3e635);
                border-radius: 4px;
            }
        """)
        card_layout.addWidget(self.progress_bar)

        # Current Recipient Info
        self.lbl_current_target = QLabel("👤 جاهز للإرسال...")
        self.lbl_current_target.setStyleSheet("color: #cbd5e1; font-size: 11px; font-weight: 800;")
        card_layout.addWidget(self.lbl_current_target)

        # Status & Countdown Timer
        status_row = QHBoxLayout()
        self.lbl_status = QLabel("🟢 الانتظار...")
        self.lbl_status.setStyleSheet("color: #38bdf8; font-size: 10px; font-weight: 700;")

        self.lbl_countdown = QLabel("⏱️ 00:00")
        self.lbl_countdown.setStyleSheet("color: #facc15; font-size: 11px; font-weight: 900; font-family: monospace;")

        status_row.addWidget(self.lbl_status)
        status_row.addStretch()
        status_row.addWidget(self.lbl_countdown)
        card_layout.addLayout(status_row)

        # Controls & Kill-Switch row
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(6)

        self.btn_pause = QPushButton("⏸️ إيقاف مؤقت")
        self.btn_pause.setFixedHeight(26)
        self.btn_pause.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #f8fafc; border: 1px solid #475569;
                border-radius: 6px; font-size: 10px; font-weight: 800; padding: 0 8px;
            }
            QPushButton:hover { background: #334155; }
        """)
        self.btn_pause.clicked.connect(self._toggle_pause)

        self.btn_stop = QPushButton("⏹️ إنهاء")
        self.btn_stop.setFixedHeight(26)
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background: #881337; color: #fecdd3; border: 1px solid #9f1239;
                border-radius: 6px; font-size: 10px; font-weight: 800; padding: 0 8px;
            }
            QPushButton:hover { background: #9f1239; color: #fff; }
        """)
        self.btn_stop.clicked.connect(self.stop_requested.emit)

        self.lbl_hotkey_hint = QLabel("طوارئ: Ctrl+K")
        self.lbl_hotkey_hint.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 700;")

        ctrl_layout.addWidget(self.btn_pause)
        ctrl_layout.addWidget(self.btn_stop)
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(self.lbl_hotkey_hint)

        card_layout.addLayout(ctrl_layout)
        outer_layout.addWidget(self.card)

    def _setup_topmost_keeper(self):
        """Periodic Win32 HWND_TOPMOST reinforcement so no full-screen window can ever cover it."""
        self.topmost_timer = QTimer(self)
        self.topmost_timer.timeout.connect(self.enforce_topmost)
        self.topmost_timer.start(800)

    def enforce_topmost(self):
        if not self.isVisible():
            return
        try:
            # SetWindowPos with HWND_TOPMOST (-1)
            ctypes.windll.user32.SetWindowPos(
                int(self.winId()),
                -1,  # HWND_TOPMOST
                0, 0, 0, 0,
                0x0001 | 0x0002 | 0x0010 | 0x0040  # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW
            )
        except Exception:
            pass

    def update_progress(self, sent: int, total: int, remaining: int, current_name: str = "", current_phone: str = ""):
        pct = int((sent / total * 100)) if total > 0 else 0
        self.lbl_counter.setText(f"{sent} / {total} ({pct}%)")
        self.lbl_remaining.setText(f"المتبقي: {remaining}")
        self.progress_bar.setValue(pct)

        if current_name or current_phone:
            name_text = current_name if current_name else "عميل"
            phone_text = f"({current_phone})" if current_phone else ""
            self.lbl_current_target.setText(f"👤 {name_text} {phone_text}")

    def update_status(self, text: str, is_active: bool = True):
        color = "#a3e635" if is_active else "#94a3b8"
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 700;")

    def update_countdown(self, seconds_left: float):
        if seconds_left <= 0:
            self.lbl_countdown.setText("🚀 إرسال...")
            self.lbl_countdown.setStyleSheet("color: #a3e635; font-size: 11px; font-weight: 900; font-family: monospace;")
        else:
            sec_int = int(seconds_left)
            ms = int((seconds_left - sec_int) * 10)
            self.lbl_countdown.setText(f"⏱️ {sec_int:02d}.{ms}s")
            self.lbl_countdown.setStyleSheet("color: #facc15; font-size: 11px; font-weight: 900; font-family: monospace;")

    def _toggle_pause(self):
        if not self.is_paused:
            self.is_paused = True
            self.btn_pause.setText("▶️ استئناف")
            self.btn_pause.setStyleSheet("""
                QPushButton {
                    background: #14532d; color: #bbf7d0; border: 1px solid #16a34a;
                    border-radius: 6px; font-size: 10px; font-weight: 800; padding: 0 8px;
                }
                QPushButton:hover { background: #16a34a; color: #fff; }
            """)
            self.pause_requested.emit()
            self.update_status("⏸️ متوقف مؤقتاً", is_active=False)
        else:
            self.is_paused = False
            self.btn_pause.setText("⏸️ إيقاف مؤقت")
            self.btn_pause.setStyleSheet("""
                QPushButton {
                    background: #1e293b; color: #f8fafc; border: 1px solid #475569;
                    border-radius: 6px; font-size: 10px; font-weight: 800; padding: 0 8px;
                }
                QPushButton:hover { background: #334155; }
            """)
            self.resume_requested.emit()
            self.update_status("🟢 جاري الإرسال...", is_active=True)

    def set_paused_state(self, paused: bool):
        self.is_paused = paused
        if paused:
            self.btn_pause.setText("▶️ استئناف")
            self.update_status("⏸️ متوقف مؤقتاً", is_active=False)
        else:
            self.btn_pause.setText("⏸️ إيقاف مؤقت")
            self.update_status("🟢 جاري الإرسال...", is_active=True)

    # Enable smooth dragging to reposition anywhere
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
