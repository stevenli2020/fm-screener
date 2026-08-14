# SGX public announcement collection

M4 uses the public SGX Company Announcements pages with the authoritative policy in
`scripts/sgx_announcement_filters.json`. The earlier undocumented
`api.sgx.com/announcements/v1.0` proposal is not used because it returned HTTP 403.

## WSL command

```bash
cd /mnt/d/Projects/FinancialMarket
set -a && source .env && set +a
.venv/bin/fm news collect --lookback-days 2
```

The command reads M3 candidates, builds one percent-encoded listing URL per mapped target
and page, applies the retained categories, and opens only matching announcement details.
`--lookback-days 2` means an inclusive three-date window ending on the run date. Values
from zero through 30 are accepted; bulk historical crawling is outside Phase 1.

Headless Playwright Firefox is the validated WSL runtime. Historical headless Chromium
Akamai failures are retained in the audit history. Adding `--show-browser` is supported by
the standalone diagnostic extractor but is not required by the normal `fm` command.

## Data contract

The authoritative M5 input is `reports/generated/news_feed.json`. Each record contains:

- stable SGX source ID, symbol, title, category, timestamps, source URL, and content hash;
- compact `announcement_sections`, with SGX fields and tables merged by section;
- deterministic `event_type` and `event_data` where a category parser exists;
- attachment provenance, local cache path, byte count, SHA-256 hash, and PDF text status.

Human-readable per-announcement Markdown is written under `extraction/records/`. It is
derived from JSON and may be regenerated. Announcement-page HTML/text snapshots are not
saved.

Attachments are cached under `extraction/attachments/<source-id>/`. The original URL is
retained as `source_url`; `local_path` points to the cached copy. If WSL `pdftotext` is
available, page-delimited text is stored beside each PDF. M4 performs no AI summary.

## Persistence and deduplication

SQLite `news_records` stores the compact sections, event data, and attachment manifest as
JSON alongside the source ID and content hash. Schema v3 adds these fields to existing
databases without removing old records. A repeat with identical content is skipped; a
changed page or attachment hash under the same SGX source ID is a replacement.

`news_api_log` tracks each logical run for compatibility. Request counts include listing,
detail, and attachment requests. A listing, detail, or attachment failure makes the run a
partial failure and is not interpreted as an empty result.

## Category and pagination behavior

Category and symbol order come directly from the JSON policy. First-page URLs omit the
`page` parameter; later pages use `page=2`, `page=3`, and so on. A repeated-page guard
stops collection when SGX ignores a page number and returns previously seen source IDs.

Live verification established that the combined retained ANNC, CACT, and TRAD groups
produce the same source-ID set as the union of separate requests. PLST remains omitted by
the current policy.

## Retention

Phase 1 does not automatically delete news records or cached attachments. A reviewed
retention/pruning command may be added later; it must protect files referenced by active
research and provide a dry run.
