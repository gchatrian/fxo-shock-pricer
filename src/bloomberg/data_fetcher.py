"""
Bloomberg market data fetcher for FX options.
Retrieves spot rates, forward points, volatility surface, and interest rates.
Supports non-USD crosses with implied rate calculation.
Supports historical data fetch for shock analysis.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Any

from .connection import BloombergConnection, BloombergConnectionError
from .tickers import TickerBuilder

try:
    import blpapi
    BLPAPI_AVAILABLE = True
except ImportError:
    BLPAPI_AVAILABLE = False

logger = logging.getLogger(__name__)


class DataFetchError(Exception):
    """Exception raised when data fetch fails."""
    pass


@dataclass
class VolSmileData:
    """Raw volatility smile data from Bloomberg."""
    tenor: str
    atm: float
    rr25: float
    bf25: float
    rr10: float
    bf10: float

    @property
    def vol_25c(self) -> float:
        """25 Delta Call volatility."""
        return self.atm + 0.5 * self.rr25 + self.bf25

    @property
    def vol_25p(self) -> float:
        """25 Delta Put volatility."""
        return self.vol_25c - self.rr25

    @property
    def vol_10c(self) -> float:
        """10 Delta Call volatility."""
        return self.atm + 0.5 * self.rr10 + self.bf10

    @property
    def vol_10p(self) -> float:
        """10 Delta Put volatility."""
        return self.vol_10c - self.rr10


@dataclass
class ForwardData:
    """Forward data for a currency pair."""
    spot: float
    forward_points: Dict[str, float] = field(default_factory=dict)  # tenor -> points
    forward_rates: Dict[str, float] = field(default_factory=dict)   # tenor -> outright rate
    n_pips: int = 4


@dataclass
class MarketData:
    """Container for all market data for a currency pair."""
    ccy_pair: str
    f_ccy: str
    d_ccy: str
    spot: float
    is_dollar_cross: bool

    # Forward data
    forward_points: Dict[str, float] = field(default_factory=dict)
    forward_rates: Dict[str, float] = field(default_factory=dict)

    # For non-USD crosses: USD cross data
    f_ccy_vs_usd: Optional[str] = None
    f_ccy_vs_usd_spot: Optional[float] = None
    f_ccy_vs_usd_forwards: Dict[str, float] = field(default_factory=dict)

    d_ccy_vs_usd: Optional[str] = None
    d_ccy_vs_usd_spot: Optional[float] = None
    d_ccy_vs_usd_forwards: Dict[str, float] = field(default_factory=dict)

    # Volatility surface
    vol_smiles: Dict[str, VolSmileData] = field(default_factory=dict)

    # Interest rates
    usd_rates: Dict[str, float] = field(default_factory=dict)
    domestic_rates: Dict[str, float] = field(default_factory=dict)
    foreign_rates: Dict[str, float] = field(default_factory=dict)

    # Days to maturity mapping
    days_to_maturity: Dict[str, int] = field(default_factory=dict)

    fetch_date: date = field(default_factory=date.today)


class MarketDataFetcher:
    """
    Fetches FX market data from Bloomberg.
    Supports USD crosses and non-USD crosses with implied rate calculation.
    """

    BBG_CUTOFF = "BGN"

    def __init__(self, connection: BloombergConnection):
        """
        Initialize fetcher with Bloomberg connection.

        Args:
            connection: BloombergConnection instance
        """
        self._connection = connection

    def _check_connection(self) -> None:
        """Verify Bloomberg connection is available."""
        if not self._connection.is_connected():
            raise BloombergConnectionError("Bloomberg is not connected")

    def _request_data(self, tickers: List[str], fields: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Request data from Bloomberg for multiple tickers and fields.

        Args:
            tickers: List of Bloomberg tickers
            fields: List of field names (e.g., ["PX_LAST"])

        Returns:
            Dictionary mapping ticker -> field -> value
        """
        self._check_connection()

        service = self._connection.get_ref_data_service()
        if service is None:
            raise BloombergConnectionError("Reference data service not available")

        request = service.createRequest("ReferenceDataRequest")

        for ticker in tickers:
            request.append("securities", ticker)

        for field_name in fields:
            request.append("fields", field_name)

        session = self._connection.get_session()
        session.sendRequest(request)

        results: Dict[str, Dict[str, Any]] = {ticker: {} for ticker in tickers}

        while True:
            event = session.nextEvent(500)

            for msg in event:
                if msg.hasElement("securityData"):
                    security_data = msg.getElement("securityData")

                    for i in range(security_data.numValues()):
                        security = security_data.getValueAsElement(i)
                        ticker = security.getElementAsString("security")

                        if security.hasElement("fieldData"):
                            field_data = security.getElement("fieldData")

                            for field_name in fields:
                                if field_data.hasElement(field_name):
                                    try:
                                        value = field_data.getElementAsFloat(field_name)
                                        results[ticker][field_name] = value
                                    except Exception:
                                        try:
                                            results[ticker][field_name] = field_data.getElementValue(field_name)
                                        except Exception as e:
                                            logger.warning(f"Could not get {field_name} for {ticker}: {e}")

            if event.eventType() == blpapi.Event.RESPONSE:
                break

        return results

    def _calculate_cross_forward_from_usd(
        self,
        f_ccy_vs_usd_fwd: float,
        d_ccy_vs_usd_fwd: float,
        f_ccy: str,
        d_ccy: str
    ) -> float:
        """
        Calculate cross forward from USD forwards.

        The formula depends on quoting convention:
        - EUR, GBP, AUD, NZD are quoted as xxxUSD ('f')
        - CHF, JPY, CAD are quoted as USDxxx ('d')

        Args:
            f_ccy_vs_usd_fwd: Forward of foreign currency vs USD
            d_ccy_vs_usd_fwd: Forward of domestic currency vs USD
            f_ccy: Foreign currency code
            d_ccy: Domestic currency code

        Returns:
            Cross forward rate
        """
        f_conv = TickerBuilder.fx_usd_quoting_convention(f_ccy)
        d_conv = TickerBuilder.fx_usd_quoting_convention(d_ccy)

        if f_conv == 'f' and d_conv == 'f':
            # xxxUSD / yyyUSD (e.g., AUDNZD = AUDUSD / NZDUSD)
            return f_ccy_vs_usd_fwd / d_ccy_vs_usd_fwd
        elif f_conv == 'f' and d_conv == 'd':
            # xxxUSD * USDyyy (e.g., EURCHF = EURUSD * USDCHF)
            return f_ccy_vs_usd_fwd * d_ccy_vs_usd_fwd
        elif f_conv == 'd' and d_conv == 'f':
            # 1 / (USDxxx * yyyUSD) - rare case
            return 1 / (f_ccy_vs_usd_fwd * d_ccy_vs_usd_fwd)
        else:  # f_conv == 'd' and d_conv == 'd'
            # USDyyy / USDxxx (e.g., CHFJPY = USDJPY / USDCHF)
            return d_ccy_vs_usd_fwd / f_ccy_vs_usd_fwd

    def _calculate_implied_rate(
        self,
        ccy: str,
        ccy_vs_usd_spot: float,
        ccy_vs_usd_fwd: float,
        usd_rate: float,
        tau: float
    ) -> float:
        """
        Calculate implied interest rate from FX forward using interest rate parity.

        Formula: F = S * (1 + r_d * tau) / (1 + r_f * tau)
        For xxxUSD (f): r_ccy = (S/F * (1 + r_usd * tau) - 1) / tau
        For USDxxx (d): r_ccy = (F/S * (1 + r_usd * tau) - 1) / tau

        Args:
            ccy: Currency code
            ccy_vs_usd_spot: Spot rate of ccy vs USD
            ccy_vs_usd_fwd: Forward rate of ccy vs USD
            usd_rate: USD interest rate (decimal)
            tau: Time to maturity in years

        Returns:
            Implied interest rate (decimal)
        """
        if tau <= 0:
            return usd_rate

        convention = TickerBuilder.fx_usd_quoting_convention(ccy)

        if convention == 'f':
            # xxxUSD: USD is domestic, ccy is foreign
            # F = S * (1 + r_usd * tau) / (1 + r_ccy * tau)
            # r_ccy = (S/F * (1 + r_usd * tau) - 1) / tau
            implied = (ccy_vs_usd_spot / ccy_vs_usd_fwd * (1 + usd_rate * tau) - 1) / tau
        else:
            # USDxxx: ccy is domestic, USD is foreign
            # F = S * (1 + r_ccy * tau) / (1 + r_usd * tau)
            # r_ccy = (F/S * (1 + r_usd * tau) - 1) / tau
            implied = (ccy_vs_usd_fwd / ccy_vs_usd_spot * (1 + usd_rate * tau) - 1) / tau

        return implied

    def fetch_all(
        self,
        ccy_pair: str,
        tenors: List[str],
        days_to_maturity: Optional[Dict[str, int]] = None
    ) -> MarketData:
        """
        Fetch all market data needed for pricing.

        Args:
            ccy_pair: Currency pair (e.g., "EURUSD", "EURGBP")
            tenors: List of tenors
            days_to_maturity: Optional dict mapping tenor -> days

        Returns:
            MarketData object with all data
        """
        ccy_pair = ccy_pair.upper().replace("/", "")
        f_ccy, d_ccy = TickerBuilder.parse_currency_pair(ccy_pair)
        is_dollar = TickerBuilder.is_dollar_cross(ccy_pair)
        n_pips = TickerBuilder.get_n_pips(ccy_pair)
        pip_scale = TickerBuilder.get_pip_scale(ccy_pair)

        # Build ticker lists
        all_tickers = []
        ticker_mapping = {}

        # Spot ticker
        spot_ticker = TickerBuilder.spot_ticker(ccy_pair, self.BBG_CUTOFF)
        all_tickers.append(spot_ticker)
        ticker_mapping["spot"] = spot_ticker

        # USD curve tickers
        usd_curve_tickers = TickerBuilder.get_usd_curve_tickers(tenors, self.BBG_CUTOFF)
        all_tickers.extend(usd_curve_tickers.values())
        ticker_mapping["usd_rates"] = usd_curve_tickers

        # Forward points for main cross
        fwd_tickers = {}
        for tenor in tenors:
            ticker = TickerBuilder.forward_points_ticker(ccy_pair, tenor, self.BBG_CUTOFF)
            all_tickers.append(ticker)
            fwd_tickers[tenor] = ticker
        ticker_mapping["forwards"] = fwd_tickers

        # Non-USD cross: add USD cross data
        f_ccy_vs_usd = None
        d_ccy_vs_usd = None
        if not is_dollar:
            f_ccy_vs_usd = TickerBuilder.get_ccy_code_vs_usd(f_ccy)
            d_ccy_vs_usd = TickerBuilder.get_ccy_code_vs_usd(d_ccy)

            # Spot tickers for USD crosses
            f_spot_ticker = TickerBuilder.spot_ticker(f_ccy_vs_usd, self.BBG_CUTOFF)
            d_spot_ticker = TickerBuilder.spot_ticker(d_ccy_vs_usd, self.BBG_CUTOFF)
            all_tickers.extend([f_spot_ticker, d_spot_ticker])
            ticker_mapping["f_ccy_vs_usd_spot"] = f_spot_ticker
            ticker_mapping["d_ccy_vs_usd_spot"] = d_spot_ticker

            # Forward tickers for USD crosses
            f_fwd_tickers = {}
            d_fwd_tickers = {}
            for tenor in tenors:
                f_ticker = TickerBuilder.forward_points_ticker(f_ccy_vs_usd, tenor, self.BBG_CUTOFF)
                d_ticker = TickerBuilder.forward_points_ticker(d_ccy_vs_usd, tenor, self.BBG_CUTOFF)
                all_tickers.extend([f_ticker, d_ticker])
                f_fwd_tickers[tenor] = f_ticker
                d_fwd_tickers[tenor] = d_ticker
            ticker_mapping["f_ccy_vs_usd_forwards"] = f_fwd_tickers
            ticker_mapping["d_ccy_vs_usd_forwards"] = d_fwd_tickers

        # Volatility tickers
        vol_tickers = {}
        for tenor in tenors:
            vol_tickers[tenor] = TickerBuilder.get_all_vol_tickers(ccy_pair, tenor)
            all_tickers.extend(vol_tickers[tenor].values())
        ticker_mapping["vols"] = vol_tickers

        # Fetch all data from Bloomberg
        results = self._request_data(all_tickers, ["PX_LAST"])

        # Parse results
        market_data = MarketData(
            ccy_pair=ccy_pair,
            f_ccy=f_ccy,
            d_ccy=d_ccy,
            spot=results.get(spot_ticker, {}).get("PX_LAST", 0.0),
            is_dollar_cross=is_dollar,
            f_ccy_vs_usd=f_ccy_vs_usd,
            d_ccy_vs_usd=d_ccy_vs_usd,
            days_to_maturity=days_to_maturity or {}
        )

        # Parse USD rates
        for tenor, ticker in usd_curve_tickers.items():
            if ticker in results and "PX_LAST" in results[ticker]:
                market_data.usd_rates[tenor] = results[ticker]["PX_LAST"] / 100.0

        # Parse non-USD cross spots and forwards
        if not is_dollar:
            f_spot_ticker = ticker_mapping["f_ccy_vs_usd_spot"]
            d_spot_ticker = ticker_mapping["d_ccy_vs_usd_spot"]
            market_data.f_ccy_vs_usd_spot = results.get(f_spot_ticker, {}).get("PX_LAST")
            market_data.d_ccy_vs_usd_spot = results.get(d_spot_ticker, {}).get("PX_LAST")

            f_n_pips = TickerBuilder.get_n_pips(f_ccy_vs_usd)
            d_n_pips = TickerBuilder.get_n_pips(d_ccy_vs_usd)
            f_pip_scale = TickerBuilder.get_pip_scale(f_ccy_vs_usd)
            d_pip_scale = TickerBuilder.get_pip_scale(d_ccy_vs_usd)

            for tenor in tenors:
                f_ticker = ticker_mapping["f_ccy_vs_usd_forwards"][tenor]
                d_ticker = ticker_mapping["d_ccy_vs_usd_forwards"][tenor]

                if f_ticker in results and "PX_LAST" in results[f_ticker]:
                    fwd_pts = results[f_ticker]["PX_LAST"]
                    market_data.f_ccy_vs_usd_forwards[tenor] = round(
                        market_data.f_ccy_vs_usd_spot + fwd_pts / f_pip_scale, f_n_pips
                    )

                if d_ticker in results and "PX_LAST" in results[d_ticker]:
                    fwd_pts = results[d_ticker]["PX_LAST"]
                    market_data.d_ccy_vs_usd_forwards[tenor] = round(
                        market_data.d_ccy_vs_usd_spot + fwd_pts / d_pip_scale, d_n_pips
                    )

        # Parse forward points and calculate outright forwards
        for tenor in tenors:
            ticker = fwd_tickers[tenor]
            if ticker in results and "PX_LAST" in results[ticker]:
                fwd_pts = results[ticker]["PX_LAST"]
                market_data.forward_points[tenor] = fwd_pts
                fwd_rate = round(market_data.spot + fwd_pts / pip_scale, n_pips)
                market_data.forward_rates[tenor] = fwd_rate
            elif not is_dollar:
                # Calculate from USD crosses if direct forward not available
                f_fwd = market_data.f_ccy_vs_usd_forwards.get(tenor)
                d_fwd = market_data.d_ccy_vs_usd_forwards.get(tenor)
                if f_fwd is not None and d_fwd is not None:
                    cross_fwd = self._calculate_cross_forward_from_usd(f_fwd, d_fwd, f_ccy, d_ccy)
                    market_data.forward_rates[tenor] = round(cross_fwd, n_pips)
                    market_data.forward_points[tenor] = (cross_fwd - market_data.spot) * pip_scale
                    logger.info(f"{ccy_pair} {tenor}: calculated forward from USD crosses")

        # Calculate implied rates
        logger.info(f"=== CALCULATING IMPLIED RATES FOR {ccy_pair} ===")
        logger.info(f"is_dollar_cross: {is_dollar}, f_ccy: {f_ccy}, d_ccy: {d_ccy}")
        logger.info(f"spot: {market_data.spot}")
        logger.info(f"forward_rates: {market_data.forward_rates}")
        logger.info(f"usd_rates: {market_data.usd_rates}")

        for tenor in tenors:
            dtm = days_to_maturity.get(tenor, 30) if days_to_maturity else 30
            tau = dtm / 365.0
            usd_rate = market_data.usd_rates.get(tenor, 0.05)

            logger.info(f"--- Tenor {tenor}: dtm={dtm}, tau={tau:.4f}, usd_rate={usd_rate:.4f}")

            # For USD crosses (EURUSD, USDJPY, etc.)
            if is_dollar:
                if d_ccy == "USD":
                    # e.g., EURUSD: USD is domestic, EUR is foreign
                    market_data.domestic_rates[tenor] = usd_rate
                    logger.info(f"  USD is domestic -> domestic_rate = {usd_rate:.4f}")

                    # Calculate EUR rate from forward using interest rate parity
                    # F = S * (1 + r_dom * tau) / (1 + r_for * tau)
                    # r_for = (S / F * (1 + r_dom * tau) - 1) / tau
                    fwd = market_data.forward_rates.get(tenor)
                    logger.info(f"  forward_rate for {tenor}: {fwd}")

                    if fwd is not None and fwd > 0 and market_data.spot > 0 and tau > 0:
                        implied_for = (market_data.spot / fwd * (1 + usd_rate * tau) - 1) / tau
                        market_data.foreign_rates[tenor] = round(implied_for, 6)
                        logger.info(f"  IMPLIED foreign_rate ({f_ccy}) = {implied_for:.6f}")
                    else:
                        market_data.foreign_rates[tenor] = usd_rate
                        logger.warning(f"  FALLBACK: foreign_rate = usd_rate (fwd={fwd}, spot={market_data.spot}, tau={tau})")

                elif f_ccy == "USD":
                    # e.g., USDJPY: USD is foreign, JPY is domestic
                    market_data.foreign_rates[tenor] = usd_rate
                    logger.info(f"  USD is foreign -> foreign_rate = {usd_rate:.4f}")

                    # Calculate domestic rate from forward
                    fwd = market_data.forward_rates.get(tenor)
                    logger.info(f"  forward_rate for {tenor}: {fwd}")

                    if fwd is not None and fwd > 0 and market_data.spot > 0 and tau > 0:
                        implied_dom = (fwd / market_data.spot * (1 + usd_rate * tau) - 1) / tau
                        market_data.domestic_rates[tenor] = round(implied_dom, 6)
                        logger.info(f"  IMPLIED domestic_rate ({d_ccy}) = {implied_dom:.6f}")
                    else:
                        market_data.domestic_rates[tenor] = usd_rate
                        logger.warning(f"  FALLBACK: domestic_rate = usd_rate")

            # For non-USD crosses (EURGBP, AUDNZD, etc.)
            else:
                # Calculate both rates from their USD crosses
                if market_data.d_ccy_vs_usd_spot and tenor in market_data.d_ccy_vs_usd_forwards:
                    d_rate = self._calculate_implied_rate(
                        d_ccy,
                        market_data.d_ccy_vs_usd_spot,
                        market_data.d_ccy_vs_usd_forwards[tenor],
                        usd_rate,
                        tau
                    )
                    market_data.domestic_rates[tenor] = round(d_rate, 6)
                    logger.info(f"  Cross: domestic_rate ({d_ccy}) = {d_rate:.6f}")
                else:
                    market_data.domestic_rates[tenor] = usd_rate
                    logger.warning(f"  Cross FALLBACK: domestic_rate = usd_rate")

                if market_data.f_ccy_vs_usd_spot and tenor in market_data.f_ccy_vs_usd_forwards:
                    f_rate = self._calculate_implied_rate(
                        f_ccy,
                        market_data.f_ccy_vs_usd_spot,
                        market_data.f_ccy_vs_usd_forwards[tenor],
                        usd_rate,
                        tau
                    )
                    market_data.foreign_rates[tenor] = round(f_rate, 6)
                    logger.info(f"  Cross: foreign_rate ({f_ccy}) = {f_rate:.6f}")
                else:
                    market_data.foreign_rates[tenor] = usd_rate
                    logger.warning(f"  Cross FALLBACK: foreign_rate = usd_rate")

        logger.info(f"=== FINAL RATES ===")
        logger.info(f"domestic_rates: {market_data.domestic_rates}")
        logger.info(f"foreign_rates: {market_data.foreign_rates}")

        # Parse volatility data
        for tenor in tenors:
            vol_t = vol_tickers[tenor]
            atm_ticker = vol_t["ATM"]
            rr25_ticker = vol_t["RR25"]
            bf25_ticker = vol_t["BF25"]
            rr10_ticker = vol_t["RR10"]
            bf10_ticker = vol_t["BF10"]

            atm = results.get(atm_ticker, {}).get("PX_LAST")
            rr25 = results.get(rr25_ticker, {}).get("PX_LAST")
            bf25 = results.get(bf25_ticker, {}).get("PX_LAST")
            rr10 = results.get(rr10_ticker, {}).get("PX_LAST")
            bf10 = results.get(bf10_ticker, {}).get("PX_LAST")

            if all(v is not None for v in [atm, rr25, bf25, rr10, bf10]):
                market_data.vol_smiles[tenor] = VolSmileData(
                    tenor=tenor,
                    atm=atm / 100.0,
                    rr25=rr25 / 100.0,
                    bf25=bf25 / 100.0,
                    rr10=rr10 / 100.0,
                    bf10=bf10 / 100.0,
                )
            else:
                logger.warning(f"Incomplete vol data for {ccy_pair} {tenor}")

        return market_data


class HistoricalDataFetcher:
    """
    Fetches historical FX market data from Bloomberg.
    Uses HistoricalDataRequest to get data for specific dates.
    """

    def __init__(self, connection: BloombergConnection):
        """Initialize fetcher with Bloomberg connection."""
        self._connection = connection

    def _check_connection(self) -> None:
        """Verify Bloomberg connection is available."""
        if not self._connection.is_connected():
            raise BloombergConnectionError("Bloomberg is not connected")

    def _request_historical_data(
        self,
        tickers: List[str],
        start_date: date,
        end_date: date,
        fields: List[str] = None
    ) -> Dict[str, Dict[str, float]]:
        """
        Request historical data from Bloomberg.

        Args:
            tickers: List of Bloomberg tickers
            start_date: Start date
            end_date: End date
            fields: List of fields (default: ["PX_LAST"])

        Returns:
            Dictionary mapping ticker -> date -> value
        """
        self._check_connection()

        if fields is None:
            fields = ["PX_LAST"]

        if not BLPAPI_AVAILABLE:
            raise BloombergConnectionError("blpapi is not available")

        service = self._connection.get_ref_data_service()
        if service is None:
            raise BloombergConnectionError("Reference data service not available")

        request = service.createRequest("HistoricalDataRequest")

        for ticker in tickers:
            request.append("securities", ticker)

        for field in fields:
            request.append("fields", field)

        request.set("startDate", start_date.strftime("%Y%m%d"))
        request.set("endDate", end_date.strftime("%Y%m%d"))
        request.set("periodicitySelection", "DAILY")

        session = self._connection.get_session()
        session.sendRequest(request)

        results: Dict[str, Dict[str, float]] = {}

        while True:
            event = session.nextEvent(5000)

            for msg in event:
                if msg.hasElement("securityData"):
                    security_data = msg.getElement("securityData")
                    ticker = security_data.getElementAsString("security")

                    if security_data.hasElement("fieldData"):
                        field_data_array = security_data.getElement("fieldData")

                        for i in range(field_data_array.numValues()):
                            field_data = field_data_array.getValueAsElement(i)

                            if field_data.hasElement("date"):
                                data_date = field_data.getElementAsString("date")

                                if ticker not in results:
                                    results[ticker] = {}

                                for field in fields:
                                    if field_data.hasElement(field):
                                        try:
                                            value = field_data.getElementAsFloat(field)
                                            results[ticker][data_date] = value
                                        except Exception as e:
                                            logger.warning(f"Could not get {field} for {ticker}: {e}")

            if event.eventType() == blpapi.Event.RESPONSE:
                break

        return results

    def fetch_historical(
        self,
        ccy_pair: str,
        tenors: List[str],
        target_date: date
    ) -> Dict:
        """
        Fetch all historical market data for a specific date.

        Args:
            ccy_pair: Currency pair (e.g., "EURUSD")
            tenors: List of tenors
            target_date: Target date for data

        Returns:
            Dictionary with spot, forward_points, vol_smiles (full surface), usd_rates
        """
        ccy_pair = ccy_pair.upper().replace("/", "")

        # Build all tickers
        all_tickers = []

        # Spot
        spot_ticker = TickerBuilder.spot_ticker(ccy_pair, "BGN")
        all_tickers.append(spot_ticker)

        # Forward points
        fwd_tickers = {}
        for tenor in tenors:
            ticker = TickerBuilder.forward_points_ticker(ccy_pair, tenor, "BGN")
            fwd_tickers[tenor] = ticker
            all_tickers.append(ticker)

        # Full volatility surface: ATM + RR25 + BF25 + RR10 + BF10
        vol_tickers = {}
        for tenor in tenors:
            vol_tickers[tenor] = TickerBuilder.get_all_vol_tickers(ccy_pair, tenor)
            all_tickers.extend(vol_tickers[tenor].values())

        # USD rates
        usd_tickers = TickerBuilder.get_usd_curve_tickers(tenors, "BGN")
        all_tickers.extend(usd_tickers.values())

        # Fetch data
        date_str = target_date.strftime("%Y-%m-%d")
        raw_data = self._request_historical_data(all_tickers, target_date, target_date)

        # Parse results
        result = {
            'spot': 0.0,
            'forward_points': {},
            'vol_smiles': {},  # Full surface: tenor -> {atm, rr25, bf25, rr10, bf10}
            'usd_rates': {},
            'date': target_date
        }

        # Get spot
        if spot_ticker in raw_data:
            for dt, val in raw_data[spot_ticker].items():
                result['spot'] = val

        # Get forward points
        for tenor, ticker in fwd_tickers.items():
            if ticker in raw_data:
                for dt, val in raw_data[ticker].items():
                    result['forward_points'][tenor] = val

        # Get full vol surface
        for tenor, tickers in vol_tickers.items():
            smile_data = {}
            for vol_type, ticker in tickers.items():
                if ticker in raw_data:
                    for dt, val in raw_data[ticker].items():
                        # vol_type is 'ATM', 'RR25', 'BF25', 'RR10', 'BF10'
                        smile_data[vol_type.lower()] = val
            
            if smile_data:
                result['vol_smiles'][tenor] = smile_data
                logger.info(f"  Vol {tenor}: ATM={smile_data.get('atm', 0):.2f}%, "
                           f"RR25={smile_data.get('rr25', 0):.2f}, "
                           f"BF25={smile_data.get('bf25', 0):.2f}")

        # Get USD rates
        for tenor, ticker in usd_tickers.items():
            if ticker in raw_data:
                for dt, val in raw_data[ticker].items():
                    result['usd_rates'][tenor] = val

        logger.info(f"Historical data for {ccy_pair} on {target_date}:")
        logger.info(f"  Spot: {result['spot']}")
        logger.info(f"  Forward points: {result['forward_points']}")
        logger.info(f"  Vol smiles: {len(result['vol_smiles'])} tenors with full surface")
        logger.info(f"  USD rates: {result['usd_rates']}")

        return result


@dataclass
class MarketDataDelta:
    """
    Contains the differences between two market data snapshots.
    Used for historical shock analysis.
    """
    start_date: date
    end_date: date
    time_diff_days: int
    
    # Spot: percentage change (end - start) / start
    spot_pct_change: float = 0.0
    
    # Forward points: percentage change per tenor
    forward_pct_changes: Dict[str, float] = field(default_factory=dict)
    
    # Interest rates: absolute difference (end - start) per tenor
    usd_rate_diffs: Dict[str, float] = field(default_factory=dict)
    
    # Volatility surface: absolute differences (end - start) per tenor
    # ATM volatility
    atm_vol_diffs: Dict[str, float] = field(default_factory=dict)
    # Risk reversals (25D and 10D)
    rr25_diffs: Dict[str, float] = field(default_factory=dict)
    rr10_diffs: Dict[str, float] = field(default_factory=dict)
    # Butterflies (25D and 10D)
    bf25_diffs: Dict[str, float] = field(default_factory=dict)
    bf10_diffs: Dict[str, float] = field(default_factory=dict)
    
    @classmethod
    def calculate(
        cls,
        start_data: Dict,
        end_data: Dict,
        start_date: date,
        end_date: date
    ) -> 'MarketDataDelta':
        """
        Calculate differences between two market data snapshots.
        
        Args:
            start_data: Historical data dict for start date
            end_data: Historical data dict for end date
            start_date: Start date
            end_date: End date
            
        Returns:
            MarketDataDelta with all calculated differences
        """
        logger.info(f"=== CALCULATING MARKET DATA DELTA ===")
        logger.info(f"Start date: {start_date}, End date: {end_date}")
        
        time_diff = (end_date - start_date).days
        logger.info(f"Time difference: {time_diff} days")
        
        # Spot percentage change
        spot_start = start_data.get('spot', 0)
        spot_end = end_data.get('spot', 0)
        if spot_start > 0:
            spot_pct = (spot_end - spot_start) / spot_start
        else:
            spot_pct = 0.0
        logger.info(f"Spot: {spot_start:.5f} -> {spot_end:.5f} ({spot_pct*100:+.2f}%)")
        
        # Forward points percentage change
        fwd_pct_changes = {}
        for tenor in start_data.get('forward_points', {}).keys():
            start_pts = start_data['forward_points'].get(tenor, 0)
            end_pts = end_data.get('forward_points', {}).get(tenor, 0)
            if start_pts != 0:
                pct_change = (end_pts - start_pts) / abs(start_pts)
            else:
                pct_change = 0.0
            fwd_pct_changes[tenor] = pct_change
            logger.info(f"  Fwd {tenor}: {start_pts:.2f} -> {end_pts:.2f} ({pct_change*100:+.2f}%)")
        
        # USD rate differences (absolute)
        rate_diffs = {}
        for tenor in start_data.get('usd_rates', {}).keys():
            start_rate = start_data['usd_rates'].get(tenor, 0)
            end_rate = end_data.get('usd_rates', {}).get(tenor, 0)
            diff = end_rate - start_rate
            rate_diffs[tenor] = diff / 100.0  # Convert from bps to decimal
            logger.info(f"  USD Rate {tenor}: {start_rate:.3f}% -> {end_rate:.3f}% ({diff:+.3f}%)")
        
        # Volatility surface differences (ATM + RR + BF)
        atm_diffs = {}
        rr25_diffs = {}
        rr10_diffs = {}
        bf25_diffs = {}
        bf10_diffs = {}
        
        logger.info(f"  === Volatility Surface Diffs ===")
        for tenor in start_data.get('vol_smiles', {}).keys():
            start_smile = start_data['vol_smiles'].get(tenor, {})
            end_smile = end_data.get('vol_smiles', {}).get(tenor, {})
            
            if start_smile and end_smile:
                # ATM
                start_atm = start_smile.get('atm', 0)
                end_atm = end_smile.get('atm', 0)
                atm_diff = (end_atm - start_atm) / 100.0  # Convert from % to decimal
                atm_diffs[tenor] = atm_diff
                
                # RR25
                start_rr25 = start_smile.get('rr25', 0)
                end_rr25 = end_smile.get('rr25', 0)
                rr25_diff = (end_rr25 - start_rr25) / 100.0
                rr25_diffs[tenor] = rr25_diff
                
                # RR10
                start_rr10 = start_smile.get('rr10', 0)
                end_rr10 = end_smile.get('rr10', 0)
                rr10_diff = (end_rr10 - start_rr10) / 100.0
                rr10_diffs[tenor] = rr10_diff
                
                # BF25
                start_bf25 = start_smile.get('bf25', 0)
                end_bf25 = end_smile.get('bf25', 0)
                bf25_diff = (end_bf25 - start_bf25) / 100.0
                bf25_diffs[tenor] = bf25_diff
                
                # BF10
                start_bf10 = start_smile.get('bf10', 0)
                end_bf10 = end_smile.get('bf10', 0)
                bf10_diff = (end_bf10 - start_bf10) / 100.0
                bf10_diffs[tenor] = bf10_diff
                
                logger.info(f"  {tenor}: ATM {start_atm:.2f}%->{end_atm:.2f}% ({atm_diff*100:+.3f}%), "
                           f"RR25 {start_rr25:.2f}->{end_rr25:.2f}, BF25 {start_bf25:.2f}->{end_bf25:.2f}")
        
        logger.info(f"=== DELTA CALCULATION COMPLETE ===")
        
        return cls(
            start_date=start_date,
            end_date=end_date,
            time_diff_days=time_diff,
            spot_pct_change=spot_pct,
            forward_pct_changes=fwd_pct_changes,
            usd_rate_diffs=rate_diffs,
            atm_vol_diffs=atm_diffs,
            rr25_diffs=rr25_diffs,
            rr10_diffs=rr10_diffs,
            bf25_diffs=bf25_diffs,
            bf10_diffs=bf10_diffs
        )


@dataclass
class ShockedMarketData:
    """
    Market data with shock applied.
    """
    spot: float
    forward_rates: Dict[str, float]
    domestic_rates: Dict[str, float]
    foreign_rates: Dict[str, float]
    
    # Complete vol surface (per tenor): each is a dict with atm, rr25, rr10, bf25, bf10
    vol_smiles: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    # Legacy: ATM vols only (for backward compatibility)
    atm_vols: Dict[str, float] = field(default_factory=dict)
    
    shocked_expiry_days: int = 0
    original_expiry_days: int = 0
    
    # Delta details for display
    spot_shock_pct: float = 0.0
    vol_shock: float = 0.0  # Average ATM vol shock for display
    rate_shock: float = 0.0  # Average rate shock for display


class ShockCalculator:
    """
    Applies historical shocks to current market data.
    """
    
    @classmethod
    def apply_shock(
        cls,
        current_market_data: 'MarketData',
        delta: MarketDataDelta,
        original_expiry_days: int
    ) -> ShockedMarketData:
        """
        Apply shock to current market data.
        
        Args:
            current_market_data: Current MarketData object
            delta: MarketDataDelta with calculated differences
            original_expiry_days: Original option expiry in days
            
        Returns:
            ShockedMarketData with all values adjusted
        """
        logger.info(f"=== APPLYING SHOCK TO MARKET DATA ===")
        
        # 1. Spot shock (percentage change)
        shocked_spot = current_market_data.spot * (1 + delta.spot_pct_change)
        logger.info(f"Spot: {current_market_data.spot:.5f} * (1 + {delta.spot_pct_change:.4f}) = {shocked_spot:.5f}")
        
        # 2. Forward rates shock (percentage change)
        shocked_forwards = {}
        pip_scale = 10000 if "JPY" not in current_market_data.ccy_pair else 100
        for tenor, fwd in current_market_data.forward_rates.items():
            pct_change = delta.forward_pct_changes.get(tenor, 0)
            # Apply percentage change to forward points, then recalculate forward
            fwd_pts = (fwd - current_market_data.spot) * pip_scale
            shocked_pts = fwd_pts * (1 + pct_change)
            shocked_fwd = shocked_spot + shocked_pts / pip_scale
            shocked_forwards[tenor] = shocked_fwd
            logger.info(f"  Fwd {tenor}: {fwd:.5f} -> {shocked_fwd:.5f}")
        
        # 3. Domestic rates shock (absolute difference)
        shocked_dom_rates = {}
        for tenor, rate in current_market_data.domestic_rates.items():
            diff = delta.usd_rate_diffs.get(tenor, 0)
            shocked_rate = rate + diff
            shocked_dom_rates[tenor] = shocked_rate
            logger.info(f"  Dom Rate {tenor}: {rate:.4f} + {diff:.4f} = {shocked_rate:.4f}")
        
        # 4. Foreign rates shock (recalculate from forwards)
        shocked_for_rates = {}
        for tenor, rate in current_market_data.foreign_rates.items():
            # Use the same diff as USD for simplicity, or recalculate from IRP
            diff = delta.usd_rate_diffs.get(tenor, 0)
            shocked_rate = rate + diff
            shocked_for_rates[tenor] = shocked_rate
            logger.info(f"  For Rate {tenor}: {rate:.4f} + {diff:.4f} = {shocked_rate:.4f}")
        
        # 5. Full volatility surface shock (ATM + RR + BF)
        shocked_vol_smiles = {}
        shocked_atm_vols = {}
        avg_vol_shock = 0.0
        vol_count = 0
        
        logger.info(f"  === Shocking Volatility Surface ===")
        for tenor, smile in current_market_data.vol_smiles.items():
            # Get diffs for this tenor
            atm_diff = delta.atm_vol_diffs.get(tenor, 0)
            rr25_diff = delta.rr25_diffs.get(tenor, 0)
            rr10_diff = delta.rr10_diffs.get(tenor, 0)
            bf25_diff = delta.bf25_diffs.get(tenor, 0)
            bf10_diff = delta.bf10_diffs.get(tenor, 0)
            
            # Apply shocks
            shocked_atm = max(0.001, smile.atm + atm_diff)
            shocked_rr25 = smile.rr25 + rr25_diff
            shocked_rr10 = smile.rr10 + rr10_diff
            shocked_bf25 = max(0, smile.bf25 + bf25_diff)  # BF should be positive
            shocked_bf10 = max(0, smile.bf10 + bf10_diff)
            
            shocked_vol_smiles[tenor] = {
                'atm': shocked_atm,
                'rr25': shocked_rr25,
                'rr10': shocked_rr10,
                'bf25': shocked_bf25,
                'bf10': shocked_bf10
            }
            shocked_atm_vols[tenor] = shocked_atm
            
            avg_vol_shock += atm_diff
            vol_count += 1
            
            logger.info(f"  {tenor}: ATM {smile.atm:.4f}->{shocked_atm:.4f}, "
                       f"RR25 {smile.rr25:.4f}->{shocked_rr25:.4f}, "
                       f"BF25 {smile.bf25:.4f}->{shocked_bf25:.4f}")
        
        if vol_count > 0:
            avg_vol_shock /= vol_count
        
        # 6. Expiry shock (time decay)
        shocked_expiry = original_expiry_days - delta.time_diff_days
        logger.info(f"Expiry: {original_expiry_days} - {delta.time_diff_days} = {shocked_expiry} days")
        
        # Average rate shock for display
        avg_rate_shock = sum(delta.usd_rate_diffs.values()) / len(delta.usd_rate_diffs) if delta.usd_rate_diffs else 0
        
        logger.info(f"=== SHOCK APPLICATION COMPLETE ===")
        
        return ShockedMarketData(
            spot=shocked_spot,
            forward_rates=shocked_forwards,
            domestic_rates=shocked_dom_rates,
            foreign_rates=shocked_for_rates,
            vol_smiles=shocked_vol_smiles,
            atm_vols=shocked_atm_vols,
            shocked_expiry_days=shocked_expiry,
            original_expiry_days=original_expiry_days,
            spot_shock_pct=delta.spot_pct_change,
            vol_shock=avg_vol_shock,
            rate_shock=avg_rate_shock
        )
