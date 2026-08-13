from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pandas as pd
import yfinance as yf


class DataError(RuntimeError):
    """Raised when an adjusted OHLCV series cannot be produced."""


_MEMORY_CACHE: dict[tuple[str, str, str], tuple[float, pd.DataFrame]] = {}


def adjust_ohlcv(raw: pd.DataFrame) -> pd.DataFrame:
    """Create one consistently split/dividend-adjusted OHLC price scale."""
    required = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise DataError(f"upstream OHLCV is missing required columns: {missing}")
    clean = raw.dropna(subset=list(required)).copy()
    if clean.empty:
        raise DataError("upstream OHLCV contains no complete rows")
    factor = (clean["Adj Close"] / clean["Close"]).replace([float("inf"), float("-inf")], pd.NA)
    if factor.isna().any() or (factor <= 0).any():
        raise DataError("OHLCV adjustment factor is missing or non-positive")
    adjusted = pd.DataFrame(index=pd.to_datetime(clean.index))
    for column in ("Open", "High", "Low", "Close"):
        adjusted[column] = clean[column] * factor
    adjusted["Volume"] = clean["Volume"].astype("int64")
    return normalize_candles(adjusted).sort_index()


def normalize_candles(frame: pd.DataFrame) -> pd.DataFrame:
    """Repair provider rows whose stated high/low does not bracket the candle prices."""
    result = frame.copy()
    required = ["Open", "High", "Low", "Close"]
    if result[required].isna().any().any():
        raise DataError("adjusted OHLCV contains missing candle prices")
    corrected_high = result[required].max(axis=1)
    corrected_low = result[required].min(axis=1)
    repaired = (result["High"] != corrected_high) | (result["Low"] != corrected_low)
    prior_repairs = result.get("CandleRepaired", pd.Series(False, index=result.index)).astype(bool)
    result["High"] = corrected_high
    result["Low"] = corrected_low
    result["CandleRepaired"] = prior_repairs | repaired
    result.attrs["candle_repair_count"] = int(result["CandleRepaired"].sum())
    return result


def filter_date_range(
    frame: pd.DataFrame,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    start = pd.Timestamp(start_date) if start_date is not None else None
    end = pd.Timestamp(end_date) if end_date is not None else None
    if start is not None and end is not None and start > end:
        raise ValueError("start_date must be on or before end_date")
    result = frame
    if start is not None:
        result = result.loc[result.index >= start]
    if end is not None:
        result = result.loc[result.index <= end]
    if result.empty:
        raise DataError(
            f"no OHLCV data in range {start_date or 'beginning'} to {end_date or 'latest'}"
        )
    return result.copy()


def load_adjusted_ohlcv(
    ticker: str,
    frequency: str = "1d",
    *,
    cache_dir: Path | None = None,
    ttl_hours: float = 24,
) -> pd.DataFrame:
    if frequency not in {"1d", "1wk", "1mo"}:
        raise ValueError("frequency must be one of: 1d, 1wk, 1mo")
    ticker = ticker.strip()
    if not ticker:
        raise ValueError("ticker cannot be empty")
    root = cache_dir or Path(os.getenv("FM_DATA_SERVER_CACHE_DIR", "data/cache/market_data"))
    root.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{ticker}_{frequency}")
    path = root / f"{safe_name}.csv.gz"
    key = (ticker.upper(), frequency, str(path.resolve()))
    now = time.time()
    memory = _MEMORY_CACHE.get(key)
    if memory and now - memory[0] <= ttl_hours * 3600:
        return memory[1].copy()
    if path.exists() and now - path.stat().st_mtime <= ttl_hours * 3600:
        cached = normalize_candles(pd.read_csv(path, index_col="Date", parse_dates=["Date"]))
        _MEMORY_CACHE[key] = (now, cached)
        return cached.copy()

    raw = yf.download(
        ticker,
        period="max",
        interval=frequency,
        auto_adjust=False,
        progress=False,
        group_by="column",
    )
    if raw is None or raw.empty:
        raise DataError(f"no OHLCV data returned for ticker {ticker!r}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    adjusted = adjust_ohlcv(raw)
    adjusted.to_csv(path, index_label="Date", compression="gzip")
    _MEMORY_CACHE[key] = (now, adjusted)
    return adjusted.copy()
