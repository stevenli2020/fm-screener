# M4.1 main-chat handoff prompt

Copy the block below into the main FinancialMarket development chat.

---

M4.1 APPROVED AND CLOSED - PERSISTENT SGX FINANCIAL-REPORT ARCHIVE

The project owner tested and explicitly approved the M4.1 targeted financial-report
collector on 2026-08-14. Treat M4.1 as closed. Do not infer that M4 itself is approved or
closed, and do not start M5 unless the owner separately approves M4 or waives its remaining
gate.

Read first:

1. `docs/milestones/M4.1-financial-report-archive.md`
2. `docs/dependencies/sgx-financial-reports.md`
3. `scripts/download_financials.py`
4. `tests/test_download_financials.py`
5. `reports/financials/z74/manifest.json`

Delivered behavior:

- Target one mapped SGX symbol with `scripts/download_financials.py`.
- Preserve the authoritative mapping type: `company` or `securityname`.
- Query Financial Statements and Related Announcement (`ANNC17`) over an inclusive range.
- Exclude only Notification of Results Release listing rows.
- Stage all attachments, extract PDF text, and classify deterministically.
- Archive primary financial statements and supplementary MDA documents by symbol/year.
- Remove confirmed releases and presentations from staging while retaining their SGX URL,
  SHA-256 hash, reason and classification in `manifest.json`.
- Retain inconclusive documents under `_review`.
- Skip existing announcements by stable SGX source ID, including when historical coverage
  is expanded.
- Keep `manifest.json` as valid JSON and retain legacy JSONL read compatibility.

Z74 live acceptance results for 2021-08-14 through 2026-08-14:

- 11 eligible announcements
- 55 attachments downloaded and classified
- 11 primary financial statements archived
- 11 supplementary MDA documents archived
- 33 releases/presentations rejected
- 0 needs-review items
- 0 failures
- repeat run skipped all 11 existing source IDs and downloaded nothing

Validation:

- Full WSL suite: 105 tests passed
- Downloader-focused coverage: 81%
- Ruff lint/formatting, compileall and pip check passed
- One existing non-blocking Starlette/httpx deprecation warning remains
- No changes were made to `D:\Projects\mh_test`

Important boundaries:

- Classification confidence (`high`, `medium`, `low`) describes document-type evidence,
  not investment conviction.
- No AI interpretation or trading occurs in M4.1.
- The approved collector currently processes one symbol per command. Automatic batch
  invocation from M3 candidates, portfolio holdings or a watch list is not yet implemented
  and requires a separately authorized integration task.
- When M5 is authorized, the AI agent must include retained M4.1 primary financial
  statements and supplementary management analysis as analysis inputs alongside M4 news,
  with missing or review-required archive content reported explicitly.
- M4 remains READY FOR REVIEW under its separate availability gate. M5 remains gated.

Current status:

- M0-M3: Closed
- M4: READY FOR REVIEW; not approved or closed
- M4.1: APPROVED and CLOSED
- M5: Not started; gated

---
