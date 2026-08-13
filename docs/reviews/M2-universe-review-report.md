# M2 — SGX universe review report

## Status

`READY FOR REVIEW` — this is a review report, not a closure record. M2 remains open until
the project owner explicitly approves it.

## Delivered scope

- Loaded 42 securities from `config/universe_sgx.csv`.
- Validated every `.SI` provider symbol through the FinancialMarket data server before
  persisting records.
- Stored identity, sector, instrument type, source notes, and daily data coverage in SQLite.
- Added `fm universe validate` and `fm universe load` commands.
- Added no candidate ranking, screening, signal, or trade-selection logic.

## Live WSL Ubuntu evidence

- Date of validation: 2026-08-12.
- 42 of 42 configured provider symbols returned adjusted daily OHLCV and were persisted.
- Oldest available first date: 2000-01-03 (`BSL`).
- Minimum daily bar count: 1,189 (`SRT`); no security falls below 120 bars.
- All 42 latest dates: 2026-08-11; therefore the data was one calendar day old at review.
- Instrument mix: 24 equities, 14 REITs, 4 ETFs.
- Largest stored candle-repair count: 2; no security exceeds 5 repairs.

## Candle-repair meaning

`candle_repair_count` is not gap filling. It is the number of upstream provider candles
whose stated High or Low did not bracket that candle's Open and Close. The data server
normalizes High to the maximum and Low to the minimum of O/H/L/C for those specific rows,
then reports the count. It does not create a missing date, interpolate a price, or change
volume. The count is recorded per security in `metadata_json.data_coverage`.

## Proposed M3 eligibility policy

The proposed policy is captured in
`config/screening_eligibility_sgx.json`; M3 must implement it as a deterministic,
reason-coded pre-screen gate:

| Check | Rule | Current M2 result |
| --- | --- | --- |
| Daily history | At least 120 bars | All 42 pass |
| Candle repairs | At most 5 | All 42 pass; maximum is 2 |
| Freshness | Latest bar no more than 3 calendar days old | All 42 pass at M2 validation |
| Price scale | `split_and_dividend_adjusted` required | All 42 pass |
| ETF policy | Exclude pending a separate validated policy | 4 excluded in M3 |
| REIT policy | Eligible using the same initial thresholds as equities | 14 eligible; type must be reported |

REIT-specific technical thresholds are intentionally not proposed for M3: there is no
out-of-sample evidence yet that would justify separate calibrated values. M3 will retain
instrument type in its report so M9 can evaluate whether a later, evidence-based split is
warranted.

## Corrected universe symbols

- Frasers Centrepoint Trust: `J61U` corrected to `J69U`.
- Suntec REIT: `MRT` corrected to `T82U`.
- Raffles Medical Group: `BS0` corrected to `BSL`.

## Test coverage and deliberate gaps

The full project is 77% line coverage because it includes earlier data-server/backtest
modules. The M2 loader itself is 89% covered. Tests cover valid parsing, duplicate symbols,
provider mapping, data coverage, persistence/upsert, atomic no-write behavior when provider
validation fails, CLI validation, and offline loading.

The remaining M2 loader branches are defensive OS/SQLite error paths and malformed-input
variants beyond the representative cases. They are now documented below and will be
expanded before any external/untrusted universe source is accepted. M2 accepts only the
checked-in, reviewed CSV.

## Non-blocking environment note

The WSL test suite produces one upstream Starlette `TestClient` deprecation warning for
the installed HTTPX integration. It does not affect the live FastAPI server.
