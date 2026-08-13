from __future__ import annotations

import math
import os
from datetime import date
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .backtest import run_backtest
from .data import DataError, filter_date_range, load_adjusted_ohlcv


def _managed_pid() -> int | None:
    pid_file = os.getenv("FM_DATA_SERVER_PID_FILE", "data/fm-data-server.pid")
    try:
        with open(pid_file, encoding="utf-8") as handle:
            pid = int(handle.read().strip())
    except (FileNotFoundError, ValueError, OSError):
        return None
    return pid if pid > 0 else None


class BacktestRequest(BaseModel):
    ticker: str
    frequency: str = "1d"
    start_date: date | None = None
    end_date: date | None = None
    warmup_start_date: date | None = None
    include_returns: bool = False
    include_positions: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


app = FastAPI(title="FinancialMarket Data Server", version="1.0.0")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, pd.Series):
        return [
            {"date": str(index.date()), "value": _json_safe(float(item))}
            for index, item in value.items()
        ]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "engine": "financial_market",
        "supports_date_range": True,
        "price_adjustment": "split_and_dividend_adjusted",
        "pid": _managed_pid(),
    }


@app.get("/api/ohlcv")
def ohlcv(
    ticker: str,
    frequency: str = Query("1d"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
) -> dict[str, Any]:
    try:
        frame = filter_date_range(load_adjusted_ohlcv(ticker, frequency), start_date, end_date)
        return {
            "ticker": ticker,
            "frequency": frequency,
            "price_adjustment": "split_and_dividend_adjusted",
            "candle_repair_count": int(
                frame.get("CandleRepaired", pd.Series(False, index=frame.index)).sum()
            ),
            "rows": [
                {
                    "t": int(index.value // 1_000_000),
                    "o": float(row["Open"]),
                    "h": float(row["High"]),
                    "l": float(row["Low"]),
                    "c": float(row["Close"]),
                    "v": int(row["Volume"]),
                }
                for index, row in frame.iterrows()
            ],
        }
    except (ValueError, DataError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/backtest")
def backtest(request: BacktestRequest) -> dict[str, Any]:
    try:
        result = run_backtest(
            request.ticker,
            request.frequency,
            request.config,
            start_date=str(request.start_date) if request.start_date else None,
            end_date=str(request.end_date) if request.end_date else None,
            warmup_start_date=(
                str(request.warmup_start_date) if request.warmup_start_date else None
            ),
        )
        if not request.include_returns:
            result.pop("returns", None)
        if not request.include_positions:
            result.pop("positions", None)
        return _json_safe(result)
    except (ValueError, DataError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
