from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date
from typing import Any

import requests

from financial_market.config import Settings

from .errors import ContractError, DependencyUnavailableError, MarketDataRequestError
from .models import BacktestRequest, BacktestResult, HealthStatus, OHLCVSeries


class DataServerClient:
    """Typed, fail-closed adapter for the FinancialMarket data server."""

    _RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        settings: Settings,
        *,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._session = session or requests.Session()
        self._owns_session = session is None
        self._sleep = sleep
        self._monotonic = monotonic
        self._cache: dict[tuple[Any, ...], tuple[float, OHLCVSeries]] = {}

    def __enter__(self) -> DataServerClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    def health(self) -> HealthStatus:
        payload = self._request_json("GET", "/api/health")
        return HealthStatus.from_payload(payload)

    def get_ohlcv(
        self,
        ticker: str,
        *,
        frequency: str = "1d",
        start_date: date | None = None,
        end_date: date | None = None,
        force_refresh: bool = False,
    ) -> OHLCVSeries:
        ticker = ticker.strip()
        frequency = frequency.strip()
        if not ticker:
            raise ValueError("ticker cannot be empty")
        if not frequency:
            raise ValueError("frequency cannot be empty")
        if start_date and end_date and start_date > end_date:
            raise ValueError("start_date cannot be after end_date")

        cache_key = (ticker, frequency, start_date, end_date)
        now = self._monotonic()
        cached = self._cache.get(cache_key)
        if not force_refresh and cached and cached[0] > now:
            return cached[1]

        params = {"ticker": ticker, "frequency": frequency}
        if start_date:
            params["start_date"] = start_date.isoformat()
        if end_date:
            params["end_date"] = end_date.isoformat()
        try:
            series = OHLCVSeries.from_payload(
                self._request_json("GET", "/api/ohlcv", params=params)
            )
        except ContractError as exc:
            raise ContractError(f"invalid OHLCV contract for {ticker}: {exc}") from exc
        if series.ticker != ticker or series.frequency != frequency:
            raise ContractError("OHLCV response identity does not match the request")
        self._cache[cache_key] = (
            now + self._settings.data_server_cache_ttl_seconds,
            series,
        )
        return series

    def run_backtest(self, request: BacktestRequest) -> BacktestResult:
        payload = self._request_json("POST", "/api/backtest", json=request.to_payload())
        return BacktestResult.from_payload(payload)

    def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self._settings.data_server_base_url}{path}"
        attempts = self._settings.data_server_max_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self._session.request(
                    method,
                    url,
                    timeout=self._settings.data_server_timeout_seconds,
                    **kwargs,
                )
                if response.status_code in self._RETRYABLE_STATUS_CODES:
                    last_error = DependencyUnavailableError(
                        f"data server returned retryable HTTP {response.status_code}"
                    )
                elif response.status_code >= 400:
                    detail = _safe_error_detail(response)
                    raise MarketDataRequestError(
                        f"data server rejected {method} {path} with HTTP "
                        f"{response.status_code}: {detail}"
                    )
                else:
                    try:
                        payload = response.json()
                    except (requests.JSONDecodeError, ValueError) as exc:
                        raise ContractError("data server returned invalid JSON") from exc
                    if not isinstance(payload, dict):
                        raise ContractError("data server response must be a JSON object")
                    return payload
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = exc

            if attempt + 1 < attempts:
                self._sleep(self._settings.data_server_retry_backoff_seconds * (2**attempt))

        raise DependencyUnavailableError(
            f"data server unavailable after {attempts} attempt(s): {last_error}"
        ) from last_error


def _safe_error_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except (requests.JSONDecodeError, ValueError):
        return "response body was not JSON"
    if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
        return payload["detail"][:500]
    return "no error detail supplied"
