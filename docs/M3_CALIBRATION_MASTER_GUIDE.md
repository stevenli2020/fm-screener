# M3 Calibration Execution Master Guide

**You are here**: M3 calibration phase

**Your goal**: Lock screener thresholds so match rate is 2–8/day (target range)

**Estimated time**: 1–2 hours

---

## File Navigation Guide

| File | Purpose | When to Use |
|------|---------|------------|
| **M3_CALIBRATION_QUICK_REF.md** | One-page cheat sheet | **START HERE** — keep open while calibrating |
| **M3_CALIBRATION_PLAYBOOK.md** | Detailed step-by-step | Reference for each step (backup, edit, test, evaluate) |
| **M3_CALIBRATION_RESULTS_TEMPLATE.md** | Recording sheet + closure template | Fill this in as you calibrate; send results to Claude |
| **M3_CALIBRATION_POSTMORTEM.md** | What happens after; preview of M4 | Read after calibration is locked (for context) |
| **M3-phase-a-review-report.md** | Codex's original M3 report | Already completed (reference only) |

---

## Execution Sequence

### Phase 1: Preparation (5 min)

1. Open `M3_CALIBRATION_QUICK_REF.md` in one window
2. Open `config/risk_rules_sgx.json` in editor (other window)
3. Have terminal ready to run `fm screening dry-run --days 5`
4. Read through `M3_CALIBRATION_PLAYBOOK.md` Steps 1–2 (backup, understand baseline)

### Phase 2: First Iteration (15–20 min)

1. **Step 1 (Playbook)**: Backup config
   ```bash
   cp config/risk_rules_sgx.json config/risk_rules_sgx.json.baseline
   ```

2. **Step 2 (Playbook)**: Edit config
   - Change `volume_spike_min_multiple: 1.5` → `2.5`
   - Save file

3. **Step 3 (Playbook)**: Run 5-day replay
   ```bash
   fm screening dry-run --days 5
   ```

4. **Step 4 (Results Template)**: Record results
   - Paste output or manually record match counts
   - Calculate average

5. **Step 4 (Playbook)**: Evaluate
   - ✅ In range (2–8/day)? → **SKIP TO PHASE 4**
   - ❌ Still too high? → **PROCEED TO PHASE 3**
   - ❌ Too low? → **REVERT & TRY VOLUME=3.0 INSTEAD**

### Phase 3: Second Iteration (If Needed, 15–20 min)

1. **Step 5 (Playbook)**: Edit config again
   - Change `pct_from_52wk_extreme_min_pct: 5.0` → `2.5`
   - Keep volume at 2.5
   - Save file

2. **Step 6 (Playbook)**: Run 5-day replay again
   ```bash
   fm screening dry-run --days 5
   ```

3. **Step 4 (Results Template)**: Record results (Iteration 2 section)
   - Compare to Iteration 1
   - Calculate average

4. **Step 4 (Playbook)**: Evaluate
   - ✅ In range? → **PROCEED TO PHASE 4**
   - ❌ Still high? → Consider 3rd iteration (or escalate)

### Phase 4: Lock Thresholds (10 min)

1. **Step 7 (Playbook)**: Confirm final config
   ```bash
   cat config/risk_rules_sgx.json | grep -A 10 '"screening"'
   ```

2. **Step 7 (Playbook)**: Run live screening (sanity check)
   ```bash
   fm screening run
   ```

3. **Results Template**: Fill in "Final Thresholds (LOCKED)" section

4. **Results Template**: Create M3 Closure document
   - Copy template from "TEMPLATE: M3 Closure Document" section
   - Save to `docs/milestones/M3-phase-a-screener.md`
   - Fill in actual values

### Phase 5: Report Back (5 min)

1. Send results template to Claude (fill in entire "Session Info" → "Approval" sections)
2. Include:
   - Baseline vs. final match counts
   - Thresholds changed
   - Iterations needed
   - Time spent

3. Wait for Claude approval before proceeding to M4

---

## Real Example (What It Looks Like)

**Baseline**: 17 matches/day (too high)

**Iteration 1**: Change volume to 2.5
```
5-day replay results:
Day 1: 12 matches ↓
Day 2: 11 matches ↓
Day 3: 10 matches ↓
Day 4: 11 matches ↓
Day 5: 11 matches ↓
Average: 11 matches/day (still too high)
```

**Iteration 2**: Change extreme to 2.5
```
5-day replay results:
Day 1: 7 matches ✅
Day 2: 6 matches ✅
Day 3: 5 matches ✅
Day 4: 7 matches ✅
Day 5: 6 matches ✅
Average: 6.2 matches/day (IN RANGE!)
```

**LOCK**: volume=2.5, extreme=2.5

---

## Key Points

### Don't Overthink This
- You're just adjusting numbers
- If it doesn't work, revert and try again
- Very hard to break anything permanently

### What Counts as "In Range"
- **2–8 matches/day** or **10–40 matches/week**
- Your average over 5 days should be in this range
- Individual days ±1–2 variation is normal

### If You Get Stuck
- **Results didn't improve?** Try bigger adjustment (volume 3.0 instead of 2.5)
- **Results too low?** Revert and try smaller adjustment (volume 2.0)
- **Can't converge?** Document attempts and escalate to Claude

### Commit Changes When Done
```bash
git add config/risk_rules_sgx.json
git add docs/milestones/M3-phase-a-screener.md
git commit -m "M3 calibration: volume=2.5, extreme=2.5"
```

---

## Success Looks Like

```
✅ Calibration complete
✅ 5-day replay in range (2–8/day)
✅ Live screening run confirms consistency
✅ Config locked
✅ M3 closure document created
✅ Results sent to Claude
✅ Claude approves M4 start
```

---

## Commands Cheat Sheet

```bash
# Backup config
cp config/risk_rules_sgx.json config/risk_rules_sgx.json.baseline

# Edit config (use your editor, or sed)
# nano config/risk_rules_sgx.json
# OR find/replace: volume_spike_min_multiple: 1.5 → 2.5

# Test
fm screening dry-run --days 5

# Verify (paste results into template)

# Sanity check (when in range)
fm screening run

# Commit
git add config/risk_rules_sgx.json docs/milestones/M3-phase-a-screener.md
git commit -m "M3 calibration: volume=X, extreme=Y"
```

---

## Troubleshooting Map

| Issue | Solution | Playbook Section |
|-------|----------|------------------|
| Command not found | Start mh_test server | N/A (ask Codex) |
| Results don't change | Try bigger adjustment | Step 5 (Iteration 2+) |
| Results too low | Revert; try smaller | Step 5 (Iteration 2) |
| Can't hit target | Escalate to Claude | N/A |
| Made mistake | `cp baseline config` | Playbook Troubleshooting |

---

## Workflow Diagram

```
START
  ↓
[Backup config] ← Step 1
  ↓
[Edit: volume=2.5] ← Step 2
  ↓
[Run 5-day replay] ← Step 3
  ↓
[Record results] ← Step 4
  ↓
In range? ───YES──→ [LOCK THRESHOLDS] → [CREATE CLOSURE DOC] → END ✅
  │
  NO
  │
  ↓
[Edit: extreme=2.5] ← Step 5
  ↓
[Run 5-day replay] ← Step 6
  ↓
[Record results]
  ↓
In range? ───YES──→ [LOCK & CLOSE]
  │
  NO
  │
  ↓
[Try 3rd adjustment OR escalate]
```

---

## Time Breakdown

- Backup + edit: 5 min
- First test + record: 10 min
- Evaluate + decide: 5 min
- If 2nd iteration: +15 min
- Lock + create closure: 10 min
- **Total**: 30–60 min (depends on iterations)

---

## Next Steps After Calibration

1. **Send results to Claude** (results template filled in)
2. **Wait for approval** (usually <1 hour)
3. **Create M3 closure** (copy template, fill in values)
4. **Commit to Git**
5. **Codex starts M4** (news pipeline)

---

## Master Checklist (Copy & Paste into Notes)

```
[ ] Backup config
[ ] Edit 1: volume=2.5
[ ] Test: fm screening dry-run --days 5
[ ] Record Iteration 1 results
[ ] Evaluate: in range?
  [ ] YES → Skip to LOCK
  [ ] NO → Continue
[ ] Edit 2: extreme=2.5
[ ] Test: fm screening dry-run --days 5
[ ] Record Iteration 2 results
[ ] Evaluate: in range?
  [ ] YES → LOCK
  [ ] NO → Escalate
[ ] Confirm final config (cat config/...)
[ ] Live run: fm screening run
[ ] Fill results template completely
[ ] Create M3 closure document
[ ] Commit to Git
[ ] Send results to Claude
[ ] Wait for approval
[ ] Start M4 ✅
```

---

**Ready?** Open `M3_CALIBRATION_QUICK_REF.md` and start. You got this! 🚀
