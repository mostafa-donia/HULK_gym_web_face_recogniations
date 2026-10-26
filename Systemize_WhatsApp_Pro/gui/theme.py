THEME_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #06090e;
    color: #f1f5f9;
    font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
}

QWidget {
    font-size: 13px;
    color: #f1f5f9;
}

QTabWidget::pane {
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: #090e17;
    border-radius: 12px;
    padding: 12px;
}

QTabBar::tab {
    background: #0f172a;
    color: #94a3b8;
    padding: 10px 18px;
    margin-right: 4px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    font-weight: 800;
}

QTabBar::tab:selected {
    background: #84cc16;
    color: #022c22;
}

QTabBar::tab:hover:!selected {
    background: #1e293b;
    color: #fff;
}

/* GroupBox */
QGroupBox {
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 14px;
    margin-top: 24px;
    padding-top: 18px;
    background-color: rgba(15, 23, 42, 0.6);
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top right;
    padding: 0 10px;
    color: #a3e635;
    font-size: 12px;
    font-weight: 900;
}

/* Inputs & Combos */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit {
    background-color: #020617;
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 8px 12px;
    color: #f8fafc;
    selection-background-color: #84cc16;
    selection-color: #000;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
    border: 1.5px solid #a3e635;
    background-color: #030712;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top left;
    width: 25px;
    border-left-width: 1px;
    border-left-color: #334155;
    border-left-style: solid;
}

QComboBox QAbstractItemView {
    background-color: #0f172a;
    border: 1px solid #334155;
    color: #f8fafc;
    selection-background-color: #84cc16;
    selection-color: #022c22;
}

/* Buttons */
QPushButton {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 8px 16px;
    font-weight: 800;
}

QPushButton:hover {
    background-color: #334155;
    border-color: #475569;
}

QPushButton:pressed {
    background-color: #0f172a;
}

QPushButton#btnPrimary {
    background-color: #84cc16;
    color: #052e16;
    border: 1px solid #65a30d;
    font-weight: 900;
}

QPushButton#btnPrimary:hover {
    background-color: #a3e635;
    color: #022c22;
}

QPushButton#btnDanger {
    background-color: #be123c;
    color: #fff;
    border: 1px solid #9f1239;
    font-weight: 800;
}

QPushButton#btnDanger:hover {
    background-color: #e11d48;
}

/* Tables */
QTableWidget, QTableView {
    background-color: #020617;
    alternate-background-color: #090e17;
    gridline-color: rgba(255, 255, 255, 0.05);
    border: 1px solid #1e293b;
    border-radius: 10px;
    color: #f8fafc;
    selection-background-color: rgba(132, 204, 22, 0.25);
    selection-color: #bef264;
}

QHeaderView::section {
    background-color: #0f172a;
    color: #94a3b8;
    padding: 8px;
    font-weight: 800;
    border: none;
    border-bottom: 1.5px solid #334155;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: #020617;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #334155;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #64748b;
}

/* CheckBox */
QCheckBox {
    spacing: 8px;
    color: #e2e8f0;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1.5px solid #475569;
    background: #020617;
}
QCheckBox::indicator:checked {
    background: #84cc16;
    border-color: #65a30d;
}
"""
