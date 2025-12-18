"""
Configuration parser for FX Option Pricer.
Reads config.txt and provides access to all settings.
"""

import configparser
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional


@dataclass
class Config:
    """Container for all configuration settings."""

    # Pillars
    tenors: List[str] = field(default_factory=list)

    # Currency pairs
    currency_pairs: List[str] = field(default_factory=list)

    # USD curve
    usd_curve_ticker_prefix: str = "SOFR"

    # Volatility
    delta_points: List[str] = field(default_factory=list)

    # Defaults
    default_asset: str = "EURUSD"
    default_style: str = "European"
    default_direction: str = "Client buys"
    default_call_put: str = "Call"
    default_notional: float = 1_000_000
    default_notional_currency: str = "EUR"
    default_price_format: str = "percent"
    default_price_currency: str = "domestic"
    default_strike: str = "ATMF"


class ConfigParser:
    """Parser for config.txt file."""

    DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.txt"

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize parser with config file path.

        Args:
            config_path: Path to config.txt. If None, uses default location.
        """
        self._config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._parser = configparser.ConfigParser()
        self._config: Optional[Config] = None

    def parse(self) -> Config:
        """
        Parse the configuration file and return Config object.

        Returns:
            Config object with all settings.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            ValueError: If required sections are missing.
        """
        if not self._config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self._config_path}")

        self._parser.read(self._config_path)

        config = Config()

        # Parse pillars
        if self._parser.has_section("pillars"):
            tenors_str = self._parser.get("pillars", "tenors", fallback="")
            config.tenors = [t.strip() for t in tenors_str.split(",") if t.strip()]

        # Parse currency pairs
        if self._parser.has_section("currency_pairs"):
            pairs_str = self._parser.get("currency_pairs", "pairs", fallback="")
            config.currency_pairs = [p.strip() for p in pairs_str.split(",") if p.strip()]

        # Parse USD curve
        if self._parser.has_section("usd_curve"):
            config.usd_curve_ticker_prefix = self._parser.get(
                "usd_curve", "ticker_prefix", fallback="SOFR"
            )

        # Parse volatility
        if self._parser.has_section("volatility"):
            delta_str = self._parser.get("volatility", "delta_points", fallback="")
            config.delta_points = [d.strip() for d in delta_str.split(",") if d.strip()]

        # Parse defaults
        if self._parser.has_section("defaults"):
            config.default_asset = self._parser.get("defaults", "asset", fallback="EURUSD")
            config.default_style = self._parser.get("defaults", "style", fallback="European")
            config.default_direction = self._parser.get("defaults", "direction", fallback="Client buys")
            config.default_call_put = self._parser.get("defaults", "call_put", fallback="Call")
            config.default_notional = self._parser.getfloat("defaults", "notional", fallback=1_000_000)
            config.default_notional_currency = self._parser.get("defaults", "notional_currency", fallback="EUR")
            config.default_price_format = self._parser.get("defaults", "price_format", fallback="percent")
            config.default_price_currency = self._parser.get("defaults", "price_currency", fallback="domestic")
            config.default_strike = self._parser.get("defaults", "strike", fallback="ATMF")

        self._config = config
        return config

    def get_config(self) -> Config:
        """
        Get parsed config, parsing if not already done.

        Returns:
            Config object.
        """
        if self._config is None:
            return self.parse()
        return self._config


def load_config(config_path: Optional[Path] = None) -> Config:
    """
    Convenience function to load configuration.

    Args:
        config_path: Optional path to config file.

    Returns:
        Config object with all settings.
    """
    parser = ConfigParser(config_path)
    return parser.parse()
