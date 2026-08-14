# M4 Startup Prompt — For Codex

> **Implementation amendment — 2026-08-14:** The undocumented SGX API described below
> returned HTTP 403 and is not the implemented source. M4 now uses targeted public SGX
> Company Announcements pages through headless Firefox. The approved output contract also
> includes compact `announcement_sections`, normalized event data, cached attachments, and
> page-delimited PDF text. JSON is authoritative for M5; Markdown is for human review; page
> snapshots are not saved. See `docs/dependencies/sgx-news-api.md` and the M4 review report.

**Status**: APPROVED FOR IMPLEMENTATION ✅  
**Timeline**: 1–2 days  
**Reviewer**: Claude  

---

## TL;DR

Build a **news collection pipeline** that:
1. Reads matched M3 candidates
2. Fetches announcements from SGX API
3. Stores to SQLite with deduplication (document hash)
4. Logs API availability
5. Outputs JSON feed + Markdown report

**No AI reasoning.** Pure data plumbing — fetch, validate, store, deduplicate.

---

## What to Build

### Core Components

1. **`src/financial_market/research/news_collector.py`**
   - `SGXNewsClient()` — HTTP wrapper around SGX API
   - `fetch_announcements(period_start, period_end)` → list of announcements
   - Timeout handling (exponential retry from M1 pattern)
   - Error handling (API down, malformed response)

2. **`src/financial_market/research/news_deduplicator.py`**
   - `compute_document_hash(symbol, title, published_at)` → SHA256 hash
   - `deduplicate(announcements)` → filter existing hashes
   - `store_news_record()` → insert into SQLite

3. **`src/financial_market/research/news_reporter.py`**
   - `generate_markdown_report()` → daily Markdown
   - `generate_json_feed()` → JSON for M5

4. **Database Schema**
   - Add `news_records` table
   - Add `news_api_log` table (track API availability)
   - Foreign key to M2 `securities(symbol)`

5. **CLI**
   - `fm news collect` → fetch, store, report

6. **Integration**
   - Read M3's `pending_candidates.json`
   - Output M4's `news_feed.json` (for M5)

---

## Key Constraints

✅ **Do**:
- Fetch from SGX API only (Approach 1)
- Deduplicate via document hash
- Log every API call (availability tracking)
- Store all fields + provenance metadata
- Configuration-driven thresholds (no hardcoding)
- Error handling (API down, timeout, malformed)
- Test coverage >80%

❌ **Don't**:
- Add AI filtering (M5 job)
- Scrape company IR pages (deferred)
- Aggregate multiple sources (single SGX API Phase 1)
- Filter news by relevance (store all, M5 analyzes)
- Skip error logging (availability metric critical)

---

## SGX API Details

### Endpoint
```
GET https://api.sgx.com/announcements/v1.0/
?periodstart=YYYYMMDD_HHMMSS
&periodend=YYYYMMDD_HHMMSS
&limit=50
```

### Response
```json
{
  "announcements": [
    {
      "symbol": "D05",
      "title": "Results Announcement",
      "type": "financial_results",
      "publishedAt": "2026-08-11T16:30:00Z",
      "url": "https://...",
      "id": "N0300123456",
      "documentType": "PDF"
    }
  ]
}
```

### Reuse from M1
- Use M1's retry + timeout logic
- Typed response models (Pydantic)
- Error classes + logging

---

## Database Schema

### `news_records` Table
```sql
CREATE TABLE news_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sgxnet_id TEXT UNIQUE NOT NULL,
  symbol TEXT NOT NULL,
  title TEXT NOT NULL,
  type TEXT,
  published_at TEXT,
  retrieved_at TEXT NOT NULL,
  url TEXT,
  document_type TEXT,
  document_hash TEXT NOT NULL,
  source TEXT DEFAULT 'sgx_api',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (symbol) REFERENCES securities(symbol),
  UNIQUE(sgxnet_id, symbol)
)
```

### `news_api_log` Table
```sql
CREATE TABLE news_api_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  api_endpoint TEXT,
  run_date TEXT,
  status TEXT,
  http_code INTEGER,
  error_message TEXT,
  announcements_fetched INTEGER,
  execution_time_ms INTEGER,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

---

## Testing Checklist

- [ ] Unit tests for announcement fetching
- [ ] Unit tests for deduplication (hash logic)
- [ ] Integration test: fetch → deduplicate → store
- [ ] Error handling (API timeout, malformed response)
- [ ] Deduplication validation (same announcement twice = one record)
- [ ] Database schema created
- [ ] API log tracking working
- [ ] CLI command works (`fm news collect`)

---

## Self-Review Before Submitting

- [ ] No data loss: Every API call logged (success or error)
- [ ] Deduplication: Document hash prevents duplicates
- [ ] API availability: Daily logs for monitoring (critical metric)
- [ ] Error resilience: Timeouts handled, bad data rejected
- [ ] Determinism: Same input → same output
- [ ] Observability: Report shows what happened (fetched, stored, skipped)
- [ ] Dependencies: Only M1 client + M3 JSON?

---

## Review Criteria (Before M5 Approval)

1. **Functionality**: `fm news collect` works; outputs JSON + report
2. **Quality**: All matched candidates checked for announcements
3. **Testing**: ≥80% coverage; error scenarios handled
4. **Audit**: Every API call logged; deduplication verified
5. **Metrics**: 1-week run showing API reliability + announcement counts

---

## Outputs

- **`news_feed.json`** — Structured announcements (for M5)
- **`news_report_YYYY-MM-DD.md`** — Human-readable daily summary
- **SQLite audit trail** — All stored announcements + API logs

---

## Documentation to Include

- README with API details + deduplication logic
- Example report (show stored + skipped announcements)
- Configuration guide (if any thresholds)
- API availability monitoring guide

---

## Reference Docs

- **Full spec**: `M4_RESEARCH_INGESTION_SPEC.md`
- **M3 output**: `pending_candidates.json` (input to M4)
- **M1 pattern**: Retry logic + timeout handling
- **SGX API**: Details in spec

---

## Submission Format (When READY FOR REVIEW)

- Code deliverables (files created/modified)
- Database schema (new tables)
- Test results (coverage %, count, pass/fail)
- Self-review checklist (all signed off)
- Example outputs (sample JSON + report)
- 1-week run metrics (API availability, announcement counts)
- Known limitations or deferred decisions

---

**Go build.** 🚀
