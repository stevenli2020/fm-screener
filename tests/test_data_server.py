from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from financial_market.data_server import api, data, server
from financial_market.data_server.backtest import run_backtest


def raw_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [100.0, 102.0],
            "High": [110.0, 112.0],
            "Low": [90.0, 92.0],
            "Close": [100.0, 104.0],
            "Adj Close": [50.0, 52.0],
            "Volume": [1000, 1200],
        },
        index=pd.to_datetime(["2025-01-02", "2025-01-03"]),
    )


def adjusted_frame(rows: int = 80) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=rows, freq="B")
    close = pd.Series([100 + index * 0.25 for index in range(rows)], index=index)
    return pd.DataFrame(
        {
            "Open": close - 0.2,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": 1_000_000,
        },
        index=index,
    )


def test_adjust_ohlcv_applies_factor_to_every_price() -> None:
    adjusted = data.adjust_ohlcv(raw_frame())

    first = adjusted.iloc[0]
    assert first["Open"] == 50.0
    assert first["High"] == 55.0
    assert first["Low"] == 45.0
    assert first["Close"] == 50.0
    assert first["Volume"] == 1000


def test_adjust_ohlcv_repairs_provider_high_below_close() -> None:
    raw = raw_frame()
    raw.loc[raw.index[0], "High"] = 99.0

    adjusted = data.adjust_ohlcv(raw)

    assert adjusted.iloc[0]["High"] == adjusted.iloc[0]["Close"]
    assert adjusted.attrs["candle_repair_count"] == 1
    assert adjusted.iloc[0]["CandleRepaired"]


def test_server_cache_is_project_owned_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def download(*args: Any, **kwargs: Any) -> pd.DataFrame:
        nonlocal calls
        calls += 1
        return raw_frame()

    data._MEMORY_CACHE.clear()
    monkeypatch.setattr(data.yf, "download", download)

    first = data.load_adjusted_ohlcv("D05.SI", cache_dir=tmp_path)
    data._MEMORY_CACHE.clear()
    second = data.load_adjusted_ohlcv("D05.SI", cache_dir=tmp_path)

    assert calls == 1
    pd.testing.assert_frame_equal(
        first,
        second,
        check_exact=False,
        check_freq=False,
        check_names=False,
    )
    assert (tmp_path / "D05.SI_1d.csv.gz").exists()


def test_server_cache_preserves_candle_repair_audit_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = raw_frame()
    raw.loc[raw.index[0], "High"] = 99.0
    data._MEMORY_CACHE.clear()
    monkeypatch.setattr(data.yf, "download", lambda *args, **kwargs: raw)

    first = data.load_adjusted_ohlcv("D05.SI", cache_dir=tmp_path)
    data._MEMORY_CACHE.clear()
    second = data.load_adjusted_ohlcv("D05.SI", cache_dir=tmp_path)

    assert first.attrs["candle_repair_count"] == 1
    assert second.attrs["candle_repair_count"] == 1
    assert second["CandleRepaired"].sum() == 1


def test_ohlcv_endpoint_declares_adjusted_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api, "load_adjusted_ohlcv", lambda ticker, frequency: adjusted_frame(2))
    client = TestClient(api.app)

    response = client.get("/api/ohlcv", params={"ticker": "D05.SI"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["price_adjustment"] == "split_and_dividend_adjusted"
    assert payload["candle_repair_count"] == 0
    assert payload["rows"][0]["l"] <= payload["rows"][0]["c"] <= payload["rows"][0]["h"]


def test_backtest_runs_on_adjusted_data() -> None:
    result = run_backtest(
        "D05.SI",
        "1d",
        {
            "indicator_id": "cci",
            "indicator_params": {"period": 10},
            "position_rule": {"type": "threshold", "threshold": 0, "direction": "above"},
            "execution_delay": 1,
            "transaction_costs_bps": 5,
            "leverage": {"mode": "none"},
        },
        data=adjusted_frame(),
    )

    assert result["bar_count"] == 80
    assert set(result["metrics"]) == {"strategy", "buyhold"}
    assert result["metrics"]["strategy"]["max_dd"] <= 0
    assert "trade_count" in result["metrics"]["strategy"]
    assert "profit_factor" in result["metrics"]["strategy"]
    assert "max_dd_duration" in result["metrics"]["strategy"]


def test_server_uses_independent_default_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call: dict[str, Any] = {}
    monkeypatch.delenv("FM_DATA_SERVER_PORT", raising=False)
    monkeypatch.setenv("FM_DATA_SERVER_FOREGROUND", "1")
    monkeypatch.setattr(server.uvicorn, "run", lambda *args, **kwargs: call.update(kwargs))

    server.main()

    assert call["port"] == 8766
    assert call["host"] == "127.0.0.1"


def test_health_includes_managed_pid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pid_file = tmp_path / "server.pid"
    pid_file.write_text("1234", encoding="utf-8")
    monkeypatch.setenv("FM_DATA_SERVER_PID_FILE", str(pid_file))
    assert api.health()["pid"] == 1234
