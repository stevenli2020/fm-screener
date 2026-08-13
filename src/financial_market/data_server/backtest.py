from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .data import filter_date_range, load_adjusted_ohlcv


def _true_range(frame: pd.DataFrame) -> pd.Series:
    previous_close = frame["Close"].shift(1)
    return pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - previous_close).abs(),
            (frame["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def calculate_indicator(
    frame: pd.DataFrame, indicator_id: str, params: dict[str, Any] | None = None
) -> pd.Series:
    params = params or {}
    key = indicator_id.lower()
    close = frame["Close"]
    if key == "rsi":
        period = int(params.get("period", 14))
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
        loss = -delta.clip(upper=0).ewm(alpha=1 / period, adjust=False).mean()
        result = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    elif key == "bollinger":
        period = int(params.get("period", 20))
        deviation = float(params.get("std_dev", 2))
        middle = close.rolling(period).mean()
        width = deviation * close.rolling(period).std()
        result = (close - (middle - width)) / (2 * width).replace(0, np.nan)
    elif key == "ma_crossover":
        fast = int(params.get("fast_period", 10))
        slow = int(params.get("slow_period", 30))
        result = close.rolling(fast).mean() - close.rolling(slow).mean()
    elif key == "atr":
        period = int(params.get("period", 14))
        result = _true_range(frame).ewm(alpha=1 / period, adjust=False).mean()
    elif key == "cci":
        period = int(params.get("period", 20))
        typical = (frame["High"] + frame["Low"] + close) / 3
        mean = typical.rolling(period).mean()
        deviation = typical.rolling(period).apply(
            lambda values: float(np.mean(np.abs(values - np.mean(values)))), raw=True
        )
        result = (typical - mean) / (0.015 * deviation).replace(0, np.nan)
    elif key == "obv":
        direction = np.sign(close.diff()).fillna(0)
        result = (direction * frame["Volume"]).cumsum()
    elif key == "stochastic":
        period = int(params.get("k_period", 14))
        low = frame["Low"].rolling(period).min()
        high = frame["High"].rolling(period).max()
        result = 100 * (close - low) / (high - low).replace(0, np.nan)
    elif key == "vwap_dev":
        period = int(params.get("period", 20))
        typical = (frame["High"] + frame["Low"] + close) / 3
        volume = frame["Volume"]
        vwap = (typical * volume).rolling(period).sum() / volume.rolling(period).sum()
        result = (close - vwap) / vwap
    elif key == "adx":
        period = int(params.get("period", 14))
        up = frame["High"].diff()
        down = -frame["Low"].diff()
        plus_dm = up.where((up > down) & (up > 0), 0.0)
        minus_dm = down.where((down > up) & (down > 0), 0.0)
        atr = _true_range(frame).ewm(alpha=1 / period, adjust=False).mean()
        plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
        minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        result = dx.ewm(alpha=1 / period, adjust=False).mean()
    else:
        raise ValueError(f"unsupported indicator {indicator_id!r}")
    return pd.Series(result, index=frame.index, name=key, dtype=float)


def apply_rule(indicator: pd.Series, rule: dict[str, Any]) -> pd.Series:
    kind = rule.get("type")
    direction = rule.get("direction", "above")
    if direction not in {"above", "below"}:
        raise ValueError("direction must be 'above' or 'below'")
    if kind == "threshold":
        condition = indicator > float(rule["threshold"])
        valid = indicator.notna()
    elif kind == "crossover":
        reference = indicator.rolling(int(rule.get("ma_window", 20))).mean()
        condition = indicator > reference
        valid = indicator.notna() & reference.notna()
    elif kind == "percentile":
        lookback = int(rule.get("lookback", 52))
        percentile = float(rule.get("percentile", 70))
        rank = indicator.rolling(lookback).apply(
            lambda values: float((values <= values[-1]).mean() * 100), raw=True
        )
        condition = rank >= percentile
        valid = indicator.notna() & rank.notna()
    else:
        raise ValueError(f"unsupported position rule {kind!r}")
    selected = condition if direction == "above" else ~condition
    return (valid & selected).fillna(False).astype(bool)


def _regime(frame: pd.DataFrame, config: dict[str, Any] | None) -> pd.Series:
    if not config:
        return pd.Series(1.0, index=frame.index)
    kind = config.get("type")
    if kind == "trend":
        window = int(config.get("sma_window", 200))
        return (frame["Close"] > frame["Close"].rolling(window).mean()).fillna(False).astype(float)
    if kind == "volatility":
        atr = calculate_indicator(frame, "atr", {"period": config.get("atr_period", 14)})
        return (
            ((atr / frame["Close"] * 100) < float(config.get("max_atr_pct", 3)))
            .fillna(False)
            .astype(float)
        )
    raise ValueError(f"unsupported regime filter {kind!r}")


def _leverage(returns: pd.Series, config: dict[str, Any] | None, annualization: int) -> pd.Series:
    config = config or {"mode": "none"}
    mode = config.get("mode", "none")
    if mode == "none":
        return pd.Series(1.0, index=returns.index)
    if mode == "fixed":
        return pd.Series(float(config.get("multiplier", 1)), index=returns.index).clip(upper=5)
    if mode == "target_vol":
        target = float(config.get("target_vol", 0.15))
        volatility = returns.rolling(63, min_periods=20).std() * math.sqrt(annualization)
        return (target / volatility.replace(0, np.nan)).clip(upper=5).fillna(1.0)
    raise ValueError(f"unsupported leverage mode {mode!r}")


def _summarize(returns: pd.Series, positions: pd.Series, annualization: int) -> dict[str, Any]:
    returns = returns.fillna(0).astype(float)
    equity = (1 + returns).cumprod()
    drawdown = equity / equity.cummax() - 1 if len(equity) else pd.Series(dtype=float)
    volatility = returns.std(ddof=1)
    downside = returns.where(returns < 0, 0).std(ddof=1)
    sharpe = math.sqrt(annualization) * returns.mean() / volatility if volatility else 0.0
    sortino = math.sqrt(annualization) * returns.mean() / downside if downside else 0.0
    years = max(len(returns) / annualization, 1 / annualization)
    cagr = float(equity.iloc[-1] ** (1 / years) - 1) if len(equity) else 0.0
    trades = _trade_returns(positions, returns)
    gains = sum(value for value in trades if value > 0)
    losses = sum(value for value in trades if value < 0)
    max_drawdown = float(drawdown.min()) if len(drawdown) else 0.0
    return {
        "cagr": float(cagr),
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "calmar": cagr / abs(max_drawdown) if max_drawdown else 0.0,
        "max_dd": max_drawdown,
        "omega": gains / abs(losses) if losses else (float("inf") if gains else 0.0),
        "recovery_factor": (
            float(equity.iloc[-1] - 1) / abs(max_drawdown) if max_drawdown else 0.0
        ),
        "trade_count": len(trades),
        "win_rate": (sum(value > 0 for value in trades) / len(trades) if trades else 0.0),
        "profit_factor": gains / abs(losses) if losses else (float("inf") if gains else 0.0),
        "avg_trade_duration_bars": (float(positions.gt(0).sum() / len(trades)) if trades else 0.0),
        "max_dd_duration": _max_drawdown_duration(equity),
        "pct_invested": float(positions.gt(0).mean()) if len(positions) else 0.0,
    }


def _trade_returns(positions: pd.Series, returns: pd.Series) -> list[float]:
    active = False
    compounded = 1.0
    trades: list[float] = []
    for position, value in zip(positions.fillna(0), returns.fillna(0), strict=True):
        if position > 0 and not active:
            active = True
            compounded = 1.0
        if active:
            compounded *= 1 + float(value)
        if active and position <= 0:
            trades.append(compounded - 1)
            active = False
    if active:
        trades.append(compounded - 1)
    return trades


def _max_drawdown_duration(equity: pd.Series) -> int:
    peak = -math.inf
    current = 0
    maximum = 0
    for value in equity:
        if value >= peak:
            peak = float(value)
            current = 0
        else:
            current += 1
            maximum = max(maximum, current)
    return maximum


def run_backtest(
    ticker: str,
    frequency: str,
    config: dict[str, Any],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    warmup_start_date: str | None = None,
    data: pd.DataFrame | None = None,
) -> dict[str, Any]:
    if (
        warmup_start_date
        and start_date
        and pd.Timestamp(warmup_start_date) > pd.Timestamp(start_date)
    ):
        raise ValueError("warmup_start_date must be on or before start_date")
    frame = data.copy() if data is not None else load_adjusted_ohlcv(ticker, frequency)
    frame = filter_date_range(frame, warmup_start_date or start_date, end_date)
    annualization = {"1d": 252, "1wk": 52, "1mo": 12}[frequency]
    indicator = calculate_indicator(frame, config["indicator_id"], config.get("indicator_params"))
    signal = apply_rule(indicator, config["position_rule"]).astype(float)
    position = (
        (signal * _regime(frame, config.get("regime_filter")))
        .shift(int(config.get("execution_delay", 1)))
        .fillna(0.0)
    )
    asset_returns = frame["Close"].pct_change().fillna(0.0)
    sized = position * _leverage(asset_returns, config.get("leverage"), annualization)
    costs = (
        sized.diff().abs().fillna(sized.abs())
        * float(config.get("transaction_costs_bps", 0))
        / 10000
    )
    strategy = sized * asset_returns - costs
    if start_date and warmup_start_date:
        mask = strategy.index >= pd.Timestamp(start_date)
        strategy, asset_returns, sized = (
            strategy.loc[mask],
            asset_returns.loc[mask],
            sized.loc[mask],
        )
    return {
        "metrics": {
            "strategy": _summarize(strategy, sized, annualization),
            "buyhold": _summarize(
                asset_returns, pd.Series(1.0, index=asset_returns.index), annualization
            ),
        },
        "bar_count": len(strategy),
        "returns": {"strategy": strategy, "buyhold": asset_returns},
        "positions": {"strategy": sized},
    }
