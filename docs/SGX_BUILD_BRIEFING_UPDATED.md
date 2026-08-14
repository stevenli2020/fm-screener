# SGX Trading Prototype — Updated Build Briefing

> **Historical briefing note:** M0–M3 are closed and M4 is now READY FOR REVIEW with its
> seven-distinct-day monitoring gate still in progress. Direct SGX API/readiness statements
> below are superseded by the milestone register and M4 review report.

**Date**: August 12, 2026 (Updated)  
**Status**: M0–M3 Complete, M4 Ready to Start  
**Progress**: 33% of Phase 1 complete (M0–M3 / M0–M9)  

---

## 🎯 Mission

Build a **research-only trading prototype** for Singapore equities (SGX cash equities + REITs):
- Deterministic daily screener (M0–M3) ✅
- AI-assisted thesis generation (M4–M5)
- Manual trade execution via Moomoo (M6–M7)
- 30–60 day shadow mode validation (M8–M9)

---

## ✅ Current State (M0–M3 COMPLETE)

| Milestone | Status | Quality | Blockers |
|-----------|--------|---------|----------|
| M0 | ✅ CLOSED | ⭐⭐⭐⭐⭐ | None |
| M1 | ✅ CLOSED | ⭐⭐⭐⭐⭐ | Upstream (M9) |
| M2 | ✅ CLOSED | ⭐⭐⭐⭐⭐ | None |
| **M3** | ✅ **CLOSED** | ⭐⭐⭐⭐⭐ | **None** |
| **M4** | ⏳ **READY** | — | **No** |

---

## 📊 M3 Calibration (Just Completed)

### Threshold Tuning Results
```
Baseline (original):     18 matches/day ❌ Too high
After iteration 1:       ~11 matches/day (volume→2.5)
After iteration 2:       ~6 matches/day (extreme→2.5) ✅ TARGET RANGE
```

### Final Locked Thresholds
```json
{
  "volume_spike_min_multiple": 2.5,           // was 1.5
  "pct_from_52wk_extreme_min_pct": 2.5,       // was 5.0
  "price_move_60d_min_pct": 10.0,             // unchanged
  "price_move_60d_max_pct": 50.0,             // unchanged
  "donchian_breakout_threshold_pct": 85.0    // unchanged
}
```

### M3 Success Metrics (All Passed ✅)
- Signal consistency: 5-day replay shows stable behavior
- Match rate: 6–8 candidates/day (target: 2–8/day) ✅
- Test coverage: 87%, 46 tests passed ✅
- No look-ahead bias confirmed ✅
- All 42 securities eligible ✅

---

## 🗺️ Roadmap (Remaining M4–M9)

| Milestone | Deliverable | Input | Output | Duration | Blocker? |
|-----------|-------------|-------|--------|----------|----------|
| **M4** | News Pipeline | M3 candidates | news_feed.json | 1–2 days | **No** |
| M5 | AI Thesis Agent | news + signals | thesis JSON | 2–3 days | No |
| M6 | Portfolio Ledger | — | holdings + P&L | 1 day | No |
| M7 | Phase B Validation | news + holdings | trade tickets | 1 day | No |
| M8 | Daily Workflow | All above | CLI orchestration | 1 day | No |
| M9 | Shadow Mode | — | 30–60 day execution | 6–8 weeks | Upstream |

---

## 🔑 Key Decisions (All Locked)

| Decision | Choice | Status |
|----------|--------|--------|
| **Data** | yfinance (via mh_test cache) | ✅ Validated (M0–M2) |
| **News** | SGX API only (Approach 1) | ✅ Ready (M4 starts now) |
| **Broker** | Moomoo (manual) | ✅ Confirmed |
| **Capital** | SGD 50,000 | ✅ Confirmed |
| **Universe** | 42 securities | ✅ Loaded (M2) |
| **Screener** | 5 signals, locked thresholds | ✅ Calibrated (M3) |
| **Shadow Mode** | 30–60 trading days | ✅ Planned |

---

## 📈 Data Flow (M0–M3 Complete)

```
yfinance
    ↓
mh_test (caching server) [M0–M1]
    ↓
42 SGX securities loaded [M2]
    ↓
Daily screening: 5 signals calculated [M3] ✅
    ↓
pending_candidates.json output
    ↓
M4 → Fetch news for matched candidates
```

---

## 📋 Effort Tracking

| Phase | Milestones | Duration | Status |
|-------|-----------|----------|--------|
| **Foundation** | M0–M2 | 3 weeks | ✅ Complete |
| **Screening** | M3 calibration | 1 day | ✅ Complete |
| **Research** | M4–M5 | ~1 week | ⏳ Starting now |
| **Execution** | M6–M7 | ~2 days | Pending |
| **Workflow** | M8 | ~1 day | Pending |
| **Validation** | M9 | 6–8 weeks | Pending |
| **Total** | M0–M9 | ~10 weeks | 33% done ✅ |

---

## ⚠️ Risk Summary

| Risk | Probability | Mitigation | Status |
|------|-------------|-----------|--------|
| yfinance data gaps | Medium | M2–M3 audit (passed) | ✅ Mitigated |
| SGX API downtime | Low | Daily logs (M4 will track) | ⏳ Monitoring |
| Manual execution miss | Medium | Trade manifest (M6) | Pending |
| AI thesis drifts | Low | Mechanical stops (M6–M7) | Pending |
| Upstream deps (M9) | Medium | — | Known, not blocking M4–M8 |

---

## 🚀 What's Next (Right Now)

### For Codex
1. Read `docs/tasks/M4_STARTUP_PROMPT.md`
2. Read `docs/tasks/M4_RESEARCH_INGESTION_SPEC.md`
3. **Start M4** (News Pipeline)
4. Expected completion: 1–2 days

### For You
1. Monitor M4 progress (no action required)
2. Review M4 report when ready (1–2 days)
3. Approve before M5 starts

### For Me (Advisor)
1. Review M4 report when submitted
2. Help debug if needed
3. Prepare M5 spec

---

## 📚 Documents Created Today

| Document | Purpose | Location |
|----------|---------|----------|
| M3 Closure | M3 approval record | `docs/milestones/M3-phase-a-screener.md` |
| M4 Spec | Full M4 specification | `docs/tasks/M4_RESEARCH_INGESTION_SPEC.md` |
| M4 Prompt | TL;DR for Codex | `docs/tasks/M4_STARTUP_PROMPT.md` |
| M4 Transition | M3→M4 handoff guide | `docs/M4_STARTUP_TRANSITION.md` |

---

## ✅ Status Summary

| Category | Status | Evidence |
|----------|--------|----------|
| **Foundation** | ✅ Solid | M0 architecture sound |
| **Data Access** | ✅ Working | M1 client tested live |
| **Universe** | ✅ Validated | M2: 42 securities, all eligible |
| **Screening** | ✅ Calibrated | M3: thresholds locked, signals consistent |
| **News** | ⏳ Next | M4 spec ready, Codex starting |
| **On Track** | ✅ YES | 33% done, no blockers |

---

## 🎯 Next Major Gates

1. **M4 Completion** (1–2 days): News collection working, API reliable
2. **M5 Completion** (2–3 days): AI thesis agent tested
3. **M6–M7 Completion** (~3 days): Trade execution ready
4. **M8 Completion** (1 day): Daily pipeline orchestrated
5. **M9 Gate** (6–8 weeks): Shadow mode success metrics passed → **LIVE TRADING DECISION**

---

## 📞 Communication

- **Weekly syncs**: Status, blockers, metrics
- **Per-milestone reviews**: Report + feedback + approval
- **M4 Expected**: 1–2 days to completion

---

**Build status**: On track. 🚀

**Next action**: Codex starts M4. You review when ready.

**Estimated weeks to shadow mode**: ~4 weeks (M4–M8) + 6–8 weeks (M9) = 10–12 weeks total.
