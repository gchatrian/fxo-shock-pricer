"""
Garman-Kohlhagen model for FX option pricing.
Implements Black-Scholes adapted for currency options with two interest rates.
"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from scipy.stats import norm


class OptionType(Enum):
    """Option type enumeration."""
    CALL = "Call"
    PUT = "Put"


class Direction(Enum):
    """Trade direction from client perspective."""
    CLIENT_BUYS = "Client buys"
    CLIENT_SELLS = "Client sells"


@dataclass
class OptionParams:
    """Input parameters for FX option pricing."""
    spot: float                     # Current spot rate
    strike: float                   # Strike price
    domestic_rate: float            # Domestic (quote) currency rate (e.g., USD for EURUSD)
    foreign_rate: float             # Foreign (base) currency rate (e.g., EUR for EURUSD)
    volatility: float               # Implied volatility (as decimal, e.g., 0.10 for 10%)
    time_to_expiry: float           # Time to expiry in years
    is_call: bool                   # True for call, False for put
    notional: float = 1_000_000     # Notional amount
    notional_currency: str = "FOR"  # "FOR" (foreign/base) or "DOM" (domestic/quote)


@dataclass
class Greeks:
    """Container for option Greeks."""
    delta: float
    gamma: float
    vega: float
    theta: Optional[float] = None
    rho_domestic: Optional[float] = None
    rho_foreign: Optional[float] = None


@dataclass
class PricingResult:
    """Complete pricing result."""
    premium: float                  # Option premium in domestic currency
    premium_pct: float              # Premium as percentage of notional
    premium_pips: float             # Premium in pips
    forward: float                  # Forward rate
    greeks: Greeks                  # Option Greeks
    d1: float                       # d1 from Black-Scholes
    d2: float                       # d2 from Black-Scholes


class GarmanKohlhagen:
    """
    Garman-Kohlhagen model for pricing European FX options.

    The model adapts Black-Scholes for currencies by treating the foreign
    interest rate as a continuous dividend yield.

    Convention: For EURUSD, EUR is the foreign (base) currency and USD is
    the domestic (quote) currency. The spot rate is expressed as USD per EUR.
    """

    @staticmethod
    def _calculate_d1_d2(
        spot: float,
        strike: float,
        r_dom: float,
        r_for: float,
        vol: float,
        t: float
    ) -> tuple:
        """
        Calculate d1 and d2 parameters.

        Args:
            spot: Spot rate
            strike: Strike price
            r_dom: Domestic interest rate
            r_for: Foreign interest rate
            vol: Volatility
            t: Time to expiry in years

        Returns:
            Tuple of (d1, d2)
        """
        if t <= 0 or vol <= 0:
            return 0.0, 0.0

        sqrt_t = math.sqrt(t)
        d1 = (math.log(spot / strike) + (r_dom - r_for + 0.5 * vol ** 2) * t) / (vol * sqrt_t)
        d2 = d1 - vol * sqrt_t

        return d1, d2

    @staticmethod
    def forward(spot: float, r_dom: float, r_for: float, t: float) -> float:
        """
        Calculate forward rate using interest rate parity.
        F = S * exp((r_dom - r_for) * t)

        Args:
            spot: Spot rate
            r_dom: Domestic interest rate
            r_for: Foreign interest rate
            t: Time to expiry in years

        Returns:
            Forward rate
        """
        return spot * math.exp((r_dom - r_for) * t)

    @classmethod
    def price(cls, params: OptionParams) -> float:
        """
        Calculate option premium using Garman-Kohlhagen formula.

        Args:
            params: Option parameters

        Returns:
            Option premium per unit of foreign currency notional
        """
        S = params.spot
        K = params.strike
        r_d = params.domestic_rate
        r_f = params.foreign_rate
        vol = params.volatility
        t = params.time_to_expiry

        if t <= 0:
            # At expiry
            if params.is_call:
                return max(S - K, 0)
            else:
                return max(K - S, 0)

        d1, d2 = cls._calculate_d1_d2(S, K, r_d, r_f, vol, t)

        # Discount factors
        df_dom = math.exp(-r_d * t)
        df_for = math.exp(-r_f * t)

        if params.is_call:
            # Call: S * exp(-r_f * t) * N(d1) - K * exp(-r_d * t) * N(d2)
            premium = S * df_for * norm.cdf(d1) - K * df_dom * norm.cdf(d2)
        else:
            # Put: K * exp(-r_d * t) * N(-d2) - S * exp(-r_f * t) * N(-d1)
            premium = K * df_dom * norm.cdf(-d2) - S * df_for * norm.cdf(-d1)

        return premium

    @classmethod
    def delta(cls, params: OptionParams) -> float:
        """
        Calculate spot delta.

        Delta represents the change in option value for a 1 unit change in spot.
        For FX options, this is typically expressed per unit of foreign notional.

        Args:
            params: Option parameters

        Returns:
            Spot delta
        """
        t = params.time_to_expiry
        if t <= 0:
            if params.is_call:
                return 1.0 if params.spot > params.strike else 0.0
            else:
                return -1.0 if params.spot < params.strike else 0.0

        d1, _ = cls._calculate_d1_d2(
            params.spot, params.strike,
            params.domestic_rate, params.foreign_rate,
            params.volatility, t
        )

        df_for = math.exp(-params.foreign_rate * t)

        if params.is_call:
            return df_for * norm.cdf(d1)
        else:
            return df_for * (norm.cdf(d1) - 1)

    @classmethod
    def gamma(cls, params: OptionParams) -> float:
        """
        Calculate gamma (second derivative of price with respect to spot).

        Gamma is the same for calls and puts.

        Args:
            params: Option parameters

        Returns:
            Gamma
        """
        t = params.time_to_expiry
        if t <= 0:
            return 0.0

        d1, _ = cls._calculate_d1_d2(
            params.spot, params.strike,
            params.domestic_rate, params.foreign_rate,
            params.volatility, t
        )

        df_for = math.exp(-params.foreign_rate * t)
        sqrt_t = math.sqrt(t)

        return df_for * norm.pdf(d1) / (params.spot * params.volatility * sqrt_t)

    @classmethod
    def vega(cls, params: OptionParams) -> float:
        """
        Calculate vega (sensitivity to volatility).

        Returns vega per 1% (0.01) move in volatility.
        Vega is the same for calls and puts.

        Args:
            params: Option parameters

        Returns:
            Vega per 1% vol move
        """
        t = params.time_to_expiry
        if t <= 0:
            return 0.0

        d1, _ = cls._calculate_d1_d2(
            params.spot, params.strike,
            params.domestic_rate, params.foreign_rate,
            params.volatility, t
        )

        df_for = math.exp(-params.foreign_rate * t)
        sqrt_t = math.sqrt(t)

        # Vega for 1% move
        return params.spot * df_for * norm.pdf(d1) * sqrt_t * 0.01

    @classmethod
    def theta(cls, params: OptionParams) -> float:
        """
        Calculate theta (time decay).

        Returns daily theta (per calendar day).

        Args:
            params: Option parameters

        Returns:
            Theta per day
        """
        t = params.time_to_expiry
        if t <= 0:
            return 0.0

        S = params.spot
        K = params.strike
        r_d = params.domestic_rate
        r_f = params.foreign_rate
        vol = params.volatility

        d1, d2 = cls._calculate_d1_d2(S, K, r_d, r_f, vol, t)

        df_dom = math.exp(-r_d * t)
        df_for = math.exp(-r_f * t)
        sqrt_t = math.sqrt(t)

        # First term: time decay of gamma
        term1 = -(S * df_for * norm.pdf(d1) * vol) / (2 * sqrt_t)

        if params.is_call:
            term2 = r_f * S * df_for * norm.cdf(d1)
            term3 = -r_d * K * df_dom * norm.cdf(d2)
        else:
            term2 = -r_f * S * df_for * norm.cdf(-d1)
            term3 = r_d * K * df_dom * norm.cdf(-d2)

        # Annual theta, convert to daily
        annual_theta = term1 + term2 + term3
        return annual_theta / 365.0

    @classmethod
    def calculate_all(cls, params: OptionParams) -> PricingResult:
        """
        Calculate all pricing outputs at once.

        Args:
            params: Option parameters

        Returns:
            PricingResult with premium, forward, and all Greeks
        """
        t = params.time_to_expiry
        d1, d2 = cls._calculate_d1_d2(
            params.spot, params.strike,
            params.domestic_rate, params.foreign_rate,
            params.volatility, t
        )

        premium = cls.price(params)
        fwd = cls.forward(params.spot, params.domestic_rate, params.foreign_rate, t)

        greeks = Greeks(
            delta=cls.delta(params),
            gamma=cls.gamma(params),
            vega=cls.vega(params),
            theta=cls.theta(params)
        )

        # Premium as percentage of notional
        # If notional is in foreign currency, premium % = premium / spot * 100
        # If notional is in domestic currency, premium % = premium * spot / notional * 100
        if params.notional_currency == "FOR":
            premium_pct = premium / params.spot * 100
        else:
            premium_pct = premium * 100

        # Premium in pips (1 pip = 0.0001 for most pairs, 0.01 for JPY pairs)
        # This is simplified; actual pip value depends on the pair
        premium_pips = premium * 10000

        return PricingResult(
            premium=premium * params.notional if params.notional_currency == "FOR" else premium * params.notional / params.spot,
            premium_pct=premium_pct,
            premium_pips=premium_pips,
            forward=fwd,
            greeks=greeks,
            d1=d1,
            d2=d2
        )

    @classmethod
    def calculate_strike_from_delta(
        cls,
        spot: float,
        delta: float,
        r_dom: float,
        r_for: float,
        vol: float,
        t: float,
        is_call: bool
    ) -> float:
        """
        Calculate strike from delta using inverse G-K formula.

        This is used to convert delta quotes (10D, 25D, etc.) to strikes
        for volatility smile interpolation.

        Args:
            spot: Spot rate
            delta: Target delta (positive for calls, negative for puts)
            r_dom: Domestic rate
            r_for: Foreign rate
            vol: Volatility
            t: Time to expiry
            is_call: True for call, False for put

        Returns:
            Strike corresponding to the given delta
        """
        if t <= 0:
            return spot

        sqrt_t = math.sqrt(t)
        df_for = math.exp(-r_for * t)

        # For calls: delta = e^(-r_f*t) * N(d1)
        # For puts: delta = e^(-r_f*t) * (N(d1) - 1)

        if is_call:
            # d1 = N_inv(delta / df_for)
            d1 = norm.ppf(delta / df_for)
        else:
            # d1 = N_inv((delta / df_for) + 1)
            d1 = norm.ppf((delta / df_for) + 1)

        # From d1, calculate strike:
        # d1 = [ln(S/K) + (r_d - r_f + 0.5*vol^2)*t] / (vol*sqrt(t))
        # ln(S/K) = d1 * vol * sqrt(t) - (r_d - r_f + 0.5*vol^2)*t
        # K = S * exp(-(d1 * vol * sqrt(t) - (r_d - r_f + 0.5*vol^2)*t))

        ln_s_over_k = d1 * vol * sqrt_t - (r_dom - r_for + 0.5 * vol ** 2) * t
        strike = spot * math.exp(-ln_s_over_k)

        return strike

    @classmethod
    def calculate_delta_hedge(
        cls,
        params: OptionParams,
        direction: Direction = Direction.CLIENT_BUYS
    ) -> float:
        """
        Calculate delta hedge notional.

        For a client buying an option, the dealer is short delta and needs
        to buy the underlying to hedge.

        Args:
            params: Option parameters
            direction: Trade direction from client perspective

        Returns:
            Hedge notional in the currency pair (e.g., EURUSD amount for EURUSD option)
        """
        delta = cls.delta(params)

        # Hedge notional = delta * notional
        # The sign depends on direction: if client buys, dealer sells (negative from dealer perspective)
        if direction == Direction.CLIENT_BUYS:
            hedge_sign = 1.0  # Dealer needs to buy underlying to hedge short option
        else:
            hedge_sign = -1.0  # Dealer needs to sell underlying

        if params.notional_currency == "FOR":
            # Notional is in foreign currency (e.g., EUR for EURUSD)
            hedge_notional = delta * params.notional * hedge_sign
        else:
            # Notional is in domestic currency, convert to foreign
            hedge_notional = delta * params.notional / params.spot * hedge_sign

        return hedge_notional
