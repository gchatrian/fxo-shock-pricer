"""
Dark theme styles for FX Option Pricer GUI.
Bloomberg-style dark theme with orange text on dark gray background.
"""

# Color palette
COLORS = {
    "background": "#2d2d2d",
    "background_alt": "#3a3a3a",
    "background_input": "#1a1a1a",
    "text_orange": "#ff8c00",
    "text_yellow": "#ffd700",
    "text_white": "#ffffff",
    "text_gray": "#888888",
    "border": "#555555",
    "border_focus": "#ff8c00",
    "button_bg": "#4a4a4a",
    "button_hover": "#5a5a5a",
    "selection": "#ff8c00",
    "error": "#ff4444",
}

DARK_THEME_QSS = """
QMainWindow {
    background-color: %(background)s;
}

QWidget {
    background-color: %(background)s;
    color: %(text_orange)s;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 14px;
}

QLabel {
    background-color: transparent;
    color: %(text_orange)s;
    padding: 2px;
    font-size: 14px;
}

QLabel[objectName="label_header"] {
    font-weight: bold;
    font-size: 15px;
}

QLabel[objectName="label_value"] {
    color: %(text_yellow)s;
}

QLabel[objectName="label_section"] {
    background-color: %(background_alt)s;
    border: 1px solid %(border)s;
    padding: 3px 5px;
    font-weight: bold;
    font-size: 14px;
}

QLineEdit {
    background-color: %(background_input)s;
    color: %(text_yellow)s;
    border: 1px solid %(border)s;
    padding: 4px 6px;
    selection-background-color: %(selection)s;
    font-size: 14px;
}

QLineEdit:focus {
    border: 1px solid %(border_focus)s;
}

QLineEdit:disabled {
    color: %(text_gray)s;
    background-color: %(background)s;
}

QLineEdit[readOnly="true"] {
    background-color: %(background)s;
    color: %(text_yellow)s;
}

QComboBox {
    background-color: %(background_input)s;
    color: %(text_orange)s;
    border: 1px solid %(border)s;
    padding: 4px 6px;
    min-width: 60px;
    font-size: 14px;
}

QComboBox:hover {
    border: 1px solid %(border_focus)s;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 7px solid %(text_orange)s;
    margin-right: 5px;
}

QComboBox QAbstractItemView {
    background-color: %(background_input)s;
    color: %(text_orange)s;
    border: 1px solid %(border)s;
    selection-background-color: %(selection)s;
    selection-color: %(background)s;
    font-size: 14px;
}

QPushButton {
    background-color: %(button_bg)s;
    color: %(text_orange)s;
    border: 1px solid %(border)s;
    padding: 6px 18px;
    min-width: 80px;
    font-size: 14px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: %(button_hover)s;
    border: 1px solid %(border_focus)s;
}

QPushButton:pressed {
    background-color: %(background_input)s;
}

QPushButton:disabled {
    color: %(text_gray)s;
    background-color: %(background)s;
}

QGroupBox {
    background-color: %(background_alt)s;
    border: 1px solid %(border)s;
    margin-top: 10px;
    padding-top: 10px;
    font-size: 14px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    color: %(text_orange)s;
    font-weight: bold;
}

QSpinBox, QDoubleSpinBox {
    background-color: %(background_input)s;
    color: %(text_yellow)s;
    border: 1px solid %(border)s;
    padding: 4px 6px;
    font-size: 14px;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid %(border_focus)s;
}

QDateEdit {
    background-color: %(background_input)s;
    color: %(text_yellow)s;
    border: 1px solid %(border)s;
    padding: 4px 6px;
    font-size: 14px;
}

QDateEdit:focus {
    border: 1px solid %(border_focus)s;
}

QDateEdit::drop-down {
    border: none;
    width: 20px;
}

QScrollBar:vertical {
    background-color: %(background)s;
    width: 14px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: %(button_bg)s;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background-color: %(button_hover)s;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QFrame {
    background-color: %(background)s;
    border: none;
}

QFrame[frameShape="4"] {
    background-color: %(border)s;
    max-height: 1px;
}

QFrame[frameShape="5"] {
    background-color: %(border)s;
    max-width: 1px;
}

QMenuBar {
    background-color: %(background)s;
    color: %(text_orange)s;
    font-size: 14px;
}

QMenuBar::item:selected {
    background-color: %(button_bg)s;
}

QMenu {
    background-color: %(background_input)s;
    color: %(text_orange)s;
    border: 1px solid %(border)s;
    font-size: 14px;
}

QMenu::item:selected {
    background-color: %(selection)s;
    color: %(background)s;
}

QStatusBar {
    background-color: %(background_alt)s;
    color: %(text_orange)s;
    border-top: 1px solid %(border)s;
    font-size: 13px;
}

QToolTip {
    background-color: %(background_input)s;
    color: %(text_yellow)s;
    border: 1px solid %(border)s;
    padding: 4px;
    font-size: 13px;
}

QMessageBox {
    background-color: %(background)s;
}

QMessageBox QLabel {
    color: %(text_orange)s;
    font-size: 14px;
}
""" % COLORS


def get_stylesheet() -> str:
    """Get the complete dark theme stylesheet."""
    return DARK_THEME_QSS


def get_color(name: str) -> str:
    """Get a color from the palette by name."""
    return COLORS.get(name, COLORS["text_orange"])
