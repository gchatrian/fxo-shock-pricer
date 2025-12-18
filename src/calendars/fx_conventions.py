"""
FX Calendar conventions using QuantLib.
Handles combined calendars, spot date calculation, expiry and delivery dates.
"""

from datetime import date
from typing import Dict, Tuple

import QuantLib as ql

from ..utils.date_utils import date_to_ql, ql_to_date, parse_tenor


class FXCalendarFactory:
    """Factory for creating combined FX calendars and calculating FX dates."""

    # Currency to QuantLib calendar mapping
    CALENDARS: Dict[str, ql.Calendar] = {
        "EUR": ql.TARGET(),
        "USD": ql.UnitedStates(ql.UnitedStates.FederalReserve),
        "GBP": ql.UnitedKingdom(ql.UnitedKingdom.Exchange),
        "JPY": ql.Japan(),
        "AUD": ql.Australia(),
        "CAD": ql.Canada(),
        "CHF": ql.Switzerland(),
        "NZD": ql.NewZealand(),
        "SEK": ql.Sweden(),
        "NOK": ql.Norway(),
        "DKK": ql.Denmark(),
        "SGD": ql.Singapore(),
        "HKD": ql.HongKong(),
    }

    # Currency pairs with T+1 spot settlement
    T_PLUS_ONE_PAIRS = {
        "USDCAD", "CADUSD",
        "USDTRY", "TRYUSD",
        "USDPHP", "PHPUSD",
        "USDRUB", "RUBUSD",
    }

    @classmethod
    def get_currency_calendar(cls, currency: str) -> ql.Calendar:
        """
        Get the calendar for a single currency.

        Args:
            currency: 3-letter currency code.

        Returns:
            QuantLib Calendar for the currency.

        Raises:
            ValueError: If currency not supported.
        """
        currency = currency.upper()
        if currency not in cls.CALENDARS:
            raise ValueError(f"Unsupported currency: {currency}. Supported: {list(cls.CALENDARS.keys())}")
        return cls.CALENDARS[currency]

    @classmethod
    def parse_currency_pair(cls, ccy_pair: str) -> Tuple[str, str]:
        """
        Parse currency pair into base and quote currencies.

        Args:
            ccy_pair: Currency pair string (e.g., "EURUSD", "EUR/USD")

        Returns:
            Tuple of (base_currency, quote_currency).
        """
        ccy_pair = ccy_pair.upper().replace("/", "").replace(" ", "")
        if len(ccy_pair) != 6:
            raise ValueError(f"Invalid currency pair: {ccy_pair}. Expected 6 characters.")
        return ccy_pair[:3], ccy_pair[3:]

    @classmethod
    def get_combined_calendar(cls, ccy_pair: str) -> ql.Calendar:
        """
        Get combined calendar for a currency pair.
        The combined calendar marks a day as holiday if either currency has a holiday.

        Args:
            ccy_pair: Currency pair (e.g., "EURUSD")

        Returns:
            QuantLib JointCalendar for the pair.
        """
        base_ccy, quote_ccy = cls.parse_currency_pair(ccy_pair)
        cal1 = cls.get_currency_calendar(base_ccy)
        cal2 = cls.get_currency_calendar(quote_ccy)
        return ql.JointCalendar(cal1, cal2)

    @classmethod
    def get_spot_days(cls, ccy_pair: str) -> int:
        """
        Get number of spot days for a currency pair.

        Args:
            ccy_pair: Currency pair.

        Returns:
            Number of days for spot settlement (1 or 2).
        """
        ccy_pair_normalized = ccy_pair.upper().replace("/", "").replace(" ", "")
        if ccy_pair_normalized in cls.T_PLUS_ONE_PAIRS:
            return 1
        return 2

    @classmethod
    def get_spot_date(cls, ccy_pair: str, trade_date: date) -> date:
        """
        Calculate spot date for a currency pair.

        Args:
            ccy_pair: Currency pair.
            trade_date: Trade/horizon date.

        Returns:
            Spot date.
        """
        calendar = cls.get_combined_calendar(ccy_pair)
        spot_days = cls.get_spot_days(ccy_pair)
        ql_trade_date = date_to_ql(trade_date)

        # Advance by spot days using business day convention
        ql_spot_date = calendar.advance(
            ql_trade_date,
            spot_days,
            ql.Days,
            ql.Following
        )

        return ql_to_date(ql_spot_date)

    @classmethod
    def get_expiry_from_tenor(
        cls,
        ccy_pair: str,
        trade_date: date,
        tenor: str
    ) -> date:
        """
        Calculate option expiry date from a tenor string.
        Uses FX conventions: expiry is calculated such that delivery = spot_date + tenor.

        Args:
            ccy_pair: Currency pair.
            trade_date: Trade/horizon date.
            tenor: Tenor string (e.g., "1M", "3M", "1Y").

        Returns:
            Option expiry date.
        """
        calendar = cls.get_combined_calendar(ccy_pair)
        spot_days = cls.get_spot_days(ccy_pair)
        ql_trade_date = date_to_ql(trade_date)
        period = parse_tenor(tenor)

        # Calculate spot date
        ql_spot_date = calendar.advance(ql_trade_date, spot_days, ql.Days, ql.Following)

        # Delivery date = spot date + tenor (adjusted for business days)
        ql_delivery_date = calendar.advance(
            ql_spot_date,
            period,
            ql.ModifiedFollowing,
            True  # End of month rule
        )

        # Expiry date = delivery date - spot days
        # This is the "inverse spot" calculation
        ql_expiry_date = calendar.advance(
            ql_delivery_date,
            -spot_days,
            ql.Days,
            ql.Preceding
        )

        return ql_to_date(ql_expiry_date)

    @classmethod
    def get_delivery_from_expiry(cls, ccy_pair: str, expiry_date: date) -> date:
        """
        Calculate delivery date from expiry date.

        Args:
            ccy_pair: Currency pair.
            expiry_date: Option expiry date.

        Returns:
            Settlement/delivery date.
        """
        calendar = cls.get_combined_calendar(ccy_pair)
        spot_days = cls.get_spot_days(ccy_pair)
        ql_expiry_date = date_to_ql(expiry_date)

        ql_delivery_date = calendar.advance(
            ql_expiry_date,
            spot_days,
            ql.Days,
            ql.Following
        )

        return ql_to_date(ql_delivery_date)

    @classmethod
    def get_expiry_and_delivery(
        cls,
        ccy_pair: str,
        trade_date: date,
        tenor: str
    ) -> Tuple[date, date]:
        """
        Calculate both expiry and delivery dates from tenor.

        Args:
            ccy_pair: Currency pair.
            trade_date: Trade date.
            tenor: Tenor string.

        Returns:
            Tuple of (expiry_date, delivery_date).
        """
        expiry = cls.get_expiry_from_tenor(ccy_pair, trade_date, tenor)
        delivery = cls.get_delivery_from_expiry(ccy_pair, expiry)
        return expiry, delivery

    @classmethod
    def is_business_day(cls, ccy_pair: str, check_date: date) -> bool:
        """
        Check if a date is a business day for both currencies.

        Args:
            ccy_pair: Currency pair.
            check_date: Date to check.

        Returns:
            True if business day, False otherwise.
        """
        calendar = cls.get_combined_calendar(ccy_pair)
        return calendar.isBusinessDay(date_to_ql(check_date))

    @classmethod
    def adjust_to_business_day(
        cls,
        ccy_pair: str,
        check_date: date,
        convention: str = "ModifiedFollowing"
    ) -> date:
        """
        Adjust a date to the nearest business day.

        Args:
            ccy_pair: Currency pair.
            check_date: Date to adjust.
            convention: Business day convention.

        Returns:
            Adjusted date.
        """
        calendar = cls.get_combined_calendar(ccy_pair)
        ql_date = date_to_ql(check_date)

        convention_map = {
            "Following": ql.Following,
            "ModifiedFollowing": ql.ModifiedFollowing,
            "Preceding": ql.Preceding,
            "ModifiedPreceding": ql.ModifiedPreceding,
            "Unadjusted": ql.Unadjusted,
        }

        ql_convention = convention_map.get(convention, ql.ModifiedFollowing)
        adjusted = calendar.adjust(ql_date, ql_convention)

        return ql_to_date(adjusted)
