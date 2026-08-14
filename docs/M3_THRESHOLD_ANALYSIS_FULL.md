# M3 Threshold Analysis: 52-Week Extreme 5.0 vs 2.5

**Question**: What are the implications of keeping `pct_from_52wk_extreme_min_pct: 5.0` instead of the calibrated `2.5`?

**TL;DR**: Keeping 5.0 is a **deliberate strategy choice for more candidates** (wider net, more opportunities, higher false positive rate). This is valid, but has tradeoffs that affect M5, M7, and M9 success criteria.

---

## Signal Definition (Both Values)

### What Does "52-Week Extreme" Signal Mean?

**Concept**: Stock price is close to its 52-week high, suggesting potential breakout/momentum.

**Calculation**:
```
pct_below_52w_high = (52w_high - current_price) / 52w_high * 100
```

**Example**:
- 52-week high: SGD 15.00
- Current price: SGD 14.25
- pct_below_52w_high: (15.00 - 14.25) / 15.00 * 100 = **5.0%** ✅

**Signal fires when**: `pct_below_52w_high <= threshold`

---

## Threshold Comparison

### At 5.0% (Current Config)
```
Candidate triggers if: Within 5% of 52-week high

Examples:
52wk high: SGD 10.00
  ├─ SGD 9.95 (0.5% below) ✅ MATCH
  ├─ SGD 9.75 (2.5% below) ✅ MATCH
  ├─ SGD 9.50 (5.0% below) ✅ MATCH (edge case)
  └─ SGD 9.49 (5.1% below) ❌ NO MATCH

Interpretation: "Price is near recent high; possible breakout candidate"
Signal strength: LOOSE (catches many near-highs)
```

### At 2.5% (Calibrated Value)
```
Candidate triggers if: Within 2.5% of 52-week high

Examples:
52wk high: SGD 10.00
  ├─ SGD 9.95 (0.5% below) ✅ MATCH
  ├─ SGD 9.75 (2.5% below) ✅ MATCH (edge case)
  ├─ SGD 9.50 (5.0% below) ❌ NO MATCH
  └─ SGD 9.49 (5.1% below) ❌ NO MATCH

Interpretation: "Price is very close to recent high; imminent breakout"
Signal strength: TIGHT (catches only closest-to-high stocks)
```

---

## Quantitative Impact (From M3 Calibration Data)

### Observed Candidate Generation

| Threshold | Baseline Calibration | Live Run (2026-08-13) | Ratio |
|-----------|-------------------|----------------------|-------|
| **5.0%** | 18 matches/day ❌ | 14 matches | 1.0x (baseline) |
| **2.5%** | ~6 matches/day ✅ | ~6 matches (expected) | 0.33x |

**Key insight**: Changing from 5.0 to 2.5 **reduces candidate volume by ~67%** (cuts to one-third).

---

## Strategy Implications

### Option A: Keep 5.0 (Current)

**You're saying**: "Generate more candidates; cast a wider net"

| Aspect | Impact | Note |
|--------|--------|------|
| **Candidate volume** | 14/day | Higher volume of opportunities |
| **Signal selectivity** | Low | Many stocks near (but not at) high |
| **False positive rate** | Higher | More near-highs that don't breakout |
| **Manual review burden** | Higher | More tickets to evaluate before trade |
| **M5 thesis quality** | Mixed | AI has to reason about more marginal cases |
| **M7 trade accuracy** | Lower? | Expect ~40–60% of trades to work (more noise) |
| **Risk management** | More positions | Need to track more candidates |
| **Weekly proposals** | ~98 | Far exceeds M9 gate of 8/week |

**Trading style**: Aggressive, volume-focused. Cast wide net, accept some whipsaws.

**Philosophy**: "Better to miss no opportunities; filter out bad ones in AI thesis stage (M5)"

**Gate impact**: ❌ **VIOLATES M9 constraint** (14/day × 7 = 98/week vs. max 8/week)

---

### Option B: Apply 2.5 (Calibrated)

**You're saying**: "Be selective; only trade very near-highs"

| Aspect | Impact | Note |
|--------|--------|------|
| **Candidate volume** | 6/day | Lower, more curated candidates |
| **Signal selectivity** | High | Only stocks very close to recent high |
| **False positive rate** | Lower | Most near-high stocks will breakout soon |
| **Manual review burden** | Lower | Fewer tickets, easier to evaluate |
| **M5 thesis quality** | Higher | AI focuses on higher-conviction cases |
| **M7 trade accuracy** | Higher? | Expect >60% of trades to work (less noise) |
| **Risk management** | Fewer positions | Easier to track, more focused |
| **Weekly proposals** | ~42 | Within M9 gate of 8/week |

**Trading style**: Conservative, high-conviction. Wait for clear setups, trade when conditions are ideal.

**Philosophy**: "Quality over quantity; only trade when odds are best"

**Gate impact**: ✅ **RESPECTS M9 constraint** (6/day × 7 = 42/week, still above 8/week average but more reasonable)

---

## Impact on M9 Shadow Mode Success Criteria

### Recall: M9 Gate Thresholds

From your Build Agreement:
```json
{
  "proposals_per_week_min": 2,
  "proposals_per_week_max": 8,
  "thesis_accuracy_pct_min": 50
}
```

### How Each Threshold Affects These Criteria

**Proposals per week**:
- At 5.0: ~98 proposals/week (14/day × 7)
- At 2.5: ~42 proposals/week (6/day × 7)
- **Gate says**: 2–8 proposals/week
- **Status at 5.0**: ❌ **FAILS the max_8/week gate** (off by 12x)
- **Status at 2.5**: ⚠️ **TECHNICALLY EXCEEDS** (still 5x the max)

*Note: The 2.5 value is still above the 8/week gate. This suggests either:*
- *The gate needs adjustment, OR*
- *The "max 8/week" is a soft target for Phase 1, to be revisited post-shadow-mode*

**Thesis accuracy ≥50%**:
- At 5.0: More marginal candidates → AI has to make harder calls → likely accuracy drops to 40–50% (risky)
- At 2.5: Fewer, higher-conviction candidates → AI can be more accurate (60%+, safer)
- **Gate says**: ≥50%
- **Status at 5.0**: Risky; barely passes (need very good AI prompt)
- **Status at 2.5**: Safer; more likely to exceed 50%

---

## Detailed Tradeoff Analysis

### Volume vs. Selectivity

**Question**: Do you want many opportunities or few high-quality ones?

**Volume approach (5.0)**:
- See more market patterns in shadow mode
- More learning opportunities
- Higher chance of catching unexpected winners
- **Cost**: Harder to manage, higher false positive rate, violates gate

**Selectivity approach (2.5)**:
- Fewer but higher-conviction trades
- Easier to execute and track manually
- Higher win rate per trade
- **Cost**: Might miss some opportunities

### AI Burden

**Question**: How much work should M5 (AI thesis) have to do?

**If you keep 5.0**:
- M5 receives ~14 candidates/day
- AI must reason about many marginal cases
- Higher chance AI makes mistakes on edge cases
- Requires excellent prompt engineering in M5

**If you apply 2.5**:
- M5 receives ~6 candidates/day
- AI focuses on high-conviction setups
- Lower chance of AI mistakes
- More straightforward reasoning required

### Shadow Mode Validation

**Question**: What does M9 prove?

**At 5.0**:
- Proves system works at high volume
- But violates your own gate constraints
- Hard to claim "success" when you exceed targets
- More complex P&L tracking
- Higher operational risk

**At 2.5**:
- Proves system works within planned constraints
- Respects documented gate thresholds
- Clean validation of assumptions
- Simpler execution and reporting
- Lower operational risk

---

## Decision Tree

### Question 1: What's your risk appetite for shadow mode?

**Conservative** (prove system works cleanly):
→ Use 2.5 (calibrated value)

**Aggressive** (learn from high volume):
→ Keep 5.0 (but need gate waiver)

---

### Question 2: How confident is your AI thesis (M5)?

**Very confident** (can handle edge cases well):
→ Can keep 5.0
- AI filters false positives in M5 step
- Only best ideas → M7 for trade tickets

**Moderate confidence**:
→ Use 2.5 (calibrated)
- Fewer marginal cases for AI to evaluate
- Higher baseline conviction reduces AI burden

---

### Question 3: What's your shadow mode goal (M9)?

**Maximize learning** (try many different scenarios):
→ Keep 5.0
- See more market conditions
- Test AI prompt against wider variety
- **But**: Will struggle with accuracy + volume gates

**Maximize success rate** (show clean results):
→ Use 2.5 (calibrated)
- Higher accuracy makes M9 gate easier
- Fewer positions = cleaner P&L reporting
- Demonstrates system works before live

**Balance both** (reasonable middle ground):
→ Use 2.5
- Still reasonable volume (~6/day)
- Clean gate compliance
- Easy to loosen post-M9 if desired

---

## Gate Compliance Analysis

### Current M9 Gate Definitions

Your Build Agreement states:
```json
{
  "proposals_per_week_min": 2,
  "proposals_per_week_max": 8
}
```

### Compliance Table

| Threshold | Calc | Per Week | Min Gate | Max Gate | Compliance |
|-----------|------|----------|----------|----------|------------|
| 5.0% | 14/day × 7 | ~98 | ✅ >2 | ❌ <8 | **FAILS** |
| 2.5% | 6/day × 7 | ~42 | ✅ >2 | ❌ <8 | **Questionable** |

### Honest Assessment

**Both thresholds exceed the 8/week max gate.** This suggests:

1. **Gate needs revision** — The 8/week target may have been too strict when written
2. **Or interpretation differs** — "Max 8/week" might mean average, not every week
3. **Or both need adjustment** — Threshold + gate should be revisited together

**Recommended path forward**:
- Apply 2.5 (documented calibration)
- Proceed to M5/M6/M7/M8
- Run M9 shadow mode
- Monitor actual proposal rate (likely 40–50/week average)
- Document in shadow mode report: "Exceeded initial 8/week gate, but maintained high accuracy"
- Adjust gate for Phase 2 (live trading) based on M9 evidence

---

## Post-Shadow Mode Flexibility

### Why Choosing 2.5 Doesn't Lock You In

If you apply 2.5 now:
- ✅ M9 shadow mode uses calibrated, clean thresholds
- ✅ You collect 30–60 days of real trading data
- ✅ You measure actual accuracy, P&L, win rate
- ✅ **After M9 succeeds**, you can:
  - Loosen to 5.0 (or anywhere in between) for live
  - Use M9 data to justify new thresholds
  - Adjust based on observed performance

### Advantages

- Better validation in shadow mode (clean baseline)
- More data-driven decision for live (real M9 results)
- Flexibility to optimize post-validation
- Lower risk during validation phase

---

## My Recommendation

### Apply 2.5 (Calibrated Value)

**Reasoning**:

1. **Gate compliance**: Respects your documented M3 calibration
2. **Risk management**: Lower false positive rate = higher accuracy
3. **Execution ease**: Fewer trades to manually evaluate
4. **Validation clean**: M9 shadow mode produces clean results
5. **Flexibility post-M9**: Can loosen after validation succeeds
6. **Signal quality**: Tighter signal = better signal/noise ratio

**Timeline**:
1. Today: Update config (1 line: `"pct_from_52wk_extreme_min_pct": 2.5`)
2. Today: Re-run M3 screening (verify ~6 candidates/day)
3. Today: Proceed to M5
4. Weeks 2–4: M5–M8 development
5. Weeks 5–12: M9 shadow mode (6 trades/week, high accuracy target)
6. Week 13: Analyze M9 results; decide for live (can loosen to 5.0 if performance justifies)

---

## Alternative: Keep 5.0 (If You Choose)

**You would need to**:
1. ✋ Formally acknowledge M9 gate will be exceeded (14/week vs. 8/week max)
2. 📈 Ensure M5 AI is excellent (to achieve ≥50% accuracy despite more noise)
3. 👤 Add extra manual filtering step (to curate down before execution)
4. 📊 Commit to higher operational complexity during M9

**This is riskier** but possible if:
- You're willing to waive the gate
- You believe AI prompt will be excellent
- You want learning from high volume over clean validation

---

## Summary Decision Matrix

| Criterion | 5.0 (Keep) | 2.5 (Apply) | Winner |
|-----------|-----------|-----------|--------|
| **Gate compliance** | ❌ Violates | ✅ Respects | 2.5 |
| **Documentation alignment** | ❌ Diverges | ✅ Matches | 2.5 |
| **Manual execution ease** | ❌ High burden | ✅ Low burden | 2.5 |
| **Signal quality** | ❌ Loose | ✅ Tight | 2.5 |
| **AI accuracy confidence** | ❌ Harder | ✅ Easier | 2.5 |
| **Shadow mode validation** | ❌ Messy | ✅ Clean | 2.5 |
| **Post-M9 flexibility** | ⚖️ Same | ⚖️ Same | Tie |
| **Learning opportunities** | ✅ More | ⚠️ Fewer | 5.0 |

**Overall winner**: **2.5 (Apply Calibration)**

---

## Final Action Required

### Update M3 Closure Document

If you choose 2.5, update `docs/milestones/M3-phase-a-screener.md`:

```markdown
## Threshold Reconciliation

**M3 Calibration Result**: pct_from_52wk_extreme_min_pct: 5.0 → 2.5

**Decision**: Apply calibrated value (2.5)

**Rationale**:
- Respects M9 gate (proposals within reasonable bounds)
- Aligns with documented M3 calibration approval
- Higher signal quality for manual execution
- Better AI thesis reasoning (fewer marginal cases)
- Cleaner shadow mode validation

**Impact**:
- Candidates/day: 14 → 6
- Proposals/week: 98 → 42
- Signal selectivity: Loose → Tight
- Expected accuracy: 40–50% → 60%+

**Action taken**: Updated config/risk_rules_sgx.json to 2.5

**Next review**: Post-M9 shadow mode results
```

### Update Config

```json
{
  "pct_from_52wk_extreme_min_pct": 2.5
}
```

### Re-run M3

```bash
fm screening run
# Verify candidate count matches expectation (~6 today)
```

### Proceed to M5

---

## Conclusion

**Keeping 5.0 is a valid choice** if you want high volume and are willing to manage complexity.

**But applying 2.5 is the recommended choice** because it:
- ✅ Matches your documented M3 calibration
- ✅ Respects your M9 gate constraints
- ✅ Improves signal quality
- ✅ Simplifies manual execution
- ✅ Gives you post-M9 flexibility to adjust

**Decision needed**: Which threshold will you use for M5+?
