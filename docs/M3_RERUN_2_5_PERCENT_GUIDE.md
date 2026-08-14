# M3 Re-run Practice: Apply 2.5% Threshold (Step-by-Step)

**Goal**: Apply the calibrated `pct_from_52wk_extreme_min_pct: 2.5` threshold to config and re-run M3 screening to verify behavior.

**Expected outcome**: ~6 candidates/day (down from 14)

**Timeline**: ~20 minutes

---

## Phase 1: Backup & Preparation (5 min)

### Step 1.1: Open Terminal

```bash
cd D:\Projects\FinancialMarket
```

### Step 1.2: Check Current Config Value

```bash
cat config/risk_rules_sgx.json | grep "pct_from_52wk"
```

**Expected output**:
```
      "pct_from_52wk_extreme_min_pct": 5.0,
```

**Record this** (in case you need to revert):
```
Baseline value: 5.0
Date of change: [today's date]
Reason: Testing calibrated threshold
```

### Step 1.3: Backup Config File

```bash
cp config/risk_rules_sgx.json config/risk_rules_sgx.json.backup_5.0
echo "Backup created at $(date)" >> docs/M3_THRESHOLD_TESTING_LOG.md
```

---

## Phase 2: Update Config (5 min)

### Step 2.1: Edit Config File

**Option A: Using nano (text editor)**
```bash
nano config/risk_rules_sgx.json
```

Then:
1. Use Ctrl+W to search for `pct_from_52wk_extreme_min_pct`
2. Find the line: `"pct_from_52wk_extreme_min_pct": 5.0,`
3. Change `5.0` to `2.5`
4. Press Ctrl+O to save
5. Press Ctrl+X to exit

**Option B: Using sed (command-line replacement)**
```bash
sed -i 's/"pct_from_52wk_extreme_min_pct": 5.0,/"pct_from_52wk_extreme_min_pct": 2.5,/' config/risk_rules_sgx.json
```

### Step 2.2: Verify Change

```bash
cat config/risk_rules_sgx.json | grep "pct_from_52wk"
```

**Expected output**:
```
      "pct_from_52wk_extreme_min_pct": 2.5,
```

**If correct** ✅ → Proceed  
**If wrong** ❌ → Revert:
```bash
cp config/risk_rules_sgx.json.backup_5.0 config/risk_rules_sgx.json
```

---

## Phase 3: Run M3 Screening (5 min)

### Step 3.1: Run Live Screening

```bash
fm screening run
```

**This will**:
- Load the 42 securities from M2 database
- Apply eligibility policy
- Fetch OHLCV data via M1 client
- Calculate 5 signals (60d price move, volume spike, **52wk extreme**, volatility, Donchian)
- **Use new 2.5% threshold** for 52wk_extreme signal
- Rank candidates
- Output `pending_candidates.json` + Markdown report

**Expected output** (last few lines):
```
Screened: 42 securities
Eligible: 38
Candidates matched: 6

Output:
  pending_candidates.json
  screening_report_2026-08-14.md
```

### Step 3.2: Check Results File

```bash
# Count candidates in JSON
wc -l pending_candidates.json
cat pending_candidates.json | grep -c '"rank":'
```

**Expected**: ~6 candidates (vs. 14 with 5.0)

### Step 3.3: View Markdown Report

```bash
cat screening_report_2026-08-14.md | head -50
```

**Look for**:
- Eligible securities: 38
- Matched candidates: 6 (or close to it)
- 52wk_extreme threshold: 2.5%

---

## Phase 4: Analysis & Verification (5 min)

### Step 4.1: Parse Candidate List

```bash
# Extract candidate symbols and ranks
grep '"symbol":' pending_candidates.json | head -10
```

**Expected output** (example):
```json
"symbol": "D05",
"symbol": "O39",
"symbol": "BS6",
"symbol": "F34",
"symbol": "G13",
"symbol": "S68",
```

### Step 4.2: Verify 52-Week Extreme Signal

Open the JSON file and check a few candidates:

```bash
# Pretty-print JSON (requires jq, or use text editor)
# If you have jq installed:
jq '.ranked_candidates[0]' pending_candidates.json

# Or just open the file:
cat pending_candidates.json | head -100
```

**Look for**:
```json
{
  "rank": 1,
  "symbol": "D05",
  "signals": {
    "52wk_extremes": {
      "pct_below_52w_high": 4.5,  // ← Should be < 2.5 to trigger
      "pct_above_52w_low": 28.6
    }
  },
  "matched_signals": ["52wk_extreme", ...]  // ← Should include this
}
```

**Key point**: Every matched candidate should have `pct_below_52w_high` close to or below 2.5%

### Step 4.3: Compare to 5.0 Baseline

**If you have the old report saved**:
```bash
# Compare two reports
diff <(grep '"symbol":' screening_report_2026-08-13.md) \
     <(grep '"symbol":' screening_report_2026-08-14.md)
```

**Expected**: ~67% fewer candidates (14 → 6)

### Step 4.4: Document Results

Create a test log file:

```bash
cat > docs/M3_THRESHOLD_TESTING_LOG.md << 'EOF'
# M3 Threshold Testing Log

## Test 1: Apply 2.5% Threshold (Practice Run)

**Date**: 2026-08-14  
**Change**: pct_from_52wk_extreme_min_pct: 5.0 → 2.5

### Config Update
```bash
sed -i 's/"pct_from_52wk_extreme_min_pct": 5.0,/"pct_from_52wk_extreme_min_pct": 2.5,/' config/risk_rules_sgx.json
```

### Screening Results

**Command**: `fm screening run`

**Output**:
- Total securities: 42
- Eligible: 38
- Candidates matched: [COUNT FROM STEP 3.2]
- Report: screening_report_2026-08-14.md

### Candidate List

[LIST FROM STEP 4.1]

### Observations

- Volume reduction: 14 → [COUNT] (target: ~6)
- Signal quality: [ASSESSMENT]
- Signal/noise ratio: [ASSESSMENT]
- Ready for M5: [YES/NO]

### Next Steps

- [ ] Commit config change to Git
- [ ] Update M3 closure document
- [ ] Proceed to M5
EOF
cat docs/M3_THRESHOLD_TESTING_LOG.md
```

---

## Phase 5: Commit Changes (3 min)

### Step 5.1: Review Changes

```bash
git diff config/risk_rules_sgx.json
```

**Should show**:
```diff
- "pct_from_52wk_extreme_min_pct": 5.0,
+ "pct_from_52wk_extreme_min_pct": 2.5,
```

### Step 5.2: Commit to Git

```bash
git add config/risk_rules_sgx.json
git add docs/M3_THRESHOLD_TESTING_LOG.md
git commit -m "M3: Apply calibrated threshold (52wk_extreme 5.0 → 2.5) for testing"
```

### Step 5.3: Verify Commit

```bash
git log --oneline -3
```

**Should show**:
```
[latest commit] M3: Apply calibrated threshold (52wk_extreme 5.0 → 2.5) for testing
...
```

---

## Phase 6: Decision & Next Steps (2 min)

### Step 6.1: Evaluate Results

**Questions to ask yourself**:

1. **Did candidate volume drop to ~6?**
   - Yes ✅ → Threshold is working as expected
   - No ❌ → Check if change was actually applied

2. **Do the 6 candidates look good?**
   - Yes ✅ → Signal quality looks solid
   - No ❌ → Might need different threshold

3. **Is this candidate set reasonable for manual trading?**
   - Yes ✅ → Manageable volume
   - No ❌ → Might prefer different threshold

### Step 6.2: Three Options Forward

**Option A: Approve 2.5 & Proceed to M5**
```bash
# Update M3 closure document to reflect 2.5 decision
# (I'll help with this next)

# Proceed to M5
echo "✅ Ready for M5"
```

**Option B: Keep Testing with 2.5**
```bash
# Run again tomorrow with same threshold
# Watch for consistency (same candidates or stable variations?)

# Run 5-day dry-run:
fm screening dry-run --days 5
```

**Option C: Revert to 5.0**
```bash
cp config/risk_rules_sgx.json.backup_5.0 config/risk_rules_sgx.json
git checkout config/risk_rules_sgx.json
echo "❌ Reverted to 5.0"
```

---

## Troubleshooting

### Issue: Config change didn't work

**Problem**: `fm screening run` still shows 14 candidates

**Solution**:
```bash
# Verify config was actually changed
cat config/risk_rules_sgx.json | grep "pct_from_52wk"

# If it shows 5.0, the edit didn't work
# Try again with nano or sed

# If it shows 2.5, restart Python environment
pip install -e .
fm screening run
```

### Issue: Screening command not found

**Problem**: `fm screening run` returns command not found

**Solution**:
```bash
# Reinstall package
pip install -e .

# Try again
fm screening run
```

### Issue: Need to compare with old run

**Problem**: Lost the old 14-candidate report

**Solution**:
```bash
# Revert config temporarily
cp config/risk_rules_sgx.json config/risk_rules_sgx.json.backup_2.5
cp config/risk_rules_sgx.json.backup_5.0 config/risk_rules_sgx.json

# Run screening
fm screening run

# Compare output
# Then restore 2.5:
cp config/risk_rules_sgx.json.backup_2.5 config/risk_rules_sgx.json
```

---

## Quick Cheat Sheet

```bash
# All commands in sequence:
cd D:\Projects\FinancialMarket

# Backup
cp config/risk_rules_sgx.json config/risk_rules_sgx.json.backup_5.0

# Update (choose one)
nano config/risk_rules_sgx.json
# OR
sed -i 's/"pct_from_52wk_extreme_min_pct": 5.0,/"pct_from_52wk_extreme_min_pct": 2.5,/' config/risk_rules_sgx.json

# Verify
cat config/risk_rules_sgx.json | grep "pct_from_52wk"

# Run screening
fm screening run

# Check results
cat pending_candidates.json | grep -c '"rank":'

# View report
cat screening_report_*.md | head -50

# Commit
git add config/risk_rules_sgx.json
git commit -m "M3: Apply calibrated threshold (52wk_extreme 5.0 → 2.5) for testing"
```

---

## Success Checklist

- [ ] Config updated: 5.0 → 2.5 ✅
- [ ] Change verified in file ✅
- [ ] M3 screening runs without errors ✅
- [ ] Candidate count drops to ~6 ✅
- [ ] Markdown report generated ✅
- [ ] JSON output valid ✅
- [ ] Results reviewed and acceptable ✅
- [ ] Changes committed to Git ✅
- [ ] Logged results in testing doc ✅
- [ ] Ready for next decision ✅

---

## What to Do After Completing This Guide

**Once you've finished the 9 steps above**, report back:

1. **What was the candidate count?** (Target: ~6)
2. **Did the signal quality look good?**
3. **Are you ready to commit this for M5**, or do you want to test more?

Then I'll help you:
- Update M3 closure document (if approving 2.5)
- Prepare to start M5
- Or revert (if keeping 5.0)

---

**Ready to start?** Begin with Phase 1, Step 1.1. Good luck! 🚀
