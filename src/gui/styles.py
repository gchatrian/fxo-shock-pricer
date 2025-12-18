"""
Dark theme styles for FX Option Pricer GUI.
Bloomberg-style dark theme with orange text on dark gray background.
"""

# Color palette (from reference image)
COLORS = {
    "background": "#2d2d2d",           # Dark gray background
    "background_alt": "#3a3a3a",       # Slightly lighter for sections
    "background_input": "#1a1a1a",     # Darker for input fields
    "text_orange": "#ff8c00",          # Orange text (main)
    "text_yellow": "#ffd700",          # Yellow for highlights/values
    "text_white": "#ffffff",           # White for some labels
    "text_gray": "#888888",            # Gray for disabled/secondary
    "border": "#555555",               # Border color
    "border_focus": "#ff8c00",         # Orange border on focus
    "button_bg": "#4a4a4a",            # Button background
    "button_hover": "#5a5a5a",         # Button hover
    "selection": "#ff8c00",            # Selection background
    "error": "#ff4444",                # Error color
}

# Main stylesheet
DARK_THEME_QSS = """
/* Main Window */
QMainWindow {
    background-color: %(background)s;
}

QWidget {
    background-color: %(background)s;
    color: %(text_orange)s;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 11px;
}

/* Labels */
QLabel {
    background-color: transparent;
    color: %(text_orange)s;
    padding: 2px;
}

QLabel[objectName="label_header"] {
    font-weight: bold;
    font-size: 12px;
}

QLabel[objectName="label_value"] {
    color: %(text_yellow)s;
}

QLabel[objectName="label_section"] {
    background-color: %(background_alt)s;
    border: 1px solid %(border)s;
    padding: 3px 5px;
    font-weight: bold;
}

/* Line Edit */
QLineEdit {
    background-color: %(background_input)s;
    color: %(text_yellow)s;
    border: 1px solid %(border)s;
    padding: 3px 5px;
    selection-background-color: %(selection)s;
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

/* Combo Box */
QComboBox {
    background-color: %(background_input)s;
    color: %(text_orange)s;
    border: 1px solid %(border)s;
    padding: 3px 5px;
    min-width: 60px;
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
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid %(text_orange)s;
    margin-right: 5px;
}

QComboBox QAbstractItemView {
    background-color: %(background_input)s;
    color: %(text_orange)s;
    border: 1px solid %(border)s;
    selection-background-color: %(selection)s;
    selection-color: %(background)s;
}

/* Push Button */
QPushButton {
    background-color: %(button_bg)s;
    color: %(text_orange)s;
    border: 1px solid %(border)s;
    padding: 5px 15px;
    min-width: 60px;
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

/* Group Box */
QGroupBox {
    background-color: %(background_alt)s;
    border: 1px solid %(border)s;
    margin-top: 10px;
    padding-top: 10px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    color: %(text_orange)s;
    font-weight: bold;
}

/* Spin Box */
QSpinBox, QDoubleSpinBox {
    background-color: %(background_input)s;
    color: %(text_yellow)s;
    border: 1px solid %(border)s;
    padding: 3px 5px;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid %(border_focus)s;
}

/* Date Edit */
QDateEdit {
    background-color: %(background_input)s;
    color: %(text_yellow)s;
    border: 1px solid %(border)s;
    padding: 3px 5px;
}

QDateEdit:focus {
    border: 1px solid %(border_focus)s;
}

QDateEdit::drop-down {
    border: none;
    width: 20px;
}

/* Scroll Bar */
QScrollBar:vertical {
    background-color: %(background)s;
    width: 12px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: %(button_bg)s;
    min-height: 20px;
    border-radius: 3px;
}

QScrollBar::handle:vertical:hover {
    background-color: %(button_hover)s;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Frame */
QFrame {
    background-color: %(background)s;
    border: none;
}

QFrame[frameShape="4"] {  /* HLine */
    background-color: %(border)s;
    max-height: 1px;
}

QFrame[frameShape="5"] {  /* VLine */
    background-color: %(border)s;
    max-width: 1px;
}

/* Menu */
QMenuBar {
    background-color: %(background)s;
    color: %(text_orange)s;
}

QMenuBar::item:selected {
    background-color: %(button_bg)s;
}

QMenu {
    background-color: %(background_input)s;
    color: %(text_orange)s;
    border: 1px solid %(border)s;
}

QMenu::item:selected {
    background-color: %(selection)s;
    color: %(background)s;
}

/* Status Bar */
QStatusBar {
    background-color: %(background_alt)s;
    color: %(text_orange)s;
    border-top: 1px solid %(border)s;
}

/* Tool Tip */
QToolTip {
    background-color: %(background_input)s;
    color: %(text_yellow)s;
    border: 1px solid %(border)s;
    padding: 3px;
}

/* Message Box */
QMessageBox {
    background-color: %(background)s;
}

QMessageBox QLabel {
    color: %(text_orange)s;
}
""" % COLORS


def get_stylesheet() -> str:
    """Get the complete dark theme stylesheet."""
    return DARK_THEME_QSS


def get_color(name: str) -> str:
    """Get a color from the palette by name."""
    return COLORS.get(name, COLORS["text_orange"])
