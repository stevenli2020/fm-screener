class MarketDataError(RuntimeError):
    """Base class for market-data adapter failures."""


class DependencyUnavailableError(MarketDataError):
    """Raised when the data server cannot provide a response after retries."""


class MarketDataRequestError(MarketDataError):
    """Raised when the data server rejects a request."""


class ContractError(MarketDataError):
    """Raised when the data server returns malformed or incompatible data."""
