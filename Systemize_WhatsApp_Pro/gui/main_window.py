import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional, List

from PySide6.QtCore import Qt, QTimer, QDateTime
from PySide6.QtGui import QIcon, QPixmap, QColor, QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QCheckBox, QGroupBox, QDateTimeEdit, QProgressBar, QMessageBox, QSplitter
)

from core.contact_manager import ContactManager, Contact
from core.whatsapp_engine import WhatsAppEngine
from core.scheduler import DispatchWorker
from gui.mini_overlay import MiniOverlayWindow
from gui.theme import THEME_STYLESHEET


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Systemize — Professional WhatsApp Bulk Sender & Scheduler")
        self.resize(1150, 780)
        self.setMinimumSize(950, 650)
        self.setStyleSheet(THEME_STYLESHEET)

        # Set App Icon
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        # Core Engines
        self.contact_mgr = ContactManager()
        self.engine = WhatsAppEngine()
        self.worker: Optional[DispatchWorker] = None
        self.attachment_file_path: Optional[str] = None

        # Floating Mini HUD Window (PySide6 Native, NO Web)
        self.overlay = MiniOverlayWindow()
        self.overlay.pause_requested.connect(self.pause_dispatch)
        self.overlay.resume_requested.connect(self.resume_dispatch)
        self.overlay.stop_requested.connect(self.stop_dispatch)
        self.overlay.show_main_window_requested.connect(self.restore_main_window)

        self._init_ui()

    def _init_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(18, 14, 18, 18)
        main_layout.setSpacing(12)

        # 1. Top Header Bar
        main_layout.addLayout(self._create_header())

        # 2. Main Tabbed Workspace
        self.tabs = QTabWidget()
        self.tabs.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.tab_contacts = self._create_contacts_tab()
        self.tab_composer = self._create_composer_tab()
        self.tab_timing = self._create_timing_tab()
        self.tab_dispatch = self._create_dispatch_tab()
        self.tab_history = self._create_history_tab()

        self.tabs.addTab(self.tab_contacts, "📋 جهات الاتصال والتصنيفات")
        self.tabs.addTab(self.tab_composer, "✍️ كتابة الرسالة والمرفقات")
        self.tabs.addTab(self.tab_timing, "⚙️ التوقيت وحركة الماوس والأمان")
        self.tabs.addTab(self.tab_dispatch, "🚀 الإرسال والجدولة والمراقبة")
        self.tabs.addTab(self.tab_history, "📊 سجل وتقارير الحملة")

        main_layout.addWidget(self.tabs)
        self.setCentralWidget(main_widget)

    def _create_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(12)

        # Logo
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "logo.png")
        lbl_logo = QLabel()
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaled(46, 46, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            lbl_logo.setPixmap(pix)
        layout.addWidget(lbl_logo)

        # Title + Description
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        lbl_title = QLabel("Systemize WhatsApp Pro Sender")
        lbl_title.setStyleSheet("font-size: 19px; font-weight: 1000; color: #ffffff;")

        badge = QLabel("STANDALONE EDITION")
        badge.setStyleSheet("""
            background: rgba(163, 230, 53, 0.15); color: #bef264;
            border: 1px solid rgba(163, 230, 53, 0.4); border-radius: 6px;
            font-size: 9px; font-weight: 900; padding: 2px 7px;
        """)
        title_row.addWidget(lbl_title)
        title_row.addWidget(badge)
        title_row.addStretch()

        lbl_sub = QLabel("المرسل المتقدم لرسائل ووسائط الواتساب للكمبيوتر — مع استيراد Excel، فلاتر التصنيف، حركة الماوس البشرية، ونافذة المراقبة العائمة")
        lbl_sub.setStyleSheet("font-size: 11px; color: #94a3b8;")

        title_box.addLayout(title_row)
        title_box.addWidget(lbl_sub)
        layout.addLayout(title_box)

        layout.addStretch()

        # Toggle Mini Overlay Button
        self.btn_toggle_overlay = QPushButton("🖥️ نافذة المراقبة العائمة (Top-Left HUD)")
        self.btn_toggle_overlay.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #a3e635; border: 1.5px solid rgba(163, 230, 53, 0.4);
                border-radius: 10px; font-weight: 800; padding: 8px 14px;
            }
            QPushButton:hover { background: #334155; }
        """)
        self.btn_toggle_overlay.clicked.connect(self.toggle_overlay)
        layout.addWidget(self.btn_toggle_overlay)

        return layout

    # ==========================================
    # TAB 1: CONTACTS & CATEGORIES
    # ==========================================
    def _create_contacts_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        # Toolbar: Import Excel + Category Filter + Search
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        btn_import = QPushButton("📥 استيراد من Excel / CSV / Google")
        btn_import.setObjectName("btnPrimary")
        btn_import.setFixedHeight(36)
        btn_import.clicked.connect(self.import_contacts_file)
        toolbar.addWidget(btn_import)

        btn_sample = QPushButton("📄 تحميل نموذج جاهز")
        btn_sample.setFixedHeight(36)
        btn_sample.clicked.connect(self.open_sample_data)
        toolbar.addWidget(btn_sample)

        toolbar.addSpacing(15)

        # Category Filter
        lbl_cat = QLabel("التصنيف:")
        lbl_cat.setStyleSheet("font-weight: 800; color: #94a3b8;")
        self.cmb_category_filter = QComboBox()
        self.cmb_category_filter.setMinimumWidth(160)
        self.cmb_category_filter.addItem("الكل")
        self.cmb_category_filter.currentIndexChanged.connect(self.apply_contact_filters)
        toolbar.addWidget(lbl_cat)
        toolbar.addWidget(self.cmb_category_filter)

        # Search Bar
        lbl_search = QLabel("بحث:")
        lbl_search.setStyleSheet("font-weight: 800; color: #94a3b8;")
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("ابحث بالاسم أو الهاتف أو الملاحظات...")
        self.txt_search.textChanged.connect(self.apply_contact_filters)
        toolbar.addWidget(lbl_search)
        toolbar.addWidget(self.txt_search)

        layout.addLayout(toolbar)

        # Contacts Table
        self.tbl_contacts = QTableWidget()
        self.tbl_contacts.setColumnCount(6)
        self.tbl_contacts.setHorizontalHeaderLabels(["تحديد", "الاسم", "رقم الهاتف", "التصنيف", "الملاحظات", "الحالة"])
        self.tbl_contacts.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_contacts.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl_contacts.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_contacts.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_contacts.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.tbl_contacts.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_contacts.setAlternatingRowColors(True)
        layout.addWidget(self.tbl_contacts)

        # Bottom Action Bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)

        btn_sel_all = QPushButton("☑️ تحديد الكل")
        btn_sel_all.clicked.connect(lambda: self.set_all_selection(True))
        btn_unsel_all = QPushButton("⬜ إلغاء التحديد")
        btn_unsel_all.clicked.connect(lambda: self.set_all_selection(False))

        btn_add_manual = QPushButton("➕ إضافة رقم يدوياً")
        btn_add_manual.clicked.connect(self.add_manual_contact)

        btn_export = QPushButton("📤 تصدير القائمة إلى Excel")
        btn_export.clicked.connect(self.export_contacts_excel)

        self.lbl_contact_stats = QLabel("إجمالي جهات الاتصال: 0 | المحددة للإرسال: 0")
        self.lbl_contact_stats.setStyleSheet("font-weight: 900; color: #a3e635;")

        bottom_bar.addWidget(btn_sel_all)
        bottom_bar.addWidget(btn_unsel_all)
        bottom_bar.addWidget(btn_add_manual)
        bottom_bar.addWidget(btn_export)
        bottom_bar.addStretch()
        bottom_bar.addWidget(self.lbl_contact_stats)

        layout.addLayout(bottom_bar)
        return widget

    # ==========================================
    # TAB 2: CAMPAIGN COMPOSER & ATTACHMENTS
    # ==========================================
    def _create_composer_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(14)

        # Message Text Group
        grp_msg = QGroupBox("نص الرسالة وقوالب التخصيص التلقائي (Personalized Tags)")
        v_msg = QVBoxLayout(grp_msg)

        # Tags Helper Buttons
        tags_layout = QHBoxLayout()
        tags_layout.setSpacing(6)
        tags_layout.addWidget(QLabel("إدراج حقل ديناميكي:"))

        tag_buttons = [
            ("{الاسم}", "الاسم"),
            ("{الهاتف}", "الهاتف"),
            ("{التصنيف}", "التصنيف"),
            ("{الوقت}", "الوقت"),
            ("{التاريخ}", "التاريخ"),
            ("{الملاحظات}", "الملاحظات"),
        ]
        for tag, title in tag_buttons:
            b = QPushButton(title)
            b.setFixedHeight(26)
            b.setStyleSheet("background: #0f172a; border: 1px solid #334155; font-size: 11px;")
            b.clicked.connect(lambda _, t=tag: self.insert_template_tag(t))
            tags_layout.addWidget(b)

        tags_layout.addStretch()
        v_msg.addLayout(tags_layout)

        self.txt_message = QTextEdit()
        self.txt_message.setPlaceholderText(
            "اكتب نص الرسالة هنا...\n"
            "مثال: أهلاً بك يا كابتن {الاسم}! نود تذكيرك بأن اشتراكك في باقة {التصنيف} سارٍ بنجاح. شكراً لثقتكم بنا!"
        )
        self.txt_message.setMinimumHeight(150)
        v_msg.addWidget(self.txt_message)

        layout.addWidget(grp_msg)

        # Attachments Group
        grp_attach = QGroupBox("مرفقات الصور والملفات (Attachments & Media)")
        v_attach = QVBoxLayout(grp_attach)

        attach_bar = QHBoxLayout()
        self.lbl_attachment_name = QLabel("لا يوجد ملف أو صورة مرفقة (إرسال نصي فقط)")
        self.lbl_attachment_name.setStyleSheet("color: #94a3b8; font-weight: bold;")

        btn_pick_img = QPushButton("🖼️ إرفاق صورة (Image)")
        btn_pick_img.clicked.connect(lambda: self.pick_attachment(is_image=True))

        btn_pick_file = QPushButton("📁 إرفاق مستند (PDF / File)")
        btn_pick_file.clicked.connect(lambda: self.pick_attachment(is_image=False))

        btn_clear_attach = QPushButton("❌ إزالة المرفق")
        btn_clear_attach.clicked.connect(self.clear_attachment)

        attach_bar.addWidget(self.lbl_attachment_name)
        attach_bar.addStretch()
        attach_bar.addWidget(btn_pick_img)
        attach_bar.addWidget(btn_pick_file)
        attach_bar.addWidget(btn_clear_attach)

        v_attach.addLayout(attach_bar)

        hint = QLabel("💡 يدعم إرسال: صور (PNG, JPG, BMP) أو ملفات (PDF, Excel, Word). سيتم لصق المرفق وإرسال نص الرسالة معه تلقائياً.")
        hint.setStyleSheet("font-size: 11px; color: #64748b;")
        v_attach.addWidget(hint)

        layout.addWidget(grp_attach)

        # Preview Button
        btn_preview = QPushButton("👁️ معاينة شكل الرسالة لأول عميل محدد")
        btn_preview.clicked.connect(self.preview_message)
        layout.addWidget(btn_preview)

        layout.addStretch()
        return widget

    # ==========================================
    # TAB 3: TIMING, MOVEMENTS & KILL SWITCH
    # ==========================================
    def _create_timing_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(14)

        # Timing intervals
        grp_timing = QGroupBox("فترات التوقف العشوائية بين الرسائل (لحماية الرقم من الحظر)")
        v_timing = QVBoxLayout(grp_timing)

        row_delays = QHBoxLayout()
        row_delays.addWidget(QLabel("أقل فترة انتظار (ثواني):"))
        self.spn_min_delay = QDoubleSpinBox()
        self.spn_min_delay.setRange(2.0, 120.0)
        self.spn_min_delay.setValue(6.0)
        row_delays.addWidget(self.spn_min_delay)

        row_delays.addSpacing(20)

        row_delays.addWidget(QLabel("أقصى فترة انتظار (ثواني):"))
        self.spn_max_delay = QDoubleSpinBox()
        self.spn_max_delay.setRange(3.0, 300.0)
        self.spn_max_delay.setValue(14.0)
        row_delays.addWidget(self.spn_max_delay)

        row_delays.addStretch()
        v_timing.addLayout(row_delays)

        lbl_delay_hint = QLabel("💡 يقوم النظام باختيار وقت عشوائي بين الحد الأدنى والأقصى مع كل رسالة لمحاكاة السلوك البشري الطبيعي.")
        lbl_delay_hint.setStyleSheet("font-size: 11px; color: #94a3b8;")
        v_timing.addWidget(lbl_delay_hint)
        layout.addWidget(grp_timing)

        # Human Movement & Typing
        grp_human = QGroupBox("محاكاة حركة الماوس وطريقة الكتابة (Human Behavior Simulation)")
        v_human = QVBoxLayout(grp_human)

        self.chk_human_mouse = QCheckBox("تفعيل حركة الماوس المنحنية الطبيعية (Human Eased Mouse Movement)")
        self.chk_human_mouse.setChecked(True)
        v_human.addWidget(self.chk_human_mouse)

        row_mode = QHBoxLayout()
        row_mode.addWidget(QLabel("طريقة إدخال نص الرسالة:"))
        self.cmb_send_mode = QComboBox()
        self.cmb_send_mode.addItem("لصق سريع من الحافظة (Fast Paste - آمن وسريع)", "paste")
        self.cmb_send_mode.addItem("محاكاة ضغطات الكيبورد حرفاً بحرف (Human Typing)", "typing")
        row_mode.addWidget(self.cmb_send_mode)

        row_mode.addSpacing(15)
        row_mode.addWidget(QLabel("سرعة كتابة الحرف (ثانية):"))
        self.spn_char_delay = QDoubleSpinBox()
        self.spn_char_delay.setRange(0.005, 0.2)
        self.spn_char_delay.setSingleStep(0.005)
        self.spn_char_delay.setValue(0.02)
        row_mode.addWidget(self.spn_char_delay)

        row_mode.addStretch()
        v_human.addLayout(row_mode)
        layout.addWidget(grp_human)

        # Search Bar Coordinates Calibration
        grp_coords = QGroupBox("إحداثيات شريط البحث في واتساب للكمبيوتر (Search Bar Coordinates)")
        v_coords = QVBoxLayout(grp_coords)

        coords_row = QHBoxLayout()
        coords_row.addWidget(QLabel("الإحداثي الأفقي (X):"))
        self.spn_coord_x = QSpinBox()
        self.spn_coord_x.setRange(0, 3840)
        self.spn_coord_x.setValue(300)
        coords_row.addWidget(self.spn_coord_x)

        coords_row.addSpacing(15)
        coords_row.addWidget(QLabel("الإحداثي الرأسي (Y):"))
        self.spn_coord_y = QSpinBox()
        self.spn_coord_y.setRange(0, 2160)
        self.spn_coord_y.setValue(190)
        coords_row.addWidget(self.spn_coord_y)

        coords_row.addSpacing(20)

        self.btn_calibrate = QPushButton("🎯 معايرة شريط البحث تلقائياً (Calibrate)")
        self.btn_calibrate.clicked.connect(self.start_coordinates_calibration)
        coords_row.addWidget(self.btn_calibrate)

        coords_row.addStretch()
        v_coords.addLayout(coords_row)

        lbl_coord_hint = QLabel("💡 القيمة الافتراضية (300, 190) متوافقة تماماً مع شاشات Full HD القياسية عندما يكون WhatsApp في وضع ملء الشاشة.")
        lbl_coord_hint.setStyleSheet("font-size: 11px; color: #94a3b8;")
        v_coords.addWidget(lbl_coord_hint)
        layout.addWidget(grp_coords)

        # Emergency Kill Switch
        grp_kill = QGroupBox("زر الطوارئ للإيقاف الفوري (Physical Emergency Kill Switch)")
        v_kill = QVBoxLayout(grp_kill)

        kill_row = QHBoxLayout()
        kill_row.addWidget(QLabel("اختصار لوحة المفاتيح للطوارئ:"))
        self.cmb_kill_hotkey = QComboBox()
        self.cmb_kill_hotkey.addItem("Ctrl + K (الافتراضي)", "ctrl+k")
        self.cmb_kill_hotkey.addItem("Esc (هروب)", "esc")
        self.cmb_kill_hotkey.addItem("F9", "f9")
        self.cmb_kill_hotkey.addItem("Ctrl + Shift + K", "ctrl+shift+k")
        kill_row.addWidget(self.cmb_kill_hotkey)
        kill_row.addStretch()

        v_kill.addLayout(kill_row)

        lbl_kill_note = QLabel("🚨 يعمل زر الطوارئ على مستوى نظام Windows بالكامل في أي جزء من الثانية لإلغاء وإيقاف الإرسال فوراً بمجرد ضغطه.")
        lbl_kill_note.setStyleSheet("font-size: 11px; color: #f43f5e; font-weight: bold;")
        v_kill.addWidget(lbl_kill_note)
        layout.addWidget(grp_kill)

        layout.addStretch()
        return widget

    # ==========================================
    # TAB 4: DISPATCH & SCHEDULE
    # ==========================================
    def _create_dispatch_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(14)

        # Dispatch Mode (Now vs Scheduled)
        grp_schedule = QGroupBox("موعد الإطلاق (Timing & Auto Scheduling)")
        v_sched = QVBoxLayout(grp_schedule)

        row_sched = QHBoxLayout()
        self.chk_schedule_later = QCheckBox("جدولة الإرسال التلقائي في وقت محدد لاحقاً (Auto Schedule)")
        self.chk_schedule_later.toggled.connect(self._toggle_schedule_inputs)
        row_sched.addWidget(self.chk_schedule_later)

        row_sched.addSpacing(20)

        self.dt_picker = QDateTimeEdit(QDateTime.currentDateTime().addSecs(300))
        self.dt_picker.setDisplayFormat("yyyy-MM-dd  hh:mm AP")
        self.dt_picker.setEnabled(False)
        self.dt_picker.setCalendarPopup(True)
        row_sched.addWidget(self.dt_picker)
        row_sched.addStretch()

        v_sched.addLayout(row_sched)
        layout.addWidget(grp_schedule)

        # Big Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.btn_start_campaign = QPushButton("🚀 بدء إرسال الحملة فوراً")
        self.btn_start_campaign.setObjectName("btnPrimary")
        self.btn_start_campaign.setFixedHeight(48)
        self.btn_start_campaign.setStyleSheet("font-size: 15px; font-weight: 1000;")
        self.btn_start_campaign.clicked.connect(self.start_dispatch)

        self.btn_pause_campaign = QPushButton("⏸️ إيقاف مؤقت")
        self.btn_pause_campaign.setFixedHeight(48)
        self.btn_pause_campaign.setEnabled(False)
        self.btn_pause_campaign.clicked.connect(self.toggle_pause_campaign)

        self.btn_stop_campaign = QPushButton("⏹️ إيقاف طوارئ (Stop)")
        self.btn_stop_campaign.setObjectName("btnDanger")
        self.btn_stop_campaign.setFixedHeight(48)
        self.btn_stop_campaign.setEnabled(False)
        self.btn_stop_campaign.clicked.connect(self.stop_dispatch)

        btn_row.addWidget(self.btn_start_campaign, 2)
        btn_row.addWidget(self.btn_pause_campaign, 1)
        btn_row.addWidget(self.btn_stop_campaign, 1)
        layout.addLayout(btn_row)

        # Live Progress Display Card
        grp_live = QGroupBox("حالة الإرسال المباشرة ونسبة الإنجاز (Live Progress)")
        v_live = QVBoxLayout(grp_live)
        v_live.setSpacing(10)

        prog_top_row = QHBoxLayout()
        self.lbl_main_counter = QLabel("0 / 0 رسالة (0%)")
        self.lbl_main_counter.setStyleSheet("font-size: 18px; font-weight: 1000; color: #a3e635;")

        self.lbl_main_status = QLabel("جاهز للبدء...")
        self.lbl_main_status.setStyleSheet("font-size: 13px; font-weight: 800; color: #38bdf8;")

        prog_top_row.addWidget(self.lbl_main_counter)
        prog_top_row.addStretch()
        prog_top_row.addWidget(self.lbl_main_status)
        v_live.addLayout(prog_top_row)

        self.main_progress_bar = QProgressBar()
        self.main_progress_bar.setRange(0, 100)
        self.main_progress_bar.setValue(0)
        self.main_progress_bar.setFixedHeight(14)
        self.main_progress_bar.setStyleSheet("""
            QProgressBar {
                background: #020617; border: 1px solid #1e293b; border-radius: 6px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #65a30d, stop:1 #a3e635);
                border-radius: 5px;
            }
        """)
        v_live.addWidget(self.main_progress_bar)

        layout.addWidget(grp_live)

        # Real-time Execution Console
        grp_log = QGroupBox("سجل العمليات اللحظي (Activity Log)")
        v_log = QVBoxLayout(grp_log)
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet("background: #020617; border: 1px solid #1e293b; font-family: monospace; font-size: 11px;")
        v_log.addWidget(self.txt_log)
        layout.addWidget(grp_log)

        return widget

    # ==========================================
    # TAB 5: HISTORY & REPORTS
    # ==========================================
    def _create_history_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        top_row = QHBoxLayout()
        self.lbl_history_summary = QLabel("إجمالي المرسل: 0 | الفاشل: 0")
        self.lbl_history_summary.setStyleSheet("font-size: 14px; font-weight: 900; color: #bef264;")

        btn_export_report = QPushButton("📊 تصدير التقرير الكامل إلى Excel")
        btn_export_report.setObjectName("btnPrimary")
        btn_export_report.clicked.connect(self.export_contacts_excel)

        top_row.addWidget(self.lbl_history_summary)
        top_row.addStretch()
        top_row.addWidget(btn_export_report)
        layout.addLayout(top_row)

        self.tbl_history = QTableWidget()
        self.tbl_history.setColumnCount(5)
        self.tbl_history.setHorizontalHeaderLabels(["الاسم", "رقم الهاتف", "الحالة", "وقت الإرسال", "التفاصيل / الخطأ"])
        self.tbl_history.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_history.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_history.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_history.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_history.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.tbl_history.setAlternatingRowColors(True)
        layout.addWidget(self.tbl_history)

        return widget

    # ==========================================
    # LOGIC & EVENT HANDLERS
    # ==========================================
    def import_contacts_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "اختر ملف جهات الاتصال",
            "",
            "Excel & CSV Files (*.xlsx *.xls *.csv);;Excel Files (*.xlsx *.xls);;CSV Files (*.csv);;All Files (*.*)"
        )
        if not file_path:
            return

        try:
            count, categories = self.contact_mgr.load_from_file(file_path)
            self._update_category_combobox(categories)
            self.refresh_contacts_table()
            QMessageBox.information(
                self,
                "تم الاستيراد بنجاح",
                f"تم استيراد {count} جهة اتصال بنجاح من الملف:\n{os.path.basename(file_path)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "خطأ في الاستيراد", f"تعذر قراءة الملف:\n{str(e)}")

    def open_sample_data(self):
        sample_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_data", "sample_contacts.xlsx")
        if os.path.exists(sample_path):
            try:
                count, categories = self.contact_mgr.load_from_file(sample_path)
                self._update_category_combobox(categories)
                self.refresh_contacts_table()
                QMessageBox.information(self, "تم تحميل النموذج", f"تم تحميل نموذج جهات الاتصال الجاهز ({count} عميل).")
            except Exception as e:
                QMessageBox.warning(self, "تنبيه", str(e))
        else:
            QMessageBox.information(self, "النموذج", "ملف النموذج موجود في مجلد sample_data داخل التطبيق.")

    def _update_category_combobox(self, categories: List[str]):
        self.cmb_category_filter.blockSignals(True)
        self.cmb_category_filter.clear()
        for cat in categories:
            self.cmb_category_filter.addItem(cat)
        self.cmb_category_filter.blockSignals(False)

    def apply_contact_filters(self):
        self.refresh_contacts_table()

    def refresh_contacts_table(self):
        cat = self.cmb_category_filter.currentText()
        query = self.txt_search.text()
        filtered = self.contact_mgr.filter_contacts(category=cat, search_query=query)

        self.tbl_contacts.blockSignals(True)
        self.tbl_contacts.setRowCount(len(filtered))

        selected_count = 0
        for row_idx, contact in enumerate(filtered):
            # Checkbox
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Checked if contact.selected else Qt.CheckState.Unchecked)
            self.tbl_contacts.setItem(row_idx, 0, chk_item)

            if contact.selected:
                selected_count += 1

            self.tbl_contacts.setItem(row_idx, 1, QTableWidgetItem(contact.name))
            self.tbl_contacts.setItem(row_idx, 2, QTableWidgetItem(contact.phone))
            self.tbl_contacts.setItem(row_idx, 3, QTableWidgetItem(contact.category))
            self.tbl_contacts.setItem(row_idx, 4, QTableWidgetItem(contact.notes))

            status_item = QTableWidgetItem(contact.status)
            if contact.status == "تم الإرسال":
                status_item.setForeground(QColor("#a3e635"))
            elif "فشل" in contact.status:
                status_item.setForeground(QColor("#fb7185"))
            self.tbl_contacts.setItem(row_idx, 5, status_item)

        self.tbl_contacts.blockSignals(False)
        self.lbl_contact_stats.setText(f"إجمالي جهات الاتصال: {len(self.contact_mgr.contacts)} | المحددة للإرسال: {selected_count}")

    def set_all_selection(self, select: bool):
        cat = self.cmb_category_filter.currentText()
        self.contact_mgr.select_all(selected=select, category=cat)
        self.refresh_contacts_table()

    def add_manual_contact(self):
        from PySide6.QtWidgets import QInputDialog
        phone, ok = QInputDialog.getText(self, "إضافة رقم", "ادخل رقم الهاتف (مثال: 010XXXXXXXX):")
        if ok and phone.strip():
            name, _ = QInputDialog.getText(self, "اسم العميل", "ادخل اسم العميل (اختياري):")
            cat, _ = QInputDialog.getText(self, "التصنيف", "ادخل التصنيف (مثال: VIP, أعضاء):", text="عام")
            self.contact_mgr.add_contact(phone=phone, name=name, category=cat)
            self._update_category_combobox(self.contact_mgr.get_categories())
            self.refresh_contacts_table()

    def export_contacts_excel(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "حفظ ملف Excel", "whatsapp_campaign_report.xlsx", "Excel Files (*.xlsx)")
        if file_path:
            try:
                self.contact_mgr.export_to_excel(file_path)
                QMessageBox.information(self, "تم التصدير", f"تم حفظ الملف بنجاح في:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر حفظ الملف:\n{str(e)}")

    def insert_template_tag(self, tag: str):
        self.txt_message.insertPlainText(tag)
        self.txt_message.setFocus()

    def pick_attachment(self, is_image: bool):
        filt = "Images (*.png *.jpg *.jpeg *.bmp *.webp)" if is_image else "All Files (*.*);;PDF Files (*.pdf);;Excel Files (*.xlsx)"
        file_path, _ = QFileDialog.getOpenFileName(self, "اختر المرفق", "", filt)
        if file_path:
            self.attachment_file_path = file_path
            self.lbl_attachment_name.setText(f"📎 {os.path.basename(file_path)} ({os.path.getsize(file_path) // 1024} KB)")
            self.lbl_attachment_name.setStyleSheet("color: #a3e635; font-weight: bold;")

    def clear_attachment(self):
        self.attachment_file_path = None
        self.lbl_attachment_name.setText("لا يوجد ملف أو صورة مرفقة (إرسال نصي فقط)")
        self.lbl_attachment_name.setStyleSheet("color: #94a3b8; font-weight: bold;")

    def preview_message(self):
        selected = self.contact_mgr.get_selected_contacts()
        first_contact = selected[0] if selected else Contact(phone="010XXXXXXXX", name="محمد أحمد", category="VIP")
        template = self.txt_message.toPlainText().strip()
        worker_helper = DispatchWorker(contacts=[], engine=self.engine)
        rendered = worker_helper._render_template(template, first_contact)
        attach_info = f"\n\n📎 المرفق: {os.path.basename(self.attachment_file_path)}" if self.attachment_file_path else ""

        QMessageBox.information(
            self,
            f"معاينة الرسالة — {first_contact.name} ({first_contact.phone})",
            f"{rendered}{attach_info}"
        )

    def start_coordinates_calibration(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("معايرة شريط البحث في واتساب")
        msg.setText(
            "سيبدأ عد تنازلي لمدة 3 ثوانٍ.\n"
            "يرجى وضع مؤشر الماوس فوراً فوق منتصف شريط البحث (Search bar) في WhatsApp Desktop وانتظار انتهاء الثواني."
        )
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        if msg.exec() == QMessageBox.StandardButton.Ok:
            self.btn_calibrate.setEnabled(False)
            self._calibration_countdown = 3

            def tick():
                if self._calibration_countdown > 0:
                    self.btn_calibrate.setText(f"⏱️ ضع الماوس على البحث... ({self._calibration_countdown})")
                    self._calibration_countdown -= 1
                    QTimer.singleShot(1000, tick)
                else:
                    import pyautogui
                    pos = pyautogui.position()
                    self.spn_coord_x.setValue(pos.x)
                    self.spn_coord_y.setValue(pos.y)
                    self.btn_calibrate.setText("🎯 معايرة شريط البحث تلقائياً (Calibrate)")
                    self.btn_calibrate.setEnabled(True)
                    QMessageBox.information(self, "تم حفظ الإحداثيات", f"تم التقاط الإحداثيات بنجاح:\nX = {pos.x}, Y = {pos.y}")

            tick()

    def _toggle_schedule_inputs(self, checked: bool):
        self.dt_picker.setEnabled(checked)
        if checked:
            self.btn_start_campaign.setText("⏰ جدولة وتثبيت الحملة التلقائية")
        else:
            self.btn_start_campaign.setText("🚀 بدء إرسال الحملة فوراً")

    def toggle_overlay(self):
        if self.overlay.isVisible():
            self.overlay.hide()
            self.btn_toggle_overlay.setText("🖥️ إظهار نافذة المراقبة (HUD)")
        else:
            self.overlay.show()
            self.overlay.enforce_topmost()
            self.btn_toggle_overlay.setText("🖥️ إخفاء نافذة المراقبة (HUD)")

    def restore_main_window(self):
        self.showNormal()
        self.activateWindow()

    # ==========================================
    # CAMPAIGN DISPATCH EXECUTION
    # ==========================================
    def start_dispatch(self):
        # Sync Table Checkboxes to Contact objects
        cat = self.cmb_category_filter.currentText()
        filtered = self.contact_mgr.filter_contacts(category=cat, search_query=self.txt_search.text())
        for row_idx, contact in enumerate(filtered):
            item = self.tbl_contacts.item(row_idx, 0)
            if item:
                contact.selected = (item.checkState() == Qt.CheckState.Checked)

        selected_contacts = self.contact_mgr.get_selected_contacts()
        if not selected_contacts:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد عميل واحد على الأقل من قائمة جهات الاتصال.")
            return

        template_text = self.txt_message.toPlainText().strip()
        if not template_text and not self.attachment_file_path:
            QMessageBox.warning(self, "تنبيه", "يرجى كتابة نص الرسالة أو اختيار مرفق للإرسال.")
            return

        # Configure Engine
        self.engine.search_x = self.spn_coord_x.value()
        self.engine.search_y = self.spn_coord_y.value()
        self.engine.min_delay = self.spn_min_delay.value()
        self.engine.max_delay = self.spn_max_delay.value()
        self.engine.send_mode = self.cmb_send_mode.currentData()
        self.engine.letter_delay = self.spn_char_delay.value()
        self.engine.human_mouse = self.chk_human_mouse.isChecked()
        self.engine.kill_switch_hotkey = self.cmb_kill_hotkey.currentData()

        # Check schedule
        sched_time = None
        if self.chk_schedule_later.isChecked():
            py_dt = self.dt_picker.dateTime().toPython()
            if py_dt > datetime.now():
                sched_time = py_dt

        # Ensure Mini Overlay is visible in top-left
        self.overlay.show()
        self.overlay.enforce_topmost()
        self.btn_toggle_overlay.setText("🖥️ إخفاء نافذة المراقبة (HUD)")

        # Prepare Worker Thread
        self.worker = DispatchWorker(
            contacts=selected_contacts,
            engine=self.engine,
            template_text=template_text,
            attachment_path=self.attachment_file_path,
            schedule_time=sched_time,
            parent=self
        )

        self.worker.progress_updated.connect(self._on_progress_updated)
        self.worker.countdown_tick.connect(self._on_countdown_tick)
        self.worker.status_updated.connect(self._on_status_updated)
        self.worker.contact_completed.connect(self._on_contact_completed)
        self.worker.batch_finished.connect(self._on_batch_finished)
        self.worker.emergency_stopped.connect(self._on_emergency_stopped)

        # UI state
        self.btn_start_campaign.setEnabled(False)
        self.btn_pause_campaign.setEnabled(True)
        self.btn_stop_campaign.setEnabled(True)
        self.tabs.setCurrentWidget(self.tab_dispatch)

        self.txt_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 بدء تجهيز حملة الإرسال لعدد ({len(selected_contacts)}) عميل...")
        self.worker.start()

    def toggle_pause_campaign(self):
        if not self.worker:
            return
        if not self.worker._is_paused:
            self.worker.pause()
            self.btn_pause_campaign.setText("▶️ استئناف الإرسال")
            self.overlay.set_paused_state(True)
        else:
            self.worker.resume()
            self.btn_pause_campaign.setText("⏸️ إيقاف مؤقت")
            self.overlay.set_paused_state(False)

    def pause_dispatch(self):
        if self.worker and not self.worker._is_paused:
            self.worker.pause()
            self.btn_pause_campaign.setText("▶️ استئناف الإرسال")

    def resume_dispatch(self):
        if self.worker and self.worker._is_paused:
            self.worker.resume()
            self.btn_pause_campaign.setText("⏸️ إيقاف مؤقت")

    def stop_dispatch(self):
        if self.worker:
            self.worker.stop()
            self.txt_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🛑 تم إيقاف الحملة بواسطة المستخدم أو زر الطوارئ.")
        self.btn_start_campaign.setEnabled(True)
        self.btn_pause_campaign.setEnabled(False)
        self.btn_stop_campaign.setEnabled(False)

    def _on_progress_updated(self, sent: int, total: int, remaining: int, name: str, phone: str):
        pct = int((sent / total * 100)) if total > 0 else 0
        self.lbl_main_counter.setText(f"{sent} / {total} رسالة ({pct}%) | المتبقي: {remaining}")
        self.main_progress_bar.setValue(pct)
        self.overlay.update_progress(sent, total, remaining, name, phone)

    def _on_countdown_tick(self, seconds_left: float):
        self.overlay.update_countdown(seconds_left)

    def _on_status_updated(self, text: str, is_active: bool):
        self.lbl_main_status.setText(text)
        self.overlay.update_status(text, is_active)
        if text.startswith("✓") or text.startswith("❌") or text.startswith("⏳"):
            self.txt_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")

    def _on_contact_completed(self, contact: Contact, success: bool, message: str):
        icon = "✓" if success else "❌"
        self.txt_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {icon} {contact.name} ({contact.phone}): {message}")
        self.refresh_contacts_table()
        self._append_history_row(contact, success, message)

    def _on_batch_finished(self, sent_count: int, failed_count: int):
        self.btn_start_campaign.setEnabled(True)
        self.btn_pause_campaign.setEnabled(False)
        self.btn_stop_campaign.setEnabled(False)
        self.txt_log.append(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🏁 انتهت الحملة: تم إرسال {sent_count} بنجاح، وفشل {failed_count}.")
        self.lbl_history_summary.setText(f"إجمالي المرسل بنجاح: {sent_count} | الفاشل: {failed_count}")
        QMessageBox.information(self, "اكتملت الحملة", f"اكتملت عمليات الإرسال!\nتم الإرسال بنجاح: {sent_count}\nفشل: {failed_count}")

    def _on_emergency_stopped(self, reason: str):
        self.btn_start_campaign.setEnabled(True)
        self.btn_pause_campaign.setEnabled(False)
        self.btn_stop_campaign.setEnabled(False)
        self.txt_log.append(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🚨 توقف طارئ: {reason}")
        QMessageBox.warning(self, "توقف طارئ", f"تم إيقاف الإرسال فوراً:\n{reason}")

    def _append_history_row(self, contact: Contact, success: bool, message: str):
        row = self.tbl_history.rowCount()
        self.tbl_history.insertRow(row)

        self.tbl_history.setItem(row, 0, QTableWidgetItem(contact.name))
        self.tbl_history.setItem(row, 1, QTableWidgetItem(contact.phone))

        st_item = QTableWidgetItem("ناجح ✓" if success else "فشل ✕")
        st_item.setForeground(QColor("#a3e635" if success else "#fb7185"))
        self.tbl_history.setItem(row, 2, st_item)

        self.tbl_history.setItem(row, 3, QTableWidgetItem(contact.sent_time or datetime.now().strftime("%H:%M:%S")))
        self.tbl_history.setItem(row, 4, QTableWidgetItem(message))
