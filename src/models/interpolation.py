"""
Linear interpolation utilities for rates and volatilities.
"""

from typing import List, Tuple, Optional
import bisect


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

    Raises:
        ValueError: If x_points and y_points have different lengths or are empty
    """
    if len(x_points) != len(y_points):
        raise ValueError("x_points and y_points must have the same length")

    if len(x_points) == 0:
        raise ValueError("Cannot interpolate with empty points")

    if len(x_points) == 1:
        return y_points[0]

    # Find position using binary search
    idx = bisect.bisect_left(x_points, x)

    # Handle boundaries
    if idx == 0:
        if extrapolate:
            # Extrapolate using first two points
            return _linear_segment(x, x_points[0], y_points[0], x_points[1], y_points[1])
        else:
            return y_points[0]

    if idx >= len(x_points):
        if extrapolate:
            # Extrapolate using last two points
            return _linear_segment(
                x,
                x_points[-2], y_points[-2],
                x_points[-1], y_points[-1]
            )
        else:
            return y_points[-1]

    # Interpolate between idx-1 and idx
    return _linear_segment(
        x,
        x_points[idx - 1], y_points[idx - 1],
        x_points[idx], y_points[idx]
    )


def _linear_segment(x: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """
    Calculate y value on a line segment.

    Args:
        x: Target x value
        x1, y1: First point
        x2, y2: Second point

    Returns:
        y value at x
    """
    if x2 == x1:
        return y1

    slope = (y2 - y1) / (x2 - x1)
    return y1 + slope * (x - x1)


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
    """
    Find indices of points that bracket the target value.

    Args:
        x: Target value
        x_points: Sorted list of points

    Returns:
        Tuple of (lower_index, upper_index)
    """
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
        z_matrix: 2D matrix of z values, z_matrix[i][j] corresponds to (x_points[i], y_points[j])
        extrapolate: If True, extrapolate beyond the grid

    Returns:
        Interpolated z value
    """
    if len(x_points) == 0 or len(y_points) == 0:
        raise ValueError("Cannot interpolate with empty points")

    # First interpolate along x dimension for each y slice
    z_at_x = []
    for j in range(len(y_points)):
        z_slice = [z_matrix[i][j] for i in range(len(x_points))]
        z_at_x.append(linear_interpolate(x, x_points, z_slice, extrapolate))

    # Then interpolate along y dimension
    return linear_interpolate(y, y_points, z_at_x, extrapolate)
