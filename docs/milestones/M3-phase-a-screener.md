# M3 — Phase A Screener (CLOSED)

## Approval
- **Approved**: 2026-08-13
- **Reviewer**: Claude (Advisor)
- **Status**: ✅ APPROVED

---

## Delivered

- Five deterministic signals (60d price move, volume spike, 52wk extremes, volatility, Donchian)
- Eligibility enforcement (120 bars, repair_count ≤5, staleness ≤3 days, price adjustment contract)
- `fm screening run` and `fm screening dry-run` CLI commands
- JSON output (`pending_candidates.json`) + Markdown reports + SQLite audit trail
- 46 tests, 87% coverage

---

## Calibration Applied

**Threshold tuning** (via 5-day replay):
- Iteration 1: Tightened volume_spike_min_multiple from 1.5 → 2.5
- Iteration 2: Tightened pct_from_52wk_extreme_min_pct from 5.0 → 2.5
- **Result**: 18 matches/day → target range (2–8/day) ✅

**Final Thresholds** (locked in `config/risk_rules_sgx.json`):
```json
{
  "screening": {
    "signals": {
      "price_move_60d_min_pct": 10.0,
      "price_move_60d_max_pct": 50.0,
      "volume_spike_min_multiple": 2.5,
      "pct_from_52wk_extreme_min_pct": 2.5,
      "donchian_breakout_threshold_pct": 85.0,
      "volatility_lookback_days": 20,
      "donchian_lookback_days": 55
    }
  }
}
```

---

## Known Limitations

- Volatility signal calculated but not thresholded (defer to M9 calibration post-shadow-mode)
- 52-week distance is long-only (doesn't flag breakdowns; by design)
- No correlation/diversification checks (rank by signal strength only)
- Donchian uses 55-day lookback (fixed; configurable if needed)

---

## Dependencies for Later Milestones

- **M4 (news)**: Consumes `pending_candidates.json` (matched symbol list)
- **M5 (AI thesis)**: Consumes `pending_candidates.json` + news feed
- **M7 (Phase B)**: Uses signal rankings for trade-ticket generation
- **M9 (shadow mode)**: Backtests 30–60 days to validate signal quality post-deployment

---

## Data Quality Verified

- ✅ All 42 securities pass eligibility
- ✅ Data is current (≤1 day stale)
- ✅ OHLCV is split/dividend adjusted (confirmed via M2 contract)
- ✅ Signal calculations are deterministic (5-day replay validates consistency)
- ✅ No look-ahead bias (screener uses only past/present data)

---

## Approved for M4 Start

✅ Ready to proceed with M4 (News Pipeline)
