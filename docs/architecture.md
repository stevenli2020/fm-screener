# Architecture

## Principles

1. Deterministic code owns screening, portfolio constraints, and audit records.
2. AI may summarize sourced evidence but cannot override mechanical rules.
3. Phase 1 has no broker order capability.
4. External services are accessed through narrow adapters.
5. Dates, timestamps, source provenance, and rejection reasons remain auditable.
6. Research and backtests must prevent look-ahead leakage.

## Components

```text
FinancialMarket data server (port 8766)
      |
      v
M2 SGX universe loader ----> deterministic Phase A screener (M3)
      |                              |
      v                              |
SQLite securities + coverage --------+
                                      |
public evidence sources (M4) --------+--> thesis CLI (M5)
                                      |
portfolio ledger (M6) ---------------+--> Phase B manual ticket (M7)
                                               |
                                               v
                                      report and audit log (M8)
```

`DataServerClient` is the only application component allowed to depend on the HTTP wire
format. Application services consume domain objects such as `OHLCVSeries`, permitting a
future provider change without rewriting the screener.

M4's SGX adapter follows a similarly narrow boundary. It maps M3 symbols to targeted SGX
listing filters, parses each matched detail page deterministically, and emits compact JSON
sections plus cached attachment provenance. `news_feed.json` is the authoritative M5
contract. Per-announcement Markdown is derived for human review; announcement-page
snapshots are not retained. PDFs and page-delimited extracted text are supporting evidence,
not summaries.

## Data ownership

- This project owns upstream retrieval, adjusted market data, indicator backtests, the SGX
  security master, screening runs, evidence, proposals,
  portfolio transactions and position snapshots, manual trade tickets, and audit events.
- SQLite is the Phase 1 local system of record. Generated reports are derived artifacts.
- Cached SGX attachments are content-addressed by recorded SHA-256 hashes and organized by
  stable SGX source ID. Original URLs remain part of the record.

## Configuration

Runtime configuration is read from `FM_*` environment variables. `.env.example` contains
non-secret examples; `.env` is ignored. Invalid URLs, timeouts, retry counts, and cache
settings fail during settings construction.

## Failure policy

- HTTP 4xx responses fail immediately and are not retried.
- connection errors, timeouts, HTTP 429, and HTTP 5xx responses are retried according to
  configuration, then reported as dependency failures.
- malformed JSON or a response that violates the expected contract fails closed.
- repeated OHLCV reads may use a short in-process cache; no cache survives a process
  restart, and callers can force a refresh.

## OHLCV adjustment contract

The FinancialMarket `/api/ohlcv` response provides consistently split/dividend-adjusted
Open/High/Low/Close and raw volume. It must declare
`price_adjustment: "split_and_dividend_adjusted"`. The adapter fails closed if this marker
is absent, preventing an older mixed-scale server from feeding Donchian, ATR, stochastic,
or other candle-based calculations.
