# M1 — Data-server integration closure record

## Approval

- Status: Closed
- Approved by: project owner
- Approval date: 2026-08-11

## Delivered scope

- FinancialMarket-owned FastAPI data server on default port `8766`.
- Health, adjusted OHLCV, and backtest endpoints.
- Typed HTTP client with retries, timeouts, short in-process cache, and fail-closed
  contract validation.
- Consistently split/dividend-adjusted O/H/L/C output, raw volume, and an explicit
  adjustment marker.
- Project-local compressed CSV data cache.
- WSL Ubuntu setup, test, and live-server instructions.

## Acceptance evidence

- Unit and integration coverage for client contracts, data adjustments, cache reload,
  server endpoints, and backtest response structure.
- WSL Ubuntu live checks confirmed health, adjusted DBS OHLCV, and backtest output through
  the typed client.
- The server is independent of the separate `mh_test` project: no runtime import, shared
  port, shared cache, or source modification.

## Decisions and limitations

- Provider candles whose High/Low do not bracket Open/Close are normalized and reported as
  `candle_repair_count`; downstream universe metadata retains the count.
- The independent backtest calculations are API-compatible but not asserted to be
  numerically identical to any external backtest implementation. M9 must independently
  validate strategy and metric behavior before comparative shadow analysis.
- The test-client dependency emits a non-blocking upstream deprecation warning under the
  current WSL dependency resolution.

