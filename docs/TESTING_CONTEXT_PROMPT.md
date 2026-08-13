# M0–M2 Testing Context Prompt

**Use this to start a new chat for manual testing assistance.**

---

## Project Summary

**SGX Trading Prototype** — Research-only screening + AI thesis system for Singapore equities.

**Architecture**:
```
yfinance
    ↓
mh_test (local caching server)
    ↓
M1: DataServerClient (typed HTTP client, retries, validation)
    ↓
M2: Universe Loader (42 SGX securities, eligibility policy)
    ↓
M3: Phase A Screener (deterministic signals, ranking, JSON + Markdown output)
```

**Capital**: SGD 50,000  
**Execution**: Manual via Moomoo (no automation in Phase 1)  
**Shadow Mode**: 30–60 trading days (M7–M9)  

---

## Completed Milestones (M0–M2)

### M0 — Foundation ✅
- Python package, git repo, config system, SQLite schema
- Located: `pyproject.toml`, `src/financial_market/`, `config/risk_rules_sgx.json`
- Status: Approved

### M1 — mh_test Client ✅
- Typed HTTP client for `/api/health`, `/api/ohlcv`, `/api/backtest`
- File: `src/financial_market/market_data/client.py`
- Tests: 18 tests, 81% coverage
- Status: Approved (upstream flags noted for M9)

### M2 — SGX Universe ✅
- Loaded 42 securities (24 equities, 14 REITs, 4 ETFs)
- File: `config/universe_sgx.csv`, `securities` SQLite table
- Eligibility policy: 120 bars, repair_count ≤5, data ≤3 days stale
- Metadata stored: bar_count, dates, candle_repair_count, price_adjustment contract
- Status: Approved (ETFs excluded, REITs use equity thresholds)

---

## Key Files

| File | Purpose | Location |
|------|---------|----------|
| `pyproject.toml` | Package config | Root |
| `config/risk_rules_sgx.json` | Risk rules + screening thresholds | `config/` |
| `config/universe_sgx.csv` | 42 SGX securities | `config/` |
| `src/financial_market/config.py` | Config loading + validation | M0 |
| `src/financial_market/storage.py` | SQLite connection + schema | M0 |
| `src/financial_market/market_data/client.py` | mh_test HTTP client | M1 |
| `src/financial_market/market_data/models.py` | OHLCV + response models | M1 |
| `src/financial_market/universe.py` | Universe loader + eligibility | M2 |
| `data/financial_market.sqlite3` | Live database (created on first load) | Generated |
| `docs/SGX_Phase1_Build_Agreement.md` | Build agreement (scope, decisions, risks) | Reference |
| `docs/SGX_BUILD_BRIEFING.md` | Current state + roadmap | Reference |
| `docs/reviews/M2-universe-review-report.md` | M2 review evidence | Reference |
| `docs/milestones/M2-sgx-universe.md` | M2 closure document | Reference |

---

## Data Flow (M0–M2)

### M0: Setup
- Config validation (yfinance URL, risk rules, database path)
- SQLite schema creation (securities table, indexes, FK)
- CLI foundation

### M1: Data Access
- HTTP GET `https://api.mh_test/api/ohlcv/{symbol}`
- Typed response validation (OHLCV bars, metadata)
- Exponential retries + in-process caching
- Example: `client.get_ohlcv("D05.SI", days=60)` → 60 daily bars

### M2: Universe Loading
- Read `universe_sgx.csv` (symbol, provider_symbol, company_name, sector, etc.)
- For each security:
  - Map SGX symbol → yfinance format (e.g., D05 → D05.SI)
  - Fetch metadata via M1 client
  - Validate eligibility (120 bars, repair_count ≤5, staleness ≤3 days)
  - Store to SQLite `securities` table with metadata_json
- Output: 42 securities loaded, eligibility policy enforced

---

## Database Schema (SQLite)

### `securities` Table
```sql
CREATE TABLE securities (
  symbol TEXT PRIMARY KEY,
  provider_symbol TEXT NOT NULL,
  company_name TEXT NOT NULL,
  sector TEXT,
  instrument_type TEXT,
  metadata_json TEXT,
  created_at TEXT,
  updated_at TEXT
)
```

**metadata_json** includes:
```json
{
  "data_coverage": {
    "bar_count": 1250,
    "first_date": "2024-01-02",
    "last_date": "2026-08-11",
    "price_adjustment": "split_and_dividend_adjusted",
    "candle_repair_count": 0
  }
}
```

---

## Testing Scope (What to Cover)

### M0 Testing
- ✅ Config loading (valid JSON, environment variables)
- ✅ Database creation (schema exists, FK enforcement)
- ✅ CLI commands (no errors, help works)

### M1 Testing
- ✅ mh_test client can fetch OHLCV
- ✅ Response validation (bars count correct, prices valid)
- ✅ Error handling (timeout, malformed response, server down)
- ✅ Retries (exponential backoff working)
- ✅ Caching (same symbol fetched twice uses cache)

### M2 Testing
- ✅ Universe CSV loaded correctly (42 rows)
- ✅ Symbol mapping (D05 → D05.SI)
- ✅ Eligibility checks (all 42 pass)
- ✅ Metadata stored (bar_count, dates, repair_count)
- ✅ CLI commands work (`fm universe validate`, `fm universe load`)
- ✅ Database integrity (no missing securities)

---

## How to Run Tests

### M0–M2 Test Suite
```bash
cd D:\Projects\FinancialMarket

# Run all tests
pytest tests/ -v

# Run specific module
pytest tests/test_universe.py -v

# Coverage
pytest tests/ --cov=src/financial_market --cov-report=term-plus

# Lint
ruff check src/
ruff format src/
```

### M0: Config Test
```bash
python -c "from financial_market.config import get_config; print(get_config())"
```

### M1: Data Client Test
```bash
fm market-data health
fm market-data ohlcv D05.SI --days 60
```

### M2: Universe Load Test
```bash
fm universe validate
fm universe load
fm universe load --skip-data-validation
```

---

## Eligibility Policy (M2)

**M2 enforces this policy** (from `screening_eligibility_sgx.json`):

```json
{
  "eligibility": {
    "min_daily_bars": 120,
    "max_repair_count": 5,
    "max_stale_days": 3,
    "require_price_adjustment": "split_and_dividend_adjusted",
    "exclude_etfs": true,
    "include_reits": true
  }
}
```

**Result**: All 42 securities pass. None excluded.

---

## Known Upstream Issues (From M1 Review)

| Issue | Severity | Blocks | Status |
|-------|----------|--------|--------|
| OHLCV inconsistency (raw Open/High/Low + adjusted Close) | Critical | M3 | **RESOLVED** by M2 (confirmed adjusted contract) |
| numpy/pandas version conflicts | High | M9 shadow mode | Pending mh_test fix |
| IPython undeclared dependency | Medium | M9 backtest | Pending mh_test fix |

**Impact**: M0–M8 are unblocked. Only M9 (shadow mode backtest) waits on upstream fixes.

---

## Testing Checklist

When you ask for help, you can reference:

- [ ] Can M0 config load without errors?
- [ ] Can M1 fetch OHLCV from mh_test?
- [ ] Can M1 handle network errors gracefully?
- [ ] Can M2 load all 42 securities?
- [ ] Do all 42 securities pass eligibility?
- [ ] Is metadata correctly stored?
- [ ] Can M2 CLI run without errors?
- [ ] Does database have correct schema?
- [ ] Are FK constraints enforced?
- [ ] Do tests cover edge cases (low bars, stale data, zero volume)?

---

## Reference Documents (In Project)

- `docs/SGX_Phase1_Build_Agreement.md` — Build scope, decisions, risks
- `docs/SGX_BUILD_BRIEFING.md` — Current state + roadmap
- `docs/architecture.md` — Project architecture
- `docs/reviews/M1-mh_test-integration-review-report.md` — M1 review
- `docs/reviews/M2-universe-review-report.md` — M2 review
- `docs/dependencies/data-server.md` — mh_test contract

---

## What to Ask the New Chat

Examples:

1. **"Can you help me test M1 OHLCV client? I want to verify it handles timeouts correctly."**
   - New chat has context about M1 client
   - Knows test structure and edge cases
   - Can suggest test scenarios

2. **"M2 loaded 42 securities but I want to manually verify 5 of them. What metadata should I check?"**
   - New chat knows database schema
   - Knows eligibility policy
   - Can help interpret metadata

3. **"How do I test the universe loader against a different CSV?"**
   - New chat knows how M2 works
   - Can suggest test data structure
   - Can help debug

---

## Context Limits

**New chat limitations**:
- Won't have full conversation history (use this prompt instead)
- Won't know about M3 calibration (reference M3 docs if needed)
- Won't know about M4–M9 (that's future; stay focused on M0–M2)

**Tip**: Reference file paths when asking questions. New chat can read project files via FM connector.

---

## How to Start New Chat

**Paste entire prompt into new chat**, then say:

> I'm testing the SGX Trading Prototype (M0–M2 completed). I need help with [specific testing task].
>
> I have access to the project directory via FM connector at `D:\Projects\FinancialMarket`.
>
> [Your specific question]

**Example**:
> I'm testing M2 universe loader. Can you help me verify the eligibility policy is working? I want to check if any stocks have repair_count >5.

---

## Quick Links

- **Project root**: `D:\Projects\FinancialMarket`
- **Config**: `config/risk_rules_sgx.json`, `config/universe_sgx.csv`
- **Source**: `src/financial_market/`
- **Tests**: `tests/`
- **Database**: `data/financial_market.sqlite3` (created after M2 load)
- **Docs**: `docs/` (reference docs + review reports)

---

**Ready to test?** Copy this prompt into a new chat. Enjoy! 🚀
