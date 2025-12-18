"""
Bloomberg API connection management.
Provides a singleton class for managing Bloomberg session lifecycle.
"""

import logging
from typing import Optional

try:
    import blpapi
    BLPAPI_AVAILABLE = True
except ImportError:
    BLPAPI_AVAILABLE = False
    blpapi = None

logger = logging.getLogger(__name__)


class BloombergConnectionError(Exception):
    """Exception raised when Bloomberg connection fails."""
    pass


class BloombergConnection:
    """
    Singleton class for managing Bloomberg API connection.

    Usage:
        conn = BloombergConnection.get_instance()
        if conn.connect():
            session = conn.get_session()
            # Use session for requests
        conn.disconnect()
    """

    _instance: Optional['BloombergConnection'] = None

    def __new__(cls) -> 'BloombergConnection':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._session: Optional['blpapi.Session'] = None
        self._connected: bool = False
        self._ref_data_service = None
        self._initialized = True

    @classmethod
    def get_instance(cls) -> 'BloombergConnection':
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (mainly for testing)."""
        if cls._instance is not None:
            cls._instance.disconnect()
            cls._instance = None

    def is_available(self) -> bool:
        """Check if blpapi module is available."""
        return BLPAPI_AVAILABLE

    def connect(self) -> bool:
        """
        Establish connection to Bloomberg.

        Returns:
            True if connection successful, False otherwise.

        Raises:
            BloombergConnectionError: If blpapi is not installed.
        """
        if not BLPAPI_AVAILABLE:
            raise BloombergConnectionError(
                "blpapi module not installed. Please install Bloomberg API."
            )

        if self._connected:
            return True

        try:
            # Session options
            session_options = blpapi.SessionOptions()
            session_options.setServerHost("localhost")
            session_options.setServerPort(8194)

            # Create and start session
            self._session = blpapi.Session(session_options)

            if not self._session.start():
                logger.error("Failed to start Bloomberg session")
                self._session = None
                return False

            # Open reference data service
            if not self._session.openService("//blp/refdata"):
                logger.error("Failed to open //blp/refdata service")
                self._session.stop()
                self._session = None
                return False

            self._ref_data_service = self._session.getService("//blp/refdata")
            self._connected = True
            logger.info("Bloomberg connection established successfully")
            return True

        except Exception as e:
            logger.error(f"Bloomberg connection failed: {e}")
            self._session = None
            self._connected = False
            return False

    def disconnect(self) -> None:
        """Disconnect from Bloomberg and cleanup resources."""
        if self._session is not None:
            try:
                self._session.stop()
            except Exception as e:
                logger.warning(f"Error stopping Bloomberg session: {e}")
            finally:
                self._session = None
                self._ref_data_service = None
                self._connected = False
                logger.info("Bloomberg connection closed")

    def is_connected(self) -> bool:
        """Check if currently connected to Bloomberg."""
        return self._connected and self._session is not None

    def get_session(self) -> Optional['blpapi.Session']:
        """
        Get the Bloomberg session.

        Returns:
            Bloomberg Session object, or None if not connected.
        """
        if not self._connected:
            return None
        return self._session

    def get_ref_data_service(self) -> Optional['blpapi.Service']:
        """
        Get the reference data service.

        Returns:
            Bloomberg Service object for reference data, or None if not connected.
        """
        if not self._connected:
            return None
        return self._ref_data_service

    def __enter__(self) -> 'BloombergConnection':
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()
