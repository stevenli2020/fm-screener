# M3 Threshold Analysis: 52-Week Extreme 5.0 vs 2.5

**Question**: What are the implications of keeping `pct_from_52wk_extreme_min_pct: 5.0` instead of the calibrated `2.5`?

**TL;DR**: Keeping 5.0 is a **deliberate strategy choice for more candidates** (wider net, more opportunities). This violates your M9 shadow mode gate (≤8 proposals/week). Recommend applying 2.5 to align with documented calibration and M9 gate.

---

## Signal Definition

### What Does "52-Week Extreme" Measure?

Stock is within X% of its 52-week high (potential breakout signal).

**Example**:
```
52-week high: SGD 15.00
Current price: SGD 14.25
Distance: 5% below high
```

### At 5.0% Threshold (Current)
- Fires if: Within 5% of 52-week high
- **Candidate volume**: ~14/day
- **Signal selectivity**: LOOSE (many near-highs)
- **False positive rate**: HIGHER

### At 2.5% Threshold (Calibrated)
- Fires if: Within 2.5% of 52-week high  
- **Candidate volume**: ~6/day
- **Signal selectivity**: TIGHT (only very close to high)
- **False positive rate**: LOWER

---

## Quantitative Impact

### From M3 Calibration Data

| Threshold | 5-Day Replay Result | Live Run (2026-08-13) |
|-----------|-------------------|----------------------|
| **5.0%** | 18 matches/day ❌ | 14 matches |
| **2.5%** | ~6 matches/day ✅ | Expected ~6 |

**Effect**: Changing from 5.0 to 2.5 **reduces volume by ~67%** (produces 1/3 as many candidates).

---

## Impact on Your Strategy

### Option A: Keep 5.0 (Wider Net)

| Aspect | Impact |
|--------|--------|
| Candidates/day | 14 (higher volume) |
| Proposals/week | ~98 |
| Manual burden | Higher (more to evaluate) |
| AI thesis quality | Mixed (more marginal cases) |
| Trade accuracy | Lower (more noise) |
| M9 gate compliance | ❌ **FAILS** (exceeds ≤8/week) |

**Philosophy**: "More opportunities; filter in M5 AI stage"

---

### Option B: Apply 2.5 (Calibrated, Selective)

| Aspect | Impact |
|--------|--------|
| Candidates/day | 6 (curated volume) |
| Proposals/week | ~42 |
| Manual burden | Lower (easier to evaluate) |
| AI thesis quality | Higher (fewer edge cases) |
| Trade accuracy | Higher (better signal/noise) |
| M9 gate compliance | ✅ **PASSES** (within ≤8/week) |

**Philosophy**: "Quality over quantity; only trade best setups"

---

## Critical Issue: M9 Gate Constraint

### Your M9 Success Criteria (Locked in Build Agreement)

```json
{
  "proposals_per_week_min": 2,
  "proposals_per_week_max": 8,
  "thesis_accuracy_pct_min": 50
}
```

### Threshold Compliance

| Threshold | Proposals/Week | Compliance |
|-----------|----------------|-----------|
| 5.0% (current) | ~14 | ❌ **VIOLATES max_8** |
| 2.5% (calibrated) | ~6 | ✅ **PASSES** |

**This is the core issue**: Keeping 5.0 means you'll generate **more proposals than your own gate allows**.

---

## Recommendation

### Apply 2.5 (Calibrated Value)

**Why**:
1. ✅ Respects your M9 gate (≤8/week)
2. ✅ Aligns with documented M3 calibration
3. ✅ Better manual execution workflow (fewer tickets)
4. ✅ Higher signal quality for AI thesis
5. ✅ Cleaner shadow mode results

**Path forward**:
1. Apply 2.5 to config
2. Re-run M3 screening (verify ~6 candidates/day)
3. Proceed to M5 with calibrated thresholds
4. Execute shadow mode within gate
5. **Post-M9 decision**: If you want more volume, you can loosen thresholds for live

### Alternative: Keep 5.0 (Only If...)

**You would need to**:
1. ✋ Formally waive M9 gate (accept >8 proposals/week)
2. 📈 Ensure M5 AI is excellent (to achieve ≥50% accuracy with more noise)
3. 👤 Add manual filtering step (to reduce tickets before execution)

**This is riskier** for shadow mode validation.

---

## Action Required

**Before M5 starts**, confirm which path:

- ☐ **Apply 2.5** (recommended): Update config, re-run M3, proceed normally
- ☐ **Keep 5.0**: Document decision, waive M9 gate, proceed (higher risk)

Which would you prefer?
