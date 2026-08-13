# M3 Calibration → M4 Transition

**What happens after calibration is locked**

---

## After You Lock Thresholds (Checklist)

Once 5-day replay results are in target range (2–8/day), do this:

### 1. Record Calibration Results
- [ ] Fill out `docs/M3_CALIBRATION_RESULTS_TEMPLATE.md` completely
- [ ] Save file
- [ ] Send to Claude (advisor) for final approval

### 2. Create M3 Closure Document
- [ ] Copy template from calibration results template
- [ ] Fill in actual thresholds + calibration date
- [ ] Save to `docs/milestones/M3-phase-a-screener.md`
- [ ] Commit to Git

### 3. Verify Config is Correct
```bash
cat config/risk_rules_sgx.json | grep -A 10 '"screening"'
# Confirm volume_spike and 52wk_extreme are at final values
```

### 4. Run Live Screening Once More (Sanity Check)
```bash
fm screening run
```
- Should produce `pending_candidates.json`
- Should generate markdown report
- Match count should be consistent with 5-day replay

---

## What M4 Does (Preview)

**M4 = News Pipeline** — Fetches announcements for matched candidates from M3

**Input**: `pending_candidates.json` (from M3 screening)

**Output**: News records in SQLite + JSON feed (for M5 AI thesis agent)

**Timeline**: 1 day

**Your role**: Monitor SGX API availability (should be reliable)

---

## What You Need to Know About M4

### M4 Will Use Your Screener Output
```
M3 Screener (daily)
    ↓
pending_candidates.json (list of matched symbols)
    ↓
M4 News Pipeline
    ├─ Fetch SGX API announcements for each symbol
    ├─ Store to SQLite
    └─ Output news JSON (for M5)
```

### M4 Success Criteria
- ✅ Fetch announcements for all matched candidates (from M3)
- ✅ Store to database with metadata (date, source, hash)
- ✅ Log API availability (track downtime)
- ✅ Handle errors gracefully (API down, missing announcements)
- ✅ ≥80% test coverage

### M4 Deliverables
- `src/financial_market/research/news_collector.py` (SGX API client)
- `fm news collect` CLI command
- Daily news reports (Markdown)
- SQLite audit trail (`news_records` table)

---

## Timeline: M4 Start

**You can start M4 immediately after**:
1. ✅ Calibration results locked
2. ✅ M3 closure document created
3. ✅ Config committed to Git

**Codex will**:
- Read M4 specification (will be provided)
- Build news collector
- Test with live SGX API
- Submit for review (1 day)

**You will**:
- Monitor Codex's progress
- Spot-check news outputs (do they match expected announcements?)
- Review M4 report when ready

---

## M4 Specification (Will Be Created)

I will provide Codex with:

```markdown
# M4 — Research Ingestion (News Pipeline)

**Goal**: Fetch announcements for matched M3 candidates

**Scope**:
- SGX API (Approach 1 from Build Agreement)
- Store news + provenance metadata
- SQLite audit trail
- Daily Markdown report

**Inputs**: pending_candidates.json (from M3)
**Outputs**: news records + JSON feed (for M5 AI thesis agent)

**Success Criteria**:
- Fetch announcements for all candidates
- Store with metadata + document hash
- Log API availability
- ≥80% test coverage
- Example: [sample news output]
```

---

## Estimated Timeline (M3 → M9)

| Milestone | Duration | Start When | Your Effort |
|-----------|----------|-----------|-----------|
| **M3** | 2–3 days | Now | Execute calibration (1–2 hrs) |
| **M3 Closure** | 30 min | After calibration | Review + approve |
| **M4** | 1 day | After M3 approved | Monitor + spot-check |
| **M5** | 2–3 days | After M4 approved | Test prompt quality |
| **M6** | 1 day | After M5 approved | Design portfolio UX |
| **M7** | 1 day | After M6 approved | Spot-check tickets |
| **M8** | 1 day | After M7 approved | Run daily pipeline |
| **M9** | 6–8 weeks | After M8 approved | Execute trades + record |
| **Total** | ~8–10 weeks | Now | ~8–10 hrs active, mostly M7–M9 |

---

## During Calibration: What to Watch For

### Red Flags 🚩
- **Results don't improve with threshold tightening**
  - Example: volume=2.5 gives same results as volume=1.5
  - Likely cause: Volume spike isn't the main driver; try 52wk extreme adjustment
  - **Action**: Skip to Iteration 2 (tighten extreme)

- **Results swing wildly day-to-day**
  - Example: 3, 12, 2, 15, 4 matches/day
  - **This is normal** — different market days have different signals
  - Look at **average** (not individual days)
  - If average is in range (2–8/day), you're good

- **Can't get within target range after 3 iterations**
  - Example: Best you can do is 10–12/day (just above target)
  - **Escalate to me** — we can discuss:
    - Accept higher target (10–15/day)?
    - Try different thresholds?
    - Change screening approach?

### Green Signs ✅
- Threshold tightening causes proportional match reduction
  - Example: volume 1.5→2.5 reduces 17→8 (roughly 50% reduction)
  - Signals are working as designed

- 5-day replay shows consistency
  - Example: 6, 7, 5, 8, 6 matches/day (±1–2 variation)
  - Normal market variation; thresholds are stable

- Live run matches 5-day replay
  - Example: 5-day avg=7, live run today=6 matches
  - Confirms screener is deterministic

---

## If Something Goes Wrong

### Can't Run fm screening
```bash
# Check mh_test server
curl http://localhost:8766/health

# Check Python environment
python -m pip list | grep financial-market

# Try rebuilding
pip install -e .
```

### Repo is Messy
```bash
# Revert config to baseline
cp config/risk_rules_sgx.json.baseline config/risk_rules_sgx.json

# Start over
fm screening dry-run --days 5
```

### Need Help
- **Data question**: Ask Claude (me)
- **Technical issue**: Codex can help debug
- **Threshold strategy**: Ask Claude

---

## Post-M9: What's Next?

Once shadow mode (M9) is complete and success criteria are met:

**You will decide**:
- ✅ **Go Live**: Deploy Phase A screener to production
  - Manual execution continues (no automation)
  - Real money trades (SGD 50K account)
  - Real P&L tracking

- OR

- ⚠️ **Iterate**: Tweak thresholds based on shadow-mode results
  - Run another 30-day shadow cycle
  - Refine before going live

This is a **human decision**. Not automated. You review the data, Codex provides analysis, and you approve live trading.

---

## Checklist: Ready for M4?

- [ ] Calibration complete
- [ ] 5-day replay in target range (2–8/day)
- [ ] Results template filled out
- [ ] M3 closure document created
- [ ] Config changes committed to Git
- [ ] Live screening run confirmed
- [ ] Results sent to Claude
- [ ] Claude approves M4 start

---

**Ready to calibrate?** Start with `docs/M3_CALIBRATION_PLAYBOOK.md` and `docs/M3_CALIBRATION_QUICK_REF.md`.

**Questions during calibration?** Ask. Don't guess.

**Let's go!** 🚀
