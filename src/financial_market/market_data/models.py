from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from .errors import ContractError


@dataclass(frozen=True, slots=True)
class HealthStatus:
    status: str
    engine: str
    supports_date_range: bool
    pid: int | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> HealthStatus:
        try:
            status = payload["status"]
            engine = payload["engine"]
            supports_date_range = payload["supports_date_range"]
        except KeyError as exc:
            raise ContractError(f"health response missing field: {exc.args[0]}") from exc
        if not isinstance(status, str) or not isinstance(engine, str):
            raise ContractError("health status and engine must be strings")
        if not isinstance(supports_date_range, bool):
            raise ContractError("health supports_date_range must be boolean")
        pid = payload.get("pid")
        if pid is not None and (isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0):
            raise ContractError("health pid must be a positive integer or null")
        return cls(status=status, engine=engine, supports_date_range=supports_date_range, pid=pid)


@dataclass(frozen=True, slots=True)
class OHLCVBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> OHLCVBar:
        try:
            timestamp_ms = payload["t"]
            open_price = payload["o"]
            high = payload["h"]
            low = payload["l"]
            close = payload["c"]
            volume = payload["v"]
        except KeyError as exc:
            raise ContractError(f"OHLCV row missing field: {exc.args[0]}") from exc
        if isinstance(timestamp_ms, bool) or not isinstance(timestamp_ms, int):
            raise ContractError("OHLCV timestamp must be integer milliseconds")
        numeric = (open_price, high, low, close)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numeric):
            raise ContractError("OHLC values must be numeric")
        if isinstance(volume, bool) or not isinstance(volume, int) or volume < 0:
            raise ContractError("OHLCV volume must be a non-negative integer")
        prices = tuple(float(value) for value in numeric)
        if any(value <= 0 for value in prices):
            raise ContractError("OHLC prices must be greater than zero")
        open_value, high_value, low_value, close_value = prices
        if high_value < max(open_value, low_value, close_value):
            raise ContractError("OHLC high is below another price")
        if low_value > min(open_value, high_value, close_value):
            raise ContractError("OHLC low is above another price")
        return cls(
            timestamp=datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC),
            open=open_value,
            high=high_value,
            low=low_value,
            close=close_value,
            volume=volume,
        )


@dataclass(frozen=True, slots=True)
class OHLCVSeries:
    ticker: str
    frequency: str
    price_adjustment: str
    rows: tuple[OHLCVBar, ...]
    candle_repair_count: int = 0

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> OHLCVSeries:
        ticker = payload.get("ticker")
        frequency = payload.get("frequency")
        price_adjustment = payload.get("price_adjustment")
        candle_repair_count = payload.get("candle_repair_count", 0)
        rows = payload.get("rows")
        if not isinstance(ticker, str) or not ticker:
            raise ContractError("OHLCV ticker must be a non-empty string")
        if not isinstance(frequency, str) or not frequency:
            raise ContractError("OHLCV frequency must be a non-empty string")
        if price_adjustment != "split_and_dividend_adjusted":
            raise ContractError("OHLCV price_adjustment must be split_and_dividend_adjusted")
        if (
            isinstance(candle_repair_count, bool)
            or not isinstance(candle_repair_count, int)
            or candle_repair_count < 0
        ):
            raise ContractError("OHLCV candle_repair_count must be a non-negative integer")
        if not isinstance(rows, list):
            raise ContractError("OHLCV rows must be a list")
        parsed_rows = tuple(OHLCVBar.from_payload(row) for row in rows if isinstance(row, dict))
        if len(parsed_rows) != len(rows):
            raise ContractError("every OHLCV row must be an object")
        adjacent_rows = zip(parsed_rows, parsed_rows[1:], strict=False)
        if any(left.timestamp >= right.timestamp for left, right in adjacent_rows):
            raise ContractError("OHLCV rows must be strictly chronological")
        return cls(
            ticker=ticker,
            frequency=frequency,
            price_adjustment=price_adjustment,
            rows=parsed_rows,
            candle_repair_count=candle_repair_count,
        )


@dataclass(frozen=True, slots=True)
class BacktestRequest:
    ticker: str
    config: dict[str, Any] = field(default_factory=dict)
    frequency: str = "1d"
    start_date: date | None = None
    end_date: date | None = None
    warmup_start_date: date | None = None
    include_returns: bool = False
    include_positions: bool = False

    def to_payload(self) -> dict[str, Any]:
        if not self.ticker.strip():
            raise ValueError("ticker cannot be empty")
        if not self.frequency.strip():
            raise ValueError("frequency cannot be empty")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date cannot be after end_date")
        if self.warmup_start_date and self.start_date and self.warmup_start_date > self.start_date:
            raise ValueError("warmup_start_date cannot be after start_date")
        payload: dict[str, Any] = {
            "ticker": self.ticker.strip(),
            "frequency": self.frequency.strip(),
            "config": self.config,
            "include_returns": self.include_returns,
            "include_positions": self.include_positions,
        }
        for key in ("start_date", "end_date", "warmup_start_date"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value.isoformat()
        return payload


@dataclass(frozen=True, slots=True)
class BacktestResult:
    bar_count: int
    metrics: dict[str, dict[str, Any]]
    payload: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> BacktestResult:
        bar_count = payload.get("bar_count")
        metrics = payload.get("metrics")
        if isinstance(bar_count, bool) or not isinstance(bar_count, int) or bar_count < 0:
            raise ContractError("backtest bar_count must be a non-negative integer")
        if not isinstance(metrics, dict):
            raise ContractError("backtest metrics must be an object")
        for required_block in ("strategy", "buyhold"):
            if not isinstance(metrics.get(required_block), dict):
                raise ContractError(f"backtest metrics.{required_block} must be an object")
        return cls(bar_count=bar_count, metrics=metrics, payload=payload)
