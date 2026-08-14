# SGX financial-report archive operations

M4.1 maintains a persistent financial-report history for a targeted SGX universe symbol.
It is separate from M4's short-window `fm news collect` feed and is currently invoked as a
standalone WSL script.

## Prerequisites

- Work in WSL Ubuntu from `/mnt/d/Projects/FinancialMarket`.
- Use the project environment at `.venv`.
- Playwright Firefox must be installed for the project environment.
- WSL `pdftotext` should be available for deterministic PDF text extraction.
- The symbol must have an authoritative mapping in
  `scripts/sgx_announcement_filters.json`.

Mappings use either `type=company` or `type=securityname`. The collector reads the mapped
value; it does not force one type for every symbol.

## Run a collection

```bash
cd /mnt/d/Projects/FinancialMarket
.venv/bin/python scripts/download_financials.py \
  --symbol z74 \
  --from-date 20210814 \
  --output-root reports/financials \
  --debug
```

`--from-date` and optional `--to-date` use inclusive `YYYYMMDD` dates. If `--to-date` is
omitted, the current date is used.

Use a short or issuer-appropriate range during ordinary maintenance. The five-year Z74
range was an explicit acceptance test, not permission for broad SGX archive crawling.

## Retrieval and classification flow

```text
authoritative symbol mapping
  -> targeted ANNC17 listing query
  -> exclude Notification of Results Release
  -> skip existing stable source IDs
  -> stage all attachments for each new announcement
  -> extract PDF text with pdftotext
  -> classify each attachment
  -> archive primary statements and MDA documents
  -> remove confirmed releases/slides from staging
  -> retain uncertain documents under _review
  -> update manifest.json and failures.jsonl
```

The filename is a hint, not the primary selection gate. This supports issuer-specific
names such as `CCIFS`, `MDA`, `NR`, `MR`, `MS` and `slides`.

## Output layout

```text
reports/financials/<lowercase-symbol>/
|-- <publication-year>/
|   |-- <date>_<source-id>_<attachment>.pdf
|   `-- <date>_<source-id>_<attachment>.txt
|-- _review/                         # only when classification is inconclusive
|-- manifest.json
`-- failures.jsonl
```

The year is the SGX announcement publication year. Annual, half-yearly and quarterly
reports can coexist in the same year directory.

## Understanding debug confidence

- `high`: extracted content directly identifies the document type.
- `medium`: content does not contradict the classification, but a strong filename or
  same-announcement context is also required.
- `low`: the evidence is insufficient; the attachment is retained under `_review`.

These values concern document classification only. They do not measure report quality,
company quality, investment merit or trading conviction.

## Manifest behavior

`manifest.json` is valid JSON with:

- `schema_version`;
- `updated_at`;
- `queried_date_range`;
- `last_collection`; and
- `records`.

Each record's `attachments` contains only archived primary/supplementary documents.
`attachment_decisions` records every downloaded attachment, including rejected items.

When the requested start date is earlier than existing coverage, the collector queries the
expanded historical range and skips existing SGX source IDs before detail retrieval. A
normal repeat is idempotent and reports the count in `skipped_existing`.

## Result counters

- `announcements_found`: unique eligible SGX announcement IDs in the listing result.
- `announcements_downloaded`: new announcement records added to the manifest.
- `attachments_downloaded`: all attachments fetched into staging during this run.
- `attachments_archived`: accepted primary plus supplementary documents.
- `primary_financial_statements`: accepted statement documents.
- `supplementary_financial_analysis`: accepted MDA or operating/financial-analysis documents.
- `rejected_non_reports`: releases and presentations removed from staging.
- `needs_review`: inconclusive attachments retained under `_review`.
- `skipped_existing`: stable source IDs already present in the manifest.
- `failures`: listing, detail, download or file-processing failures.

## Operational checks

After a successful first run:

1. Open `manifest.json` and confirm the requested range and record count.
2. Inspect a sample primary PDF and its extracted `.txt` file.
3. Confirm medium-confidence decisions are appropriate for that issuer.
4. Review anything under `_review` before using it downstream.
5. Run the same command again and confirm no duplicate download occurs.

Project validation commands:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests scripts/run.py scripts/download_financials.py
.venv/bin/python -m ruff format --check src tests scripts/run.py scripts/download_financials.py
.venv/bin/python -m compileall -q src scripts/run.py scripts/download_financials.py
.venv/bin/python -m pip check
```

## Safety boundary

The collector is read-only with respect to SGX and has no broker capability. It does not
modify or import `D:\Projects\mh_test`. Rejected local attachments remain recoverable from
their recorded SGX URL; their hash and classification decision remain in the manifest.

## Downstream M5 input contract

The archive is a mandatory source for M5 AI-agent analysis, not merely an optional human
reference. M5 must resolve the candidate symbol to `reports/financials/<symbol>/`, load
`manifest.json`, and supply retained primary statements plus supplementary financial
analysis to the agent together with the M4 announcement feed. Page-delimited `.txt` files
are preferred for model input, while PDFs and manifest hashes provide source provenance.

Missing symbol archives, missing retained files and `_review` decisions must be surfaced
as explicit input-coverage warnings. M5 must not infer that a company has no relevant
financial information simply because its M4.1 archive is absent or incomplete.
