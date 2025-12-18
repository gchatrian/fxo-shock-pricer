"""
Bloomberg ticker construction for FX market data.
"""

from typing import List, Dict


class TickerBuilder:
    """
    Build Bloomberg tickers for FX market data.

    Ticker formats:
    - Spot: EURUSD BGN Curncy
    - Vol ATM: EURUSDV1M BGN Curncy
    - Vol RR 25D: EURUSD25R1M BGN Curncy
    - Vol BF 25D: EURUSD25B1M BGN Curncy
    - Vol RR 10D: EURUSD10R1M BGN Curncy
    - Vol BF 10D: EURUSD10B1M BGN Curncy
    - Forward Points: EUR1M BGN Curncy
    - SOFR: US00O/N Index, SOFR1M Index
    """

    # Map tenor to Bloomberg tenor code
    TENOR_MAP = {
        "O/N": "O/N",
        "1W": "1W",
        "2W": "2W",
        "3W": "3W",
        "1M": "1M",
        "2M": "2M",
        "3M": "3M",
        "4M": "4M",
        "5M": "5M",
        "6M": "6M",
        "7M": "7M",
        "8M": "8M",
        "9M": "9M",
        "10M": "10M",
        "11M": "11M",
        "12M": "12M",
        "1Y": "1Y",
        "15M": "15M",
        "18M": "18M",
        "2Y": "2Y",
        "3Y": "3Y",
        "4Y": "4Y",
        "5Y": "5Y",
        "7Y": "7Y",
        "10Y": "10Y",
    }

    @classmethod
    def spot_ticker(cls, ccy_pair: str) -> str:
        """
        Build spot rate ticker.

        Args:
            ccy_pair: Currency pair (e.g., "EURUSD")

        Returns:
            Bloomberg ticker (e.g., "EURUSD BGN Curncy")
        """
        ccy_pair = ccy_pair.upper().replace("/", "").replace(" ", "")
        return f"{ccy_pair} BGN Curncy"

    @classmethod
    def forward_points_ticker(cls, ccy_pair: str, tenor: str) -> str:
        """
        Build forward points ticker.

        Args:
            ccy_pair: Currency pair (e.g., "EURUSD")
            tenor: Tenor (e.g., "1M", "3M")

        Returns:
            Bloomberg ticker (e.g., "EUR1M BGN Curncy")
        """
        ccy_pair = ccy_pair.upper().replace("/", "").replace(" ", "")
        base_ccy = ccy_pair[:3]
        tenor = tenor.upper()

        return f"{base_ccy}{tenor} BGN Curncy"

    @classmethod
    def vol_atm_ticker(cls, ccy_pair: str, tenor: str) -> str:
        """
        Build ATM volatility ticker.

        Args:
            ccy_pair: Currency pair (e.g., "EURUSD")
            tenor: Tenor (e.g., "1M", "3M")

        Returns:
            Bloomberg ticker (e.g., "EURUSDV1M BGN Curncy")
        """
        ccy_pair = ccy_pair.upper().replace("/", "").replace(" ", "")
        tenor = tenor.upper()

        return f"{ccy_pair}V{tenor} BGN Curncy"

    @classmethod
    def vol_rr_ticker(cls, ccy_pair: str, tenor: str, delta: int = 25) -> str:
        """
        Build Risk Reversal volatility ticker.

        Args:
            ccy_pair: Currency pair (e.g., "EURUSD")
            tenor: Tenor (e.g., "1M", "3M")
            delta: Delta level (10 or 25)

        Returns:
            Bloomberg ticker (e.g., "EURUSD25R1M BGN Curncy")
        """
        ccy_pair = ccy_pair.upper().replace("/", "").replace(" ", "")
        tenor = tenor.upper()

        return f"{ccy_pair}{delta}R{tenor} BGN Curncy"

    @classmethod
    def vol_bf_ticker(cls, ccy_pair: str, tenor: str, delta: int = 25) -> str:
        """
        Build Butterfly volatility ticker.

        Args:
            ccy_pair: Currency pair (e.g., "EURUSD")
            tenor: Tenor (e.g., "1M", "3M")
            delta: Delta level (10 or 25)

        Returns:
            Bloomberg ticker (e.g., "EURUSD25B1M BGN Curncy")
        """
        ccy_pair = ccy_pair.upper().replace("/", "").replace(" ", "")
        tenor = tenor.upper()

        return f"{ccy_pair}{delta}B{tenor} BGN Curncy"

    @classmethod
    def sofr_ticker(cls, tenor: str) -> str:
        """
        Build SOFR rate ticker.

        Args:
            tenor: Tenor (e.g., "O/N", "1M", "3M")

        Returns:
            Bloomberg ticker (e.g., "SOFRRATE Index" for O/N, "SOFR1M Index" for 1M)
        """
        tenor = tenor.upper()

        if tenor == "O/N":
            return "SOFRRATE Index"
        else:
            return f"SOFR{tenor} Index"

    @classmethod
    def usd_rate_ticker(cls, prefix: str, tenor: str) -> str:
        """
        Build USD rate ticker with configurable prefix.

        Args:
            prefix: Rate prefix (e.g., "SOFR", "US00")
            tenor: Tenor (e.g., "O/N", "1M")

        Returns:
            Bloomberg ticker
        """
        tenor = tenor.upper()
        prefix = prefix.upper()

        if prefix == "SOFR":
            return cls.sofr_ticker(tenor)
        else:
            # Generic format for other curves
            if tenor == "O/N":
                return f"{prefix}O/N Index"
            else:
                return f"{prefix}{tenor} Index"

    @classmethod
    def get_all_vol_tickers(cls, ccy_pair: str, tenor: str) -> Dict[str, str]:
        """
        Get all volatility tickers for a tenor (ATM, RR, BF).

        Args:
            ccy_pair: Currency pair
            tenor: Tenor

        Returns:
            Dictionary with keys: 'ATM', 'RR25', 'BF25', 'RR10', 'BF10'
        """
        return {
            "ATM": cls.vol_atm_ticker(ccy_pair, tenor),
            "RR25": cls.vol_rr_ticker(ccy_pair, tenor, 25),
            "BF25": cls.vol_bf_ticker(ccy_pair, tenor, 25),
            "RR10": cls.vol_rr_ticker(ccy_pair, tenor, 10),
            "BF10": cls.vol_bf_ticker(ccy_pair, tenor, 10),
        }

    @classmethod
    def get_all_tickers_for_pair(
        cls,
        ccy_pair: str,
        tenors: List[str],
        usd_curve_prefix: str = "SOFR"
    ) -> Dict[str, List[str]]:
        """
        Get all tickers needed for pricing an FX option.

        Args:
            ccy_pair: Currency pair
            tenors: List of tenors
            usd_curve_prefix: Prefix for USD rate curve

        Returns:
            Dictionary with categories: 'spot', 'forwards', 'vols', 'rates'
        """
        tickers = {
            "spot": [cls.spot_ticker(ccy_pair)],
            "forwards": [],
            "vols_atm": [],
            "vols_rr25": [],
            "vols_bf25": [],
            "vols_rr10": [],
            "vols_bf10": [],
            "usd_rates": [],
        }

        for tenor in tenors:
            # Forward points
            tickers["forwards"].append(cls.forward_points_ticker(ccy_pair, tenor))

            # Volatilities
            tickers["vols_atm"].append(cls.vol_atm_ticker(ccy_pair, tenor))
            tickers["vols_rr25"].append(cls.vol_rr_ticker(ccy_pair, tenor, 25))
            tickers["vols_bf25"].append(cls.vol_bf_ticker(ccy_pair, tenor, 25))
            tickers["vols_rr10"].append(cls.vol_rr_ticker(ccy_pair, tenor, 10))
            tickers["vols_bf10"].append(cls.vol_bf_ticker(ccy_pair, tenor, 10))

            # USD rates
            tickers["usd_rates"].append(cls.usd_rate_ticker(usd_curve_prefix, tenor))

        return tickers
