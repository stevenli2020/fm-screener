# M0 — Foundation closure record

## Approval

- Status: Closed
- Approved by: project owner
- Approval date: 2026-08-11

## Delivered scope

- Python `src/` package, editable-install configuration, isolated environment guidance,
  and WSL Ubuntu test workflow.
- Validated environment-based settings, with `.env` excluded from source control.
- SQLite initialization with foreign-key enforcement and versioned schema.
- Schema support for securities, screening-run outputs, research documents, transactions,
  cash ledger entries, portfolio snapshots/positions, manual trade tickets, and audit
  events.
- Mechanical SGX risk rules with validation and `manual_only` execution mode.
- Development workflow and architecture documentation.

## Acceptance evidence

- Automated tests cover configuration, storage initialization, execution-manifest
  constraints, risk rules, and CLI validation.
- `fm validate-config` validates the supplied SGX rules.
- No broker SDK, broker credential, or order-placement capability was added.

## Decisions and limitations

- SQLite is the Phase 1 local system of record.
- A manual execution manifest is required before a ticket can be marked
  `executed_manual`.
- Database migration tooling beyond schema version 1 is deferred until a later milestone
  requires an in-place schema change.

