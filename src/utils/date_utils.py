"""
Date utilities for FX Option Pricer.
Handles tenor string parsing and date conversions.
"""

import re
from datetime import date, datetime
from typing import Optional, Tuple, Union

import QuantLib as ql


# Tenor pattern: number followed by D(ay), W(eek), M(onth), Y(ear)
TENOR_PATTERN = re.compile(r"^(\d+)([DWMY])$", re.IGNORECASE)


def is_tenor(value: str) -> bool:
    """
    Check if a string is a valid tenor format.

    Args:
        value: String to check (e.g., "1Y", "6M", "2W", "5D")

    Returns:
        True if valid tenor format, False otherwise.
    """
    if not value:
        return False
    return TENOR_PATTERN.match(value.strip()) is not None


def parse_tenor(tenor: str) -> ql.Period:
    """
    Parse a tenor string into a QuantLib Period.

    Args:
        tenor: Tenor string (e.g., "1Y", "6M", "2W", "5D")

    Returns:
        QuantLib Period object.

    Raises:
        ValueError: If tenor format is invalid.
    """
    tenor = tenor.strip().upper()
    match = TENOR_PATTERN.match(tenor)

    if not match:
        raise ValueError(f"Invalid tenor format: {tenor}. Expected format like '1Y', '6M', '2W', '5D'")

    number = int(match.group(1))
    unit = match.group(2)

    unit_map = {
        "D": ql.Days,
        "W": ql.Weeks,
        "M": ql.Months,
        "Y": ql.Years,
    }

    return ql.Period(number, unit_map[unit])


def parse_tenor_to_components(tenor: str) -> Tuple[int, str]:
    """
    Parse a tenor string into its numeric and unit components.

    Args:
        tenor: Tenor string (e.g., "1Y", "6M")

    Returns:
        Tuple of (number, unit_letter).

    Raises:
        ValueError: If tenor format is invalid.
    """
    tenor = tenor.strip().upper()
    match = TENOR_PATTERN.match(tenor)

    if not match:
        raise ValueError(f"Invalid tenor format: {tenor}")

    return int(match.group(1)), match.group(2)


def tenor_to_years(tenor: str) -> float:
    """
    Convert tenor string to approximate number of years.

    Args:
        tenor: Tenor string (e.g., "1Y", "6M", "2W")

    Returns:
        Approximate number of years as float.
    """
    number, unit = parse_tenor_to_components(tenor)

    if unit == "D":
        return number / 365.0
    elif unit == "W":
        return number * 7 / 365.0
    elif unit == "M":
        return number / 12.0
    elif unit == "Y":
        return float(number)
    else:
        raise ValueError(f"Unknown tenor unit: {unit}")


def date_to_ql(py_date: date) -> ql.Date:
    """
    Convert Python date to QuantLib Date.

    Args:
        py_date: Python date object.

    Returns:
        QuantLib Date object.
    """
    return ql.Date(py_date.day, py_date.month, py_date.year)


def ql_to_date(ql_date: ql.Date) -> date:
    """
    Convert QuantLib Date to Python date.

    Args:
        ql_date: QuantLib Date object.

    Returns:
        Python date object.
    """
    return date(ql_date.year(), ql_date.month(), ql_date.dayOfMonth())


def parse_date_or_tenor(value: str, reference_date: Optional[date] = None) -> Union[date, str]:
    """
    Parse a string that could be either a date or a tenor.

    Args:
        value: String to parse (date format or tenor like "1Y")
        reference_date: Reference date for tenor calculation (default: today)

    Returns:
        If tenor: returns the tenor string (unchanged, for later processing with calendar)
        If date: returns parsed date

    Raises:
        ValueError: If neither a valid date nor tenor.
    """
    value = value.strip()

    # Check if it's a tenor first
    if is_tenor(value):
        return value.upper()

    # Try to parse as date (multiple formats)
    date_formats = [
        "%Y-%m-%d",  # 2024-12-31
        "%d/%m/%Y",  # 31/12/2024
        "%m/%d/%Y",  # 12/31/2024
        "%d-%m-%Y",  # 31-12-2024
        "%d.%m.%Y",  # 31.12.2024
        "%Y%m%d",    # 20241231
    ]

    for fmt in date_formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    raise ValueError(
        f"Invalid date or tenor format: {value}. "
        "Expected tenor (e.g., '1Y', '6M') or date (e.g., '2024-12-31', '31/12/2024')"
    )


def format_date(d: date, fmt: str = "%d/%m/%Y") -> str:
    """
    Format a date for display.

    Args:
        d: Date to format.
        fmt: Format string.

    Returns:
        Formatted date string.
    """
    return d.strftime(fmt)


def year_fraction(start_date: date, end_date: date, day_count: str = "ACT/365") -> float:
    """
    Calculate year fraction between two dates.

    Args:
        start_date: Start date.
        end_date: End date.
        day_count: Day count convention (ACT/365, ACT/360, 30/360).

    Returns:
        Year fraction as float.
    """
    days = (end_date - start_date).days

    if day_count == "ACT/365":
        return days / 365.0
    elif day_count == "ACT/360":
        return days / 360.0
    elif day_count == "30/360":
        # Simplified 30/360
        d1 = min(start_date.day, 30)
        d2 = min(end_date.day, 30) if d1 == 30 else end_date.day
        return (
            (end_date.year - start_date.year) * 360
            + (end_date.month - start_date.month) * 30
            + (d2 - d1)
        ) / 360.0
    else:
        raise ValueError(f"Unknown day count convention: {day_count}")
