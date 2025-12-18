"""
Main window for FX Option Pricer.
"""

import logging
import math
from datetime import date, timedelta, datetime
from typing import Optional, Dict

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QFrame, QMessageBox,
    QStatusBar, QGroupBox, QSizePolicy, QDateEdit
)
from PyQt6.QtCore import Qt, QTimer, QDate

from .styles import get_stylesheet, COLORS
from .widgets import (
    InputRow, ResultRow, TenorDateEdit, NumericInput,
    ReadOnlyField, DropdownField, SectionHeader
)
from ..config.config_parser import Config, load_config
from ..bloomberg.connection import BloombergConnection, BloombergConnectionError
from ..bloomberg.data_fetcher import (
    MarketDataFetcher, MarketData, HistoricalDataFetcher,
    MarketDataDelta, ShockCalculator, ShockedMarketData
)
from ..models.garman_kohlhagen import GarmanKohlhagen, OptionParams, Direction
from ..calendars.fx_conventions import FXCalendarFactory
from ..volatility.surface import VolSurface, VolSmile
from ..rates.curves import RateCurve, FXRates, ForwardCurve
from ..utils.date_utils import is_tenor, year_fraction, tenor_to_years

logger = logging.getLogger(__name__)


class FXOptionPricer(QMainWindow):
    """Main application window for FX Option Pricer."""

    def __init__(self):
        super().__init__()

        self._config: Optional[Config] = None
        self._market_data: Optional[MarketData] = None
        self._vol_surface: Optional[VolSurface] = None
        self._fx_rates: Optional[FXRates] = None
        self._bbg_connected: bool = False
        
        # Shock analysis data
        self._shock_start_data: Optional[Dict] = None
        self._shock_end_data: Optional[Dict] = None
        self._market_delta: Optional[MarketDataDelta] = None
        self._shocked_market_data: Optional[ShockedMarketData] = None
        self._last_pricing_result = None
        self._last_pricing_params: Optional[OptionParams] = None

        # Initialize
        self._load_config()
        self._setup_ui()
        self._apply_style()
        self._connect_signals()
        self._set_defaults()

        # Try to connect to Bloomberg
        QTimer.singleShot(100, self._try_connect_bloomberg)

        # Try to connect to Bloomberg
        QTimer.singleShot(100, self._try_connect_bloomberg)

    def _load_config(self) -> None:
        """Load configuration from file."""
        try:
            self._config = load_config()
        except FileNotFoundError as e:
            logger.warning(f"Config file not found: {e}")
            self._config = Config()
            # Set default tenors and pairs
            self._config.tenors = ["1W", "2W", "1M", "2M", "3M", "6M", "9M", "1Y", "18M", "2Y"]
            self._config.currency_pairs = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "EURGBP", "AUDNZD"]

    def _setup_ui(self) -> None:
        """Set up the user interface with two columns."""
        self.setWindowTitle("FX Option Pricer")
        self.setMinimumSize(900, 700)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        # Main horizontal layout for two columns
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(10)

        # LEFT COLUMN - Pricer
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)

        self._create_header_section(left_layout)
        self._create_input_section(left_layout)
        self._create_market_data_section(left_layout)
        self._create_greeks_section(left_layout)
        self._create_results_section(left_layout)

        main_layout.addWidget(left_widget, stretch=1)

        # Vertical separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(separator)

        # RIGHT COLUMN - Shock Analysis
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)

        self._create_shock_params_section(right_layout)
        self._create_shock_deltas_section(right_layout)
        self._create_shocked_results_section(right_layout)

        main_layout.addWidget(right_widget, stretch=1)

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
        self.spot_source = QLabel("Mid")
        self.spot_source.setFixedWidth(50)
        grid.addWidget(self.spot_source, row, 1)
        self.spot_input = NumericInput(decimals=5)
        grid.addWidget(self.spot_input, row, 2, 1, 2)
        row += 1

        # Style
        grid.addWidget(QLabel("Style"), row, 0)
        self.style_label = QLabel("European")
        self.style_label.setFixedWidth(80)
        grid.addWidget(self.style_label, row, 1)
        self.style_type = QLabel("Vanilla")
        grid.addWidget(self.style_type, row, 2)
        row += 1

        # Direction
        grid.addWidget(QLabel("Direction"), row, 0)
        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["Client buys", "Client sells"])
        grid.addWidget(self.direction_combo, row, 1)
        self.settlement_label = QLabel("Physical")
        grid.addWidget(self.settlement_label, row, 2)
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
        self.notional_input = NumericInput(decimals=0)
        self.notional_input.setText("1,000,000")
        grid.addWidget(self.notional_input, row, 2)
        row += 1

        # Model
        grid.addWidget(QLabel("Model"), row, 0)
        self.model_label = QLabel("Black-Scholes")
        grid.addWidget(self.model_label, row, 1, 1, 2)

        parent_layout.addLayout(grid)

    def _create_market_data_section(self, parent_layout: QVBoxLayout) -> None:
        """Create the market data section."""
        header = SectionHeader("More Market Data")
        parent_layout.addWidget(header)

        grid = QGridLayout()
        grid.setSpacing(2)

        row = 0

        # Vol
        grid.addWidget(QLabel("Vol"), row, 0)
        self.vol_source = QLabel("BGN")
        self.vol_source.setFixedWidth(50)
        grid.addWidget(self.vol_source, row, 1)
        self.vol_display = QLineEdit()
        self.vol_display.setReadOnly(True)
        grid.addWidget(self.vol_display, row, 2)
        row += 1

        # Points
        grid.addWidget(QLabel("Points"), row, 0)
        self.points_source = QLabel("BGN")
        self.points_source.setFixedWidth(50)
        grid.addWidget(self.points_source, row, 1)
        self.points_display = QLineEdit()
        self.points_display.setReadOnly(True)
        grid.addWidget(self.points_display, row, 2)
        row += 1

        # Forward
        grid.addWidget(QLabel("Forward"), row, 0)
        self.forward_source = QLabel("Mid")
        self.forward_source.setFixedWidth(50)
        grid.addWidget(self.forward_source, row, 1)
        self.forward_display = QLineEdit()
        self.forward_display.setReadOnly(True)
        grid.addWidget(self.forward_display, row, 2)
        row += 1

        # Foreign Depo (base currency rate)
        self.foreign_depo_label = QLabel("EUR Depo")
        grid.addWidget(self.foreign_depo_label, row, 0)
        self.foreign_depo_source = QLabel("Implied")
        self.foreign_depo_source.setFixedWidth(60)
        grid.addWidget(self.foreign_depo_source, row, 1)
        self.foreign_depo_display = QLineEdit()
        self.foreign_depo_display.setReadOnly(True)
        grid.addWidget(self.foreign_depo_display, row, 2)
        row += 1

        # Domestic Depo (quote currency rate)
        self.domestic_depo_label = QLabel("USD Depo")
        grid.addWidget(self.domestic_depo_label, row, 0)
        self.domestic_depo_source = QLabel("Implied")
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
        self.gamma_ccy_label = QLabel("EUR")
        self.gamma_ccy_label.setFixedWidth(50)
        grid.addWidget(self.gamma_ccy_label, 0, 1)
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

    def _create_shock_params_section(self, parent_layout: QVBoxLayout) -> None:
        """Create the shock parameters section."""
        header = SectionHeader("SHOCK Params")
        parent_layout.addWidget(header)

        grid = QGridLayout()
        grid.setSpacing(2)

        # Start Date
        grid.addWidget(QLabel("Start Date"), 0, 0)
        self.shock_start_date = QDateEdit()
        self.shock_start_date.setCalendarPopup(True)
        self.shock_start_date.setDate(QDate.currentDate().addMonths(-1))
        self.shock_start_date.setDisplayFormat("MM/dd/yy")
        grid.addWidget(self.shock_start_date, 0, 1)

        # End Date
        grid.addWidget(QLabel("End Date"), 1, 0)
        self.shock_end_date = QDateEdit()
        self.shock_end_date.setCalendarPopup(True)
        self.shock_end_date.setDate(QDate.currentDate())
        self.shock_end_date.setDisplayFormat("MM/dd/yy")
        grid.addWidget(self.shock_end_date, 1, 1)

        parent_layout.addLayout(grid)

        # Load Historical Data button
        self.load_historical_btn = QPushButton("Load Historical Data")
        self.load_historical_btn.clicked.connect(self._on_load_historical)
        parent_layout.addWidget(self.load_historical_btn)

        # Apply Shock button
        self.apply_shock_btn = QPushButton("Apply Shock")
        self.apply_shock_btn.clicked.connect(self._on_apply_shock)
        self.apply_shock_btn.setEnabled(False)  # Disabled until historical data loaded
        parent_layout.addWidget(self.apply_shock_btn)

    def _create_shock_deltas_section(self, parent_layout: QVBoxLayout) -> None:
        """Create the section showing calculated deltas."""
        header = SectionHeader("Shock Deltas")
        parent_layout.addWidget(header)

        grid = QGridLayout()
        grid.setSpacing(2)

        row = 0

        # Time Decay
        grid.addWidget(QLabel("Time Decay"), row, 0)
        self.shock_time_decay = QLineEdit()
        self.shock_time_decay.setReadOnly(True)
        grid.addWidget(self.shock_time_decay, row, 1)
        row += 1

        # Spot Change
        grid.addWidget(QLabel("Spot Change"), row, 0)
        self.shock_spot_change = QLineEdit()
        self.shock_spot_change.setReadOnly(True)
        grid.addWidget(self.shock_spot_change, row, 1)
        row += 1

        # Vol Change
        grid.addWidget(QLabel("Vol Change"), row, 0)
        self.shock_vol_change = QLineEdit()
        self.shock_vol_change.setReadOnly(True)
        grid.addWidget(self.shock_vol_change, row, 1)
        row += 1

        # Rate Change
        grid.addWidget(QLabel("Rate Change"), row, 0)
        self.shock_rate_change = QLineEdit()
        self.shock_rate_change.setReadOnly(True)
        grid.addWidget(self.shock_rate_change, row, 1)
        row += 1

        # Status
        grid.addWidget(QLabel("Status"), row, 0)
        self.shock_status = QLineEdit()
        self.shock_status.setReadOnly(True)
        self.shock_status.setText("Not loaded")
        grid.addWidget(self.shock_status, row, 1)

        parent_layout.addLayout(grid)

    def _create_shocked_results_section(self, parent_layout: QVBoxLayout) -> None:
        """Create the shocked results section."""
        header = SectionHeader("Shocked Results")
        parent_layout.addWidget(header)

        grid = QGridLayout()
        grid.setSpacing(2)

        row = 0

        # Shocked Expiry
        grid.addWidget(QLabel("Shocked Expiry"), row, 0)
        self.shocked_expiry_display = QLineEdit()
        self.shocked_expiry_display.setReadOnly(True)
        grid.addWidget(self.shocked_expiry_display, row, 1)
        row += 1

        # Shocked Spot
        grid.addWidget(QLabel("Shocked Spot"), row, 0)
        self.shocked_spot_display = QLineEdit()
        self.shocked_spot_display.setReadOnly(True)
        grid.addWidget(self.shocked_spot_display, row, 1)
        row += 1

        # Shocked Vol
        grid.addWidget(QLabel("Shocked Vol"), row, 0)
        self.shocked_vol_display = QLineEdit()
        self.shocked_vol_display.setReadOnly(True)
        grid.addWidget(self.shocked_vol_display, row, 1)
        row += 1

        # Shocked Forward
        grid.addWidget(QLabel("Shocked Fwd"), row, 0)
        self.shocked_forward_display = QLineEdit()
        self.shocked_forward_display.setReadOnly(True)
        grid.addWidget(self.shocked_forward_display, row, 1)
        row += 1

        parent_layout.addLayout(grid)

        # Separator
        parent_layout.addWidget(QLabel(""))

        grid2 = QGridLayout()
        grid2.setSpacing(2)

        row = 0

        # Shocked Premium
        grid2.addWidget(QLabel("Shocked Premium"), row, 0)
        self.shocked_premium_display = QLineEdit()
        self.shocked_premium_display.setReadOnly(True)
        grid2.addWidget(self.shocked_premium_display, row, 1)
        row += 1

        # P&L
        grid2.addWidget(QLabel("P&L"), row, 0)
        self.shocked_pnl_display = QLineEdit()
        self.shocked_pnl_display.setReadOnly(True)
        grid2.addWidget(self.shocked_pnl_display, row, 1)
        row += 1

        # Shocked Delta
        grid2.addWidget(QLabel("Shocked Delta"), row, 0)
        self.shocked_delta_display = QLineEdit()
        self.shocked_delta_display.setReadOnly(True)
        grid2.addWidget(self.shocked_delta_display, row, 1)
        row += 1

        # Shocked Gamma
        grid2.addWidget(QLabel("Shocked Gamma"), row, 0)
        self.shocked_gamma_display = QLineEdit()
        self.shocked_gamma_display.setReadOnly(True)
        grid2.addWidget(self.shocked_gamma_display, row, 1)
        row += 1

        # Shocked Vega
        grid2.addWidget(QLabel("Shocked Vega"), row, 0)
        self.shocked_vega_display = QLineEdit()
        self.shocked_vega_display.setReadOnly(True)
        grid2.addWidget(self.shocked_vega_display, row, 1)

        parent_layout.addLayout(grid2)

        # Add stretch
        parent_layout.addStretch()

    def _apply_style(self) -> None:
        """Apply the dark theme stylesheet."""
        self.setStyleSheet(get_stylesheet())

    def _connect_signals(self) -> None:
        """Connect widget signals to slots."""
        self.asset_combo.currentTextChanged.connect(self._on_asset_changed)
        self.expiry_input.textChanged.connect(self._on_expiry_changed)
        self.spot_input.valueChanged.connect(self._on_input_changed)
        self.strike_input.valueChanged.connect(self._on_input_changed)
        self.call_put_combo.currentTextChanged.connect(self._on_input_changed)
        self.notional_input.valueChanged.connect(self._on_input_changed)
        # Recalculate when delta type or premium currency changes
        self.delta_type.currentTextChanged.connect(self._on_calculate)
        self.premium_ccy.currentTextChanged.connect(self._on_calculate)
        self.price_format.currentTextChanged.connect(self._on_calculate)

    def _set_defaults(self) -> None:
        """Set default values from config."""
        if not self._config:
            return

        idx = self.asset_combo.findText(self._config.default_asset)
        if idx >= 0:
            self.asset_combo.setCurrentIndex(idx)

        self.notional_input.set_value(self._config.default_notional, use_thousands_sep=True)

        idx = self.call_put_combo.findText(self._config.default_call_put)
        if idx >= 0:
            self.call_put_combo.setCurrentIndex(idx)

        idx = self.direction_combo.findText(self._config.default_direction)
        if idx >= 0:
            self.direction_combo.setCurrentIndex(idx)

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
                    self.statusBar().showMessage("Bloomberg connection failed")
            else:
                self._bbg_connected = False
                self.statusBar().showMessage("Bloomberg API not available")
        except Exception as e:
            logger.error(f"Bloomberg connection error: {e}")
            self._bbg_connected = False
            self.statusBar().showMessage(f"Error: {e}")

    def _load_market_data(self) -> None:
        """Load market data from Bloomberg."""
        if not self._config or not self._bbg_connected:
            return

        ccy_pair = self.asset_combo.currentText()
        tenors = self._config.tenors
        today = date.today()

        try:
            # Calculate days to maturity for each tenor
            days_to_maturity = {}
            for tenor in tenors:
                try:
                    expiry = FXCalendarFactory.get_expiry_from_tenor(ccy_pair, today, tenor)
                    days_to_maturity[tenor] = (expiry - today).days
                except Exception as e:
                    logger.warning(f"Could not calculate days for {tenor}: {e}")

            logger.info(f"=== LOADING MARKET DATA FOR {ccy_pair} ===")
            logger.info(f"Tenors: {tenors}")
            logger.info(f"Days to maturity: {days_to_maturity}")

            conn = BloombergConnection.get_instance()
            fetcher = MarketDataFetcher(conn)
            self._market_data = fetcher.fetch_all(ccy_pair, tenors, days_to_maturity)

            logger.info(f"=== MARKET DATA RECEIVED ===")
            logger.info(f"Spot: {self._market_data.spot}")
            logger.info(f"Forward points: {self._market_data.forward_points}")
            logger.info(f"Forward rates: {self._market_data.forward_rates}")
            logger.info(f"USD rates: {self._market_data.usd_rates}")
            logger.info(f"Domestic rates: {self._market_data.domestic_rates}")
            logger.info(f"Foreign rates: {self._market_data.foreign_rates}")

            # Build FX rates with cubic spline interpolation
            self._fx_rates = FXRates.from_market_data(self._market_data)

            logger.info(f"=== FX RATES BUILT ===")
            logger.info(f"Domestic curve rates: {self._fx_rates.domestic_curve.rates}")
            logger.info(f"Foreign curve rates: {self._fx_rates.foreign_curve.rates}")

            # Build vol surface
            self._build_vol_surface()

            self._update_market_data_display()
            self.statusBar().showMessage(f"Market data loaded for {ccy_pair}")

        except Exception as e:
            logger.error(f"Failed to load market data: {e}", exc_info=True)
            self.statusBar().showMessage(f"Data load failed: {e}")

    def _build_vol_surface(self) -> None:
        """Build volatility surface from market data."""
        if not self._market_data:
            return

        self._vol_surface = VolSurface()
        today = date.today()

        for tenor, smile_data in self._market_data.vol_smiles.items():
            days = self._market_data.days_to_maturity.get(tenor, 30)
            expiry_date = today + timedelta(days=days)
            t = days / 365.0

            smile = VolSmile(
                tenor=tenor,
                expiry_date=expiry_date,
                time_to_expiry=t,
                days_to_expiry=days,
                vol_10p=smile_data.vol_10p,
                vol_25p=smile_data.vol_25p,
                vol_atm=smile_data.atm,
                vol_25c=smile_data.vol_25c,
                vol_10c=smile_data.vol_10c,
            )

            # Calculate strikes using interpolated rates
            r_dom = self._fx_rates.get_domestic_rate(t) if self._fx_rates else 0.05
            r_for = self._fx_rates.get_foreign_rate(t) if self._fx_rates else 0.03
            smile.calculate_strikes(self._market_data.spot, r_dom, r_for)

            self._vol_surface.add_smile(smile)

    def _update_market_data_display(self) -> None:
        """Update the market data display fields."""
        if not self._market_data:
            return

        self.spot_input.set_value(self._market_data.spot)

        ccy_pair = self._market_data.ccy_pair
        self.ts_description.setText(f"{ccy_pair[:3]}/{ccy_pair[3:]} Vanilla")

    def _on_asset_changed(self, ccy_pair: str) -> None:
        """Handle currency pair change."""
        if not ccy_pair:
            return

        ccy_pair = ccy_pair.replace("/", "")
        base_ccy = ccy_pair[:3]
        quote_ccy = ccy_pair[3:]

        self.base_ccy_label.setText(base_ccy)
        self.foreign_depo_label.setText(f"{base_ccy} Depo")
        self.domestic_depo_label.setText(f"{quote_ccy} Depo")

        self.notional_ccy.clear()
        self.notional_ccy.addItems([base_ccy, quote_ccy])

        # Update gamma currency label (follows base currency)
        self.gamma_ccy_label.setText(base_ccy)

        self.premium_ccy.clear()
        self.premium_ccy.addItems([base_ccy, quote_ccy])

        self.price_format.clear()
        self.price_format.addItems([f"% {base_ccy}", f"% {quote_ccy}", "Pips"])

        # Reset surfaces
        self._vol_surface = None
        self._fx_rates = None

        if self._bbg_connected:
            self._load_market_data()

    def _on_expiry_changed(self, text: str) -> None:
        """Handle expiry input change."""
        text = text.strip()
        if not text:
            return

        ccy_pair = self.asset_combo.currentText()
        today = date.today()

        try:
            if is_tenor(text):
                expiry = FXCalendarFactory.get_expiry_from_tenor(ccy_pair, today, text)
                delivery = FXCalendarFactory.get_delivery_from_expiry(ccy_pair, expiry)

                self.expiry_date_display.setText(expiry.strftime("%m/%d/%y"))
                self.delivery_date_display.setText(delivery.strftime("%m/%d/%y"))
            else:
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
        """Handle input field changes."""
        pass

    def _on_calculate(self) -> None:
        """Perform the option pricing calculation."""
        # Silently return if data not ready (e.g., when signals fire during init)
        if not self._market_data:
            return
        if not self.expiry_date_display.text():
            return
            
        try:
            self._calculate()
        except Exception as e:
            logger.error(f"Calculation error: {e}")
            QMessageBox.warning(self, "Calculation Error", str(e))

    def _calculate(self) -> None:
        """Execute the pricing calculation."""
        if not self._market_data:
            raise ValueError("No market data available. Connect to Bloomberg first.")

        ccy_pair = self.asset_combo.currentText().replace("/", "")
        spot = self.spot_input.get_value()
        strike = self.strike_input.get_value()
        notional = self.notional_input.get_value()
        is_call = self.call_put_combo.currentText() == "Call"

        expiry_text = self.expiry_date_display.text()
        if not expiry_text:
            raise ValueError("Please enter an expiry date or tenor")

        from datetime import datetime
        expiry = datetime.strptime(expiry_text, "%m/%d/%y").date()
        today = date.today()
        time_to_expiry = year_fraction(today, expiry)

        if time_to_expiry <= 0:
            raise ValueError("Expiry must be in the future")

        # Get interpolated rates using cubic spline
        if self._fx_rates:
            r_dom = self._fx_rates.get_domestic_rate(time_to_expiry)
            r_for = self._fx_rates.get_foreign_rate(time_to_expiry)
            forward = self._fx_rates.get_forward(time_to_expiry)
        else:
            r_dom = 0.05
            r_for = 0.03
            forward = spot * (1 + (r_dom - r_for) * time_to_expiry)

        logger.info(f"=== CALCULATION ===")
        logger.info(f"Spot: {spot}, Strike: {strike}, Time: {time_to_expiry:.4f}")
        logger.info(f"r_dom: {r_dom:.6f}, r_for: {r_for:.6f}")
        logger.info(f"Forward: {forward:.5f}")

        # Get forward points for display
        fwd_points = (forward - spot) * 10000  # Convert to pips

        # Get interpolated volatility
        vol = self._get_interpolated_vol(strike, time_to_expiry, spot, r_dom, r_for)
        logger.info(f"Vol: {vol:.4f}")

        # If strike is 0 or not set, use ATMF
        if strike <= 0:
            strike = forward
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
            domestic_rate=r_dom,
            foreign_rate=r_for,
            volatility=vol,
            time_to_expiry=time_to_expiry,
            is_call=is_call,
            notional=notional,
            notional_currency="FOR" if notional_ccy == base_ccy else "DOM"
        )

        result = GarmanKohlhagen.calculate_all(params)

        # Save for shock analysis
        self._last_pricing_result = result
        self._last_pricing_params = params

        logger.info(f"Premium (domestic): {result.premium:.2f}")
        logger.info(f"Premium %: {result.premium_pct:.4f}")
        logger.info(f"Delta: {result.greeks.delta:.4f}")
        logger.info(f"Gamma: {result.greeks.gamma:.8f}")

        direction_text = self.direction_combo.currentText()
        direction = Direction.CLIENT_BUYS if "buys" in direction_text.lower() else Direction.CLIENT_SELLS

        hedge = GarmanKohlhagen.calculate_delta_hedge(params, direction)

        self._update_results_display(result, r_dom, r_for, forward, vol, fwd_points, hedge, params)

    def _get_interpolated_vol(
        self,
        strike: float,
        time_to_expiry: float,
        spot: float,
        r_dom: float,
        r_for: float
    ) -> float:
        """Get interpolated volatility for strike and expiry."""
        # Default volatility if no surface available
        DEFAULT_VOL = 0.10  # 10%

        if not self._vol_surface:
            return DEFAULT_VOL

        # Check if surface has valid smiles
        if len(self._vol_surface.tenors) == 0:
            return DEFAULT_VOL

        try:
            if strike <= 0:
                vol = self._vol_surface.get_atm_vol(time_to_expiry)
            else:
                vol = self._vol_surface.get_vol(strike, time_to_expiry, spot, r_dom, r_for)

            # Sanity check: vol should be between 0.01 (1%) and 2.0 (200%)
            if vol < 0.01 or vol > 2.0:
                logger.warning(f"Volatility {vol} out of range, using default")
                return DEFAULT_VOL

            return vol

        except Exception as e:
            logger.warning(f"Error interpolating volatility: {e}, using default")
            return DEFAULT_VOL

    def _update_results_display(
        self,
        result,
        r_dom: float,
        r_for: float,
        forward: float,
        vol: float,
        fwd_points: float,
        hedge: float,
        params: OptionParams
    ) -> None:
        """Update the results display fields."""
        ccy_pair = self.asset_combo.currentText().replace("/", "")
        base_ccy = ccy_pair[:3]  # Foreign (e.g., EUR)
        quote_ccy = ccy_pair[3:]  # Domestic (e.g., USD)

        self.vol_display.setText(f"{vol * 100:.3f}%")
        self.points_display.setText(f"{fwd_points:.2f}")
        self.forward_display.setText(f"{forward:.5f}")
        self.foreign_depo_display.setText(f"{r_for * 100:.3f}%")
        self.domestic_depo_display.setText(f"{r_dom * 100:.3f}%")

        # Get selected currency for premium (gamma and vega follow)
        premium_ccy = self.premium_ccy.currentText()

        # Gamma: Bloomberg convention is gamma cash per 1% spot move
        # This gives the same value regardless of currency because S cancels out
        gamma_1pct = result.greeks.gamma * params.spot * 0.01 * params.notional
        self.gamma_display.setText(f"{gamma_1pct:,.2f}")

        # Vega: per 1% vol move, in premium currency
        # The calculated vega is in DOMESTIC currency (USD for EURUSD)
        vega_dom = result.greeks.vega * params.notional
        if premium_ccy == base_ccy:
            # Convert to foreign currency (EUR)
            vega_value = vega_dom / params.spot
        else:
            # Keep in domestic currency (USD)
            vega_value = vega_dom
        self.vega_display.setText(f"{vega_value:,.2f}")

        # result.premium is in DOMESTIC currency (USD for EURUSD)
        # Convert to selected currency
        if premium_ccy == quote_ccy:
            # Already in domestic (USD)
            premium_display = result.premium
        else:
            # Convert to foreign (EUR): divide by spot
            premium_display = result.premium / params.spot

        # Price format
        price_format = self.price_format.currentText()
        if f"% {base_ccy}" in price_format:
            # % of foreign (EUR)
            premium_in_for = result.premium / params.spot
            if params.notional_currency == "FOR":
                price_pct = premium_in_for / params.notional * 100
            else:
                price_pct = premium_in_for / (params.notional / params.spot) * 100
            self.price_display.setText(f"{price_pct:.4f}%")
        elif f"% {quote_ccy}" in price_format:
            # % of domestic (USD)
            if params.notional_currency == "FOR":
                notional_dom = params.notional * params.spot
            else:
                notional_dom = params.notional
            price_pct = result.premium / notional_dom * 100
            self.price_display.setText(f"{price_pct:.4f}%")
        else:
            # Pips - show as number without %
            price_pips = result.premium_pips
            self.price_display.setText(f"{price_pips:.2f}")

        self.premium_display.setText(f"{premium_display:,.2f}")
        self.prem_date_display.setText(date.today().strftime("%m/%d/%y"))
        
        # Delta - spot or forward
        delta_type = self.delta_type.currentText()
        if delta_type == "Fwd":
            # Forward delta = spot delta * exp(r_for * t)
            import math
            fwd_delta = result.greeks.delta * math.exp(r_for * params.time_to_expiry)
            self.delta_display.setText(f"{fwd_delta * 100:.4f}%")
        else:
            self.delta_display.setText(f"{result.greeks.delta * 100:.4f}%")
        
        self.hedge_display.setText(f"{hedge:,.2f}")

    def _on_refresh_data(self) -> None:
        """Refresh market data from Bloomberg."""
        self._vol_surface = None
        self._fx_rates = None
        if self._bbg_connected:
            self._load_market_data()
        else:
            QMessageBox.warning(
                self,
                "No Connection",
                "Bloomberg is not connected. Please connect to Bloomberg first."
            )

    def _on_load_historical(self) -> None:
        """Load historical data for start and end dates."""
        logger.info("=== LOAD HISTORICAL DATA STARTED ===")
        
        if not self._bbg_connected:
            QMessageBox.warning(
                self,
                "No Connection",
                "Bloomberg is not connected. Cannot load historical data."
            )
            logger.error("Bloomberg not connected")
            return

        # Get dates from QDateEdit widgets
        start_qdate = self.shock_start_date.date()
        end_qdate = self.shock_end_date.date()
        
        start_date = date(start_qdate.year(), start_qdate.month(), start_qdate.day())
        end_date = date(end_qdate.year(), end_qdate.month(), end_qdate.day())
        
        logger.info(f"Start date: {start_date}, End date: {end_date}")

        # Validate dates
        if start_date >= end_date:
            QMessageBox.warning(
                self,
                "Date Error",
                "Start date must be before end date."
            )
            logger.error(f"Invalid date range: {start_date} >= {end_date}")
            return

        # Check if dates are business days
        ccy_pair = self.asset_combo.currentText().replace("/", "")
        tenors = self._config.tenors if self._config else ["1M", "3M", "6M", "1Y"]

        self.statusBar().showMessage("Loading historical data...")
        self.shock_status.setText("Loading...")
        logger.info(f"Loading historical data for {ccy_pair}")

        try:
            conn = BloombergConnection.get_instance()
            fetcher = HistoricalDataFetcher(conn)

            # Fetch data for start date
            logger.info(f"Fetching data for start date: {start_date}")
            self._shock_start_data = fetcher.fetch_historical(ccy_pair, tenors, start_date)
            
            # Validate start data
            if self._shock_start_data.get('spot', 0) == 0:
                raise ValueError(f"No data available for start date {start_date}. It might be a weekend or holiday.")
            
            # Fetch data for end date
            logger.info(f"Fetching data for end date: {end_date}")
            self._shock_end_data = fetcher.fetch_historical(ccy_pair, tenors, end_date)
            
            # Validate end data
            if self._shock_end_data.get('spot', 0) == 0:
                raise ValueError(f"No data available for end date {end_date}. It might be a weekend or holiday.")

            # Calculate deltas
            logger.info("Calculating market data deltas...")
            self._market_delta = MarketDataDelta.calculate(
                self._shock_start_data,
                self._shock_end_data,
                start_date,
                end_date
            )

            # Update UI with deltas
            self._update_shock_deltas_display()

            # Enable Apply Shock button
            self.apply_shock_btn.setEnabled(True)
            self.shock_status.setText("Ready to apply")
            self.statusBar().showMessage("Historical data loaded successfully!")
            logger.info("=== LOAD HISTORICAL DATA COMPLETE ===")

        except Exception as e:
            logger.error(f"Failed to load historical data: {e}", exc_info=True)
            QMessageBox.warning(
                self,
                "Load Error",
                f"Failed to load historical data:\n{str(e)}"
            )
            self.shock_status.setText("Load failed")
            self.apply_shock_btn.setEnabled(False)
            self.statusBar().showMessage("Load failed")

    def _update_shock_deltas_display(self) -> None:
        """Update the shock deltas display fields."""
        if not self._market_delta:
            return

        logger.info("Updating shock deltas display")

        # Time decay
        self.shock_time_decay.setText(f"{self._market_delta.time_diff_days} days")

        # Spot change
        spot_pct = self._market_delta.spot_pct_change * 100
        self.shock_spot_change.setText(f"{spot_pct:+.2f}%")

        # Vol change (average)
        if self._market_delta.atm_vol_diffs:
            avg_vol_diff = sum(self._market_delta.atm_vol_diffs.values()) / len(self._market_delta.atm_vol_diffs)
            self.shock_vol_change.setText(f"{avg_vol_diff * 100:+.2f}%")
        else:
            self.shock_vol_change.setText("N/A")

        # Rate change (average)
        if self._market_delta.usd_rate_diffs:
            avg_rate_diff = sum(self._market_delta.usd_rate_diffs.values()) / len(self._market_delta.usd_rate_diffs)
            self.shock_rate_change.setText(f"{avg_rate_diff * 100:+.2f}%")
        else:
            self.shock_rate_change.setText("N/A")

    def _on_apply_shock(self) -> None:
        """Apply the calculated shock to current market data and reprice."""
        logger.info("=== APPLY SHOCK STARTED ===")

        if not self._market_delta:
            QMessageBox.warning(
                self,
                "No Shock Data",
                "Please load historical data first."
            )
            return

        if not self._market_data:
            QMessageBox.warning(
                self,
                "No Market Data",
                "Please load current market data first by calculating the option."
            )
            return

        if not self._last_pricing_params:
            QMessageBox.warning(
                self,
                "No Pricing",
                "Please calculate the option first before applying shock."
            )
            return

        self.statusBar().showMessage("Applying shock...")
        self.shock_status.setText("Calculating...")

        try:
            # Get original expiry in days
            original_expiry_days = int(self._last_pricing_params.time_to_expiry * 365)
            logger.info(f"Original expiry: {original_expiry_days} days")

            # Apply shock to market data
            self._shocked_market_data = ShockCalculator.apply_shock(
                self._market_data,
                self._market_delta,
                original_expiry_days
            )

            # Calculate shocked expiry
            shocked_expiry_days = self._shocked_market_data.shocked_expiry_days
            if shocked_expiry_days <= 0:
                raise ValueError(f"Shocked expiry is {shocked_expiry_days} days. The shock period exceeds the option's remaining life.")

            shocked_time_to_expiry = shocked_expiry_days / 365.0
            logger.info(f"Shocked expiry: {shocked_expiry_days} days ({shocked_time_to_expiry:.4f} years)")

            # Get shocked rates and vol for the option's expiry
            shocked_spot = self._shocked_market_data.spot
            
            # Interpolate shocked domestic rate
            shocked_dom_rate = self._get_interpolated_shocked_rate(
                shocked_time_to_expiry,
                self._shocked_market_data.domestic_rates
            )
            
            # Interpolate shocked foreign rate
            shocked_for_rate = self._get_interpolated_shocked_rate(
                shocked_time_to_expiry,
                self._shocked_market_data.foreign_rates
            )
            
            # Interpolate shocked vol
            shocked_vol = self._get_interpolated_shocked_vol(
                shocked_time_to_expiry,
                self._shocked_market_data.atm_vols
            )

            logger.info(f"Shocked spot: {shocked_spot:.5f}")
            logger.info(f"Shocked domestic rate: {shocked_dom_rate:.4f}")
            logger.info(f"Shocked foreign rate: {shocked_for_rate:.4f}")
            logger.info(f"Shocked volatility: {shocked_vol:.4f}")

            # Calculate shocked forward
            shocked_forward = shocked_spot * math.exp((shocked_dom_rate - shocked_for_rate) * shocked_time_to_expiry)
            logger.info(f"Shocked forward: {shocked_forward:.5f}")

            # Build shocked option params
            shocked_params = OptionParams(
                spot=shocked_spot,
                strike=self._last_pricing_params.strike,
                domestic_rate=shocked_dom_rate,
                foreign_rate=shocked_for_rate,
                volatility=shocked_vol,
                time_to_expiry=shocked_time_to_expiry,
                is_call=self._last_pricing_params.is_call,
                notional=self._last_pricing_params.notional,
                notional_currency=self._last_pricing_params.notional_currency
            )

            # Calculate shocked option
            logger.info("Calculating shocked option price...")
            shocked_result = GarmanKohlhagen.calculate_all(shocked_params)

            # Calculate P&L
            original_premium = self._last_pricing_result.premium
            shocked_premium = shocked_result.premium
            pnl = shocked_premium - original_premium
            logger.info(f"Original premium: {original_premium:.2f}")
            logger.info(f"Shocked premium: {shocked_premium:.2f}")
            logger.info(f"P&L: {pnl:+.2f}")

            # Update shocked results display
            self._update_shocked_results_display(
                shocked_result,
                shocked_params,
                shocked_forward,
                shocked_vol,
                pnl
            )

            self.shock_status.setText("Applied")
            self.statusBar().showMessage("Shock applied successfully!")
            logger.info("=== APPLY SHOCK COMPLETE ===")

        except Exception as e:
            logger.error(f"Failed to apply shock: {e}", exc_info=True)
            QMessageBox.warning(
                self,
                "Shock Error",
                f"Failed to apply shock:\n{str(e)}"
            )
            self.shock_status.setText("Error")
            self.statusBar().showMessage("Shock failed")

    def _get_interpolated_shocked_rate(
        self,
        time_to_expiry: float,
        rates: Dict[str, float]
    ) -> float:
        """Interpolate rate from shocked rates dictionary."""
        if not rates:
            return 0.0

        from ..models.interpolation import linear_interpolate

        times = []
        values = []
        for tenor, rate in rates.items():
            t = tenor_to_years(tenor)
            times.append(t)
            values.append(rate)

        # Sort by time
        sorted_data = sorted(zip(times, values))
        times = [d[0] for d in sorted_data]
        values = [d[1] for d in sorted_data]

        return linear_interpolate(time_to_expiry, times, values, extrapolate=True)

    def _get_interpolated_shocked_vol(
        self,
        time_to_expiry: float,
        vols: Dict[str, float]
    ) -> float:
        """Interpolate volatility from shocked vols dictionary."""
        if not vols:
            return 0.08  # Default

        from ..models.interpolation import variance_interpolate

        times = []
        values = []
        for tenor, vol in vols.items():
            t = tenor_to_years(tenor)
            times.append(t)
            values.append(vol)

        # Sort by time
        sorted_data = sorted(zip(times, values))
        times = [d[0] for d in sorted_data]
        values = [d[1] for d in sorted_data]

        return variance_interpolate(time_to_expiry, times, values, extrapolate=True)

    def _update_shocked_results_display(
        self,
        shocked_result,
        shocked_params: OptionParams,
        shocked_forward: float,
        shocked_vol: float,
        pnl: float
    ) -> None:
        """Update the shocked results display fields."""
        logger.info("Updating shocked results display")

        ccy_pair = self.asset_combo.currentText().replace("/", "")
        base_ccy = ccy_pair[:3]
        quote_ccy = ccy_pair[3:]

        # Shocked expiry
        shocked_days = int(shocked_params.time_to_expiry * 365)
        self.shocked_expiry_display.setText(f"{shocked_days} days")

        # Shocked spot
        self.shocked_spot_display.setText(f"{shocked_params.spot:.5f}")

        # Shocked vol
        self.shocked_vol_display.setText(f"{shocked_vol * 100:.3f}%")

        # Shocked forward
        self.shocked_forward_display.setText(f"{shocked_forward:.5f}")

        # Get premium currency
        premium_ccy = self.premium_ccy.currentText()

        # Shocked premium
        if premium_ccy == base_ccy:
            shocked_premium_value = shocked_result.premium / shocked_params.spot
        else:
            shocked_premium_value = shocked_result.premium
        self.shocked_premium_display.setText(f"{shocked_premium_value:,.2f} {premium_ccy}")

        # P&L
        if premium_ccy == base_ccy:
            pnl_value = pnl / shocked_params.spot
        else:
            pnl_value = pnl
        
        # Color P&L: green for profit, red for loss
        if pnl_value >= 0:
            self.shocked_pnl_display.setStyleSheet("color: #00FF00;")
        else:
            self.shocked_pnl_display.setStyleSheet("color: #FF4444;")
        self.shocked_pnl_display.setText(f"{pnl_value:+,.2f} {premium_ccy}")

        # Shocked delta
        r_for = shocked_params.foreign_rate
        t = shocked_params.time_to_expiry
        delta_type = self.delta_type.currentText()
        if delta_type == "Fwd":
            shocked_delta = shocked_result.greeks.delta * math.exp(r_for * t)
        else:
            shocked_delta = shocked_result.greeks.delta
        self.shocked_delta_display.setText(f"{shocked_delta * 100:.4f}%")

        # Shocked gamma (in base currency)
        gamma_dom = shocked_result.greeks.gamma * shocked_params.notional
        gamma_value = gamma_dom / shocked_params.spot
        self.shocked_gamma_display.setText(f"{gamma_value:,.0f} {base_ccy}")

        # Shocked vega
        vega_dom = shocked_result.greeks.vega * shocked_params.notional
        if premium_ccy == base_ccy:
            vega_value = vega_dom / shocked_params.spot
        else:
            vega_value = vega_dom
        self.shocked_vega_display.setText(f"{vega_value:,.0f} {premium_ccy}")

    def closeEvent(self, event) -> None:
        """Handle window close."""
        if self._bbg_connected:
            try:
                BloombergConnection.get_instance().disconnect()
            except Exception:
                pass
        event.accept()
