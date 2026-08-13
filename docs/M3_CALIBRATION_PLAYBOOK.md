# M3 Threshold Calibration Playbook

**Goal**: Reduce screener matches from 18/day to target range (2–8/day or ~10–40/week)

**Timeline**: ~1–2 hours (3–4 iteration cycles)

**Owner**: You (executing calibration)

---

## Before You Start: Understand Current State

**Baseline**:
- Live run (2026-08-12): **18 matches/day**
- 5-day replay (2026-08-08 to 2026-08-12): **17, 17, 15, 18, 18** matches
- **Average**: ~17 matches/day (~85 matches/week) — **WAY above target**

**Target**: 2–8 matches/day (~10–40/week)

**Task**: Find thresholds that drop this to target range without losing good candidates.

---

## Step 1: Backup Current Config

**Action**: Make a snapshot of current thresholds before you start tuning.

```bash
cd D:\Projects\FinancialMarket
cp config/risk_rules_sgx.json config/risk_rules_sgx.json.baseline
cat config/risk_rules_sgx.json | grep -A 10 '"screening"'
```

**Record baseline thresholds** (you'll compare before/after):

| Signal | Current | Will Adjust? |
|--------|---------|-------------|
| price_move_60d_min_pct | 10.0 | ❌ Keep |
| price_move_60d_max_pct | 50.0 | ❌ Keep |
| **volume_spike_min_multiple** | **1.5** | ✅ **Tighten to 2.5** |
| **pct_from_52wk_extreme_min_pct** | **5.0** | ✅ **Maybe tighten to 2.5** |
| donchian_breakout_threshold_pct | 85.0 | ❌ Keep |

---

## Step 2: First Adjustment — Tighten Volume Spike

**Why**: Volume spike at 1.5x is very loose. SGX is quiet; 1.5x catches most days. Tightening to 2.5x should cut matches significantly.

**Action**: Edit `config/risk_rules_sgx.json`

Find this section:
```json
{
  "screening": {
    "signals": {
      "price_move_60d_min_pct": 10.0,
      "price_move_60d_max_pct": 50.0,
      "volume_spike_min_multiple": 1.5,
      "pct_from_52wk_extreme_min_pct": 5.0,
      "donchian_breakout_threshold_pct": 85.0,
      "volatility_lookback_days": 20,
      "donchian_lookback_days": 55
    }
  }
}
```

**Change**:
```json
      "volume_spike_min_multiple": 2.5,  // was 1.5
```

**Save the file.**

---

## Step 3: Run 5-Day Replay with New Threshold

**Action**: Run historical consistency check

```bash
cd D:\Projects\FinancialMarket
fm screening dry-run --days 5
```

**What this does**:
- Replays screening for the last 5 trading days (2026-08-08 to 2026-08-12)
- Uses new threshold (volume_spike = 2.5x)
- Shows match counts per day

**Expected output** (example):
```
2026-08-08: 38 eligible, 12 matched ← down from 17 ✅
2026-08-09: 38 eligible, 10 matched ← down from 17 ✅
2026-08-10: 38 eligible, 9 matched  ← down from 15 ✅
2026-08-11: 38 eligible, 11 matched ← down from 18 ✅
2026-08-12: 38 eligible, 10 matched ← down from 18 ✅

Average: 10.4 matches/day (target range: 2–8/day)
```

**Record results**:

| Iteration | Threshold Changed | 5-Day Results | Avg/Day | Status |
|-----------|------------------|---------------|---------|--------|
| Baseline | volume=1.5 | 17,17,15,18,18 | 17.0 | ✅ Baseline |
| **1** | **volume=2.5** | **?,?,?,?,?** | **?** | ⏳ Running |

---

## Step 4: Evaluate Results

**Scenarios**:

### Scenario A: Results are in target range (2–8/day) ✅

**Example**: New results are 6, 5, 7, 6, 5 matches/day (avg 5.8)

**Action**: 
- ✅ **STOP.** You found good thresholds.
- Document and lock (go to Step 7)

### Scenario B: Results are still too high (>8/day)

**Example**: New results are 12, 11, 10, 11, 10 matches/day (avg 10.8)

**Action**:
- You need to tighten more
- Go to **Step 5** (tighten 52wk extreme)

### Scenario C: Results are too low (<2/day)

**Example**: New results are 1, 0, 2, 1, 1 matches/day (avg 1.0)

**Action**:
- You over-tightened; revert and adjust differently
- Go back to baseline and try smaller adjustment (volume = 2.0 instead of 2.5)

---

## Step 5: Second Adjustment (If Needed) — Tighten 52-Week Extreme

**Only do this if Step 4 Scenario B (still too high)**

**Why**: 52-week extreme at 5% is loose. Many stocks stay within 5% of their high. Tightening to 2.5% should catch fewer candidates.

**Action**: Edit `config/risk_rules_sgx.json`

```json
      "pct_from_52wk_extreme_min_pct": 2.5,  // was 5.0
```

**Save the file.**

---

## Step 6: Run 5-Day Replay Again

```bash
fm screening dry-run --days 5
```

**Record results**:

| Iteration | Threshold Changed | 5-Day Results | Avg/Day | Status |
|-----------|------------------|---------------|---------|--------|
| Baseline | volume=1.5 | 17,17,15,18,18 | 17.0 | ✅ Baseline |
| 1 | volume=2.5 | (results from Step 4) | 10.8 | ⏳ Too high |
| **2** | **volume=2.5 + extreme=2.5** | **?,?,?,?,?** | **?** | ⏳ Running |

**Evaluate**:
- If now in range (2–8/day): **STOP, lock thresholds** (Step 7)
- If still too high: **Tighten one more** (Step 5 again, but more aggressive)
- If too low: **Revert 52wk back to 5.0** and try smaller adjustment

---

## Step 7: Lock Thresholds + Document

**Once you hit target range (2–8/day)**, lock your final thresholds.

### A. Record Final Config

```bash
cat config/risk_rules_sgx.json | grep -A 10 '"screening"'
```

**Create a calibration log** (new file or add to README):

Create `docs/M3_CALIBRATION_LOG.md`:

```markdown
# M3 Calibration Log

## Objective
Reduce screener matches from 17–18/day to target range 2–8/day

## Calibration Results

### Baseline (2026-08-12)
- volume_spike_min_multiple: 1.5
- pct_from_52wk_extreme_min_pct: 5.0
- **5-day replay results**: 17, 17, 15, 18, 18 matches/day
- **Average**: 17.0 matches/day ❌ Too high

### Iteration 1 (2026-08-12)
- volume_spike_min_multiple: 1.5 → **2.5**
- pct_from_52wk_extreme_min_pct: 5.0 (unchanged)
- **5-day replay results**: [YOUR RESULTS HERE]
- **Average**: [YOUR AVERAGE HERE]
- **Status**: [On target? Too high? Too low?]

### Iteration 2 (if needed)
- volume_spike_min_multiple: 2.5
- pct_from_52wk_extreme_min_pct: 5.0 → **2.5**
- **5-day replay results**: [YOUR RESULTS HERE]
- **Average**: [YOUR AVERAGE HERE]
- **Status**: [On target? Too high? Too low?]

## Final Thresholds (LOCKED)
- price_move_60d_min_pct: 10.0 (unchanged)
- price_move_60d_max_pct: 50.0 (unchanged)
- volume_spike_min_multiple: **[FINAL VALUE]**
- pct_from_52wk_extreme_min_pct: **[FINAL VALUE]**
- donchian_breakout_threshold_pct: 85.0 (unchanged)

## Calibration Date
2026-08-12

## Approval
- Calibration performed by: [You]
- Results reviewed by: Claude (Advisor)
- Status: ✅ LOCKED

## Notes
- Volatility still not thresholded (will calibrate post-M9)
- Donchian threshold kept at 85% (reasonable for breakouts)
- Price move range kept at ±10–50% (good signal quality)
```

### B. One Final Validation

Run live screening one more time to confirm:

```bash
fm screening run
```

**Check output**:
- Should show similar match count to your 5-day replay
- All signals auditable in JSON
- Markdown report generated

---

## Step 8: Report Back to Me

Once calibration is locked, send me:

```
CALIBRATION COMPLETE ✅

Final Thresholds:
- volume_spike_min_multiple: [X] (was 1.5)
- pct_from_52wk_extreme_min_pct: [Y] (was 5.0)

5-Day Replay Results:
- [date]: N matches
- [date]: N matches
- [date]: N matches
- [date]: N matches
- [date]: N matches
Average: N matches/day (target: 2–8/day)

Status: [LOCKED / NEEDS MORE TUNING]
```

---

## Troubleshooting

### Problem: I made a mistake, want to revert
```bash
cp config/risk_rules_sgx.json.baseline config/risk_rules_sgx.json
fm screening dry-run --days 5  # Start over
```

### Problem: 5-day replay not showing results
```bash
# Check if mh_test server is running
curl http://localhost:8766/health

# If not, you may need to start it (depends on your setup)
```

### Problem: Results are too varied day-to-day (17, 8, 15, 12, 10)
**This is normal.** Different market conditions on different days. Look at the **average** across 5 days, not individual days.

### Problem: Can't get within target range
- You might need a 3rd threshold adjustment
- Or your target range (2–8/day) is too tight for this strategy
- **Escalate to me** — we can discuss whether target should be higher (10–20/day) or approach differently

---

## Success Checklist

- [ ] Baseline recorded (volume=1.5, 52wk=5.0)
- [ ] First adjustment made (volume=2.5)
- [ ] 5-day replay run
- [ ] Results recorded
- [ ] Target range hit? (2–8/day)
  - [ ] Yes → Lock thresholds (Step 7)
  - [ ] No → Second adjustment (Step 5)
- [ ] Calibration log created
- [ ] Live screening run once more (sanity check)
- [ ] Results reported to me

---

## Go Execute

**Start now**:

```bash
cd D:\Projects\FinancialMarket
cp config/risk_rules_sgx.json config/risk_rules_sgx.json.baseline
# Edit config/risk_rules_sgx.json (change volume to 2.5)
fm screening dry-run --days 5
```

**Report results** when done. I'll help debug if needed. 🚀
