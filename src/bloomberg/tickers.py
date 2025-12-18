"""
Bloomberg ticker construction for FX market data.
"""

from typing import List, Dict, Tuple


class TickerBuilder:
    """
    Build Bloomberg tickers for FX market data.

    Ticker formats:
    - Spot: EURUSD BGN Curncy
    - Vol ATM: EURUSDV1M Curncy
    - Vol RR 25D: EURUSD25R1M Curncy
    - Vol BF 25D: EURUSD25B1M Curncy
    - Vol RR 10D: EURUSD10R1M Curncy
    - Vol BF 10D: EURUSD10B1M Curncy
    - Forward Points: EUR1M BGN Curncy
    - USD SOFR: USOSFR* BGN Curncy
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

    # Forward code mapping for major pairs
    FORWARD_CODE_MAP = {
        "EURUSD": "EUR",
        "GBPUSD": "GBP",
        "USDJPY": "JPY",
        "AUDUSD": "AUD",
        "USDCAD": "CAD",
        "NZDUSD": "NZD",
        "USDCHF": "CHF",
    }

    # USD SOFR curve tenor mapping
    USD_CURVE_TENOR_MAP = {
        "1W": "1Z",
        "2W": "2Z",
        "3W": "3Z",
        "1M": "A",
        "2M": "B",
        "3M": "C",
        "4M": "D",
        "5M": "E",
        "6M": "F",
        "7M": "G",
        "8M": "H",
        "9M": "I",
        "10M": "J",
        "11M": "K",
        "1Y": "1",
        "18M": "1F",
        "2Y": "2",
        "3Y": "3",
    }

    # Forward points tenor mapping (Bloomberg uses 12M not 1Y)
    FWD_TENOR_MAP = {
        "1Y": "12M",
    }

    # Currencies quoted as xxxUSD (foreign convention)
    FOREIGN_CONVENTION_CCYS = {"EUR", "GBP", "AUD", "NZD"}

    @classmethod
    def get_forward_code(cls, ccy_pair: str) -> str:
        """
        Get the Bloomberg forward code for a currency pair.

        Args:
            ccy_pair: Currency pair (e.g., "EURUSD")

        Returns:
            Forward code (e.g., "EUR" for EURUSD)
        """
        ccy_pair = ccy_pair.upper().replace("/", "").replace(" ", "")
        return cls.FORWARD_CODE_MAP.get(ccy_pair, ccy_pair)

    @classmethod
    def get_n_pips(cls, ccy_pair: str) -> int:
        """
        Get number of decimal places (pips) for a currency pair.

        Args:
            ccy_pair: Currency pair

        Returns:
            Number of decimal places (2 for JPY pairs, 4 otherwise)
        """
        ccy_pair = ccy_pair.upper().replace("/", "").replace(" ", "")
        if ccy_pair[-3:] == "JPY":
            return 2
        return 4

    @classmethod
    def get_pip_scale(cls, ccy_pair: str) -> float:
        """
        Get the pip scale factor for forward points conversion.

        Args:
            ccy_pair: Currency pair

        Returns:
            Scale factor (100 for JPY pairs, 10000 otherwise)
        """
        n_pips = cls.get_n_pips(ccy_pair)
        return pow(10, n_pips)

    @classmethod
    def fx_usd_quoting_convention(cls, ccy: str) -> str:
        """
        Determine FX quoting convention vs USD.

        Args:
            ccy: Currency code (e.g., "EUR", "JPY")

        Returns:
            'f' if quoted as xxxUSD (foreign), 'd' if quoted as USDxxx (domestic)
        """
        ccy = ccy.upper()
        if ccy in cls.FOREIGN_CONVENTION_CCYS:
            return "f"
        return "d"

    @classmethod
    def get_ccy_code_vs_usd(cls, ccy: str) -> str:
        """
        Get the currency pair code vs USD.

        Args:
            ccy: Currency code (e.g., "EUR", "CHF")

        Returns:
            Currency pair vs USD (e.g., "EURUSD" or "USDCHF")
        """
        ccy = ccy.upper()
        if cls.fx_usd_quoting_convention(ccy) == "f":
            return f"{ccy}USD"
        return f"USD{ccy}"

    @classmethod
    def is_dollar_cross(cls, ccy_pair: str) -> bool:
        """
        Check if currency pair involves USD.

        Args:
            ccy_pair: Currency pair

        Returns:
            True if USD is in the pair
        """
        ccy_pair = ccy_pair.upper().replace("/", "").replace(" ", "")
        return "USD" in ccy_pair

    @classmethod
    def parse_currency_pair(cls, ccy_pair: str) -> Tuple[str, str]:
        """
        Parse currency pair into foreign and domestic currencies.

        Args:
            ccy_pair: Currency pair (e.g., "EURUSD")

        Returns:
            Tuple of (foreign_ccy, domestic_ccy)
        """
        ccy_pair = ccy_pair.upper().replace("/", "").replace(" ", "")
        return ccy_pair[:3], ccy_pair[3:]

    @classmethod
    def spot_ticker(cls, ccy_pair: str, cutoff: str = "BGN") -> str:
        """
        Build spot rate ticker.

        Args:
            ccy_pair: Currency pair (e.g., "EURUSD")
            cutoff: Bloomberg cutoff (e.g., "BGN")

        Returns:
            Bloomberg ticker (e.g., "EURUSD BGN Curncy")
        """
        ccy_pair = ccy_pair.upper().replace("/", "").replace(" ", "")
        return f"{ccy_pair} {cutoff} Curncy"

    @classmethod
    def forward_points_ticker(cls, ccy_pair: str, tenor: str, cutoff: str = "BGN") -> str:
        """
        Build forward points ticker.

        Args:
            ccy_pair: Currency pair (e.g., "EURUSD")
            tenor: Tenor (e.g., "1M", "3M", "1Y")
            cutoff: Bloomberg cutoff

        Returns:
            Bloomberg ticker (e.g., "EUR1M BGN Curncy", "EUR12M BGN Curncy" for 1Y)
        """
        ccy_pair = ccy_pair.upper().replace("/", "").replace(" ", "")
        fwd_code = cls.get_forward_code(ccy_pair)
        tenor = tenor.upper()
        # Map tenor (e.g., 1Y -> 12M for Bloomberg)
        bbg_tenor = cls.FWD_TENOR_MAP.get(tenor, tenor)
        return f"{fwd_code}{bbg_tenor} {cutoff} Curncy"

    @classmethod
    def vol_atm_ticker(cls, ccy_pair: str, tenor: str) -> str:
        """
        Build ATM volatility ticker.

        Args:
            ccy_pair: Currency pair (e.g., "EURUSD")
            tenor: Tenor (e.g., "1M", "3M")

        Returns:
            Bloomberg ticker (e.g., "EURUSDV1M Curncy")
        """
        ccy_pair = ccy_pair.upper().replace("/", "").replace(" ", "")
        tenor = tenor.upper()
        return f"{ccy_pair}V{tenor} Curncy"

    @classmethod
    def vol_rr_ticker(cls, ccy_pair: str, tenor: str, delta: int = 25) -> str:
        """
        Build Risk Reversal volatility ticker.

        Args:
            ccy_pair: Currency pair (e.g., "EURUSD")
            tenor: Tenor (e.g., "1M", "3M")
            delta: Delta level (10 or 25)

        Returns:
            Bloomberg ticker (e.g., "EURUSD25R1M Curncy")
        """
        ccy_pair = ccy_pair.upper().replace("/", "").replace(" ", "")
        tenor = tenor.upper()
        return f"{ccy_pair}{delta}R{tenor} Curncy"

    @classmethod
    def vol_bf_ticker(cls, ccy_pair: str, tenor: str, delta: int = 25) -> str:
        """
        Build Butterfly volatility ticker.

        Args:
            ccy_pair: Currency pair (e.g., "EURUSD")
            tenor: Tenor (e.g., "1M", "3M")
            delta: Delta level (10 or 25)

        Returns:
            Bloomberg ticker (e.g., "EURUSD25B1M Curncy")
        """
        ccy_pair = ccy_pair.upper().replace("/", "").replace(" ", "")
        tenor = tenor.upper()
        return f"{ccy_pair}{delta}B{tenor} Curncy"

    @classmethod
    def usd_sofr_ticker(cls, tenor: str, cutoff: str = "BGN") -> str:
        """
        Build USD SOFR rate ticker.

        Args:
            tenor: Tenor (e.g., "1M", "3M", "1Y")
            cutoff: Bloomberg cutoff

        Returns:
            Bloomberg ticker (e.g., "USOSFRA BGN Curncy" for 1M)
        """
        tenor = tenor.upper()
        tenor_code = cls.USD_CURVE_TENOR_MAP.get(tenor)
        if tenor_code is None:
            raise ValueError(f"Unknown tenor for USD SOFR curve: {tenor}")
        return f"USOSFR{tenor_code} {cutoff} CURNCY"

    @classmethod
    def get_usd_curve_tickers(cls, tenors: List[str], cutoff: str = "BGN") -> Dict[str, str]:
        """
        Get all USD SOFR curve tickers for given tenors.

        Args:
            tenors: List of tenors
            cutoff: Bloomberg cutoff

        Returns:
            Dictionary mapping tenor -> ticker
        """
        result = {}
        for tenor in tenors:
            tenor = tenor.upper()
            if tenor in cls.USD_CURVE_TENOR_MAP:
                result[tenor] = cls.usd_sofr_ticker(tenor, cutoff)
        return result

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
        cutoff: str = "BGN"
    ) -> Dict[str, List[str]]:
        """
        Get all tickers needed for pricing an FX option.

        Args:
            ccy_pair: Currency pair
            tenors: List of tenors
            cutoff: Bloomberg cutoff

        Returns:
            Dictionary with categories: 'spot', 'forwards', 'vols', 'rates', etc.
        """
        ccy_pair = ccy_pair.upper().replace("/", "").replace(" ", "")
        f_ccy, d_ccy = cls.parse_currency_pair(ccy_pair)
        is_dollar = cls.is_dollar_cross(ccy_pair)

        tickers = {
            "spot": [cls.spot_ticker(ccy_pair, cutoff)],
            "forwards": [],
            "vols_atm": [],
            "vols_rr25": [],
            "vols_bf25": [],
            "vols_rr10": [],
            "vols_bf10": [],
            "usd_rates": [],
        }

        # For non-USD crosses, add the USD cross spots and forwards
        if not is_dollar:
            f_ccy_vs_usd = cls.get_ccy_code_vs_usd(f_ccy)
            d_ccy_vs_usd = cls.get_ccy_code_vs_usd(d_ccy)

            tickers["f_ccy_vs_usd_spot"] = [cls.spot_ticker(f_ccy_vs_usd, cutoff)]
            tickers["d_ccy_vs_usd_spot"] = [cls.spot_ticker(d_ccy_vs_usd, cutoff)]
            tickers["f_ccy_vs_usd_forwards"] = []
            tickers["d_ccy_vs_usd_forwards"] = []

        # USD curve tickers
        usd_curve = cls.get_usd_curve_tickers(tenors, cutoff)
        tickers["usd_rates"] = list(usd_curve.values())

        for tenor in tenors:
            # Forward points for the main cross
            tickers["forwards"].append(cls.forward_points_ticker(ccy_pair, tenor, cutoff))

            # Forward points for USD crosses (for non-USD pairs)
            if not is_dollar:
                f_ccy_vs_usd = cls.get_ccy_code_vs_usd(f_ccy)
                d_ccy_vs_usd = cls.get_ccy_code_vs_usd(d_ccy)
                tickers["f_ccy_vs_usd_forwards"].append(
                    cls.forward_points_ticker(f_ccy_vs_usd, tenor, cutoff)
                )
                tickers["d_ccy_vs_usd_forwards"].append(
                    cls.forward_points_ticker(d_ccy_vs_usd, tenor, cutoff)
                )

            # Volatilities
            tickers["vols_atm"].append(cls.vol_atm_ticker(ccy_pair, tenor))
            tickers["vols_rr25"].append(cls.vol_rr_ticker(ccy_pair, tenor, 25))
            tickers["vols_bf25"].append(cls.vol_bf_ticker(ccy_pair, tenor, 25))
            tickers["vols_rr10"].append(cls.vol_rr_ticker(ccy_pair, tenor, 10))
            tickers["vols_bf10"].append(cls.vol_bf_ticker(ccy_pair, tenor, 10))

        return tickers
