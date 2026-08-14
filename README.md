# Financial Market SGX

An auditable, manual-execution SGX screening and research application inspired by
FriesTrader. Phase 1 produces research outputs and trade tickets only; it cannot place
broker orders.

## Current scope

- M0: project foundation, configuration, SQLite schema, and test conventions.
- M1: an independent adjusted market-data/backtest server and typed HTTP adapter.
- M2: validated SGX universe and deterministic eligibility policy.
- M3: deterministic Phase A screening, ranking, JSON/Markdown output, and audit records.
- M4: SGX announcement ingestion, hash deduplication, availability logging, and M5 feed.
- Later milestones: thesis consolidation, portfolio controls, and morning revalidation.

The `FriesTrader/` directory is retained as a reference input and is not application code.

## WSL Ubuntu setup and testing

Run these commands inside WSL Ubuntu. If Python virtual environments are unavailable,
install the Ubuntu package once with `sudo apt update && sudo apt install python3-venv`.

```bash
cd /mnt/d/Projects/FinancialMarket
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev,server]'
cp .env.example .env
set -a && source .env && set +a
```

The application deliberately does not load `.env` itself. The `source` command above
makes the non-secret configuration available to the current WSL shell; use the same
command in each terminal that needs custom settings.

Start this project's data server from WSL. It listens on port `8766` by default, runs
quietly in the background, and replaces the previous managed instance. Runtime output
is stored in `data/fm-data-server.log`; the managed PID is stored in
`data/fm-data-server.pid`:

```bash
cd /mnt/d/Projects/FinancialMarket
set -a && source .env && set +a
.venv/bin/fm-data-server
```

Then verify connectivity and fetch data:

```bash
cd /mnt/d/Projects/FinancialMarket
set -a && source .env && set +a
.venv/bin/fm health
.venv/bin/fm ohlcv D05.SI --start-date 2025-01-01 --end-date 2025-01-31
```

The server produces consistently split/dividend-adjusted O/H/L/C and declares that
contract in every OHLCV response. The client rejects a missing or different declaration.

Initialize the local database:

```bash
.venv/bin/fm init-db
```

Mechanical Phase 1 limits live in `config/risk_rules_sgx.json`. The validated defaults
cap a position at 20% of account value, allow four concurrent positions, retain a 10%
cash buffer, and apply 5% daily and 10% weekly loss limits. Execution mode is locked to
`manual_only`.

```bash
.venv/bin/fm validate-config
```

## M2: SGX universe

Validate the configuration file without writing to the database:

```bash
.venv/bin/fm universe validate
```

Load the configured securities only after each `.SI` symbol has returned adjusted daily
OHLCV from the FinancialMarket data server:

```bash
.venv/bin/fm universe load
```

This stores security identity, sector, instrument type, source notes, and data coverage in
SQLite. It does not calculate or rank any trading signal.

The next milestone's deterministic data-quality and instrument eligibility policy is
versioned in `config/screening_eligibility_sgx.json`. It is documented for review now but
will not be executed until M3 is explicitly authorized.

## M4: SGX announcements

M4 consumes the matched candidates written by M3 and queries the public SGX Company
Announcements pages once per mapped company or security over a short inclusive date
window. The checked-in filter policy controls the exact SGX autocomplete mapping and
retained announcement categories. No AI classification, relevance filtering, or
sentiment logic is applied.

```bash
set -a && source .env && set +a
.venv/bin/fm news collect --run-date 2026-08-13
```

The default input is `reports/generated/pending_candidates.json`. Outputs are
`reports/generated/news_feed.json`, a dated Markdown report, compact source records under
`reports/generated/extraction/records/`, and cached attachments under
`reports/generated/extraction/attachments/<source-id>/`. JSON is the authoritative M5
agent input; Markdown is a human-review derivative. Announcement fields and tables are
stored once in `announcement_sections`. M4 does not save announcement-page snapshots.

PDF attachments are cached with their original SGX URL, local path, byte count, and
SHA-256 hash. When WSL `pdftotext` is available, M4 also creates page-delimited text beside
the PDF for M5. Stable SGX source IDs and content hashes make repeat collection idempotent
while retaining replacement announcements. Every logical collection attempt is recorded
in `news_api_log`, including partial or attachment failures.

The endpoint and pacing controls are configured with `FM_SGX_NEWS_API_URL`,
`FM_SGX_NEWS_FILTERS_PATH`, `FM_SGX_NEWS_MAX_PAGES`, and
`FM_SGX_NEWS_REQUEST_PACING_SECONDS`. Records are retained; Phase 1 performs no
automatic purge. Headless Firefox is the validated WSL browser; historical Chromium/Akamai
failures remain in the audit record. The seven-distinct-day operational gate remains in
progress; see the M4 review report.

Run quality checks:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check src tests
.venv/bin/python -m ruff format --check src tests
```
```

## Safety boundary

No broker SDK, credentials, or order endpoint is included. Provider errors and malformed
responses fail closed with explicit application exceptions. Market information is for
research and must not be treated as financial advice.
