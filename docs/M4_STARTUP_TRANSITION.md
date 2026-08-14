# M4 Startup — Phase A to Phase B Transition

> **Historical handoff note:** M4 has since been implemented with targeted public SGX
> pages, compact announcement sections, attachment caching, and PDF text preprocessing.
> The direct SGX API references below are superseded by
> `docs/dependencies/sgx-news-api.md` and the current M4 review report.

**Status**: M3 Approved ✅, M4 Ready to Start ✅

---

## What Just Happened (M3 Complete)

### M3 Final Results
- **Threshold tuning complete**: volume=2.5, 52wk_extreme=2.5
- **5-day replay**: ~6–8 candidates/day (in target range ✅)
- **Live test**: Consistent with replay results ✅
- **M3 closure document**: Created + filed ✅

### M3 Deliverables Now Available
- `pending_candidates.json` — Daily matched candidates with all 5 signal values
- `screening_report_YYYY-MM-DD.md` — Human-readable daily summary
- SQLite audit trail — Every candidate + signal stored in database

---

## What M4 Does

### Input
```
pending_candidates.json (from M3)
  ↓
Extract matched symbols: D05, O39, C6L, ME8U, etc.
```

### Process
```
For each symbol → Fetch announcements from SGX API
  ↓
Deduplicate (document hash)
  ↓
Store to SQLite (news_records table)
  ↓
Log API call (availability tracking)
```

### Output
```
news_feed.json (for M5 AI agent)
news_report_YYYY-MM-DD.md (human-readable)
SQLite audit trail
```

---

## M4 Timeline & Effort

| Task | Codex | You | Duration |
|------|-------|-----|----------|
| M4 Implementation | 8–10 hrs | Monitor | 1–2 days |
| M4 Testing | 2–3 hrs | Spot-check | 1 day |
| M4 Review | — | Approve | 1 day |
| **Total** | **10–13 hrs** | **1–2 hrs** | **2–3 days** |

---

## Key Files Created for M4

| File | Purpose | Read First? |
|------|---------|------------|
| `docs/tasks/M4_STARTUP_PROMPT.md` | TL;DR for Codex | ✅ **YES** |
| `docs/tasks/M4_RESEARCH_INGESTION_SPEC.md` | Full specification | Reference |
| `docs/milestones/M3-phase-a-screener.md` | M3 closure (just created) | Approval record |

---

## Handoff Checklist (M3 → M4)

- [x] M3 thresholds locked in config
- [x] M3 closure document created
- [x] M3 approved by reviewer
- [x] `pending_candidates.json` available (M3 output)
- [x] M4 specification written
- [x] M4 startup prompt written
- [ ] Codex starts M4 (next step)

---

## What Codex Needs to Know

**M4 inputs**:
- M3's `pending_candidates.json` (list of matched symbols)
- SGX API endpoint (documented in spec)

**M4 outputs**:
- `news_feed.json` (for M5)
- `news_report_YYYY-MM-DD.md`
- SQLite tables (`news_records`, `news_api_log`)

**M4 success criteria**:
- Fetch announcements for all matched candidates ✅
- Deduplicate via document hash ✅
- Log every API call (availability metric) ✅
- ≥80% test coverage ✅
- Error handling (API down, timeout, malformed) ✅

---

## How to Hand Off to Codex

Send Codex this message:

```
M3 is APPROVED ✅. You can now start M4 (News Pipeline).

Read these files:
1. docs/tasks/M4_STARTUP_PROMPT.md (quick overview)
2. docs/tasks/M4_RESEARCH_INGESTION_SPEC.md (full spec)

Key points:
- Input: pending_candidates.json from M3
- Fetch: Announcements from SGX API (Approach 1)
- Process: Deduplicate, store, log API availability
- Output: news_feed.json for M5 + Markdown report
- Data plumbing only; no AI reasoning

Timeline: 1–2 days
Questions? Escalate before coding.
```

---

## Timeline: M4 → M5 → M6 → M7

| Milestone | Duration | Start | Owner | Your Role |
|-----------|----------|-------|-------|-----------|
| **M4** | 1–2 days | Now | Codex | Monitor |
| **M5** | 2–3 days | After M4 | Codex | Test prompt |
| **M6** | 1 day | After M5 | Codex | Design UX |
| **M7** | 1 day | After M6 | Codex | Spot-check |
| **Total M4–M7** | ~1 week | Now | — | ~2–3 hrs |

Then M8 (daily workflow) + M9 (shadow mode, 6–8 weeks).

---

## Success Looks Like (M4 Completion)

```
✅ fm news collect runs without errors
✅ Announcements fetched for all M3 candidates
✅ news_feed.json valid JSON
✅ news_report_YYYY-MM-DD.md generated
✅ SQLite news_records table populated
✅ API availability logged (daily)
✅ 1-week run shows API reliability ≥95%
✅ Deduplication verified (no duplicates)
✅ Tests pass (≥80% coverage)
✅ M4 closure document created
✅ Ready for M5 ✅
```

---

## Next: M5 Preview (For Context)

M5 (AI Thesis Agent) will:
- Read `news_feed.json` (from M4)
- Read `pending_candidates.json` (from M3)
- Consolidate evidence → thesis
- Output: Structured thesis + conviction + risk flags
- **Timeline**: 2–3 days after M4

---

## Questions Before Codex Starts?

- Should M4 fetch ALL announcements, or only for matched candidates?
  - **Answer**: Both OK; recommendation = fetch all, store all (flexibility for M5)

- Should M4 retry failed API calls?
  - **Answer**: Log + continue (don't block)

- How long to keep news records?
  - **Answer**: 6 months (180 days) in Phase 1

---

## You're Ready for M4

All specifications written. Codex can start immediately.

**Estimated completion**: 2–3 days (M4 implementation + review)

**Then**: M5 (AI thesis) starts right after.

**Shadow mode**: Starts Week 5 (M7 revalidation + M8 orchestration + M9 execution)

**Go! 🚀**
