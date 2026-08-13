from __future__ import annotations

from datetime import date
from typing import Any

import pytest
import requests

from financial_market.config import Settings
from financial_market.market_data.client import DataServerClient
from financial_market.market_data.errors import (
    ContractError,
    DependencyUnavailableError,
    MarketDataRequestError,
)
from financial_market.market_data.models import BacktestRequest


class FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def settings(**overrides: Any) -> Settings:
    values = {
        "data_server_base_url": "http://data-server.local",
        "data_server_timeout_seconds": 2,
        "data_server_max_retries": 0,
        "data_server_retry_backoff_seconds": 0,
        "data_server_cache_ttl_seconds": 60,
    }
    values.update(overrides)
    return Settings(**values)


def ohlcv_payload() -> dict[str, Any]:
    return {
        "ticker": "D05.SI",
        "frequency": "1d",
        "price_adjustment": "split_and_dividend_adjusted",
        "rows": [
            {"t": 1_700_000_000_000, "o": 30.0, "h": 31.0, "l": 29.5, "c": 30.5, "v": 10},
            {"t": 1_700_086_400_000, "o": 30.5, "h": 32.0, "l": 30.0, "c": 31.5, "v": 20},
        ],
    }


def test_health_parses_contract() -> None:
    session = FakeSession(
        [FakeResponse(200, {"status": "ok", "engine": "local", "supports_date_range": True})]
    )

    result = DataServerClient(settings(), session=session).health()

    assert result.status == "ok"
    assert result.supports_date_range is True


def test_get_ohlcv_sends_dates_and_uses_cache() -> None:
    session = FakeSession([FakeResponse(200, ohlcv_payload())])

    def clock() -> float:
        return 100.0

    client = DataServerClient(settings(), session=session, monotonic=clock)

    first = client.get_ohlcv("D05.SI", start_date=date(2024, 1, 1))
    second = client.get_ohlcv("D05.SI", start_date=date(2024, 1, 1))

    assert first is second
    assert len(session.calls) == 1
    assert session.calls[0][2]["params"]["start_date"] == "2024-01-01"
    assert first.rows[-1].close == 31.5


def test_force_refresh_bypasses_cache() -> None:
    session = FakeSession([FakeResponse(200, ohlcv_payload()), FakeResponse(200, ohlcv_payload())])
    client = DataServerClient(settings(), session=session, monotonic=lambda: 100.0)

    client.get_ohlcv("D05.SI")
    client.get_ohlcv("D05.SI", force_refresh=True)

    assert len(session.calls) == 2


def test_retryable_failure_retries_then_succeeds() -> None:
    session = FakeSession(
        [
            requests.ConnectionError("offline"),
            FakeResponse(503, {"detail": "warming up"}),
            FakeResponse(200, {"status": "ok", "engine": "local", "supports_date_range": True}),
        ]
    )
    sleeps: list[float] = []
    client = DataServerClient(
        settings(data_server_max_retries=2, data_server_retry_backoff_seconds=0.5),
        session=session,
        sleep=sleeps.append,
    )

    assert client.health().status == "ok"
    assert sleeps == [0.5, 1.0]


def test_retry_exhaustion_raises_dependency_error() -> None:
    session = FakeSession([FakeResponse(503, {}), FakeResponse(503, {})])
    client = DataServerClient(
        settings(data_server_max_retries=1), session=session, sleep=lambda _: None
    )

    with pytest.raises(DependencyUnavailableError, match="after 2 attempt"):
        client.health()


def test_400_is_not_retried_and_preserves_safe_detail() -> None:
    session = FakeSession([FakeResponse(400, {"detail": "invalid ticker"})])
    client = DataServerClient(settings(data_server_max_retries=3), session=session)

    with pytest.raises(MarketDataRequestError, match="invalid ticker"):
        client.get_ohlcv("NOPE.SI")
    assert len(session.calls) == 1


def test_malformed_ohlcv_fails_closed() -> None:
    payload = ohlcv_payload()
    payload["rows"][0]["h"] = 1.0
    session = FakeSession([FakeResponse(200, payload)])

    with pytest.raises(ContractError, match="D05.SI.*high"):
        DataServerClient(settings(), session=session).get_ohlcv("D05.SI")


def test_adjusted_close_outside_adjusted_intraday_range_is_rejected() -> None:
    payload = ohlcv_payload()
    payload["rows"][0]["c"] = 20.0
    session = FakeSession([FakeResponse(200, payload)])

    with pytest.raises(ContractError, match="low"):
        DataServerClient(settings(), session=session).get_ohlcv("D05.SI")


def test_missing_adjustment_contract_is_rejected() -> None:
    payload = ohlcv_payload()
    payload.pop("price_adjustment")
    session = FakeSession([FakeResponse(200, payload)])

    with pytest.raises(ContractError, match="price_adjustment"):
        DataServerClient(settings(), session=session).get_ohlcv("D05.SI")


def test_invalid_candle_repair_count_is_rejected() -> None:
    payload = ohlcv_payload()
    payload["candle_repair_count"] = -1
    session = FakeSession([FakeResponse(200, payload)])

    with pytest.raises(ContractError, match="candle_repair_count"):
        DataServerClient(settings(), session=session).get_ohlcv("D05.SI")


def test_response_identity_must_match_request() -> None:
    payload = ohlcv_payload()
    payload["ticker"] = "O39.SI"
    session = FakeSession([FakeResponse(200, payload)])

    with pytest.raises(ContractError, match="identity"):
        DataServerClient(settings(), session=session).get_ohlcv("D05.SI")


def test_backtest_serializes_dates() -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "bar_count": 100,
                    "metrics": {"strategy": {"sharpe": 1.2}, "buyhold": {"sharpe": 0.8}},
                },
            )
        ]
    )
    client = DataServerClient(settings(), session=session)

    result = client.run_backtest(
        BacktestRequest(
            ticker="D05.SI",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            warmup_start_date=date(2023, 1, 1),
            config={"rule": "donchian"},
        )
    )

    assert result.bar_count == 100
    assert result.metrics["strategy"]["sharpe"] == 1.2
    sent = session.calls[0][2]["json"]
    assert sent["start_date"] == "2024-01-01"
    assert sent["warmup_start_date"] == "2023-01-01"


def test_malformed_backtest_fails_closed() -> None:
    session = FakeSession([FakeResponse(200, {"bar_count": 10, "metrics": {}})])

    with pytest.raises(ContractError, match="metrics.strategy"):
        DataServerClient(settings(), session=session).run_backtest(BacktestRequest(ticker="D05.SI"))
