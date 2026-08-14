from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class ConfigurationError(ValueError):
    """Raised when runtime configuration is unsafe or invalid."""


def _non_negative_int(name: str, value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if parsed < 0:
        raise ConfigurationError(f"{name} must be non-negative")
    return parsed


def _non_negative_float(name: str, value: str, *, allow_zero: bool = True) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be numeric") from exc
    minimum_ok = parsed >= 0 if allow_zero else parsed > 0
    if not minimum_ok:
        qualifier = "non-negative" if allow_zero else "greater than zero"
        raise ConfigurationError(f"{name} must be {qualifier}")
    return parsed


@dataclass(frozen=True, slots=True)
class Settings:
    data_server_base_url: str = "http://127.0.0.1:8766"
    data_server_timeout_seconds: float = 15.0
    data_server_max_retries: int = 2
    data_server_retry_backoff_seconds: float = 0.25
    data_server_cache_ttl_seconds: float = 60.0
    database_path: Path = Path("data/financial_market.sqlite3")
    risk_rules_path: Path = Path("config/risk_rules_sgx.json")
    universe_path: Path = Path("config/universe_sgx.csv")
    screening_eligibility_path: Path = Path("config/screening_eligibility_sgx.json")
    sgx_news_api_url: str = "https://www.sgx.com/stock-exchange/company-announcements"
    sgx_news_timeout_seconds: float = 15.0
    sgx_news_max_retries: int = 2
    sgx_news_retry_backoff_seconds: float = 0.25
    sgx_news_limit: int = 50
    sgx_announcement_filters_path: Path = Path("scripts/sgx_announcement_filters.json")
    sgx_news_max_pages_per_target: int = 10
    sgx_news_request_pacing_seconds: float = 0.5

    def __post_init__(self) -> None:
        parsed = urlparse(self.data_server_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigurationError("FM_DATA_SERVER_BASE_URL must be an http(s) URL")
        if parsed.query or parsed.fragment:
            raise ConfigurationError("FM_DATA_SERVER_BASE_URL cannot contain a query or fragment")
        if self.data_server_timeout_seconds <= 0:
            raise ConfigurationError("FM_DATA_SERVER_TIMEOUT_SECONDS must be greater than zero")
        if self.data_server_max_retries < 0:
            raise ConfigurationError("FM_DATA_SERVER_MAX_RETRIES must be non-negative")
        if self.data_server_retry_backoff_seconds < 0:
            raise ConfigurationError("FM_DATA_SERVER_RETRY_BACKOFF_SECONDS must be non-negative")
        if self.data_server_cache_ttl_seconds < 0:
            raise ConfigurationError("FM_DATA_SERVER_CACHE_TTL_SECONDS must be non-negative")
        news_url = urlparse(self.sgx_news_api_url)
        if news_url.scheme != "https" or not news_url.netloc:
            raise ConfigurationError("FM_SGX_NEWS_API_URL must be an https URL")
        if self.sgx_news_timeout_seconds <= 0:
            raise ConfigurationError("FM_SGX_NEWS_TIMEOUT_SECONDS must be greater than zero")
        if self.sgx_news_max_retries < 0:
            raise ConfigurationError("FM_SGX_NEWS_MAX_RETRIES must be non-negative")
        if self.sgx_news_retry_backoff_seconds < 0:
            raise ConfigurationError("FM_SGX_NEWS_RETRY_BACKOFF_SECONDS must be non-negative")
        if self.sgx_news_limit <= 0:
            raise ConfigurationError("FM_SGX_NEWS_LIMIT must be greater than zero")
        if self.sgx_news_max_pages_per_target <= 0:
            raise ConfigurationError("FM_SGX_NEWS_MAX_PAGES_PER_TARGET must be greater than zero")
        if self.sgx_news_request_pacing_seconds < 0:
            raise ConfigurationError("FM_SGX_NEWS_REQUEST_PACING_SECONDS must be non-negative")
        object.__setattr__(self, "data_server_base_url", self.data_server_base_url.rstrip("/"))

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            data_server_base_url=os.getenv("FM_DATA_SERVER_BASE_URL", "http://127.0.0.1:8766"),
            data_server_timeout_seconds=_non_negative_float(
                "FM_DATA_SERVER_TIMEOUT_SECONDS",
                os.getenv("FM_DATA_SERVER_TIMEOUT_SECONDS", "15"),
                allow_zero=False,
            ),
            data_server_max_retries=_non_negative_int(
                "FM_DATA_SERVER_MAX_RETRIES", os.getenv("FM_DATA_SERVER_MAX_RETRIES", "2")
            ),
            data_server_retry_backoff_seconds=_non_negative_float(
                "FM_DATA_SERVER_RETRY_BACKOFF_SECONDS",
                os.getenv("FM_DATA_SERVER_RETRY_BACKOFF_SECONDS", "0.25"),
            ),
            data_server_cache_ttl_seconds=_non_negative_float(
                "FM_DATA_SERVER_CACHE_TTL_SECONDS",
                os.getenv("FM_DATA_SERVER_CACHE_TTL_SECONDS", "60"),
            ),
            database_path=Path(os.getenv("FM_DATABASE_PATH", "data/financial_market.sqlite3")),
            risk_rules_path=Path(os.getenv("FM_RISK_RULES_PATH", "config/risk_rules_sgx.json")),
            universe_path=Path(os.getenv("FM_UNIVERSE_PATH", "config/universe_sgx.csv")),
            screening_eligibility_path=Path(
                os.getenv("FM_SCREENING_ELIGIBILITY_PATH", "config/screening_eligibility_sgx.json")
            ),
            sgx_news_api_url=os.getenv(
                "FM_SGX_NEWS_API_URL",
                "https://www.sgx.com/stock-exchange/company-announcements",
            ),
            sgx_news_timeout_seconds=_non_negative_float(
                "FM_SGX_NEWS_TIMEOUT_SECONDS",
                os.getenv("FM_SGX_NEWS_TIMEOUT_SECONDS", "15"),
                allow_zero=False,
            ),
            sgx_news_max_retries=_non_negative_int(
                "FM_SGX_NEWS_MAX_RETRIES", os.getenv("FM_SGX_NEWS_MAX_RETRIES", "2")
            ),
            sgx_news_retry_backoff_seconds=_non_negative_float(
                "FM_SGX_NEWS_RETRY_BACKOFF_SECONDS",
                os.getenv("FM_SGX_NEWS_RETRY_BACKOFF_SECONDS", "0.25"),
            ),
            sgx_news_limit=_non_negative_int(
                "FM_SGX_NEWS_LIMIT", os.getenv("FM_SGX_NEWS_LIMIT", "50")
            ),
            sgx_announcement_filters_path=Path(
                os.getenv(
                    "FM_SGX_ANNOUNCEMENT_FILTERS_PATH",
                    "scripts/sgx_announcement_filters.json",
                )
            ),
            sgx_news_max_pages_per_target=_non_negative_int(
                "FM_SGX_NEWS_MAX_PAGES_PER_TARGET",
                os.getenv("FM_SGX_NEWS_MAX_PAGES_PER_TARGET", "10"),
            ),
            sgx_news_request_pacing_seconds=_non_negative_float(
                "FM_SGX_NEWS_REQUEST_PACING_SECONDS",
                os.getenv("FM_SGX_NEWS_REQUEST_PACING_SECONDS", "0.5"),
            ),
        )
