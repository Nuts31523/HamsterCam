STYLESHEET = """
QWidget {
    color: #ece9f6;
    font-family: "Segoe UI";
    font-size: 13px;
}
QMainWindow, QDialog { background: #13111a; }
QFrame[card="true"] {
    background: #1c1926;
    border: 1px solid #312b40;
    border-radius: 14px;
}
QFrame[separator="true"] { background: #312b40; min-height: 1px; max-height: 1px; }
QLabel { background: transparent; }
QLabel[role="title"] { font-size: 26px; font-weight: 700; color: #f4efff; }
QLabel[role="heading"] { font-size: 16px; font-weight: 650; }
QLabel[role="muted"] { color: #b4adc8; }
QLabel[role="accent"] { color: #cbb4ff; font-weight: 650; }
QLabel[role="status"] { color: #d3c4ee; background: #241d36; border-radius: 9px; padding: 8px 12px; }
QLabel[role="error"] { color: #ffc5c5; background: #35232e; border-radius: 8px; padding: 7px 10px; }
QPushButton, QComboBox, QSpinBox {
    background: #292338;
    border: 1px solid #443858;
    border-radius: 8px;
    padding: 7px 11px;
    min-height: 19px;
}
QPushButton:hover, QComboBox:hover { background: #352b49; border-color: #9674d8; }
QPushButton:focus, QComboBox:focus, QSpinBox:focus, QListWidget:focus { border-color: #bc99ff; }
QPushButton:pressed { background: #432f66; }
QPushButton[primary="true"] {
    background: #bda0ff;
    border-color: #bda0ff;
    color: #1b102e;
    font-weight: 700;
    min-height: 26px;
}
QPushButton[primary="true"]:hover { background: #d0bdff; border-color: #d0bdff; }
QPushButton:disabled, QComboBox:disabled { color: #a19ab1; background: #221e2d; border-color: #352e43; }
QComboBox QAbstractItemView, QListWidget {
    background: #292338;
    border: 1px solid #443858;
    selection-background-color: #5b4380;
    selection-color: white;
    outline: 0;
}
QListWidget::item { padding: 5px; }
QSlider::groove:horizontal { height: 5px; background: #443858; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #bda0ff; border-radius: 2px; }
QSlider::handle:horizontal { background: #dbc8ff; width: 13px; margin: -4px 0; border-radius: 6px; }
QCheckBox { spacing: 8px; min-height: 22px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QMenu { background: #292338; border: 1px solid #443858; padding: 4px; }
QMenu::item { padding: 6px 18px; }
QMenu::item:selected { background: #5b4380; }
QScrollArea { background: transparent; border: 0; }
QWidget#scrollBody { background: transparent; }
QScrollBar:vertical { background: #1c1926; width: 8px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #534368; min-height: 24px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { color: #f4efff; background: #31253f; border: 1px solid #604a7b; padding: 4px; }
"""
