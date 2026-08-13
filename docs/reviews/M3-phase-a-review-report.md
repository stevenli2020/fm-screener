# M3 Phase A screener — READY FOR REVIEW

## Delivered

- Deterministic daily screener using only the independent FinancialMarket data server and M2 SQLite universe.
- Five auditable signals: 60-day price move, 20-day median-volume multiple, 52-week high/low distance, 20-day annualized volatility, and a 55-day Donchian position.
- Eligibility checks: 120 bars, maximum five repaired candles, three-day staleness, adjusted-price contract, ETF exclusion; REITs retain the initial equity thresholds.
- `fm screening run` writes `pending_candidates.json` and a dated Markdown report; every universe record is persisted to `screening_results`.
- `fm screening dry-run --days 5` is a historical consistency replay, explicitly not a return/performance backtest.

## WSL evidence

- 46 tests passed; M3 module coverage: 87%; Ruff, compileall, and pip check passed.
- Live run (2026-08-12): universe 42, eligible/screened 38, matched 18; 4 ETFs excluded.
- Five-date replay: 2026-08-08 to 2026-08-12; each day screened 38 and matched 17, 17, 15, 18, 18 respectively.

## Self-review

- No look-ahead: every OHLCV call is constrained with `end_date=as_of`; signal windows end at that bar.
- Deterministic: universe SQL ordering and ranking tie-break by symbol.
- The 52-week condition is deliberately long-only: it means within the configured 5% of the 52-week high. The raw high/low distances remain in the audit output. The threshold key is retained for specification compatibility.

## Deferred / reviewer attention

- 18 live matches is above the specification's aspirational 2–5 range; this is a configuration calibration decision, not an implementation change. No thresholds were tuned to the observed names.
- Volatility is calculated and reported but has no selection threshold in the approved configuration.
- The first health request immediately after server launch can race startup; the subsequent screening run completed successfully. Operational runbooks should start the server before invoking the CLI.
