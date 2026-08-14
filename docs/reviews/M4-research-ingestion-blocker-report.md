# M4 research ingestion — IMMEDIATE GATES PASSED; MONITORING IN PROGRESS

## Gap-closing implementation

- `fm news collect` uses the targeted SGX public Company Announcements pages instead of
  the blocked `api.sgx.com` endpoint.
- It loads all category codes and 42 exact company/security mappings from
  `scripts/sgx_announcement_filters.json`.
- Each M3 candidate is queried over a short inclusive date range with ordered category
  codes, `pagesize=100`, per-target pagination, stable-source-ID deduplication, and
  respectful pacing.
- Explicit empty results, mapping failures, malformed details, partial runs, replacements,
  SQLite persistence, `news_api_log`, JSON output, and Markdown reporting are covered.
- A repeated-page guard stops pagination if SGX ignores the page parameter and returns IDs
  already seen for that target. This prevents a repeated response from amplifying requests.

## Category union verification

Live browser verification on 2026-08-13 used S68 over 2025-11-06. The combined ANNC,
CACT, and TRAD request returned stable IDs `5HFIKQTHMIW8IUNU` and `BQAAYS9N7D9CSDFD`.
The union of separate group requests returned the same IDs. M4 therefore uses one combined
category request per target/page. PLST is omitted by policy.

## Historical Chromium blocker and resolution

The original 14-candidate WSL run failed on its first request because headless Chromium
received an Akamai Access Denied page. That failure remains in `news_api_log` and the prior
live artifacts as historical evidence.

Protocol and mapping errors were ruled out by comparing browser modes:

- WSL headless Chromium: Access Denied.
- WSL visible Chromium: success.
- WSL headless Firefox: success.

All three extractor launch paths now use Playwright Firefox. Headless operation requires no
visible browser. Live O39 company queries returned four records on two independent runs;
C38U's security query returned a valid successful empty result.

## Full live validation

The official runs used the canonical M2/M3 SQLite database because `news_records.symbol`
correctly references `securities.symbol`. Both runs queried the same 14 candidates over the
inclusive period 2026-08-11 through 2026-08-13.

| Metric | First run | Repeat run |
| --- | ---: | ---: |
| Mapped candidates | 14 | 14 |
| Mapping failures | 0 | 0 |
| Requests successful/attempted | 34/34 | 34/34 |
| Announcements fetched | 20 | 20 |
| New rows stored | 20 | 0 |
| Existing rows skipped | 0 | 20 |
| Replacements | 0 | 0 |
| Extraction failures | 0 | 0 |

Twenty announcements were relevant to seven candidates: BN4 (5), BS6 (2), D05 (1), F34
(4), G13 (3), O39 (4), and S68 (1). Each normalized record included its mapped target
symbol. C38U, S58, T82U, U11, BUOU, C2PU, and SRT had successful empty results.

SQLite contains 20 rows and 20 distinct SGX source IDs, with zero duplicate source-ID
groups. The latest two `news_api_log` entries are successful HTTP 200 collections with 20
announcements and 34 attempts each. Replacement behavior is proven by deterministic tests;
no live source changed between these two runs, so zero live replacements is expected.

## Full-content extraction amendment

The owner reviewed an isolated full-flow trial and approved its content contract for M4.
The production pipeline now:

- preserves SGX fields and multi-column tables once in compact `announcement_sections`;
- deterministically normalizes cash-dividend and share-buyback fields while retaining the
  complete compact sections for categories that remain unclassified;
- caches attachments under `extraction/attachments/<source-id>/`, retaining original URL,
  local path, byte count, retrieval time, and SHA-256 hash;
- creates page-delimited PDF text with WSL `pdftotext` when available, without AI summary;
- omits announcement-page HTML/text snapshots;
- treats JSON/SQLite as authoritative for M5 and Markdown as a human-review derivative;
- includes page content and attachment hashes in replacement detection; and
- migrates existing SQLite databases to schema v3 without dropping news records.

The approved live trial queried all 14 M3 candidates over 2026-08-11 through 2026-08-13.
It discovered and completed 20 announcements with zero record or attachment failures,
cached 19 PDFs, extracted 19 page-delimited text files, and created no page-snapshot
directory.

The enriched production refresh was then completed against the canonical database over the
same window. It migrated schema v2 to v3 additively and returned 53/53 successful requests:
14 listing requests, 20 detail requests, and 19 attachment requests. All 20 metadata-only
rows were updated as replacements. SQLite still contains exactly 20 rows and 20 distinct
SGX source IDs, with zero duplicate groups. All 20 rows contain announcement sections, 15
rows have cached attachments (19 files total), and five rows have deterministic dividend or
share-buyback event classifications. The failure log is empty.

Self-review additionally made partial attachment downloads fail closed: the affected record
is audited but is not emitted to SQLite or the M5 feed, preventing an incomplete refresh
from replacing a previously complete authoritative record.

## WSL quality gate

- Final full-project suite: 89 passed with one pre-existing Starlette/httpx deprecation
  warning.
- M4 research package coverage is 89%, exceeding the 80% requirement.
- Production-specific tests cover compact sections, multi-column tables, event fields,
  attachment success/failure, PDF text boundaries, content hashes, SQLite persistence,
  schema-v3 migration, and fail-closed partial attachment handling.
- Ruff lint, Ruff formatting, `compileall`, and `pip check` passed in WSL.

## Availability gate

The implementation and immediate live gates pass. The agreed seven-day operational gate
started on 2026-08-13 and currently covers two distinct days:

| Monitoring day | Result | Requests | Fetched | Stored | Skipped | Failures |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2026-08-13 | Success | 34/34 | 20 | 20 first run; 0 repeat | 0 first run; 20 repeat | 0 |
| 2026-08-14 | Success | 31/31 | 17 | 0 | 17 | 0 |

Post-resolution availability is three successful full collections out of three (100%) over
two of seven required calendar days. Historical failures remain preserved in the database,
so the rolling report over all pre- and post-fix attempts is lower and must not be
misrepresented as current Firefox availability.

M4 remains open and M5 remains gated until seven distinct monitoring days are complete with
at least 95% availability, or the owner explicitly waives that gate. M4 must not be marked
closed without explicit owner approval.

## Self-review

- No broad archive crawl, AI reasoning, automatic trading, or `mh_test` modification exists.
- Access-denied and malformed pages cannot be treated as successful empty results.
- Full hashes and unique constraints make repeat runs deterministic; changed content under
  an existing source ID updates that row as a replacement.
- The live feed and report reflect the repeat run: 20 fetched, 20 skipped, zero failures.
