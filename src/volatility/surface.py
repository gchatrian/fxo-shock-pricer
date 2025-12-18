"""
Volatility surface with smile interpolation on strike.
Uses cubic spline for time dimension and linear/ND interpolation for strike.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.interpolate import CubicSpline, LinearNDInterpolator
from scipy.stats import norm

from ..bloomberg.data_fetcher import VolSmileData
from ..models.garman_kohlhagen import GarmanKohlhagen
from ..models.interpolation import linear_interpolate, variance_interpolate
from ..utils.date_utils import year_fraction


@dataclass
class VolSmile:
    """
    Volatility smile for a single tenor with strikes calculated.

    The smile is defined by 5 points: 10D Put, 25D Put, ATM, 25D Call, 10D Call.
    Strikes are calculated from delta using the G-K delta formula.
    """
    tenor: str
    expiry_date: date
    time_to_expiry: float  # In years
    days_to_expiry: int = 0

    # Volatilities (as decimals)
    vol_10p: float = 0.0
    vol_25p: float = 0.0
    vol_atm: float = 0.0
    vol_25c: float = 0.0
    vol_10c: float = 0.0

    # Calculated strikes
    strike_10p: float = 0.0
    strike_25p: float = 0.0
    strike_atm: float = 0.0
    strike_25c: float = 0.0
    strike_10c: float = 0.0

    def calculate_strikes(
        self,
        spot: float,
        r_dom: float,
        r_for: float
    ) -> None:
        """
        Calculate strikes from delta points using G-K model.

        Args:
            spot: Spot rate
            r_dom: Domestic interest rate
            r_for: Foreign interest rate
        """
        t = self.time_to_expiry

        # ATM strike (ATM DNS - Delta Neutral Straddle)
        forward = spot * (1 + (r_dom - r_for) * t)
        self.strike_atm = forward * (1 + 0.5 * self.vol_atm ** 2 * t)

        # Calculate strikes from delta
        self.strike_25c = GarmanKohlhagen.calculate_strike_from_delta(
            spot, 0.25, r_dom, r_for, self.vol_25c, t, is_call=True
        )
        self.strike_25p = GarmanKohlhagen.calculate_strike_from_delta(
            spot, -0.25, r_dom, r_for, self.vol_25p, t, is_call=False
        )
        self.strike_10c = GarmanKohlhagen.calculate_strike_from_delta(
            spot, 0.10, r_dom, r_for, self.vol_10c, t, is_call=True
        )
        self.strike_10p = GarmanKohlhagen.calculate_strike_from_delta(
            spot, -0.10, r_dom, r_for, self.vol_10p, t, is_call=False
        )

    def get_strikes_list(self) -> List[float]:
        """Get list of strikes in order: 10P, 25P, ATM, 25C, 10C."""
        return [
            self.strike_10p,
            self.strike_25p,
            self.strike_atm,
            self.strike_25c,
            self.strike_10c
        ]

    def get_vols_list(self) -> List[float]:
        """Get list of volatilities in order: 10P, 25P, ATM, 25C, 10C."""
        return [
            self.vol_10p,
            self.vol_25p,
            self.vol_atm,
            self.vol_25c,
            self.vol_10c
        ]

    def get_vol_for_strike(self, strike: float) -> float:
        """
        Get volatility for a given strike using linear interpolation.

        Args:
            strike: Target strike

        Returns:
            Interpolated volatility
        """
        strikes = self.get_strikes_list()
        vols = self.get_vols_list()

        # Sort by strike
        sorted_pairs = sorted(zip(strikes, vols), key=lambda x: x[0])
        sorted_strikes = [p[0] for p in sorted_pairs]
        sorted_vols = [p[1] for p in sorted_pairs]

        return linear_interpolate(strike, sorted_strikes, sorted_vols, extrapolate=True)

    @classmethod
    def from_vol_smile_data(
        cls,
        data: VolSmileData,
        expiry_date: date,
        reference_date: date,
        days_to_expiry: Optional[int] = None
    ) -> 'VolSmile':
        """Create VolSmile from Bloomberg VolSmileData."""
        t = year_fraction(reference_date, expiry_date)
        days = days_to_expiry if days_to_expiry else (expiry_date - reference_date).days

        return cls(
            tenor=data.tenor,
            expiry_date=expiry_date,
            time_to_expiry=t,
            days_to_expiry=days,
            vol_10p=data.vol_10p,
            vol_25p=data.vol_25p,
            vol_atm=data.atm,
            vol_25c=data.vol_25c,
            vol_10c=data.vol_10c,
        )


class VolSurface:
    """
    Full volatility surface with interpolation on both strike and time dimensions.

    Uses:
    - LinearNDInterpolator for 2D interpolation (maturity x strike)
    - Cubic spline for time dimension when interpolating ATM
    - Variance interpolation for term structure consistency
    """

    def __init__(self):
        self._smiles: Dict[str, VolSmile] = {}
        self._tenor_times: List[Tuple[str, float]] = []  # Sorted by time
        self._tenor_days: List[Tuple[str, int]] = []     # Sorted by days

        # Cached data for fast interpolation
        self._maturities_in_days: List[int] = []
        self._strikes_mapping: Dict[int, List[float]] = {}
        self._volatilities: Dict[int, List[float]] = {}
        self._nd_interpolator: Optional[LinearNDInterpolator] = None
        self._atm_spline: Optional[CubicSpline] = None

    def add_smile(self, smile: VolSmile) -> None:
        """Add a smile to the surface."""
        self._smiles[smile.tenor] = smile
        self._rebuild_tenor_times()
        self._invalidate_cache()

    def _rebuild_tenor_times(self) -> None:
        """Rebuild sorted tenor/time lists."""
        self._tenor_times = [
            (tenor, smile.time_to_expiry)
            for tenor, smile in self._smiles.items()
        ]
        self._tenor_times.sort(key=lambda x: x[1])

        self._tenor_days = [
            (tenor, smile.days_to_expiry)
            for tenor, smile in self._smiles.items()
        ]
        self._tenor_days.sort(key=lambda x: x[1])

    def _invalidate_cache(self) -> None:
        """Invalidate interpolation cache."""
        self._nd_interpolator = None
        self._atm_spline = None
        self._maturities_in_days = []
        self._strikes_mapping = {}
        self._volatilities = {}

    def _build_cache(self) -> None:
        """Build interpolation cache."""
        if not self._smiles:
            return

        self._maturities_in_days = [
            self._smiles[tenor].days_to_expiry
            for tenor, _ in self._tenor_days
        ]

        for tenor, days in self._tenor_days:
            smile = self._smiles[tenor]
            self._strikes_mapping[days] = smile.get_strikes_list()
            self._volatilities[days] = smile.get_vols_list()

        # Build 2D interpolator
        points = []
        values = []
        for mat in self._maturities_in_days:
            for i, s in enumerate(self._strikes_mapping[mat]):
                points.append([mat, s])
                values.append(self._volatilities[mat][i])

        if len(points) >= 3:
            self._nd_interpolator = LinearNDInterpolator(
                np.array(points),
                np.array(values)
            )

        # Build ATM spline
        if len(self._maturities_in_days) >= 2:
            atm_vols = [self._smiles[t].vol_atm for t, _ in self._tenor_days]
            self._atm_spline = CubicSpline(
                self._maturities_in_days,
                atm_vols,
                bc_type='natural'
            )

    def calculate_all_strikes(
        self,
        spot: float,
        r_dom: float,
        r_for: float
    ) -> None:
        """Calculate strikes for all smiles."""
        for smile in self._smiles.values():
            smile.calculate_strikes(spot, r_dom, r_for)
        self._invalidate_cache()

    def get_vol(
        self,
        strike: float,
        time_to_expiry: float,
        spot: Optional[float] = None,
        r_dom: Optional[float] = None,
        r_for: Optional[float] = None
    ) -> float:
        """
        Get interpolated volatility for any strike and expiry.

        Args:
            strike: Target strike
            time_to_expiry: Time to expiry in years
            spot: Spot rate (needed if strikes not yet calculated)
            r_dom: Domestic rate
            r_for: Foreign rate

        Returns:
            Interpolated volatility (as decimal, e.g., 0.10 for 10%)
        """
        DEFAULT_VOL = 0.10

        if len(self._smiles) == 0:
            return DEFAULT_VOL

        # Calculate strikes if needed
        if spot is not None:
            first_smile = list(self._smiles.values())[0]
            if first_smile.strike_atm == 0:
                self.calculate_all_strikes(spot, r_dom or 0, r_for or 0)

        # Build cache if needed
        if not self._maturities_in_days:
            self._build_cache()

        # Convert time to days
        days = int(time_to_expiry * 365)

        # If only one tenor, just interpolate on strike
        if len(self._smiles) == 1:
            smile = list(self._smiles.values())[0]
            vol = smile.get_vol_for_strike(strike)
            # Sanity check
            if 0.001 < vol < 2.0:
                return vol
            return DEFAULT_VOL

        # Try 2D interpolation
        if self._nd_interpolator is not None:
            try:
                vol = self._nd_interpolator(days, strike)
                if not np.isnan(vol) and 0.001 < float(vol) < 2.0:
                    return round(float(vol), 4)
            except Exception:
                pass

        # Fallback: variance interpolation
        try:
            vol = self._interpolate_with_variance(strike, time_to_expiry)
            if 0.001 < vol < 2.0:
                return vol
        except Exception:
            pass

        return DEFAULT_VOL

    def _interpolate_with_variance(self, strike: float, time_to_expiry: float) -> float:
        """Interpolate using variance method for term structure."""
        if len(self._smiles) == 0:
            return 0.10

        # Get bracketing tenors
        lower_idx = 0
        upper_idx = len(self._tenor_times) - 1

        for i, (_, t) in enumerate(self._tenor_times):
            if t >= time_to_expiry:
                upper_idx = i
                lower_idx = max(0, i - 1)
                break

        lower_tenor = self._tenor_times[lower_idx][0]
        upper_tenor = self._tenor_times[upper_idx][0]
        lower_t = self._tenor_times[lower_idx][1]
        upper_t = self._tenor_times[upper_idx][1]

        lower_smile = self._smiles[lower_tenor]
        upper_smile = self._smiles[upper_tenor]

        vol_lower = lower_smile.get_vol_for_strike(strike)
        vol_upper = upper_smile.get_vol_for_strike(strike)

        return variance_interpolate(
            time_to_expiry,
            [lower_t, upper_t],
            [vol_lower, vol_upper],
            extrapolate=True
        )

    def get_atm_vol(self, time_to_expiry: float) -> float:
        """
        Get ATM volatility for a given expiry using cubic spline.

        Args:
            time_to_expiry: Time to expiry in years

        Returns:
            Interpolated ATM volatility (as decimal)
        """
        DEFAULT_VOL = 0.10

        if len(self._smiles) == 0:
            return DEFAULT_VOL

        if not self._atm_spline:
            self._build_cache()

        if self._atm_spline is None:
            # Fallback to variance interpolation
            t_points = [t for _, t in self._tenor_times]
            vol_points = [self._smiles[tenor].vol_atm for tenor, _ in self._tenor_times]

            # Check if vol_points are valid
            if not vol_points or any(v <= 0 or v > 2.0 for v in vol_points):
                return DEFAULT_VOL

            try:
                vol = variance_interpolate(time_to_expiry, t_points, vol_points, extrapolate=True)
                if 0.001 < vol < 2.0:
                    return vol
            except Exception:
                pass
            return DEFAULT_VOL

        try:
            days = int(time_to_expiry * 365)
            days = max(self._maturities_in_days[0], min(days, self._maturities_in_days[-1]))
            vol = float(self._atm_spline(days))
            if 0.001 < vol < 2.0:
                return vol
        except Exception:
            pass

        return DEFAULT_VOL

    def get_smile_for_tenor(self, tenor: str) -> Optional[VolSmile]:
        """Get smile for a specific tenor."""
        return self._smiles.get(tenor)

    @property
    def tenors(self) -> List[str]:
        """Get list of available tenors."""
        return [tenor for tenor, _ in self._tenor_times]

    @property
    def maturities_in_days(self) -> List[int]:
        """Get list of maturities in days."""
        if not self._maturities_in_days:
            self._build_cache()
        return self._maturities_in_days

    @property
    def strikes_mapping(self) -> Dict[int, List[float]]:
        """Get strikes mapping (days -> strikes list)."""
        if not self._strikes_mapping:
            self._build_cache()
        return self._strikes_mapping

    @property
    def volatilities(self) -> Dict[int, List[float]]:
        """Get volatilities mapping (days -> vols list)."""
        if not self._volatilities:
            self._build_cache()
        return self._volatilities

    @classmethod
    def from_market_data(
        cls,
        vol_smiles: Dict[str, VolSmileData],
        expiry_dates: Dict[str, date],
        reference_date: date,
        days_to_maturity: Optional[Dict[str, int]] = None
    ) -> 'VolSurface':
        """Create VolSurface from Bloomberg market data."""
        surface = cls()

        for tenor, data in vol_smiles.items():
            if tenor in expiry_dates:
                days = days_to_maturity.get(tenor) if days_to_maturity else None
                smile = VolSmile.from_vol_smile_data(
                    data, expiry_dates[tenor], reference_date, days
                )
                surface.add_smile(smile)

        return surface
