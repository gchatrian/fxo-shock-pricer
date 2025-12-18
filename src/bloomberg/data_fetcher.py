"""
Bloomberg market data fetcher for FX options.
Retrieves spot rates, forward points, volatility surface, and interest rates.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
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
        return self.atm - 0.5 * self.rr25 + self.bf25

    @property
    def vol_10c(self) -> float:
        """10 Delta Call volatility."""
        return self.atm + 0.5 * self.rr10 + self.bf10

    @property
    def vol_10p(self) -> float:
        """10 Delta Put volatility."""
        return self.atm - 0.5 * self.rr10 + self.bf10


@dataclass
class MarketData:
    """Container for all market data for a currency pair."""
    ccy_pair: str
    spot: float
    forward_points: Dict[str, float] = field(default_factory=dict)
    vol_smiles: Dict[str, VolSmileData] = field(default_factory=dict)
    usd_rates: Dict[str, float] = field(default_factory=dict)
    fetch_date: date = field(default_factory=date.today)


class MarketDataFetcher:
    """
    Fetches FX market data from Bloomberg.

    Usage:
        connection = BloombergConnection.get_instance()
        if connection.connect():
            fetcher = MarketDataFetcher(connection)
            data = fetcher.fetch_all("EURUSD", ["1M", "3M", "6M", "1Y"])
    """

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
                                        # Field might be string or other type
                                        try:
                                            results[ticker][field_name] = field_data.getElementValue(field_name)
                                        except Exception as e:
                                            logger.warning(f"Could not get {field_name} for {ticker}: {e}")

            if event.eventType() == blpapi.Event.RESPONSE:
                break

        return results

    def fetch_spot(self, ccy_pair: str) -> float:
        """
        Fetch spot rate for a currency pair.

        Args:
            ccy_pair: Currency pair (e.g., "EURUSD")

        Returns:
            Spot rate
        """
        ticker = TickerBuilder.spot_ticker(ccy_pair)
        results = self._request_data([ticker], ["PX_LAST"])

        if ticker not in results or "PX_LAST" not in results[ticker]:
            raise DataFetchError(f"Failed to fetch spot for {ccy_pair}")

        return results[ticker]["PX_LAST"]

    def fetch_forward_points(self, ccy_pair: str, tenors: List[str]) -> Dict[str, float]:
        """
        Fetch forward points for all tenors.

        Args:
            ccy_pair: Currency pair
            tenors: List of tenors

        Returns:
            Dictionary mapping tenor -> forward points
        """
        tickers = [TickerBuilder.forward_points_ticker(ccy_pair, tenor) for tenor in tenors]
        results = self._request_data(tickers, ["PX_LAST"])

        forward_points = {}
        for tenor, ticker in zip(tenors, tickers):
            if ticker in results and "PX_LAST" in results[ticker]:
                forward_points[tenor] = results[ticker]["PX_LAST"]
            else:
                logger.warning(f"Missing forward points for {ccy_pair} {tenor}")

        return forward_points

    def fetch_vol_surface(self, ccy_pair: str, tenors: List[str]) -> Dict[str, VolSmileData]:
        """
        Fetch volatility surface (ATM, RR, BF) for all tenors.

        Args:
            ccy_pair: Currency pair
            tenors: List of tenors

        Returns:
            Dictionary mapping tenor -> VolSmileData
        """
        # Build all vol tickers
        all_tickers = []
        ticker_map = {}  # Map ticker -> (tenor, vol_type)

        for tenor in tenors:
            vol_tickers = TickerBuilder.get_all_vol_tickers(ccy_pair, tenor)
            for vol_type, ticker in vol_tickers.items():
                all_tickers.append(ticker)
                ticker_map[ticker] = (tenor, vol_type)

        # Fetch all at once
        results = self._request_data(all_tickers, ["PX_LAST"])

        # Parse results into VolSmileData
        raw_data: Dict[str, Dict[str, float]] = {tenor: {} for tenor in tenors}

        for ticker, (tenor, vol_type) in ticker_map.items():
            if ticker in results and "PX_LAST" in results[ticker]:
                raw_data[tenor][vol_type] = results[ticker]["PX_LAST"]

        # Create VolSmileData objects
        vol_smiles = {}
        for tenor in tenors:
            data = raw_data[tenor]
            if all(key in data for key in ["ATM", "RR25", "BF25", "RR10", "BF10"]):
                vol_smiles[tenor] = VolSmileData(
                    tenor=tenor,
                    atm=data["ATM"] / 100.0,  # Convert from percentage
                    rr25=data["RR25"] / 100.0,
                    bf25=data["BF25"] / 100.0,
                    rr10=data["RR10"] / 100.0,
                    bf10=data["BF10"] / 100.0,
                )
            else:
                logger.warning(f"Incomplete vol data for {ccy_pair} {tenor}: {data.keys()}")

        return vol_smiles

    def fetch_usd_rates(self, tenors: List[str], curve_prefix: str = "SOFR") -> Dict[str, float]:
        """
        Fetch USD interest rates for all tenors.

        Args:
            tenors: List of tenors
            curve_prefix: Curve identifier (e.g., "SOFR")

        Returns:
            Dictionary mapping tenor -> rate
        """
        tickers = [TickerBuilder.usd_rate_ticker(curve_prefix, tenor) for tenor in tenors]
        results = self._request_data(tickers, ["PX_LAST"])

        rates = {}
        for tenor, ticker in zip(tenors, tickers):
            if ticker in results and "PX_LAST" in results[ticker]:
                rates[tenor] = results[ticker]["PX_LAST"] / 100.0  # Convert from percentage
            else:
                logger.warning(f"Missing USD rate for {tenor}")

        return rates

    def fetch_all(
        self,
        ccy_pair: str,
        tenors: List[str],
        usd_curve_prefix: str = "SOFR"
    ) -> MarketData:
        """
        Fetch all market data needed for pricing.

        Args:
            ccy_pair: Currency pair
            tenors: List of tenors
            usd_curve_prefix: USD curve identifier

        Returns:
            MarketData object with all data
        """
        spot = self.fetch_spot(ccy_pair)
        forward_points = self.fetch_forward_points(ccy_pair, tenors)
        vol_smiles = self.fetch_vol_surface(ccy_pair, tenors)
        usd_rates = self.fetch_usd_rates(tenors, usd_curve_prefix)

        return MarketData(
            ccy_pair=ccy_pair,
            spot=spot,
            forward_points=forward_points,
            vol_smiles=vol_smiles,
            usd_rates=usd_rates,
            fetch_date=date.today()
        )


class MockMarketDataFetcher:
    """
    Mock data fetcher for testing without Bloomberg connection.
    Returns synthetic market data for common currency pairs.
    """

    MOCK_DATA = {
        "EURUSD": {
            "spot": 1.0850,
            "forward_points": {
                "1W": 2.5, "2W": 5.0, "1M": 12.0, "2M": 25.0, "3M": 38.0,
                "6M": 78.0, "9M": 120.0, "1Y": 165.0, "18M": 250.0, "2Y": 340.0
            },
            "atm_vols": {
                "1W": 8.5, "2W": 8.3, "1M": 8.0, "2M": 7.8, "3M": 7.6,
                "6M": 7.5, "9M": 7.4, "1Y": 7.3, "18M": 7.2, "2Y": 7.1
            },
            "rr25": {
                "1W": -0.3, "2W": -0.35, "1M": -0.4, "2M": -0.45, "3M": -0.5,
                "6M": -0.6, "9M": -0.7, "1Y": -0.8, "18M": -0.9, "2Y": -1.0
            },
            "bf25": {
                "1W": 0.15, "2W": 0.18, "1M": 0.2, "2M": 0.22, "3M": 0.25,
                "6M": 0.3, "9M": 0.35, "1Y": 0.4, "18M": 0.45, "2Y": 0.5
            },
            "rr10": {
                "1W": -0.6, "2W": -0.7, "1M": -0.8, "2M": -0.9, "3M": -1.0,
                "6M": -1.2, "9M": -1.4, "1Y": -1.6, "18M": -1.8, "2Y": -2.0
            },
            "bf10": {
                "1W": 0.4, "2W": 0.45, "1M": 0.5, "2M": 0.55, "3M": 0.6,
                "6M": 0.7, "9M": 0.8, "1Y": 0.9, "18M": 1.0, "2Y": 1.1
            },
        },
        "USD_RATES": {
            "1W": 5.30, "2W": 5.31, "1M": 5.32, "2M": 5.33, "3M": 5.34,
            "6M": 5.20, "9M": 5.05, "1Y": 4.90, "18M": 4.60, "2Y": 4.40
        }
    }

    def fetch_all(
        self,
        ccy_pair: str,
        tenors: List[str],
        usd_curve_prefix: str = "SOFR"
    ) -> MarketData:
        """Fetch mock market data."""
        ccy_pair = ccy_pair.upper().replace("/", "")

        if ccy_pair not in self.MOCK_DATA:
            # Use EURUSD as template with adjusted spot
            data = self.MOCK_DATA["EURUSD"].copy()
            if ccy_pair == "GBPUSD":
                data["spot"] = 1.2650
            elif ccy_pair == "USDJPY":
                data["spot"] = 149.50
            elif ccy_pair == "AUDUSD":
                data["spot"] = 0.6550
            elif ccy_pair == "USDCAD":
                data["spot"] = 1.3550
            elif ccy_pair == "USDCHF":
                data["spot"] = 0.8850
            else:
                data["spot"] = 1.0000
        else:
            data = self.MOCK_DATA[ccy_pair]

        # Build forward points
        forward_points = {t: data["forward_points"].get(t, 0.0) for t in tenors}

        # Build vol smiles
        vol_smiles = {}
        for tenor in tenors:
            if tenor in data["atm_vols"]:
                vol_smiles[tenor] = VolSmileData(
                    tenor=tenor,
                    atm=data["atm_vols"][tenor] / 100.0,
                    rr25=data["rr25"].get(tenor, 0.0) / 100.0,
                    bf25=data["bf25"].get(tenor, 0.0) / 100.0,
                    rr10=data["rr10"].get(tenor, 0.0) / 100.0,
                    bf10=data["bf10"].get(tenor, 0.0) / 100.0,
                )

        # USD rates
        usd_rates = {t: self.MOCK_DATA["USD_RATES"].get(t, 5.0) / 100.0 for t in tenors}

        return MarketData(
            ccy_pair=ccy_pair,
            spot=data["spot"],
            forward_points=forward_points,
            vol_smiles=vol_smiles,
            usd_rates=usd_rates,
            fetch_date=date.today()
        )
