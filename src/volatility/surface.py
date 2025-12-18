"""
Volatility surface with smile interpolation on strike.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

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

    # Volatilities (as decimals)
    vol_10p: float
    vol_25p: float
    vol_atm: float
    vol_25c: float
    vol_10c: float

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
        # For DNS: strike such that call delta = -put delta
        # Approximation: F * exp(0.5 * vol^2 * t)
        forward = spot * (1 + (r_dom - r_for) * t)  # Simple approximation
        self.strike_atm = forward * (1 + 0.5 * self.vol_atm ** 2 * t)

        # Calculate strikes from delta
        # Note: delta input is absolute value (e.g., 0.25 for 25D)
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

    def get_vol_for_strike(self, strike: float) -> float:
        """
        Get volatility for a given strike using linear interpolation.

        Args:
            strike: Target strike

        Returns:
            Interpolated volatility
        """
        # Build sorted strike/vol pairs
        strikes = [
            self.strike_10p,
            self.strike_25p,
            self.strike_atm,
            self.strike_25c,
            self.strike_10c
        ]
        vols = [
            self.vol_10p,
            self.vol_25p,
            self.vol_atm,
            self.vol_25c,
            self.vol_10c
        ]

        # Sort by strike (should already be sorted for normal smile)
        sorted_pairs = sorted(zip(strikes, vols), key=lambda x: x[0])
        sorted_strikes = [p[0] for p in sorted_pairs]
        sorted_vols = [p[1] for p in sorted_pairs]

        return linear_interpolate(strike, sorted_strikes, sorted_vols, extrapolate=True)

    @classmethod
    def from_vol_smile_data(
        cls,
        data: VolSmileData,
        expiry_date: date,
        reference_date: date
    ) -> 'VolSmile':
        """
        Create VolSmile from Bloomberg VolSmileData.

        Args:
            data: VolSmileData from Bloomberg
            expiry_date: Option expiry date
            reference_date: Today/pricing date

        Returns:
            VolSmile instance
        """
        t = year_fraction(reference_date, expiry_date)

        return cls(
            tenor=data.tenor,
            expiry_date=expiry_date,
            time_to_expiry=t,
            vol_10p=data.vol_10p,
            vol_25p=data.vol_25p,
            vol_atm=data.atm,
            vol_25c=data.vol_25c,
            vol_10c=data.vol_10c,
        )


class VolSurface:
    """
    Full volatility surface with interpolation on both strike and time dimensions.

    Interpolation approach:
    1. For a given expiry, find the two bracketing tenor pillars
    2. For each pillar, interpolate the smile on strike (linear on strike)
    3. Interpolate between the two pillar vols using variance interpolation
    """

    def __init__(self):
        self._smiles: Dict[str, VolSmile] = {}
        self._tenor_times: List[Tuple[str, float]] = []  # Sorted by time

    def add_smile(self, smile: VolSmile) -> None:
        """
        Add a smile to the surface.

        Args:
            smile: VolSmile instance
        """
        self._smiles[smile.tenor] = smile
        self._rebuild_tenor_times()

    def _rebuild_tenor_times(self) -> None:
        """Rebuild sorted tenor/time list."""
        self._tenor_times = [
            (tenor, smile.time_to_expiry)
            for tenor, smile in self._smiles.items()
        ]
        self._tenor_times.sort(key=lambda x: x[1])

    def calculate_all_strikes(
        self,
        spot: float,
        r_dom: float,
        r_for: float
    ) -> None:
        """
        Calculate strikes for all smiles.

        Args:
            spot: Spot rate
            r_dom: Domestic interest rate
            r_for: Foreign interest rate
        """
        for smile in self._smiles.values():
            smile.calculate_strikes(spot, r_dom, r_for)

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
            Interpolated volatility
        """
        if len(self._smiles) == 0:
            raise ValueError("No smiles in surface")

        # If only one tenor, just interpolate on strike
        if len(self._smiles) == 1:
            smile = list(self._smiles.values())[0]
            if spot is not None and smile.strike_atm == 0:
                smile.calculate_strikes(spot, r_dom or 0, r_for or 0)
            return smile.get_vol_for_strike(strike)

        # Find bracketing tenors
        lower_tenor = None
        upper_tenor = None
        lower_t = 0.0
        upper_t = 0.0

        for i, (tenor, t) in enumerate(self._tenor_times):
            if t >= time_to_expiry:
                upper_tenor = tenor
                upper_t = t
                if i > 0:
                    lower_tenor = self._tenor_times[i - 1][0]
                    lower_t = self._tenor_times[i - 1][1]
                else:
                    # Extrapolate from first two
                    lower_tenor = self._tenor_times[0][0]
                    lower_t = self._tenor_times[0][1]
                    if len(self._tenor_times) > 1:
                        upper_tenor = self._tenor_times[1][0]
                        upper_t = self._tenor_times[1][1]
                break

        if upper_tenor is None:
            # Extrapolate beyond last tenor
            if len(self._tenor_times) >= 2:
                lower_tenor = self._tenor_times[-2][0]
                lower_t = self._tenor_times[-2][1]
                upper_tenor = self._tenor_times[-1][0]
                upper_t = self._tenor_times[-1][1]
            else:
                return self._smiles[self._tenor_times[-1][0]].get_vol_for_strike(strike)

        # Get vols at both tenors for the target strike
        lower_smile = self._smiles[lower_tenor]
        upper_smile = self._smiles[upper_tenor]

        if spot is not None:
            if lower_smile.strike_atm == 0:
                lower_smile.calculate_strikes(spot, r_dom or 0, r_for or 0)
            if upper_smile.strike_atm == 0:
                upper_smile.calculate_strikes(spot, r_dom or 0, r_for or 0)

        vol_lower = lower_smile.get_vol_for_strike(strike)
        vol_upper = upper_smile.get_vol_for_strike(strike)

        # Interpolate using variance
        t_points = [lower_t, upper_t]
        vol_points = [vol_lower, vol_upper]

        return variance_interpolate(time_to_expiry, t_points, vol_points, extrapolate=True)

    def get_atm_vol(self, time_to_expiry: float) -> float:
        """
        Get ATM volatility for a given expiry.

        Args:
            time_to_expiry: Time to expiry in years

        Returns:
            Interpolated ATM volatility
        """
        if len(self._smiles) == 0:
            raise ValueError("No smiles in surface")

        t_points = [t for _, t in self._tenor_times]
        vol_points = [self._smiles[tenor].vol_atm for tenor, _ in self._tenor_times]

        return variance_interpolate(time_to_expiry, t_points, vol_points, extrapolate=True)

    def get_smile_for_tenor(self, tenor: str) -> Optional[VolSmile]:
        """Get smile for a specific tenor."""
        return self._smiles.get(tenor)

    @property
    def tenors(self) -> List[str]:
        """Get list of available tenors."""
        return [tenor for tenor, _ in self._tenor_times]

    @classmethod
    def from_market_data(
        cls,
        vol_smiles: Dict[str, VolSmileData],
        expiry_dates: Dict[str, date],
        reference_date: date
    ) -> 'VolSurface':
        """
        Create VolSurface from Bloomberg market data.

        Args:
            vol_smiles: Dictionary of tenor -> VolSmileData
            expiry_dates: Dictionary of tenor -> expiry date
            reference_date: Today/pricing date

        Returns:
            VolSurface instance
        """
        surface = cls()

        for tenor, data in vol_smiles.items():
            if tenor in expiry_dates:
                smile = VolSmile.from_vol_smile_data(
                    data, expiry_dates[tenor], reference_date
                )
                surface.add_smile(smile)

        return surface
