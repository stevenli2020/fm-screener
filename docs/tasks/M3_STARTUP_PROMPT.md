# M3 Startup Prompt — For Codex

**Status**: APPROVED FOR IMPLEMENTATION ✅  
**Timeline**: 2–3 days  
**Reviewer**: Claude  

---

## TL;DR

Build a **deterministic, end-of-day screener** that loads the SGX universe (M2), calculates 5 signals (price move, volume, 52wk extreme, volatility, Donchian), ranks candidates, and outputs JSON + markdown report.

**No AI reasoning.** Pure math, fully auditable.

---

## What to Build

### Core Components

1. **`src/financial_market/screening/signals.py`**
   - `signal_price_move_60d()` — 60-day % change
   - `signal_volume_spike()` — volume multiple vs. 20d median
   - `signal_52week_extremes()` — distance from 52wk high/low
   - `signal_volatility_20d()` — annualized volatility
   - `signal_donchian_breakout()` — Donchian channel position

2. **`src/financial_market/screening/screener.py`**
   - Load universe from M2 database
   - Apply eligibility policy
   - Fetch OHLCV via M1 client
   - Calculate signals for each security
   - Evaluate against thresholds

3. **`src/financial_market/screening/ranker.py`**
   - Rank candidates: signal count → 52wk distance → volume spike → symbol

4. **`src/financial_market/screening/reporter.py`**
   - Generate markdown report (tables, audit)

5. **CLI**
   - `fm screening run` → fetch, screen, rank, output JSON + report

6. **Config**
   - Add `screening.signals` to `config/risk_rules_sgx.json`:
     - `price_move_60d_min_pct`: 10.0
     - `volume_spike_min_multiple`: 1.5
     - `pct_from_52wk_extreme_min_pct`: 5.0
     - `donchian_breakout_threshold_pct`: 85.0

### Outputs

- **`pending_candidates.json`** — Structured signals + ranking
- **`screening_report_YYYY-MM-DD.md`** — Human-readable summary

---

## Key Constraints

✅ **Do**:
- Use M1 client to fetch OHLCV
- Use M2 database + eligibility policy
- Configuration-driven thresholds
- Test coverage >80%
- Audit trail (every decision documented)

❌ **Don't**:
- Add AI reasoning (M5 job)
- Add backtesting (M9 job)
- Hardcode thresholds
- Skip edge-case handling
- Optimize for specific stocks

---

## Testing

- [ ] Unit tests for each signal (edge cases: <20 bars, zero volume, etc.)
- [ ] Integration test: universe → data → screen → rank → report
- [ ] Mock OHLCV with known outcomes
- [ ] All 42 securities produce outputs
- [ ] Output schema matches spec
- [ ] Report markdown is readable

---

## Self-Review Checklist

- [ ] Look-ahead bias: Only past/present data?
- [ ] Calculation correctness: Verify 2–3 securities by hand
- [ ] Edge cases: Stale data? New IPO? Zero-range?
- [ ] Determinism: Same input → same output?
- [ ] Dependencies: Only M1 + M2? (No magic numbers?)
- [ ] Observability: Trace every candidate matched/rejected?

---

## Review Criteria

Before M4 approval:

1. **Functionality**: `fm screening run` works; outputs valid JSON + report
2. **Quality**: All 42 securities screened; rejection reasons documented
3. **Testing**: ≥80% coverage; edge cases handled
4. **Audit**: Trace every signal; no look-ahead bias
5. **Metrics**: 1-week dry-run results (consistency, candidate rate)

---

## Documentation

- README with signal definitions + thresholds
- Example report (matched + rejected securities)
- Configuration guide (how to adjust thresholds)

---

## Reference Docs

- **Full spec**: `M3_PHASE_A_SCREENER_SPEC.md`
- **Config**: `screening_eligibility_sgx.json` (from M2)
- **M2 universe**: `securities` table + metadata
- **M1 client**: `DataServerClient.get_ohlcv()` method

---

## Submission Format (READY FOR REVIEW)

- Code deliverables (files created/modified)
- Test results (coverage %, count, pass/fail)
- Self-review checklist (all signed off)
- Example outputs (sample JSON + report)
- 1-week dry-run metrics (signal consistency, candidate rate)
- Known limitations or deferred decisions
- Test command examples for verification

---

**Go build.** 🚀
