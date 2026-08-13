# FinancialMarket data-server contract

The data server is implemented inside this repository under
`financial_market.data_server`. It does not import, start, write to, or otherwise depend
on the separate `mh_test` project.

## Runtime isolation

- default address: `http://127.0.0.1:8766`
- configurable port: `FM_DATA_SERVER_PORT`
- local cache: `data/cache/market_data`
- cache format: compressed CSV, not executable serialization
- upstream source: yfinance with explicit adjustment performed by this server

## WSL Ubuntu operation

Run the server and test client from WSL, using the Linux virtual-environment executables:

```bash
.venv/bin/fm-data-server
# Separate terminal
.venv/bin/fm health
```

The default `127.0.0.1` binding confines the server to the WSL instance. Keep it that way
for testing. Exposing it on `0.0.0.0` requires an explicit deployment and network-security
decision.

## Required OHLCV semantics

- endpoint: `GET /api/ohlcv`
- `o`, `h`, `l`, and `c`: split/dividend-adjusted prices on one consistent scale
- `v`: raw volume
- response marker: `price_adjustment: "split_and_dividend_adjusted"`
- `candle_repair_count`: provider candles normalized because High or Low did not bracket
  Open and Close

The project-local cache persists the per-row repair flag, so `candle_repair_count` remains
auditable after a data-server restart.

The client rejects missing or different markers. M3 must use only this adjusted feed for
Donchian and other technical calculations; raw and adjusted prices must never be mixed.

## Endpoints

- `GET /api/health`
- `GET /api/ohlcv`
- `POST /api/backtest`

The API shape is intentionally familiar to users of `mh_test`, but its implementation,
dependencies, process, port, and cache are owned independently by FinancialMarket.
