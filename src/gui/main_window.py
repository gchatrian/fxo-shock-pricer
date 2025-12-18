"""
Main window for FX Option Pricer.
"""

import logging
from datetime import date
from typing import Optional, Dict

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QFrame, QMessageBox,
    QStatusBar, QGroupBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer

from .styles import get_stylesheet, COLORS
from .widgets import (
    InputRow, ResultRow, TenorDateEdit, NumericInput,
    ReadOnlyField, DropdownField, SectionHeader
)
from ..config.config_parser import Config, load_config
from ..bloomberg.connection import BloombergConnection, BloombergConnectionError
from ..bloomberg.data_fetcher import MarketDataFetcher, MockMarketDataFetcher, MarketData
from ..models.garman_kohlhagen import GarmanKohlhagen, OptionParams, Direction
from ..calendars.fx_conventions import FXCalendarFactory
from ..volatility.surface import VolSurface, VolSmile
from ..rates.curves import RateCurve, FXRates, ImpliedDepoCalculator
from ..utils.date_utils import is_tenor, year_fraction, tenor_to_years

logger = logging.getLogger(__name__)


class FXOptionPricer(QMainWindow):
    """Main application window for FX Option Pricer."""

    def __init__(self):
        super().__init__()

        self._config: Optional[Config] = None
        self._market_data: Optional[MarketData] = None
        self._vol_surface: Optional[VolSurface] = None
        self._usd_curve: Optional[RateCurve] = None
        self._bbg_connected: bool = False

        # Initialize
        self._load_config()
        self._setup_ui()
        self._apply_style()
        self._connect_signals()
        self._set_defaults()

        # Try to connect to Bloomberg
        QTimer.singleShot(100, self._try_connect_bloomberg)

    def _load_config(self) -> None:
        """Load configuration from file."""
        try:
            self._config = load_config()
        except FileNotFoundError as e:
            logger.warning(f"Config file not found: {e}")
            self._config = Config()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self.setWindowTitle("FX Option Pricer")
        self.setMinimumSize(420, 600)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(2)

        # Create all sections
        self._create_header_section(main_layout)
        self._create_input_section(main_layout)
        self._create_market_data_section(main_layout)
        self._create_greeks_section(main_layout)
        self._create_results_section(main_layout)

        # Status bar
        self.statusBar().showMessage("Ready")

    def _create_header_section(self, parent_layout: QVBoxLayout) -> None:
        """Create the header section with description and date."""
        grid = QGridLayout()
        grid.setSpacing(2)

        # TS Description
        grid.addWidget(QLabel("TS Description"), 0, 0)
        self.ts_description = QLineEdit()
        self.ts_description.setReadOnly(True)
        grid.addWidget(self.ts_description, 0, 1, 1, 3)

        # Price Date
        grid.addWidget(QLabel("Price Date"), 1, 0)
        self.price_date = QLineEdit()
        self.price_date.setText(date.today().strftime("%m/%d/%y"))
        self.price_date.setFixedWidth(80)
        grid.addWidget(self.price_date, 1, 1)

        # Time
        self.price_time = QLineEdit()
        self.price_time.setFixedWidth(60)
        self.price_time.setReadOnly(True)
        grid.addWidget(self.price_time, 1, 2)

        # Asset
        grid.addWidget(QLabel("Asset"), 2, 0)
        self.asset_combo = QComboBox()
        if self._config:
            self.asset_combo.addItems(self._config.currency_pairs)
        grid.addWidget(self.asset_combo, 2, 1, 1, 2)

        parent_layout.addLayout(grid)

    def _create_input_section(self, parent_layout: QVBoxLayout) -> None:
        """Create the main input section."""
        grid = QGridLayout()
        grid.setSpacing(2)

        row = 0

        # Spot
        grid.addWidget(QLabel("Spot"), row, 0)
        self.spot_source = QComboBox()
        self.spot_source.addItems(["Mid", "Bid", "Ask"])
        self.spot_source.setFixedWidth(50)
        grid.addWidget(self.spot_source, row, 1)
        self.spot_input = NumericInput(decimals=5)
        grid.addWidget(self.spot_input, row, 2, 1, 2)
        row += 1

        # Style
        grid.addWidget(QLabel("Style"), row, 0)
        self.style_combo = QComboBox()
        self.style_combo.addItems(["European", "American"])
        self.style_combo.setFixedWidth(80)
        grid.addWidget(self.style_combo, row, 1)
        self.style_type = QComboBox()
        self.style_type.addItems(["Vanilla", "Barrier"])
        grid.addWidget(self.style_type, row, 2)
        row += 1

        # Direction
        grid.addWidget(QLabel("Direction"), row, 0)
        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["Client buys", "Client sells"])
        grid.addWidget(self.direction_combo, row, 1)
        self.settlement_combo = QComboBox()
        self.settlement_combo.addItems(["Physical", "Cash"])
        grid.addWidget(self.settlement_combo, row, 2)
        row += 1

        # Call/Put
        grid.addWidget(QLabel("Call/Put"), row, 0)
        self.base_ccy_label = QLabel("EUR")
        self.base_ccy_label.setFixedWidth(40)
        grid.addWidget(self.base_ccy_label, row, 1)
        self.call_put_combo = QComboBox()
        self.call_put_combo.addItems(["Call", "Put"])
        grid.addWidget(self.call_put_combo, row, 2)
        row += 1

        # Expiry
        grid.addWidget(QLabel("Expiry"), row, 0)
        self.expiry_input = QLineEdit()
        self.expiry_input.setPlaceholderText("1Y or date")
        grid.addWidget(self.expiry_input, row, 1)
        self.expiry_date_display = QLineEdit()
        self.expiry_date_display.setReadOnly(True)
        grid.addWidget(self.expiry_date_display, row, 2)
        row += 1

        # Delivery
        grid.addWidget(QLabel("Delivery"), row, 0)
        self.delivery_time = QLineEdit()
        self.delivery_time.setReadOnly(True)
        self.delivery_time.setFixedWidth(60)
        grid.addWidget(self.delivery_time, row, 1)
        self.delivery_date_display = QLineEdit()
        self.delivery_date_display.setReadOnly(True)
        grid.addWidget(self.delivery_date_display, row, 2)
        row += 1

        # Strike
        grid.addWidget(QLabel("Strike"), row, 0)
        self.strike_input = NumericInput(decimals=5)
        grid.addWidget(self.strike_input, row, 1, 1, 2)
        self.strike_label = QLabel("ATMF")
        self.strike_label.setFixedWidth(50)
        grid.addWidget(self.strike_label, row, 3)
        row += 1

        # Notional
        grid.addWidget(QLabel("Notional"), row, 0)
        self.notional_ccy = QComboBox()
        self.notional_ccy.addItems(["EUR", "USD"])
        self.notional_ccy.setFixedWidth(50)
        grid.addWidget(self.notional_ccy, row, 1)
        self.notional_input = NumericInput(decimals=2)
        self.notional_input.setText("1,000,000.00")
        grid.addWidget(self.notional_input, row, 2)
        row += 1

        # Model
        grid.addWidget(QLabel("Model"), row, 0)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["Black-Scholes"])
        grid.addWidget(self.model_combo, row, 1, 1, 2)

        parent_layout.addLayout(grid)

    def _create_market_data_section(self, parent_layout: QVBoxLayout) -> None:
        """Create the market data section."""
        # Section header
        header = SectionHeader("More Market Data")
        parent_layout.addWidget(header)

        grid = QGridLayout()
        grid.setSpacing(2)

        row = 0

        # Vol
        grid.addWidget(QLabel("Vol"), row, 0)
        self.vol_source = QComboBox()
        self.vol_source.addItems(["BGN", "Mid", "Bid", "Ask"])
        self.vol_source.setFixedWidth(50)
        grid.addWidget(self.vol_source, row, 1)
        self.vol_display = QLineEdit()
        self.vol_display.setReadOnly(True)
        grid.addWidget(self.vol_display, row, 2)
        row += 1

        # Vol Spread
        grid.addWidget(QLabel("Vol Spread"), row, 0)
        self.vol_spread = NumericInput(decimals=3)
        self.vol_spread.setText("0.000")
        grid.addWidget(self.vol_spread, row, 2)
        row += 1

        # Points
        grid.addWidget(QLabel("Points"), row, 0)
        self.points_source = QComboBox()
        self.points_source.addItems(["BGN", "Mid"])
        self.points_source.setFixedWidth(50)
        grid.addWidget(self.points_source, row, 1)
        self.points_display = QLineEdit()
        self.points_display.setReadOnly(True)
        grid.addWidget(self.points_display, row, 2)
        row += 1

        # Forward
        grid.addWidget(QLabel("Forward"), row, 0)
        self.forward_source = QComboBox()
        self.forward_source.addItems(["Mid", "Bid", "Ask"])
        self.forward_source.setFixedWidth(50)
        grid.addWidget(self.forward_source, row, 1)
        self.forward_display = QLineEdit()
        self.forward_display.setReadOnly(True)
        grid.addWidget(self.forward_display, row, 2)
        row += 1

        # EUR Depo (foreign rate)
        self.foreign_depo_label = QLabel("EUR Depo")
        grid.addWidget(self.foreign_depo_label, row, 0)
        self.foreign_depo_source = QComboBox()
        self.foreign_depo_source.addItems(["Implied", "Mid"])
        self.foreign_depo_source.setFixedWidth(60)
        grid.addWidget(self.foreign_depo_source, row, 1)
        self.foreign_depo_display = QLineEdit()
        self.foreign_depo_display.setReadOnly(True)
        grid.addWidget(self.foreign_depo_display, row, 2)
        row += 1

        # USD Depo (domestic rate)
        grid.addWidget(QLabel("USD Depo"), row, 0)
        self.domestic_depo_source = QComboBox()
        self.domestic_depo_source.addItems(["USD SOFR", "USD FF"])
        self.domestic_depo_source.setFixedWidth(70)
        grid.addWidget(self.domestic_depo_source, row, 1)
        self.domestic_depo_display = QLineEdit()
        self.domestic_depo_display.setReadOnly(True)
        grid.addWidget(self.domestic_depo_display, row, 2)

        parent_layout.addLayout(grid)

    def _create_greeks_section(self, parent_layout: QVBoxLayout) -> None:
        """Create the Greeks section."""
        header = SectionHeader("Greeks")
        parent_layout.addWidget(header)

        grid = QGridLayout()
        grid.setSpacing(2)

        # Gamma
        grid.addWidget(QLabel("Gamma"), 0, 0)
        self.gamma_ccy = QComboBox()
        self.gamma_ccy.addItems(["EUR", "USD"])
        self.gamma_ccy.setFixedWidth(50)
        grid.addWidget(self.gamma_ccy, 0, 1)
        self.gamma_display = QLineEdit()
        self.gamma_display.setReadOnly(True)
        grid.addWidget(self.gamma_display, 0, 2)

        # Vega
        grid.addWidget(QLabel("Vega"), 1, 0)
        self.vega_display = QLineEdit()
        self.vega_display.setReadOnly(True)
        grid.addWidget(self.vega_display, 1, 2)

        parent_layout.addLayout(grid)

    def _create_results_section(self, parent_layout: QVBoxLayout) -> None:
        """Create the results section."""
        header = SectionHeader("Results")
        parent_layout.addWidget(header)

        grid = QGridLayout()
        grid.setSpacing(2)

        row = 0

        # Price
        grid.addWidget(QLabel("Price"), row, 0)
        self.price_format = QComboBox()
        self.price_format.addItems(["% EUR", "% USD", "Pips"])
        self.price_format.setFixedWidth(60)
        grid.addWidget(self.price_format, row, 1)
        self.price_display = QLineEdit()
        self.price_display.setReadOnly(True)
        grid.addWidget(self.price_display, row, 2)
        row += 1

        # Premium
        grid.addWidget(QLabel("Premium"), row, 0)
        self.premium_ccy = QComboBox()
        self.premium_ccy.addItems(["EUR", "USD"])
        self.premium_ccy.setFixedWidth(50)
        grid.addWidget(self.premium_ccy, row, 1)
        self.premium_display = QLineEdit()
        self.premium_display.setReadOnly(True)
        grid.addWidget(self.premium_display, row, 2)
        row += 1

        # Prem Date
        grid.addWidget(QLabel("Prem Date"), row, 0)
        self.prem_date_display = QLineEdit()
        self.prem_date_display.setReadOnly(True)
        grid.addWidget(self.prem_date_display, row, 2)
        row += 1

        # Delta
        grid.addWidget(QLabel("Delta"), row, 0)
        self.delta_type = QComboBox()
        self.delta_type.addItems(["Spot", "Fwd"])
        self.delta_type.setFixedWidth(50)
        grid.addWidget(self.delta_type, row, 1)
        self.delta_display = QLineEdit()
        self.delta_display.setReadOnly(True)
        grid.addWidget(self.delta_display, row, 2)
        row += 1

        # Hedge
        grid.addWidget(QLabel("Hedge"), row, 0)
        self.hedge_display = QLineEdit()
        self.hedge_display.setReadOnly(True)
        grid.addWidget(self.hedge_display, row, 2)

        parent_layout.addLayout(grid)

        # Add stretch at the end
        parent_layout.addStretch()

        # Calculate button
        self.calculate_btn = QPushButton("Calculate")
        self.calculate_btn.clicked.connect(self._on_calculate)
        parent_layout.addWidget(self.calculate_btn)

        # Refresh data button
        self.refresh_btn = QPushButton("Refresh Market Data")
        self.refresh_btn.clicked.connect(self._on_refresh_data)
        parent_layout.addWidget(self.refresh_btn)

    def _apply_style(self) -> None:
        """Apply the dark theme stylesheet."""
        self.setStyleSheet(get_stylesheet())

    def _connect_signals(self) -> None:
        """Connect widget signals to slots."""
        # Asset change
        self.asset_combo.currentTextChanged.connect(self._on_asset_changed)

        # Expiry change
        self.expiry_input.textChanged.connect(self._on_expiry_changed)

        # Auto-calculate on key changes
        self.spot_input.valueChanged.connect(self._on_input_changed)
        self.strike_input.valueChanged.connect(self._on_input_changed)
        self.call_put_combo.currentTextChanged.connect(self._on_input_changed)
        self.notional_input.valueChanged.connect(self._on_input_changed)

    def _set_defaults(self) -> None:
        """Set default values from config."""
        if not self._config:
            return

        # Set default asset
        idx = self.asset_combo.findText(self._config.default_asset)
        if idx >= 0:
            self.asset_combo.setCurrentIndex(idx)

        # Set default notional
        self.notional_input.set_value(self._config.default_notional)

        # Set default call/put
        idx = self.call_put_combo.findText(self._config.default_call_put)
        if idx >= 0:
            self.call_put_combo.setCurrentIndex(idx)

        # Set default direction
        idx = self.direction_combo.findText(self._config.default_direction)
        if idx >= 0:
            self.direction_combo.setCurrentIndex(idx)

        # Trigger asset changed to update labels
        self._on_asset_changed(self.asset_combo.currentText())

    def _try_connect_bloomberg(self) -> None:
        """Try to connect to Bloomberg."""
        try:
            conn = BloombergConnection.get_instance()
            if conn.is_available():
                if conn.connect():
                    self._bbg_connected = True
                    self.statusBar().showMessage("Bloomberg connected")
                    self._load_market_data()
                else:
                    self._bbg_connected = False
                    self.statusBar().showMessage("Bloomberg connection failed - using mock data")
                    self._load_mock_data()
            else:
                self._bbg_connected = False
                self.statusBar().showMessage("Bloomberg API not available - using mock data")
                self._load_mock_data()
        except Exception as e:
            logger.error(f"Bloomberg connection error: {e}")
            self._bbg_connected = False
            self.statusBar().showMessage(f"Error: {e} - using mock data")
            self._load_mock_data()

    def _load_market_data(self) -> None:
        """Load market data from Bloomberg."""
        if not self._config:
            return

        ccy_pair = self.asset_combo.currentText()
        tenors = self._config.tenors

        try:
            conn = BloombergConnection.get_instance()
            fetcher = MarketDataFetcher(conn)
            self._market_data = fetcher.fetch_all(
                ccy_pair, tenors, self._config.usd_curve_ticker_prefix
            )
            self._update_market_data_display()
            self.statusBar().showMessage(f"Market data loaded for {ccy_pair}")
        except Exception as e:
            logger.error(f"Failed to load market data: {e}")
            self.statusBar().showMessage(f"Data load failed: {e}")
            self._load_mock_data()

    def _load_mock_data(self) -> None:
        """Load mock market data for testing."""
        if not self._config:
            return

        ccy_pair = self.asset_combo.currentText()
        tenors = self._config.tenors

        fetcher = MockMarketDataFetcher()
        self._market_data = fetcher.fetch_all(ccy_pair, tenors)
        self._update_market_data_display()

    def _update_market_data_display(self) -> None:
        """Update the market data display fields."""
        if not self._market_data:
            return

        # Update spot
        self.spot_input.set_value(self._market_data.spot)

        # Build USD curve
        self._usd_curve = RateCurve(currency="USD")
        self._usd_curve.set_rates(self._market_data.usd_rates)

        # Update description
        ccy_pair = self._market_data.ccy_pair
        self.ts_description.setText(f"{ccy_pair[:3]}/{ccy_pair[3:]} Vanilla")

    def _on_asset_changed(self, ccy_pair: str) -> None:
        """Handle currency pair change."""
        if not ccy_pair:
            return

        ccy_pair = ccy_pair.replace("/", "")
        base_ccy = ccy_pair[:3]
        quote_ccy = ccy_pair[3:]

        # Update labels
        self.base_ccy_label.setText(base_ccy)
        self.foreign_depo_label.setText(f"{base_ccy} Depo")

        # Update notional currency options
        self.notional_ccy.clear()
        self.notional_ccy.addItems([base_ccy, quote_ccy])

        # Update gamma currency options
        self.gamma_ccy.clear()
        self.gamma_ccy.addItems([base_ccy, quote_ccy])

        # Update premium currency options
        self.premium_ccy.clear()
        self.premium_ccy.addItems([base_ccy, quote_ccy])

        # Update price format options
        self.price_format.clear()
        self.price_format.addItems([f"% {base_ccy}", f"% {quote_ccy}", "Pips"])

        # Reload market data
        if self._bbg_connected:
            self._load_market_data()
        else:
            self._load_mock_data()

    def _on_expiry_changed(self, text: str) -> None:
        """Handle expiry input change."""
        text = text.strip()
        if not text:
            return

        ccy_pair = self.asset_combo.currentText()
        today = date.today()

        try:
            if is_tenor(text):
                # Calculate expiry from tenor
                expiry = FXCalendarFactory.get_expiry_from_tenor(ccy_pair, today, text)
                delivery = FXCalendarFactory.get_delivery_from_expiry(ccy_pair, expiry)

                self.expiry_date_display.setText(expiry.strftime("%m/%d/%y"))
                self.delivery_date_display.setText(delivery.strftime("%m/%d/%y"))
            else:
                # Try to parse as date
                from ..utils.date_utils import parse_date_or_tenor
                result = parse_date_or_tenor(text)
                if isinstance(result, date):
                    expiry = result
                    delivery = FXCalendarFactory.get_delivery_from_expiry(ccy_pair, expiry)
                    self.expiry_date_display.setText(expiry.strftime("%m/%d/%y"))
                    self.delivery_date_display.setText(delivery.strftime("%m/%d/%y"))

        except Exception as e:
            logger.warning(f"Failed to parse expiry: {e}")
            self.expiry_date_display.setText("")
            self.delivery_date_display.setText("")

    def _on_input_changed(self) -> None:
        """Handle input field changes - trigger recalculation."""
        # Could auto-calculate here, but let's wait for explicit calculate button
        pass

    def _on_calculate(self) -> None:
        """Perform the option pricing calculation."""
        try:
            self._calculate()
        except Exception as e:
            logger.error(f"Calculation error: {e}")
            QMessageBox.warning(self, "Calculation Error", str(e))

    def _calculate(self) -> None:
        """Execute the pricing calculation."""
        if not self._market_data:
            raise ValueError("No market data available")

        # Get inputs
        ccy_pair = self.asset_combo.currentText().replace("/", "")
        spot = self.spot_input.get_value()
        strike = self.strike_input.get_value()
        notional = self.notional_input.get_value()
        is_call = self.call_put_combo.currentText() == "Call"

        # Get expiry date
        expiry_text = self.expiry_date_display.text()
        if not expiry_text:
            raise ValueError("Please enter an expiry date or tenor")

        from datetime import datetime
        expiry = datetime.strptime(expiry_text, "%m/%d/%y").date()
        today = date.today()
        time_to_expiry = year_fraction(today, expiry)

        if time_to_expiry <= 0:
            raise ValueError("Expiry must be in the future")

        # Get interpolated rates
        usd_rate = self._usd_curve.get_rate(time_to_expiry) if self._usd_curve else 0.05

        # Get forward points for interpolation
        fwd_points = self._get_interpolated_forward_points(time_to_expiry)

        # Calculate FX rates
        fx_rates = FXRates.calculate(
            ccy_pair, spot, fwd_points, usd_rate, time_to_expiry
        )

        # Get interpolated volatility
        vol = self._get_interpolated_vol(strike, time_to_expiry, spot, fx_rates.domestic_rate, fx_rates.foreign_rate)

        # If strike is 0 or not set, use ATMF
        if strike <= 0:
            strike = fx_rates.forward_rate
            self.strike_input.set_value(strike)
            self.strike_label.setText("ATMF")
        else:
            self.strike_label.setText("")

        # Build option parameters
        notional_ccy = self.notional_ccy.currentText()
        base_ccy = ccy_pair[:3]

        params = OptionParams(
            spot=spot,
            strike=strike,
            domestic_rate=fx_rates.domestic_rate,
            foreign_rate=fx_rates.foreign_rate,
            volatility=vol,
            time_to_expiry=time_to_expiry,
            is_call=is_call,
            notional=notional,
            notional_currency="FOR" if notional_ccy == base_ccy else "DOM"
        )

        # Calculate
        result = GarmanKohlhagen.calculate_all(params)

        # Get direction
        direction_text = self.direction_combo.currentText()
        direction = Direction.CLIENT_BUYS if "buys" in direction_text.lower() else Direction.CLIENT_SELLS

        # Calculate hedge
        hedge = GarmanKohlhagen.calculate_delta_hedge(params, direction)

        # Update displays
        self._update_results_display(result, fx_rates, vol, fwd_points, hedge, params)

    def _get_interpolated_forward_points(self, time_to_expiry: float) -> float:
        """Get interpolated forward points for the given time."""
        if not self._market_data or not self._market_data.forward_points:
            return 0.0

        from ..models.interpolation import linear_interpolate

        tenors = list(self._market_data.forward_points.keys())
        points = list(self._market_data.forward_points.values())
        times = [tenor_to_years(t) for t in tenors]

        # Sort by time
        sorted_data = sorted(zip(times, points))
        times = [d[0] for d in sorted_data]
        points = [d[1] for d in sorted_data]

        return linear_interpolate(time_to_expiry, times, points)

    def _get_interpolated_vol(
        self,
        strike: float,
        time_to_expiry: float,
        spot: float,
        r_dom: float,
        r_for: float
    ) -> float:
        """Get interpolated volatility for strike and expiry."""
        if not self._market_data or not self._market_data.vol_smiles:
            return 0.08  # Default 8%

        # Build vol surface if not already built
        if self._vol_surface is None:
            from ..volatility.surface import VolSurface, VolSmile

            self._vol_surface = VolSurface()
            today = date.today()

            for tenor, smile_data in self._market_data.vol_smiles.items():
                t = tenor_to_years(tenor)
                from datetime import timedelta
                expiry_date = today + timedelta(days=int(t * 365))

                smile = VolSmile(
                    tenor=tenor,
                    expiry_date=expiry_date,
                    time_to_expiry=t,
                    vol_10p=smile_data.vol_10p,
                    vol_25p=smile_data.vol_25p,
                    vol_atm=smile_data.atm,
                    vol_25c=smile_data.vol_25c,
                    vol_10c=smile_data.vol_10c,
                )
                smile.calculate_strikes(spot, r_dom, r_for)
                self._vol_surface.add_smile(smile)

        # If strike is 0, use ATM
        if strike <= 0:
            return self._vol_surface.get_atm_vol(time_to_expiry)

        return self._vol_surface.get_vol(strike, time_to_expiry, spot, r_dom, r_for)

    def _update_results_display(
        self,
        result,
        fx_rates: FXRates,
        vol: float,
        fwd_points: float,
        hedge: float,
        params: OptionParams
    ) -> None:
        """Update the results display fields."""
        # Market data
        self.vol_display.setText(f"{vol * 100:.3f}%")
        self.points_display.setText(f"{fwd_points:.2f}")
        self.forward_display.setText(f"{fx_rates.forward_rate:.5f}")
        self.foreign_depo_display.setText(f"{fx_rates.foreign_rate * 100:.3f}%")
        self.domestic_depo_display.setText(f"{fx_rates.domestic_rate * 100:.3f}%")

        # Greeks
        gamma_value = result.greeks.gamma * params.notional
        self.gamma_display.setText(f"{gamma_value:,.2f}")
        vega_value = result.greeks.vega * params.notional
        self.vega_display.setText(f"{vega_value:,.2f}")

        # Results
        self.price_display.setText(f"{result.premium_pct:.4f}%")
        self.premium_display.setText(f"{result.premium:,.2f}")
        self.prem_date_display.setText(date.today().strftime("%m/%d/%y"))
        self.delta_display.setText(f"{result.greeks.delta * 100:.4f}%")
        self.hedge_display.setText(f"{hedge:,.2f}")

    def _on_refresh_data(self) -> None:
        """Refresh market data from Bloomberg."""
        self._vol_surface = None  # Reset cached surface
        if self._bbg_connected:
            self._load_market_data()
        else:
            self._load_mock_data()

    def closeEvent(self, event) -> None:
        """Handle window close."""
        # Disconnect Bloomberg if connected
        if self._bbg_connected:
            try:
                BloombergConnection.get_instance().disconnect()
            except Exception:
                pass
        event.accept()
