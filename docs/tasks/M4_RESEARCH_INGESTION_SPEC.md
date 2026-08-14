# M4 — Research Ingestion (News Pipeline) Specification

> **Implemented-source amendment — 2026-08-14:** References below to
> `api.sgx.com/announcements/v1.0` are superseded because that endpoint returned HTTP 403.
> The accepted implementation uses targeted public SGX Company Announcements pages,
> authoritative company/security mappings and retained category filters. The M5 feed now
> carries compact page sections, deterministic event fields, and locally cached attachment
> provenance/text. No page snapshots or AI summaries are produced. Operational details are
> maintained in `docs/dependencies/sgx-news-api.md`.

**Status**: READY FOR IMPLEMENTATION ✅  
**Timeline**: 1–2 days  
**Owner**: Codex  
**Reviewer**: Claude  

---

## Mission

Build a **news collection pipeline** that:
1. Reads matched candidates from M3 (`pending_candidates.json`)
2. Fetches announcements from SGX API (Approach 1)
3. Stores news records in SQLite with provenance metadata
4. Deduplicates via document hash
5. Generates daily Markdown report
6. Outputs news JSON feed (for M5 AI thesis agent)

**This is data plumbing.** No AI reasoning, no filtering. Just fetch, validate, store, deduplicate.

---

## Scope

### ✅ In Scope
- Fetch announcements from SGX API (`https://api.sgx.com/announcements/v1.0/`)
- Store to SQLite with metadata (date, source, hash, retrieved_at)
- Deduplicate by document hash
- Log API availability (track downtime)
- Generate daily Markdown report
- Output news JSON feed (for M5)
- Error handling (API down, missing announcements, malformed responses)
- Test coverage >80%
- CLI command: `fm news collect`

### ❌ Out of Scope
- AI analysis or sentiment scoring (M5 job)
- Company IR page scraping (deferred; Approach 2 fallback)
- RSS feed aggregation (deferred)
- News filtering or ranking (M5 job)
- Multi-source consolidation (single SGX API in Phase 1)

---

## Input Data

### Matched Candidates (from M3)
```json
{
  "run_date": "2026-08-13",
  "ranked_candidates": [
    {
      "rank": 1,
      "symbol": "D05",
      "company_name": "DBS Group Holdings Ltd",
      "sector": "Banking",
      "instrument_type": "equity"
    },
    // ... more candidates
  ]
}
```

**Source**: `pending_candidates.json` (M3 output)

---

## SGX API Integration

### Endpoint
```
GET https://api.sgx.com/announcements/v1.0/?periodstart=YYYYMMDD_HHMMSS&periodend=YYYYMMDD_HHMMSS&limit=50
```

### Parameters
- `periodstart`: Start time (format: `20260812_000000`)
- `periodend`: End time (format: `20260812_235959`)
- `limit`: Max results per call (default 50)
- `symbol` (optional): Filter by specific symbol

### Response Schema
```json
{
  "announcements": [
    {
      "symbol": "D05",
      "title": "Results Announcement",
      "type": "financial_results",
      "publishedAt": "2026-08-11T16:30:00Z",
      "url": "https://www.sgx.com/...",
      "id": "N0300123456",
      "documentType": "PDF"
    }
  ]
}
```

### Error Handling
- **API down**: Log error, continue (don't crash)
- **Empty response**: OK (no announcements that day)
- **Malformed response**: Reject, log error
- **Timeout**: Retry with exponential backoff (same as M1)

---

## Database Schema

### `news_records` Table
```sql
CREATE TABLE news_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sgxnet_id TEXT UNIQUE NOT NULL,        -- N0300123456
  symbol TEXT NOT NULL,                  -- D05
  title TEXT NOT NULL,
  type TEXT,                             -- dividend, trading_halt, general, etc.
  published_at TEXT,                     -- ISO 8601 timestamp
  retrieved_at TEXT NOT NULL,            -- When we fetched it
  url TEXT,
  document_type TEXT,                    -- PDF, HTML
  document_hash TEXT NOT NULL,           -- SHA256(title + symbol + published_at)
  source TEXT DEFAULT 'sgx_api',         -- Source endpoint
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (symbol) REFERENCES securities(symbol),
  UNIQUE(sgxnet_id, symbol)
)
```

**Index**: `CREATE INDEX idx_symbol_date ON news_records(symbol, published_at)`

### `news_api_log` Table (Availability Tracking)
```sql
CREATE TABLE news_api_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  api_endpoint TEXT,
  run_date TEXT,
  status TEXT,                           -- success, timeout, error
  http_code INTEGER,
  error_message TEXT,
  announcements_fetched INTEGER,
  execution_time_ms INTEGER,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

---

## Workflow

### Daily News Collection Process

```python
def news_collection_pipeline(run_date: date) -> dict:
    """
    Daily end-of-day news collection.
    """
    
    # 1. Load M3 candidates
    candidates = load_candidates_from_json()  # pending_candidates.json
    candidate_symbols = [c.symbol for c in candidates]
    
    # 2. Fetch announcements from SGX API
    announcements = []
    api_log = {
        "run_date": run_date.isoformat(),
        "status": "success",
        "announcements_fetched": 0,
        "errors": []
    }
    
    try:
        # Fetch for all matched symbols
        response = sgx_client.get_announcements(
            period_start=run_date,
            period_end=run_date
        )
        
        if response.status_code != 200:
            api_log["status"] = "error"
            api_log["error"] = f"HTTP {response.status_code}"
            log_api_call(api_log)
            return {"error": api_log["error"]}
        
        announcements = response.announcements
        api_log["announcements_fetched"] = len(announcements)
    
    except TimeoutError:
        api_log["status"] = "timeout"
        api_log["error"] = "SGX API timeout"
        log_api_call(api_log)
        return {"error": "API timeout"}
    
    except Exception as exc:
        api_log["status"] = "error"
        api_log["error"] = str(exc)
        log_api_call(api_log)
        return {"error": str(exc)}
    
    # 3. Filter for candidates only (optional optimization)
    relevant_announcements = [
        ann for ann in announcements
        if ann.symbol in candidate_symbols
    ]
    
    # 4. Deduplicate + store
    stored_count = 0
    skipped_count = 0
    
    for ann in relevant_announcements:
        doc_hash = hashlib.sha256(
            f"{ann.symbol}{ann.title}{ann.published_at}".encode()
        ).hexdigest()[:8]
        
        try:
            # Insert or skip if duplicate
            stored = store_news_record(
                sgxnet_id=ann.id,
                symbol=ann.symbol,
                title=ann.title,
                type=ann.type,
                published_at=ann.published_at,
                retrieved_at=datetime.utcnow(),
                url=ann.url,
                document_type=ann.document_type,
                document_hash=doc_hash,
                source="sgx_api"
            )
            if stored:
                stored_count += 1
            else:
                skipped_count += 1
        except Exception as exc:
            api_log["errors"].append(f"Store failed: {ann.sgxnet_id} - {str(exc)}")
    
    # 5. Generate report
    report = generate_news_report(run_date, stored_count, skipped_count, api_log)
    
    # 6. Output JSON feed (for M5)
    news_feed = {
        "run_date": run_date.isoformat(),
        "announcements_fetched": api_log["announcements_fetched"],
        "announcements_stored": stored_count,
        "announcements_skipped": skipped_count,
        "api_status": api_log["status"],
        "records": get_daily_news_records(run_date)  # All stored for this date
    }
    
    return news_feed
```

---

## Output Formats

### `news_feed.json` (For M5 AI Agent)
```json
{
  "run_date": "2026-08-13",
  "announcements_fetched": 42,
  "announcements_stored": 18,
  "announcements_skipped": 24,
  "api_status": "success",
  "records": [
    {
      "sgxnet_id": "N0300123456",
      "symbol": "D05",
      "title": "Interim Results Announcement",
      "type": "financial_results",
      "published_at": "2026-08-11T16:30:00Z",
      "url": "https://www.sgx.com/...",
      "document_hash": "a1b2c3d4",
      "retrieved_at": "2026-08-13T08:00:00Z",
      "source": "sgx_api"
    }
    // ... more records
  ]
}
```

### Daily Markdown Report
```markdown
# News Collection Report — 2026-08-13

## Summary
- Announcements fetched: 42
- Announcements stored: 18 (new)
- Announcements skipped: 24 (duplicates)
- API status: ✅ OK

## By Symbol

### D05 — DBS Group Holdings Ltd (3 announcements)
| Title | Type | Published | URL |
|-------|------|-----------|-----|
| Interim Results Announcement | financial_results | 2026-08-11 | [link] |
| Dividend Declaration | dividend | 2026-08-10 | [link] |
| Trading Halt Notice | trading_halt | 2026-08-09 | [link] |

### O39 — OCBC (2 announcements)
[...]

## API Availability Log

| Date | Time | Status | HTTP Code | Count | Notes |
|------|------|--------|-----------|-------|-------|
| 2026-08-13 | 08:00 | ✅ Success | 200 | 42 | Normal |
| 2026-08-12 | 08:00 | ✅ Success | 200 | 38 | Normal |
| 2026-08-11 | 08:00 | ✅ Success | 200 | 35 | Normal |

**30-day availability**: 100% (27/27 days)

## Symbols with No Announcements (15)

| Symbol | Status |
|--------|--------|
| [symbol] | No news this period |
[...]
```

---

## Implementation Checklist

### Code Structure
- [ ] `src/financial_market/research/news_collector.py` (SGX API client + fetching)
- [ ] `src/financial_market/research/news_deduplicator.py` (hash-based dedup)
- [ ] `src/financial_market/research/news_reporter.py` (Markdown report generation)
- [ ] CLI: `fm news collect` command
- [ ] Database: Add `news_records` + `news_api_log` tables to schema

### Testing
- [ ] Unit tests for news collection logic
- [ ] Integration test: M3 candidates → SGX API → SQLite
- [ ] Error handling tests (API down, timeout, malformed response)
- [ ] Deduplication tests (same announcement fetched twice)
- [ ] Target coverage: >80%

### Self-Review Checklist
- [ ] **No data loss**: All fetches logged (success or error)
- [ ] **Deduplication works**: Document hash prevents duplicates
- [ ] **API availability tracked**: Daily logs for monitoring
- [ ] **Error resilience**: Timeouts handled, bad announcements rejected
- [ ] **Determinism**: Same input (candidates + date) → same output (news)
- [ ] **Observability**: Report shows what happened (fetched, stored, skipped, errors)
- [ ] **Dependencies**: Only M1 client + M3 JSON? (No hardcoded URLs beyond SGX API)

---

## Success Criteria (Gate for M5)

Before M5 (AI thesis agent) can start, M4 must deliver:

✅ **Functionality**:
- `fm news collect` runs without errors
- Fetches announcements for matched M3 candidates
- Stores to SQLite with metadata + hash
- Outputs valid `news_feed.json`
- Generates Markdown report

✅ **Data Quality**:
- All announcements have required fields (symbol, title, date, source)
- Duplicate detection working (verified via manual check)
- No data loss (API log shows every call)

✅ **Testing**:
- ≥80% code coverage
- Error scenarios handled (API down, timeout, malformed)
- Deduplication validated

✅ **Monitoring**:
- 7-day API availability metric
- Daily error log (if any)
- Announcement count trend

**Gate**: Run news collection for 1 week. Validate:
- Announcements are relevant to matched candidates
- No duplicates in SQLite
- API is reliable (≥95% availability)

If any gate fails, pause M5 and investigate before proceeding.

---

## Data Validation Metrics (Report in Review)

When submitting M4 for review, include:

```json
{
  "m4_validation_metrics": {
    "run_date": "2026-08-13",
    "api_status": "success",
    "announcements_fetched": 42,
    "announcements_stored": 18,
    "announcements_skipped": 24,
    "candidates_with_news": 12,
    "candidates_without_news": 26,
    "deduplication": {
      "new_records": 18,
      "duplicate_records": 24,
      "hash_collisions": 0
    },
    "api_availability": {
      "last_7_days_success_rate": 100,
      "last_7_days_total_calls": 7,
      "last_7_days_failures": 0
    },
    "database": {
      "total_news_records": 150,
      "symbol_coverage": 42,
      "earliest_record_date": "2026-08-06",
      "latest_record_date": "2026-08-13"
    }
  }
}
```

---

## References

- **Build Agreement**: Milestone 4 (News Pipeline)
- **M3 Delivered**: `pending_candidates.json` (matched symbols)
- **M1 Delivered**: Retry logic + timeout handling (reuse pattern)
- **SGX API**: Approach 1 from Build Agreement

---

## Questions for Codex (Before Starting)

1. Should M4 **filter announcements** to only matched candidates, or fetch all?
   - **Recommendation**: Fetch all, store all (M5 can filter); this gives future flexibility
   - But optimize by querying matched symbols only if API supports

2. Should M4 **retry failed API calls** or just log and continue?
   - **Recommendation**: Log with timestamp + error; continue; don't block on one failure

3. Should dedup use **full document hash** (all fields) or just title + date + symbol?
   - **Recommendation**: Use `hash(symbol + title + published_at)` (simple, effective)

4. **How long to keep news records** in SQLite? Purge old records?
   - **Recommendation**: Keep 6 months (180 days); don't purge in Phase 1

---

**Ready to build?** If Codex has any questions, escalate before writing code.

Good luck! 🚀
