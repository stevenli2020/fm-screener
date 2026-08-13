from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from typing import Any

from financial_market.market_data.models import OHLCVBar


def signal_price_move_60d(candles: Sequence[OHLCVBar]) -> dict[str, Any]:
    if len(candles) < 60:
        return {"move_pct": None, "reason": "insufficient_bars"}
    old, current = candles[-60].close, candles[-1].close
    if old <= 0:
        return {"move_pct": None, "reason": "invalid_start_close"}
    return {
        "move_pct": round((current - old) / old * 100, 2),
        "close_60d_ago": old,
        "close_today": current,
        "bar_count": 60,
    }


def signal_volume_spike(candles: Sequence[OHLCVBar]) -> dict[str, Any]:
    if len(candles) < 20:
        return {"spike_multiple": None, "reason": "insufficient_bars"}
    window = [bar.volume for bar in candles[-20:]]
    median = statistics.median(window)
    if median == 0:
        return {"spike_multiple": None, "reason": "zero_median_volume"}
    return {
        "spike_multiple": round(candles[-1].volume / median, 2),
        "volume_today": candles[-1].volume,
        "median_20d": median,
        "bar_count": 20,
    }


def signal_52week_extremes(candles: Sequence[OHLCVBar]) -> dict[str, Any]:
    if not candles:
        return {"pct_below_52w_high": None, "reason": "insufficient_bars"}
    window = candles[-252:]
    high, low, close = (
        max(bar.high for bar in window),
        min(bar.low for bar in window),
        candles[-1].close,
    )
    below = (high - close) / high * 100 if high > 0 else None
    above = (close - low) / low * 100 if low > 0 else None
    return {
        "close_today": close,
        "high_52w": high,
        "low_52w": low,
        "pct_below_52w_high": round(below, 2) if below is not None else None,
        "pct_above_52w_low": round(above, 2) if above is not None else None,
        "bar_count": len(window),
    }


def signal_volatility_20d(candles: Sequence[OHLCVBar], lookback_days: int = 20) -> dict[str, Any]:
    if len(candles) < lookback_days:
        return {"volatility_annual_pct": None, "reason": "insufficient_bars"}
    window = candles[-lookback_days:]
    returns = [
        (right.close - left.close) / left.close
        for left, right in zip(window, window[1:], strict=False)
        if left.close > 0
    ]
    if len(returns) < 2:
        return {"volatility_annual_pct": None, "reason": "insufficient_returns"}
    daily = statistics.stdev(returns)
    return {
        "volatility_annual_pct": round(daily * math.sqrt(252) * 100, 2),
        "volatility_daily_pct": round(daily * 100, 2),
        "bar_count": len(returns) + 1,
    }


def signal_donchian_breakout(
    candles: Sequence[OHLCVBar], lookback_days: int = 55
) -> dict[str, Any]:
    if len(candles) < lookback_days:
        return {"donchian_high": None, "reason": "insufficient_bars"}
    window = candles[-lookback_days:]
    high, low, close = (
        max(bar.high for bar in window),
        min(bar.low for bar in window),
        candles[-1].close,
    )
    span = high - low
    if span == 0:
        return {"donchian_high": None, "reason": "zero_range"}
    return {
        "donchian_high": high,
        "donchian_low": low,
        "close_today": close,
        "pct_of_range": round((close - low) / span * 100, 1),
        "lookback_days": lookback_days,
        "bar_count": lookback_days,
    }
