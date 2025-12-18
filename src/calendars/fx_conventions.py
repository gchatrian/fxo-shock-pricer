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
    # To add a new currency, add an entry here with the appropriate QuantLib calendar
    # See QuantLib documentation for available calendars
    # If a calendar doesn't exist in your QuantLib version, TARGET will be used as fallback
    CALENDARS: Dict[str, ql.Calendar] = {}
    
    @classmethod
    def _init_calendars(cls) -> None:
        """Initialize calendars with fallback for unsupported ones."""
        if cls.CALENDARS:
            return  # Already initialized
            
        import logging
        logger = logging.getLogger(__name__)
        
        # Define desired calendars - will use TARGET as fallback if not available
        calendar_definitions = {
            # G10 currencies
            "EUR": lambda: ql.TARGET(),
            "USD": lambda: ql.UnitedStates(ql.UnitedStates.FederalReserve),
            "GBP": lambda: ql.UnitedKingdom(ql.UnitedKingdom.Exchange),
            "JPY": lambda: ql.Japan(),
            "AUD": lambda: ql.Australia(),
            "CAD": lambda: ql.Canada(),
            "CHF": lambda: ql.Switzerland(),
            "NZD": lambda: ql.NewZealand(),
            "SEK": lambda: ql.Sweden(),
            "NOK": lambda: ql.Norway(),
            
            # European
            "DKK": lambda: ql.Denmark(),
            "PLN": lambda: ql.Poland(),
            "CZK": lambda: ql.CzechRepublic(),
            "HUF": lambda: ql.Hungary(),
            "RON": lambda: ql.Romania(),
            
            # Asia Pacific
            "SGD": lambda: ql.Singapore(),
            "HKD": lambda: ql.HongKong(),
            "CNY": lambda: ql.China(),
            "CNH": lambda: ql.China(),
            "KRW": lambda: ql.SouthKorea(ql.SouthKorea.KRX),
            "TWD": lambda: ql.Taiwan(),
            "INR": lambda: ql.India(),
            "THB": lambda: ql.Thailand(),
            "IDR": lambda: ql.Indonesia(),
            
            # Americas
            "MXN": lambda: ql.Mexico(),
            "BRL": lambda: ql.Brazil(),
            "ARS": lambda: ql.Argentina(),
            
            # EMEA
            "ZAR": lambda: ql.SouthAfrica(),
            "TRY": lambda: ql.Turkey(),
            "ILS": lambda: ql.Israel(),
            "RUB": lambda: ql.Russia(),
            "SAR": lambda: ql.SaudiArabia(),
        }
        
        for ccy, cal_func in calendar_definitions.items():
            try:
                cls.CALENDARS[ccy] = cal_func()
            except Exception as e:
                logger.warning(f"Calendar for {ccy} not available in QuantLib: {e}. Using TARGET.")
                cls.CALENDARS[ccy] = ql.TARGET()

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
        
        If currency is not in the predefined list, uses TARGET as fallback.
        This allows trading any currency pair without explicitly adding calendars.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Initialize calendars on first access
        cls._init_calendars()
        
        currency = currency.upper()
        if currency not in cls.CALENDARS:
            logger.warning(f"Currency {currency} not in calendar list, using TARGET as fallback")
            return ql.TARGET()
        return cls.CALENDARS[currency]

    @classmethod
    def parse_currency_pair(cls, ccy_pair: str) -> Tuple[str, str]:
        """Parse currency pair into base and quote currencies."""
        ccy_pair = ccy_pair.upper().replace("/", "").replace(" ", "")
        if len(ccy_pair) != 6:
            raise ValueError(f"Invalid currency pair: {ccy_pair}. Expected 6 characters.")
        return ccy_pair[:3], ccy_pair[3:]

    @classmethod
    def get_combined_calendar(cls, ccy_pair: str) -> ql.Calendar:
        """Get combined calendar for a currency pair."""
        base_ccy, quote_ccy = cls.parse_currency_pair(ccy_pair)
        cal1 = cls.get_currency_calendar(base_ccy)
        cal2 = cls.get_currency_calendar(quote_ccy)
        return ql.JointCalendar(cal1, cal2)

    @classmethod
    def get_spot_days(cls, ccy_pair: str) -> int:
        """Get number of spot days for a currency pair."""
        ccy_pair_normalized = ccy_pair.upper().replace("/", "").replace(" ", "")
        if ccy_pair_normalized in cls.T_PLUS_ONE_PAIRS:
            return 1
        return 2

    @classmethod
    def get_spot_date(cls, ccy_pair: str, trade_date: date) -> date:
        """Calculate spot date for a currency pair."""
        calendar = cls.get_combined_calendar(ccy_pair)
        spot_days = cls.get_spot_days(ccy_pair)
        ql_trade_date = date_to_ql(trade_date)

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
        """Calculate option expiry date from a tenor string."""
        calendar = cls.get_combined_calendar(ccy_pair)
        spot_days = cls.get_spot_days(ccy_pair)
        ql_trade_date = date_to_ql(trade_date)
        period = parse_tenor(tenor)

        ql_spot_date = calendar.advance(ql_trade_date, spot_days, ql.Days, ql.Following)

        ql_delivery_date = calendar.advance(
            ql_spot_date,
            period,
            ql.ModifiedFollowing,
            True
        )

        ql_expiry_date = calendar.advance(
            ql_delivery_date,
            -spot_days,
            ql.Days,
            ql.Preceding
        )

        return ql_to_date(ql_expiry_date)

    @classmethod
    def get_delivery_from_expiry(cls, ccy_pair: str, expiry_date: date) -> date:
        """Calculate delivery date from expiry date."""
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
        """Calculate both expiry and delivery dates from tenor."""
        expiry = cls.get_expiry_from_tenor(ccy_pair, trade_date, tenor)
        delivery = cls.get_delivery_from_expiry(ccy_pair, expiry)
        return expiry, delivery

    @classmethod
    def is_business_day(cls, ccy_pair: str, check_date: date) -> bool:
        """Check if a date is a business day for both currencies."""
        calendar = cls.get_combined_calendar(ccy_pair)
        return calendar.isBusinessDay(date_to_ql(check_date))

    @classmethod
    def adjust_to_business_day(
        cls,
        ccy_pair: str,
        check_date: date,
        convention: str = "ModifiedFollowing"
    ) -> date:
        """Adjust a date to the nearest business day."""
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

    @classmethod
    def get_days_to_maturity(cls, ccy_pair: str, trade_date: date, tenors: list) -> Dict[str, int]:
        """
        Calculate days to maturity for each tenor.

        Args:
            ccy_pair: Currency pair
            trade_date: Trade date
            tenors: List of tenor strings

        Returns:
            Dictionary mapping tenor -> days to maturity
        """
        days_map = {}
        for tenor in tenors:
            expiry = cls.get_expiry_from_tenor(ccy_pair, trade_date, tenor)
            days = (expiry - trade_date).days
            days_map[tenor] = days
        return days_map
