# M3 — Phase A Screener Specification

**Status**: READY FOR IMPLEMENTATION ✅  
**Timeline**: 2–3 days  
**Owner**: Codex  
**Reviewer**: Claude  

---

## Mission

Build a **deterministic, end-of-day screener** that:
1. Loads the SGX universe (42 securities from M2)
2. Applies eligibility policy
3. Fetches OHLCV data via M1 client
4. Calculates 5 deterministic signals
5. Ranks candidates by signal strength
6. Documents rejection reasons
7. Outputs `pending_candidates.json` + markdown report

**This is NOT AI reasoning.** Pure math. Every decision must be auditable and reproducible.

---

## Scope

### ✅ In Scope
- Read universe from M2 database + apply eligibility policy
- Fetch daily OHLCV from M1 client
- Calculate 5 signals (price move, volume, 52wk extreme, volatility, Donchian)
- Rank candidates by signal strength
- Output structured JSON + markdown report
- CLI command: `fm screening run`
- Error handling for stale/missing data
- Test coverage >80%

### ❌ Out of Scope
- AI reasoning or thesis generation (M5 job)
- Machine learning or backtesting (M9 job)
- Broker order logic (manual only)
- REIT-specific thresholds (use equity rules; calibrate post-M9)
- ETF screening (already excluded by M2 policy)
- Intraday data or momentum signals

---

## 5 Signals to Calculate

### 1. 60-Day Price Move (%)
```python
def signal_price_move_60d(candles: list[OHLCV]) -> dict:
    """
    (Close_today - Close_60d_ago) / Close_60d_ago
    
    Example:
      Close 60d ago: SGD 10.00
      Close today:   SGD 11.50
      Move: +15.0%
    """
    if len(candles) < 60:
        return {"move_pct": None, "reason": "insufficient_bars"}
    
    close_60d_ago = candles[0].close
    close_today = candles[-1].close
    move_pct = ((close_today - close_60d_ago) / close_60d_ago) * 100
    
    return {
        "move_pct": round(move_pct, 2),
        "close_60d_ago": close_60d_ago,
        "close_today": close_today,
        "bar_count": len(candles)
    }
```

### 2. Volume Spike (Relative to 20-Day Median)
```python
def signal_volume_spike(candles: list[OHLCV]) -> dict:
    """
    Today_volume / median_20d_volume
    
    Example:
      Volume today: 5.0M shares
      Median 20d:   2.0M shares
      Spike: 2.5x
    """
    if len(candles) < 20:
        return {"spike_multiple": None, "reason": "insufficient_bars"}
    
    volumes = [c.volume for c in candles[-20:]]
    median_volume = sorted(volumes)[len(volumes) // 2]
    today_volume = candles[-1].volume
    
    if median_volume == 0:
        return {"spike_multiple": None, "reason": "zero_median_volume"}
    
    spike = today_volume / median_volume
    
    return {
        "spike_multiple": round(spike, 2),
        "volume_today": today_volume,
        "median_20d": median_volume,
        "bar_count": 20
    }
```

### 3. Distance from 52-Week High/Low (%)
```python
def signal_52week_extremes(candles: list[OHLCV]) -> dict:
    """
    How far current price from 52-week high/low
    
    Example:
      52wk high: SGD 15.00, 52wk low: SGD 8.00, Close: SGD 11.00
      Pct below high: 26.7%, Pct above low: 37.5%
    """
    high_52w = max(c.high for c in candles[-252:]) if len(candles) >= 252 else max(c.high for c in candles)
    low_52w = min(c.low for c in candles[-252:]) if len(candles) >= 252 else min(c.low for c in candles)
    close_today = candles[-1].close
    
    pct_below_high = ((high_52w - close_today) / high_52w) * 100 if high_52w > 0 else None
    pct_above_low = ((close_today - low_52w) / low_52w) * 100 if low_52w > 0 else None
    
    return {
        "close_today": close_today,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "pct_below_52w_high": round(pct_below_high, 2) if pct_below_high else None,
        "pct_above_52w_low": round(pct_above_low, 2) if pct_above_low else None,
        "bar_count": min(len(candles), 252)
    }
```

### 4. 20-Day Volatility (Annualized %)
```python
def signal_volatility_20d(candles: list[OHLCV]) -> dict:
    """
    Annualized volatility from 20-day returns
    
    Formula:
      1. Daily returns: (Close_t - Close_{t-1}) / Close_{t-1}
      2. Std dev of returns
      3. Annualize: stdev * sqrt(252)
    
    Example:
      Daily stdev: 1.8%, Annualized: 28.5%
    """
    import math, statistics
    
    if len(candles) < 20:
        return {"volatility_annual_pct": None, "reason": "insufficient_bars"}
    
    returns = []
    for i in range(1, min(20, len(candles))):
        prev_close = candles[i-1].close
        curr_close = candles[i].close
        if prev_close > 0:
            ret = (curr_close - prev_close) / prev_close
            returns.append(ret)
    
    if len(returns) < 2:
        return {"volatility_annual_pct": None, "reason": "insufficient_returns"}
    
    daily_vol = statistics.stdev(returns)
    annual_vol = daily_vol * math.sqrt(252)
    
    return {
        "volatility_annual_pct": round(annual_vol * 100, 2),
        "volatility_daily_pct": round(daily_vol * 100, 2),
        "bar_count": len(returns) + 1
    }
```

### 5. Donchian Breakout (55-Day Channel)
```python
def signal_donchian_breakout(candles: list[OHLCV], lookback_days: int = 55) -> dict:
    """
    Identify if price is near Donchian channel boundary
    
    Donchian:
      High = max(High over 55d)
      Low = min(Low over 55d)
    
    Example:
      55d high: SGD 12.50, 55d low: SGD 10.00, Close: SGD 12.45
      Pct of range: (12.45 - 10.00) / (12.50 - 10.00) = 98%
    
    Interpretation:
      >90% = breakout candidate (top)
      <10% = breakdown candidate (bottom)
    """
    if len(candles) < lookback_days:
        return {"donchian_high": None, "reason": "insufficient_bars"}
    
    high_55d = max(c.high for c in candles[-lookback_days:])
    low_55d = min(c.low for c in candles[-lookback_days:])
    close_today = candles[-1].close
    
    range_span = high_55d - low_55d
    if range_span == 0:
        return {"donchian_high": None, "reason": "zero_range"}
    
    pct_of_range = ((close_today - low_55d) / range_span) * 100
    
    return {
        "donchian_high": high_55d,
        "donchian_low": low_55d,
        "close_today": close_today,
        "pct_of_range": round(pct_of_range, 1),
        "lookback_days": lookback_days,
        "bar_count": lookback_days
    }
```

---

## Signal Thresholds (In config/risk_rules_sgx.json)

```json
{
  "screening": {
    "signals": {
      "price_move_60d_min_pct": 10.0,
      "price_move_60d_max_pct": 50.0,
      "volume_spike_min_multiple": 1.5,
      "pct_from_52wk_extreme_min_pct": 5.0,
      "donchian_breakout_threshold_pct": 85.0,
      "volatility_lookback_days": 20,
      "donchian_lookback_days": 55
    }
  }
}
```

---

## Screening Workflow

```python
def phase_a_screening(run_date: date) -> dict:
    """Daily end-of-day screening."""
    
    # 1. Load universe + eligibility policy
    securities = load_universe_from_db()
    eligible = apply_eligibility_policy(securities)
    
    # 2. Fetch OHLCV + calculate signals
    candidates = []
    rejected = []
    
    for security in eligible:
        try:
            ohlcv = client.get_ohlcv(security.provider_symbol, days=60)
        except MarketDataError as exc:
            rejected.append({
                "symbol": security.symbol,
                "reason": "data_fetch_failed",
                "error": str(exc)
            })
            continue
        
        signals = {
            "price_move_60d": signal_price_move_60d(ohlcv.rows),
            "volume_spike": signal_volume_spike(ohlcv.rows),
            "52wk_extremes": signal_52week_extremes(ohlcv.rows),
            "volatility_20d": signal_volatility_20d(ohlcv.rows),
            "donchian_55d": signal_donchian_breakout(ohlcv.rows, lookback_days=55)
        }
        
        matched_signals = evaluate_signals(signals, thresholds)
        
        if matched_signals:
            candidates.append({
                "symbol": security.symbol,
                "signals": signals,
                "matched_signals": matched_signals
            })
        else:
            rejected.append({
                "symbol": security.symbol,
                "reason": "no_signal_match",
                "signals": signals
            })
    
    # 3. Rank + output
    ranked = rank_candidates(candidates)
    return {
        "run_date": run_date.isoformat(),
        "candidates_matched": len(ranked),
        "ranked_candidates": ranked,
        "rejected": rejected
    }
```

### Ranking Logic

```python
def rank_candidates(candidates: list[dict]) -> list[dict]:
    """
    Sort by:
    1. Signal count (more signals = higher conviction)
    2. Distance from 52wk extreme
    3. Volume spike magnitude
    4. Symbol (tiebreaker)
    """
    def score(candidate):
        signal_count = len(candidate["matched_signals"])
        extremes = candidate["signals"]["52wk_extremes"]
        pct_extreme = max(
            extremes.get("pct_below_52w_high", 0),
            extremes.get("pct_above_52w_low", 0)
        )
        volume_spike = candidate["signals"]["volume_spike"].get("spike_multiple", 1.0)
        
        return (
            -signal_count,
            -pct_extreme,
            -volume_spike,
            candidate["symbol"]
        )
    
    return sorted(candidates, key=score)
```

---

## Outputs

### `pending_candidates.json`
```json
{
  "run_date": "2026-08-13",
  "eligible_count": 42,
  "candidates_screened": 42,
  "candidates_matched": 5,
  "ranked_candidates": [
    {
      "rank": 1,
      "symbol": "D05",
      "signals": {
        "price_move_60d": {"move_pct": 12.5},
        "volume_spike": {"spike_multiple": 2.1},
        "52wk_extremes": {"pct_below_52w_high": 5.3},
        "volatility_20d": {"volatility_annual_pct": 22.5},
        "donchian_55d": {"pct_of_range": 92.3}
      },
      "matched_signals": ["price_move_60d", "volume_spike", "pct_from_52wk_extreme", "donchian_breakout"]
    }
  ],
  "rejected": [...]
}
```

### Daily Markdown Report
- Summary (eligible count, matched count, data quality)
- Ranked candidates table (signals, thresholds, status)
- Rejected securities table (reason)
- Data quality audit (bars, repair count, dates)

---

## Implementation Checklist

- [ ] `src/financial_market/screening/signals.py` (5 signal functions)
- [ ] `src/financial_market/screening/screener.py` (main logic)
- [ ] `src/financial_market/screening/ranker.py` (ranking)
- [ ] `src/financial_market/screening/reporter.py` (report generation)
- [ ] CLI: `fm screening run` command
- [ ] Config: Add `screening.signals` to `risk_rules_sgx.json`
- [ ] Tests: >80% coverage, edge cases (low bars, zero volume, etc.)
- [ ] Self-review: Look-ahead bias, determinism, correctness

---

## Success Criteria (Gate for M4)

✅ **Functionality**:
- Screener runs: `fm screening run` (no errors)
- Outputs valid `pending_candidates.json`
- Generates markdown report
- Produces 2–8 candidates per run

✅ **Quality**:
- All calculations auditable
- No look-ahead bias
- All 42 securities tested; rejection reasons documented

✅ **Testing**:
- ≥80% code coverage
- Edge cases covered
- Integration test validates end-to-end

✅ **Metrics**:
- 1–2 weeks dry-run (validate signal consistency)
- Report: Match rate, data quality, signal distribution

---

**Reference**: `docs/M2-universe-review-report.md` (data coverage metadata)
