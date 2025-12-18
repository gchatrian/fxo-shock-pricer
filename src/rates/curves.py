"""
Interest rate curves and implied deposit rate calculation.
"""

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from ..models.interpolation import linear_interpolate
from ..utils.date_utils import year_fraction, tenor_to_years


@dataclass
class RateCurve:
    """
    Interest rate curve with linear interpolation between pillars.
    """
    currency: str
    rates: Dict[str, float] = field(default_factory=dict)  # tenor -> rate
    reference_date: date = field(default_factory=date.today)

    # Cached time/rate points for interpolation
    _time_points: List[float] = field(default_factory=list, repr=False)
    _rate_points: List[float] = field(default_factory=list, repr=False)

    def add_rate(self, tenor: str, rate: float) -> None:
        """
        Add a rate point.

        Args:
            tenor: Tenor string (e.g., "1M", "3M")
            rate: Interest rate as decimal (e.g., 0.05 for 5%)
        """
        self.rates[tenor] = rate
        self._rebuild_interpolation_points()

    def set_rates(self, rates: Dict[str, float]) -> None:
        """
        Set all rates at once.

        Args:
            rates: Dictionary of tenor -> rate
        """
        self.rates = rates.copy()
        self._rebuild_interpolation_points()

    def _rebuild_interpolation_points(self) -> None:
        """Rebuild sorted time/rate points for interpolation."""
        points = []
        for tenor, rate in self.rates.items():
            t = tenor_to_years(tenor)
            points.append((t, rate))

        # Sort by time
        points.sort(key=lambda x: x[0])

        self._time_points = [p[0] for p in points]
        self._rate_points = [p[1] for p in points]

    def get_rate(self, time_to_maturity: float) -> float:
        """
        Get interpolated rate for a given time to maturity.

        Args:
            time_to_maturity: Time in years

        Returns:
            Interpolated interest rate
        """
        if len(self._time_points) == 0:
            raise ValueError("No rates in curve")

        return linear_interpolate(
            time_to_maturity,
            self._time_points,
            self._rate_points,
            extrapolate=True
        )

    def get_rate_for_date(self, target_date: date) -> float:
        """
        Get interpolated rate for a target date.

        Args:
            target_date: Target maturity date

        Returns:
            Interpolated interest rate
        """
        t = year_fraction(self.reference_date, target_date)
        return self.get_rate(t)

    def get_rate_for_tenor(self, tenor: str) -> float:
        """
        Get rate for a specific tenor (exact if available, interpolated otherwise).

        Args:
            tenor: Tenor string

        Returns:
            Interest rate
        """
        # Check if we have exact tenor
        if tenor in self.rates:
            return self.rates[tenor]

        # Otherwise interpolate
        t = tenor_to_years(tenor)
        return self.get_rate(t)

    def get_discount_factor(self, time_to_maturity: float) -> float:
        """
        Calculate discount factor.

        Args:
            time_to_maturity: Time in years

        Returns:
            Discount factor
        """
        rate = self.get_rate(time_to_maturity)
        return math.exp(-rate * time_to_maturity)


class ImpliedDepoCalculator:
    """
    Calculate implied foreign deposit rate from USD rate and forward points.

    Uses covered interest rate parity:
    F = S * exp((r_dom - r_for) * t)

    Where:
    - F = Forward rate
    - S = Spot rate
    - r_dom = Domestic (USD) rate
    - r_for = Foreign rate
    - t = Time to maturity

    Forward Points = F - S (or (F - S) * scale for some pairs)

    Solving for r_for:
    r_for = r_dom - ln(F / S) / t
    r_for = r_dom - ln((S + FwdPts/scale) / S) / t
    """

    # Scale factors for forward points by currency pair
    # Most pairs quote forward points in pips (10000 multiplier)
    # JPY pairs quote in 100s
    FORWARD_POINT_SCALES = {
        "USDJPY": 100,
        "EURJPY": 100,
        "GBPJPY": 100,
        "AUDJPY": 100,
        "CADJPY": 100,
        "CHFJPY": 100,
        "DEFAULT": 10000
    }

    @classmethod
    def get_forward_point_scale(cls, ccy_pair: str) -> float:
        """Get the forward point scale for a currency pair."""
        ccy_pair = ccy_pair.upper().replace("/", "")
        return cls.FORWARD_POINT_SCALES.get(ccy_pair, cls.FORWARD_POINT_SCALES["DEFAULT"])

    @classmethod
    def calculate_forward_rate(
        cls,
        spot: float,
        forward_points: float,
        ccy_pair: str
    ) -> float:
        """
        Calculate outright forward rate from spot and forward points.

        Args:
            spot: Spot rate
            forward_points: Forward points
            ccy_pair: Currency pair (for scale determination)

        Returns:
            Forward rate
        """
        scale = cls.get_forward_point_scale(ccy_pair)
        return spot + forward_points / scale

    @classmethod
    def calculate_implied_rate(
        cls,
        usd_rate: float,
        spot: float,
        forward_points: float,
        time_to_maturity: float,
        ccy_pair: str,
        usd_is_domestic: bool = True
    ) -> float:
        """
        Calculate implied foreign deposit rate.

        Args:
            usd_rate: USD interest rate (as decimal)
            spot: Spot rate
            forward_points: Forward points
            time_to_maturity: Time in years
            ccy_pair: Currency pair
            usd_is_domestic: True if USD is domestic currency (quote currency)

        Returns:
            Implied foreign deposit rate
        """
        if time_to_maturity <= 0:
            return usd_rate  # At spot, no carry

        forward = cls.calculate_forward_rate(spot, forward_points, ccy_pair)

        # Covered interest rate parity
        # F = S * exp((r_dom - r_for) * t)
        # ln(F/S) = (r_dom - r_for) * t
        # r_for = r_dom - ln(F/S) / t

        if forward <= 0 or spot <= 0:
            return usd_rate

        if usd_is_domestic:
            # USD is domestic (e.g., EURUSD where USD is quote currency)
            # r_for = r_USD - ln(F/S) / t
            implied_rate = usd_rate - math.log(forward / spot) / time_to_maturity
        else:
            # USD is foreign (e.g., USDJPY where USD is base currency)
            # r_dom = r_USD + ln(F/S) / t
            # Actually for USDJPY, JPY is domestic, USD is foreign
            # r_USD = r_JPY - ln(F/S) / t
            # r_JPY = r_USD + ln(F/S) / t
            implied_rate = usd_rate + math.log(forward / spot) / time_to_maturity

        return implied_rate

    @classmethod
    def determine_usd_position(cls, ccy_pair: str) -> str:
        """
        Determine if USD is base or quote currency.

        Args:
            ccy_pair: Currency pair

        Returns:
            "BASE" if USD is base currency, "QUOTE" if USD is quote currency,
            "NONE" if USD is not in the pair
        """
        ccy_pair = ccy_pair.upper().replace("/", "")
        base = ccy_pair[:3]
        quote = ccy_pair[3:]

        if base == "USD":
            return "BASE"
        elif quote == "USD":
            return "QUOTE"
        else:
            return "NONE"


@dataclass
class FXRates:
    """
    Container for FX-specific rates: domestic, foreign, and forward.
    """
    domestic_rate: float
    foreign_rate: float
    forward_rate: float
    spot: float
    time_to_expiry: float
    domestic_currency: str
    foreign_currency: str

    @property
    def forward_points(self) -> float:
        """Calculate forward points from forward and spot."""
        return self.forward_rate - self.spot

    @classmethod
    def calculate(
        cls,
        ccy_pair: str,
        spot: float,
        forward_points: float,
        usd_rate: float,
        time_to_expiry: float
    ) -> 'FXRates':
        """
        Calculate all FX rates for a currency pair with USD.

        Args:
            ccy_pair: Currency pair (e.g., "EURUSD")
            spot: Spot rate
            forward_points: Forward points
            usd_rate: USD interest rate
            time_to_expiry: Time in years

        Returns:
            FXRates instance
        """
        ccy_pair = ccy_pair.upper().replace("/", "")
        base_ccy = ccy_pair[:3]
        quote_ccy = ccy_pair[3:]

        usd_position = ImpliedDepoCalculator.determine_usd_position(ccy_pair)

        forward = ImpliedDepoCalculator.calculate_forward_rate(
            spot, forward_points, ccy_pair
        )

        if usd_position == "QUOTE":
            # e.g., EURUSD: USD is domestic (quote), EUR is foreign (base)
            domestic_rate = usd_rate
            foreign_rate = ImpliedDepoCalculator.calculate_implied_rate(
                usd_rate, spot, forward_points, time_to_expiry,
                ccy_pair, usd_is_domestic=True
            )
            domestic_currency = quote_ccy
            foreign_currency = base_ccy

        elif usd_position == "BASE":
            # e.g., USDJPY: USD is foreign (base), JPY is domestic (quote)
            foreign_rate = usd_rate
            domestic_rate = ImpliedDepoCalculator.calculate_implied_rate(
                usd_rate, spot, forward_points, time_to_expiry,
                ccy_pair, usd_is_domestic=False
            )
            domestic_currency = quote_ccy
            foreign_currency = base_ccy

        else:
            # Cross pair without USD - would need different approach
            # For now, assume both rates are 0 (should be rare for this app)
            domestic_rate = 0.0
            foreign_rate = 0.0
            domestic_currency = quote_ccy
            foreign_currency = base_ccy

        return cls(
            domestic_rate=domestic_rate,
            foreign_rate=foreign_rate,
            forward_rate=forward,
            spot=spot,
            time_to_expiry=time_to_expiry,
            domestic_currency=domestic_currency,
            foreign_currency=foreign_currency
        )
