"""
Interpolation utilities for rates and volatilities.
Supports linear, variance, and 2D interpolation.
"""

from typing import List, Tuple, Optional
import bisect

import numpy as np
from scipy.interpolate import CubicSpline, LinearNDInterpolator


def linear_interpolate(
    x: float,
    x_points: List[float],
    y_points: List[float],
    extrapolate: bool = True
) -> float:
    """
    Perform linear interpolation (and optionally extrapolation).

    Args:
        x: Target x value
        x_points: List of known x values (must be sorted ascending)
        y_points: List of corresponding y values
        extrapolate: If True, extrapolate linearly beyond the range

    Returns:
        Interpolated (or extrapolated) y value
    """
    if len(x_points) != len(y_points):
        raise ValueError("x_points and y_points must have the same length")

    if len(x_points) == 0:
        raise ValueError("Cannot interpolate with empty points")

    if len(x_points) == 1:
        return y_points[0]

    idx = bisect.bisect_left(x_points, x)

    if idx == 0:
        if extrapolate:
            return _linear_segment(x, x_points[0], y_points[0], x_points[1], y_points[1])
        else:
            return y_points[0]

    if idx >= len(x_points):
        if extrapolate:
            return _linear_segment(
                x,
                x_points[-2], y_points[-2],
                x_points[-1], y_points[-1]
            )
        else:
            return y_points[-1]

    return _linear_segment(
        x,
        x_points[idx - 1], y_points[idx - 1],
        x_points[idx], y_points[idx]
    )


def _linear_segment(x: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Calculate y value on a line segment."""
    if x2 == x1:
        return y1
    slope = (y2 - y1) / (x2 - x1)
    return y1 + slope * (x - x1)


def cubic_spline_interpolate(
    x: float,
    x_points: List[float],
    y_points: List[float],
    extrapolate: bool = True
) -> float:
    """
    Perform cubic spline interpolation.

    Args:
        x: Target x value
        x_points: List of known x values (must be sorted ascending)
        y_points: List of corresponding y values
        extrapolate: If True, extrapolate beyond the range (flat)

    Returns:
        Interpolated y value
    """
    if len(x_points) != len(y_points):
        raise ValueError("x_points and y_points must have the same length")

    if len(x_points) == 0:
        raise ValueError("Cannot interpolate with empty points")

    if len(x_points) == 1:
        return y_points[0]

    if len(x_points) == 2:
        return linear_interpolate(x, x_points, y_points, extrapolate)

    spline = CubicSpline(x_points, y_points, bc_type='natural')

    if not extrapolate:
        if x < x_points[0]:
            return y_points[0]
        if x > x_points[-1]:
            return y_points[-1]

    return float(spline(x))


def variance_interpolate(
    t: float,
    t_points: List[float],
    vol_points: List[float],
    extrapolate: bool = True
) -> float:
    """
    Interpolate volatility using variance (vol^2 * t) interpolation.

    This is more appropriate for volatility term structure interpolation
    as it preserves no-arbitrage conditions.

    Args:
        t: Target time (in years)
        t_points: List of known times
        vol_points: List of corresponding volatilities
        extrapolate: If True, extrapolate beyond the range

    Returns:
        Interpolated volatility
    """
    if len(t_points) != len(vol_points):
        raise ValueError("t_points and vol_points must have the same length")

    if len(t_points) == 0:
        raise ValueError("Cannot interpolate with empty points")

    if len(t_points) == 1:
        return vol_points[0]

    if t <= 0:
        return vol_points[0]

    # Convert to variance
    variance_points = [vol ** 2 * time for vol, time in zip(vol_points, t_points)]

    # Interpolate variance
    variance = linear_interpolate(t, t_points, variance_points, extrapolate)

    # Convert back to volatility
    if variance <= 0:
        return vol_points[0]

    return (variance / t) ** 0.5


def find_bracketing_indices(
    x: float,
    x_points: List[float]
) -> Tuple[int, int]:
    """Find indices of points that bracket the target value."""
    if len(x_points) == 0:
        raise ValueError("Cannot find brackets in empty list")

    if len(x_points) == 1:
        return 0, 0

    idx = bisect.bisect_left(x_points, x)

    if idx == 0:
        return 0, 1
    if idx >= len(x_points):
        return len(x_points) - 2, len(x_points) - 1

    return idx - 1, idx


def interpolate_2d(
    x: float,
    y: float,
    x_points: List[float],
    y_points: List[float],
    z_matrix: List[List[float]],
    extrapolate: bool = True
) -> float:
    """
    Perform bilinear interpolation on a 2D surface.

    Args:
        x: Target x value
        y: Target y value
        x_points: List of x grid points
        y_points: List of y grid points
        z_matrix: 2D matrix of z values
        extrapolate: If True, extrapolate beyond the grid

    Returns:
        Interpolated z value
    """
    if len(x_points) == 0 or len(y_points) == 0:
        raise ValueError("Cannot interpolate with empty points")

    z_at_x = []
    for j in range(len(y_points)):
        z_slice = [z_matrix[i][j] for i in range(len(x_points))]
        z_at_x.append(linear_interpolate(x, x_points, z_slice, extrapolate))

    return linear_interpolate(y, y_points, z_at_x, extrapolate)


def interpolate_volatility_surface(
    maturity: float,
    strike: float,
    maturities_in_days: List[int],
    strikes_mapping: dict,
    volatilities: dict
) -> float:
    """
    Interpolate volatility from a surface using LinearNDInterpolator.

    Args:
        maturity: Target maturity in days
        strike: Target strike
        maturities_in_days: List of available maturities
        strikes_mapping: Dict mapping maturity -> list of strikes
        volatilities: Dict mapping maturity -> list of volatilities

    Returns:
        Interpolated volatility
    """
    points = []
    values = []

    for mat in maturities_in_days:
        for i, s in enumerate(strikes_mapping[mat]):
            points.append([mat, s])
            values.append(volatilities[mat][i])

    points = np.array(points)
    values = np.array(values)

    interpolator = LinearNDInterpolator(points, values)
    interpolated_value = interpolator(maturity, strike)

    if np.isnan(interpolated_value):
        interpolated_value = _extrapolate_volatility(
            maturity, strike, maturities_in_days, strikes_mapping, volatilities
        )

    return round(float(interpolated_value), 4)


def _extrapolate_volatility(
    maturity: float,
    strike: float,
    maturities_in_days: List[int],
    strikes_mapping: dict,
    volatilities: dict
) -> float:
    """Extrapolate volatility when outside the interpolation bounds."""
    maturities = sorted(maturities_in_days)

    if maturity < maturities[0]:
        nearest_maturity = maturities[0]
    elif maturity > maturities[-1]:
        nearest_maturity = maturities[-1]
    else:
        nearest_maturity = min(maturities, key=lambda x: abs(x - maturity))

    strikes = sorted(strikes_mapping[nearest_maturity])

    if strike < strikes[0]:
        nearest_strike = strikes[0]
    elif strike > strikes[-1]:
        nearest_strike = strikes[-1]
    else:
        nearest_strike = min(strikes, key=lambda x: abs(x - strike))

    strike_index = strikes_mapping[nearest_maturity].index(nearest_strike)
    return volatilities[nearest_maturity][strike_index]
