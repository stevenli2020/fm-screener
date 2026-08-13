# M3 Calibration Results Template

**Fill this in as you calibrate.** Send back to Claude when done.

---

## Session Info

- **Date**: 2026-08-12
- **Time Started**: ___:___
- **Executor**: You

---

## Baseline (Before Any Changes)

```
Matches per day (5-day replay, 2026-08-08 to 2026-08-12):
Day 1 (2026-08-08): 17 matches
Day 2 (2026-08-09): 17 matches
Day 3 (2026-08-10): 15 matches
Day 4 (2026-08-11): 18 matches
Day 5 (2026-08-12): 18 matches

Average: 17.0 matches/day
Status: TOO HIGH (target: 2–8/day)

Current Thresholds:
- volume_spike_min_multiple: 1.5
- pct_from_52wk_extreme_min_pct: 5.0
```

---

## Iteration 1: Tighten Volume Spike

**Adjustment Made**:
```
volume_spike_min_multiple: 1.5 → 2.5
pct_from_52wk_extreme_min_pct: 5.0 (unchanged)
```

**Date/Time Run**: 2026-08-12 at ___:___

**5-Day Replay Results** (paste command output or manually record):
```
Day 1 (2026-08-08): ___ matches
Day 2 (2026-08-09): ___ matches
Day 3 (2026-08-10): ___ matches
Day 4 (2026-08-11): ___ matches
Day 5 (2026-08-12): ___ matches

Average: ___ matches/day
```

**Analysis**:
- Reduction from baseline: ___ → ___ (approximately ___ matches/day less)
- Status: 
  - [ ] ✅ IN RANGE (2–8/day) → **LOCK THRESHOLDS & SKIP TO STEP 7**
  - [ ] ❌ STILL TOO HIGH (>8/day) → **PROCEED TO ITERATION 2**
  - [ ] ❌ TOO LOW (<2/day) → **REVERT & TRY SMALLER ADJUSTMENT**

**Notes**: _______________

---

## Iteration 2: Tighten 52-Week Extreme (If Needed)

**Adjustment Made**:
```
volume_spike_min_multiple: 2.5 (unchanged)
pct_from_52wk_extreme_min_pct: 5.0 → 2.5
```

**Date/Time Run**: 2026-08-12 at ___:___

**5-Day Replay Results**:
```
Day 1 (2026-08-08): ___ matches
Day 2 (2026-08-09): ___ matches
Day 3 (2026-08-10): ___ matches
Day 4 (2026-08-11): ___ matches
Day 5 (2026-08-12): ___ matches

Average: ___ matches/day
```

**Analysis**:
- Reduction from iteration 1: ___ → ___ (approximately ___ matches/day less)
- Status:
  - [ ] ✅ IN RANGE (2–8/day) → **LOCK THRESHOLDS & SKIP TO STEP 7**
  - [ ] ❌ STILL TOO HIGH (>8/day) → **PROCEED TO ITERATION 3**
  - [ ] ❌ TOO LOW (<2/day) → **REVERT & TRY DIFFERENT APPROACH**

**Notes**: _______________

---

## Iteration 3: Further Adjustment (If Needed)

**Adjustment Made**:
```
volume_spike_min_multiple: ___ (from: ___)
pct_from_52wk_extreme_min_pct: ___ (from: ___)
```

**Date/Time Run**: 2026-08-12 at ___:___

**5-Day Replay Results**:
```
Day 1: ___ matches
Day 2: ___ matches
Day 3: ___ matches
Day 4: ___ matches
Day 5: ___ matches

Average: ___ matches/day
```

**Analysis**:
- Status:
  - [ ] ✅ IN RANGE (2–8/day) → **LOCK THRESHOLDS**
  - [ ] ❌ STILL NEEDS TUNING → **ESCALATE TO CLAUDE**

**Notes**: _______________

---

## Final Thresholds (LOCKED)

```json
{
  "screening": {
    "signals": {
      "price_move_60d_min_pct": 10.0,
      "price_move_60d_max_pct": 50.0,
      "volume_spike_min_multiple": ___,
      "pct_from_52wk_extreme_min_pct": ___,
      "donchian_breakout_threshold_pct": 85.0,
      "volatility_lookback_days": 20,
      "donchian_lookback_days": 55
    }
  }
}
```

---

## Final Validation

**Live Screening Run** (sanity check):

```bash
fm screening run
```

**Output**:
```
Matches today: ___ (should be similar to 5-day avg)
Report generated: ✅
JSON output: ✅
```

---

## Calibration Summary

| Metric | Value | Status |
|--------|-------|--------|
| Starting matches/day | 17.0 | Too high ❌ |
| Ending matches/day | ___ | ✅ In range? |
| Iterations needed | ___ (1? 2? 3?) | — |
| Time spent | ___ min | — |
| Final volume_spike | ___ | Locked ✅ |
| Final 52wk_extreme | ___ | Locked ✅ |

---

## Next Steps (After Calibration Locked)

- [ ] Create M3 closure document (see template below)
- [ ] Commit config changes to Git
- [ ] **START M4 (News Pipeline)**

---

## Approval

**Calibrated by**: You  
**Date**: 2026-08-12  
**Approved by**: Claude (Advisor) — pending results  

**Status**: ⏳ AWAITING RESULTS

---

## TEMPLATE: M3 Closure Document

(Copy this to `docs/milestones/M3-phase-a-screener.md` once calibration is locked)

```markdown
# M3 — Phase A Screener (CLOSED)

## Approval
- Approved: 2026-08-12
- Reviewer: Claude (Advisor)
- Status: ✅ APPROVED

## Delivered
- Five deterministic signals (price move, volume, 52wk extreme, volatility, Donchian)
- Eligibility enforcement (120 bars, repair count, staleness, price adjustment)
- `fm screening run` and `fm screening dry-run` CLI commands
- JSON + Markdown outputs + SQLite audit trail
- 46 tests, 87% coverage

## Calibration Applied
- **volume_spike_min_multiple**: 1.5 → [FINAL VALUE]
- **pct_from_52wk_extreme_min_pct**: 5.0 → [FINAL VALUE]
- **Calibration date**: 2026-08-12
- **5-day replay average**: [FINAL VALUE] matches/day (target: 2–8/day) ✅

## Known Limitations
- Volatility signal calculated but not thresholded (defer to M9)
- 52-week distance is long-only (doesn't flag breakdowns; by design)
- No correlation/diversification checks (rank by signal strength only)

## Dependencies for Later Milestones
- M4 (news): Use `pending_candidates.json` output
- M7 (Phase B): Use rankings for trade-ticket generation
- M9 (shadow): Backtest 30–60 days to validate signal quality post-deployment

## Approved for M4 Start
- ✅ Ready to proceed
```
