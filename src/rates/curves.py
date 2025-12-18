"""
Interest rate curves and implied deposit rate calculation.
Uses cubic spline interpolation for smooth curves.
"""

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from scipy.interpolate import CubicSpline
import numpy as np

from ..utils.date_utils import year_fraction, tenor_to_years


@dataclass
class RateCurve:
    """
    Interest rate curve with cubic spline interpolation between pillars.
    """
    currency: str
    rates: Dict[str, float] = field(default_factory=dict)  # tenor -> rate
    reference_date: date = field(default_factory=date.today)
    days_to_maturity: Dict[str, int] = field(default_factory=dict)  # tenor -> days

    # Cached spline interpolator
    _spline: Optional[CubicSpline] = field(default=None, repr=False)
    _time_points: List[float] = field(default_factory=list, repr=False)
    _rate_points: List[float] = field(default_factory=list, repr=False)

    def add_rate(self, tenor: str, rate: float, days: Optional[int] = None) -> None:
        """
        Add a rate point.

        Args:
            tenor: Tenor string (e.g., "1M", "3M")
            rate: Interest rate as decimal (e.g., 0.05 for 5%)
            days: Optional days to maturity
        """
        self.rates[tenor] = rate
        if days is not None:
            self.days_to_maturity[tenor] = days
        self._rebuild_spline()

    def set_rates(
        self,
        rates: Dict[str, float],
        days_to_maturity: Optional[Dict[str, int]] = None
    ) -> None:
        """
        Set all rates at once.

        Args:
            rates: Dictionary of tenor -> rate
            days_to_maturity: Optional dictionary of tenor -> days
        """
        self.rates = rates.copy()
        if days_to_maturity:
            self.days_to_maturity = days_to_maturity.copy()
        self._rebuild_spline()

    def _get_time_for_tenor(self, tenor: str) -> float:
        """Get time in years for a tenor, using days_to_maturity if available."""
        if tenor in self.days_to_maturity:
            return self.days_to_maturity[tenor] / 365.0
        return tenor_to_years(tenor)

    def _rebuild_spline(self) -> None:
        """Rebuild cubic spline interpolator."""
        if len(self.rates) < 2:
            self._spline = None
            return

        points = []
        for tenor, rate in self.rates.items():
            t = self._get_time_for_tenor(tenor)
            points.append((t, rate))

        # Sort by time
        points.sort(key=lambda x: x[0])

        self._time_points = [p[0] for p in points]
        self._rate_points = [p[1] for p in points]

        # Build cubic spline
        if len(self._time_points) >= 2:
            self._spline = CubicSpline(
                self._time_points,
                self._rate_points,
                bc_type='natural'  # Natural boundary conditions
            )

    def get_rate(self, time_to_maturity: float) -> float:
        """
        Get interpolated rate for a given time to maturity using cubic spline.

        Args:
            time_to_maturity: Time in years

        Returns:
            Interpolated interest rate
        """
        if len(self.rates) == 0:
            raise ValueError("No rates in curve")

        if len(self.rates) == 1:
            return list(self.rates.values())[0]

        if self._spline is None:
            self._rebuild_spline()

        if self._spline is None:
            # Fallback to simple interpolation
            return self._rate_points[0] if self._rate_points else 0.0

        # Clamp to valid range for extrapolation
        t_min = self._time_points[0]
        t_max = self._time_points[-1]

        if time_to_maturity < t_min:
            # Linear extrapolation from first two points
            return float(self._spline(t_min))
        elif time_to_maturity > t_max:
            # Linear extrapolation from last two points
            return float(self._spline(t_max))

        return float(self._spline(time_to_maturity))

    def get_rate_for_days(self, days: int) -> float:
        """
        Get interpolated rate for a given number of days.

        Args:
            days: Days to maturity

        Returns:
            Interpolated interest rate
        """
        return self.get_rate(days / 365.0)

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
        if tenor in self.rates:
            return self.rates[tenor]

        t = self._get_time_for_tenor(tenor)
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


@dataclass
class ForwardCurve:
    """
    Forward rate curve with cubic spline interpolation.
    """
    ccy_pair: str
    spot: float
    forwards: Dict[str, float] = field(default_factory=dict)  # tenor -> forward rate
    days_to_maturity: Dict[str, int] = field(default_factory=dict)

    _spline: Optional[CubicSpline] = field(default=None, repr=False)
    _time_points: List[float] = field(default_factory=list, repr=False)
    _fwd_points: List[float] = field(default_factory=list, repr=False)

    def set_forwards(
        self,
        forwards: Dict[str, float],
        days_to_maturity: Optional[Dict[str, int]] = None
    ) -> None:
        """Set all forward rates."""
        self.forwards = forwards.copy()
        if days_to_maturity:
            self.days_to_maturity = days_to_maturity.copy()
        self._rebuild_spline()

    def _get_time_for_tenor(self, tenor: str) -> float:
        """Get time in years for a tenor."""
        if tenor in self.days_to_maturity:
            return self.days_to_maturity[tenor] / 365.0
        return tenor_to_years(tenor)

    def _rebuild_spline(self) -> None:
        """Rebuild cubic spline interpolator."""
        if len(self.forwards) < 2:
            self._spline = None
            return

        points = []
        for tenor, fwd in self.forwards.items():
            t = self._get_time_for_tenor(tenor)
            points.append((t, fwd))

        points.sort(key=lambda x: x[0])

        self._time_points = [p[0] for p in points]
        self._fwd_points = [p[1] for p in points]

        if len(self._time_points) >= 2:
            self._spline = CubicSpline(
                self._time_points,
                self._fwd_points,
                bc_type='natural'
            )

    def get_forward(self, time_to_maturity: float) -> float:
        """Get interpolated forward rate."""
        if len(self.forwards) == 0:
            return self.spot

        if len(self.forwards) == 1:
            return list(self.forwards.values())[0]

        if self._spline is None:
            self._rebuild_spline()

        if self._spline is None:
            return self.spot

        t_min = self._time_points[0]
        t_max = self._time_points[-1]

        if time_to_maturity <= 0:
            return self.spot
        elif time_to_maturity < t_min:
            return float(self._spline(t_min))
        elif time_to_maturity > t_max:
            return float(self._spline(t_max))

        return float(self._spline(time_to_maturity))

    def get_forward_for_days(self, days: int) -> float:
        """Get interpolated forward for given days."""
        return self.get_forward(days / 365.0)


@dataclass
class FXRates:
    """
    Container for FX-specific rates: domestic, foreign, and forward.
    Uses cubic spline interpolation for all curves.
    """
    ccy_pair: str
    spot: float
    domestic_currency: str
    foreign_currency: str

    # Curves with cubic spline interpolation
    domestic_curve: RateCurve = field(default_factory=lambda: RateCurve(currency=""))
    foreign_curve: RateCurve = field(default_factory=lambda: RateCurve(currency=""))
    forward_curve: ForwardCurve = field(default_factory=lambda: ForwardCurve(ccy_pair="", spot=0.0))

    def get_domestic_rate(self, time_to_expiry: float) -> float:
        """Get interpolated domestic rate."""
        return self.domestic_curve.get_rate(time_to_expiry)

    def get_foreign_rate(self, time_to_expiry: float) -> float:
        """Get interpolated foreign rate."""
        return self.foreign_curve.get_rate(time_to_expiry)

    def get_forward(self, time_to_expiry: float) -> float:
        """Get interpolated forward rate."""
        return self.forward_curve.get_forward(time_to_expiry)

    @classmethod
    def from_market_data(cls, market_data) -> 'FXRates':
        """
        Create FXRates from MarketData object.

        Args:
            market_data: MarketData instance from data_fetcher

        Returns:
            FXRates instance with cubic spline curves
        """
        # Create domestic rate curve
        domestic_curve = RateCurve(currency=market_data.d_ccy)
        domestic_curve.set_rates(
            market_data.domestic_rates,
            market_data.days_to_maturity
        )

        # Create foreign rate curve
        foreign_curve = RateCurve(currency=market_data.f_ccy)
        foreign_curve.set_rates(
            market_data.foreign_rates,
            market_data.days_to_maturity
        )

        # Create forward curve
        forward_curve = ForwardCurve(
            ccy_pair=market_data.ccy_pair,
            spot=market_data.spot
        )
        forward_curve.set_forwards(
            market_data.forward_rates,
            market_data.days_to_maturity
        )

        return cls(
            ccy_pair=market_data.ccy_pair,
            spot=market_data.spot,
            domestic_currency=market_data.d_ccy,
            foreign_currency=market_data.f_ccy,
            domestic_curve=domestic_curve,
            foreign_curve=foreign_curve,
            forward_curve=forward_curve
        )


class ImpliedDepoCalculator:
    """
    Calculate implied foreign deposit rate from USD rate and forward points.

    Uses covered interest rate parity:
    F = S * exp((r_dom - r_for) * t)
    """

    # Scale factors for forward points by currency pair
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
        """Calculate outright forward rate from spot and forward points."""
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
            usd_is_domestic: True if USD is domestic currency

        Returns:
            Implied foreign deposit rate
        """
        if time_to_maturity <= 0:
            return usd_rate

        forward = cls.calculate_forward_rate(spot, forward_points, ccy_pair)

        if forward <= 0 or spot <= 0:
            return usd_rate

        if usd_is_domestic:
            implied_rate = usd_rate - math.log(forward / spot) / time_to_maturity
        else:
            implied_rate = usd_rate + math.log(forward / spot) / time_to_maturity

        return implied_rate

    @classmethod
    def determine_usd_position(cls, ccy_pair: str) -> str:
        """
        Determine if USD is base or quote currency.

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
