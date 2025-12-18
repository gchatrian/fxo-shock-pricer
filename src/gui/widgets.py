"""
Custom widgets for FX Option Pricer GUI.
"""

from datetime import date
from typing import Optional, Callable, List

from PyQt6.QtWidgets import (
    QWidget, QLineEdit, QComboBox, QLabel, QHBoxLayout, QVBoxLayout,
    QGridLayout, QFrame, QDoubleSpinBox, QDateEdit, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QDate
from PyQt6.QtGui import QDoubleValidator

from ..utils.date_utils import is_tenor, parse_date_or_tenor, format_date


class LabeledField(QWidget):
    """A label with an associated input field."""

    valueChanged = pyqtSignal()

    def __init__(
        self,
        label_text: str,
        field_widget: QWidget,
        label_width: int = 80,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.label = QLabel(label_text)
        self.label.setFixedWidth(label_width)
        self.label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.field = field_widget

        layout.addWidget(self.label)
        layout.addWidget(self.field, 1)


class TenorDateEdit(QWidget):
    """Combined widget that accepts either a tenor string or a date."""

    valueChanged = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.input = QLineEdit()
        self.input.setPlaceholderText("1Y or 12/16/25")
        self.input.textChanged.connect(self._on_text_changed)

        self.date_display = QLineEdit()
        self.date_display.setReadOnly(True)
        self.date_display.setFixedWidth(80)

        layout.addWidget(self.input, 1)
        layout.addWidget(self.date_display)

        self._calculated_date: Optional[date] = None
        self._tenor: Optional[str] = None

    def _on_text_changed(self, text: str) -> None:
        """Handle input text change."""
        text = text.strip()

        if is_tenor(text):
            self._tenor = text.upper()
            self._calculated_date = None
            self.date_display.setText("")
        else:
            self._tenor = None
            try:
                result = parse_date_or_tenor(text)
                if isinstance(result, date):
                    self._calculated_date = result
                    self.date_display.setText(format_date(result))
            except ValueError:
                self._calculated_date = None
                self.date_display.setText("")

        self.valueChanged.emit()

    def set_calculated_date(self, d: date) -> None:
        """Set the calculated date (when using tenor)."""
        self._calculated_date = d
        self.date_display.setText(format_date(d))

    def get_value(self) -> tuple:
        """Get the current value."""
        return self._tenor, self._calculated_date

    def get_date(self) -> Optional[date]:
        """Get the calculated/entered date."""
        return self._calculated_date

    def get_tenor(self) -> Optional[str]:
        """Get the tenor if entered."""
        return self._tenor

    def set_value(self, value: str) -> None:
        """Set the input value."""
        self.input.setText(value)


class NumericInput(QLineEdit):
    """Line edit that only accepts numeric input. Accepts both . and , as decimal separator."""

    valueChanged = pyqtSignal(float)

    def __init__(
        self,
        decimals: int = 4,
        min_val: float = -1e12,
        max_val: float = 1e12,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)

        self._decimals = decimals
        # No validator - we handle validation manually to support both . and ,
        self.textChanged.connect(self._on_text_changed)

    def _normalize_number(self, text: str) -> str:
        """Normalize number string: handle various international formats."""
        if not text:
            return "0"
        # Remove spaces
        text = text.replace(" ", "").replace("'", "")
        
        # Count occurrences
        comma_count = text.count(",")
        dot_count = text.count(".")
        
        if comma_count == 0 and dot_count == 0:
            # No separators: plain number
            return text
        elif comma_count == 0:
            # Only dots: could be decimal or thousands
            # If single dot, treat as decimal
            # If multiple dots, treat as thousands (European: 1.000.000)
            if dot_count == 1:
                return text  # Already correct format
            else:
                return text.replace(".", "")  # Remove thousands separators
        elif dot_count == 0:
            # Only commas: could be decimal or thousands
            # If single comma, treat as decimal (European: 1000,50)
            # If multiple commas, treat as thousands (US: 1,000,000)
            if comma_count == 1:
                return text.replace(",", ".")  # European decimal
            else:
                return text.replace(",", "")  # US thousands
        else:
            # Both present: determine which is decimal
            last_comma = text.rfind(",")
            last_dot = text.rfind(".")
            
            if last_comma > last_dot:
                # Comma is decimal separator (European: 1.000.000,50)
                text = text.replace(".", "").replace(",", ".")
            else:
                # Dot is decimal separator (US: 1,000,000.50)
                text = text.replace(",", "")
            return text

    def _on_text_changed(self, text: str) -> None:
        """Emit value changed signal."""
        try:
            normalized = self._normalize_number(text)
            value = float(normalized) if normalized else 0.0
            self.valueChanged.emit(value)
        except ValueError:
            pass

    def get_value(self) -> float:
        """Get the numeric value."""
        try:
            return float(self._normalize_number(self.text()))
        except ValueError:
            return 0.0

    def set_value(self, value: float, use_thousands_sep: bool = False) -> None:
        """Set the numeric value using dot as decimal separator."""
        if use_thousands_sep:
            self.setText(f"{value:,.{self._decimals}f}")
        else:
            self.setText(f"{value:.{self._decimals}f}")


class ReadOnlyField(QLineEdit):
    """Read-only display field."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setReadOnly(True)

    def set_value(self, value: str) -> None:
        """Set the display value."""
        self.setText(value)

    def set_numeric(self, value: float, decimals: int = 4, suffix: str = "") -> None:
        """Set a numeric value with formatting."""
        self.setText(f"{value:,.{decimals}f}{suffix}")


class DropdownField(QComboBox):
    """Styled dropdown field."""

    def __init__(
        self,
        items: List[str],
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.addItems(items)

    def get_value(self) -> str:
        """Get the selected value."""
        return self.currentText()

    def set_value(self, value: str) -> None:
        """Set the selected value."""
        index = self.findText(value)
        if index >= 0:
            self.setCurrentIndex(index)


class SectionHeader(QFrame):
    """Collapsible section header."""

    def __init__(self, title: str, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("section_header")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 3, 5, 3)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("label_section")

        layout.addWidget(self.title_label)
        layout.addStretch()


class ResultRow(QWidget):
    """A row displaying a result with label and value."""

    def __init__(
        self,
        label_text: str,
        label_width: int = 80,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.label = QLabel(label_text)
        self.label.setFixedWidth(label_width)
        self.label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.value = ReadOnlyField()

        layout.addWidget(self.label)
        layout.addWidget(self.value, 1)

    def set_value(self, value: str) -> None:
        """Set the result value."""
        self.value.setText(value)

    def set_numeric(self, value: float, decimals: int = 4, suffix: str = "") -> None:
        """Set a numeric value."""
        self.value.set_numeric(value, decimals, suffix)


class InputRow(QWidget):
    """A row with label, optional dropdown, and input field."""

    valueChanged = pyqtSignal()

    def __init__(
        self,
        label_text: str,
        dropdown_items: Optional[List[str]] = None,
        label_width: int = 70,
        dropdown_width: int = 60,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(3)

        self.label = QLabel(label_text)
        self.label.setFixedWidth(label_width)
        self.label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.label)

        self.dropdown = None
        if dropdown_items:
            self.dropdown = DropdownField(dropdown_items)
            self.dropdown.setFixedWidth(dropdown_width)
            self.dropdown.currentTextChanged.connect(lambda: self.valueChanged.emit())
            layout.addWidget(self.dropdown)

        self.input = QLineEdit()
        self.input.textChanged.connect(lambda: self.valueChanged.emit())
        layout.addWidget(self.input, 1)

    def get_value(self) -> str:
        """Get the input value."""
        return self.input.text()

    def set_value(self, value: str) -> None:
        """Set the input value."""
        self.input.setText(value)

    def get_dropdown_value(self) -> Optional[str]:
        """Get the dropdown value if present."""
        return self.dropdown.currentText() if self.dropdown else None

    def set_dropdown_value(self, value: str) -> None:
        """Set the dropdown value if present."""
        if self.dropdown:
            self.dropdown.set_value(value)

    def set_readonly(self, readonly: bool = True) -> None:
        """Set input as read-only."""
        self.input.setReadOnly(readonly)


class DualValueRow(QWidget):
    """A row that displays two values."""

    def __init__(
        self,
        label_text: str,
        label_width: int = 70,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(3)

        self.label = QLabel(label_text)
        self.label.setFixedWidth(label_width)
        self.label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.label)

        self.value1 = ReadOnlyField()
        layout.addWidget(self.value1, 1)

        sep = QLabel("/")
        sep.setFixedWidth(10)
        sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sep)

        self.value2 = ReadOnlyField()
        layout.addWidget(self.value2, 1)

    def set_values(self, val1: str, val2: str) -> None:
        """Set both values."""
        self.value1.setText(val1)
        self.value2.setText(val2)

    def set_numeric_values(
        self,
        val1: float,
        val2: float,
        decimals1: int = 4,
        decimals2: int = 4
    ) -> None:
        """Set both values as numbers."""
        self.value1.set_numeric(val1, decimals1)
        self.value2.set_numeric(val2, decimals2)
