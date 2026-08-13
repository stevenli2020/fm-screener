# M3 Calibration Quick Reference

**Quick version** — use this while executing calibration.

---

## Current State (Baseline)

```
Matches/day: 17–18 (target: 2–8)
Config location: config/risk_rules_sgx.json
```

---

## Thresholds to Adjust

| Signal | Current | Try 1st | Try 2nd |
|--------|---------|---------|---------|
| volume_spike_min_multiple | 1.5 | **2.5** | 3.0 |
| pct_from_52wk_extreme_min_pct | 5.0 | 5.0 | **2.5** |
| price_move_60d_min_pct | 10.0 | 10.0 | 10.0 |
| price_move_60d_max_pct | 50.0 | 50.0 | 50.0 |
| donchian_breakout_threshold_pct | 85.0 | 85.0 | 85.0 |

---

## Execution Sequence

### 1. Backup
```bash
cp config/risk_rules_sgx.json config/risk_rules_sgx.json.baseline
```

### 2. Edit (First Adjustment)
```json
"volume_spike_min_multiple": 2.5,  // ← change this
```

### 3. Test
```bash
fm screening dry-run --days 5
```

### 4. Record Results
```
Day 1: ___ matches
Day 2: ___ matches
Day 3: ___ matches
Day 4: ___ matches
Day 5: ___ matches
Average: ___ matches/day
```

### 5. Evaluate
- ✅ In range (2–8/day)? → **LOCK** (skip Step 6)
- ❌ Still high (>8/day)? → **Step 6**
- ❌ Too low (<2/day)? → **REVERT + TRY 3.0 INSTEAD**

### 6. Second Adjustment (If Needed)
```json
"pct_from_52wk_extreme_min_pct": 2.5,  // ← change this
```

### 7. Test Again
```bash
fm screening dry-run --days 5
```

### 8. Record & Evaluate
- ✅ In range? → **LOCK**
- ❌ Still high? → **TRY 3RD ADJUSTMENT** (volume to 3.0, or extreme to 1.5)

---

## Lock Thresholds

Once in range:

```bash
# Confirm current config
cat config/risk_rules_sgx.json | grep -A 10 '"screening"'

# Run live once more
fm screening run

# Create log (see M3_CALIBRATION_PLAYBOOK.md Step 7)
```

---

## Report Format

```
Iteration 1: volume=2.5
Results: X, X, X, X, X
Average: X/day
Status: [IN RANGE / TOO HIGH / TOO LOW]

Iteration 2: volume=2.5, extreme=2.5
Results: X, X, X, X, X
Average: X/day
Status: [LOCKED / NEEDS MORE]

FINAL: volume=___, extreme=___
```

---

## What If?

| Problem | Solution |
|---------|----------|
| Made mistake | `cp config/risk_rules_sgx.json.baseline config/risk_rules_sgx.json` |
| Results too variable | Look at **average**, not individual days |
| Can't hit target | Report to Claude; may adjust target or try different approach |

---

**Estimated time**: 30–60 minutes (3 iterations max)

Go execute! 🚀
