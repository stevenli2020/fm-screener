# SGX Trading Prototype — Build Briefing

**Date**: August 12, 2026  
**Status**: M0–M2 Complete, Ready for M3  
**Budget**: 8 weeks to shadow mode  

---

## 🎯 Mission

Build a **research-only trading prototype** for Singapore equities (SGX cash equities + REITs):
- Deterministic daily screener (yfinance + mh_test caching)
- AI-assisted thesis generation (news + analysis)
- Manual trade execution via Moomoo
- 30–60 day shadow mode validation before any live deployment

---

## ✅ Current State

| Milestone | Status | Quality | Notes |
|-----------|--------|---------|-------|
| M0 | ✅ CLOSED | ⭐⭐⭐⭐⭐ | Python package, config, SQLite schema |
| M1 | ✅ CLOSED | ⭐⭐⭐⭐⭐ | mh_test client, 18 tests, 81% coverage |
| M2 | ✅ CLOSED | ⭐⭐⭐⭐⭐ | Universe loader, 42 securities, data validation |
| **M3** | ⏳ READY | — | Phase A screener (starting now) |

**Upstream flags** (not blocking M0–M8):
- Flag #1: numpy/pandas version conflicts → blocks M9
- Flag #2: IPython undeclared → blocks M9
- Flag #3: OHLCV inconsistency → **RESOLVED** by M2 (confirmed adjusted O/H/L/C)

---

## 📊 Key Decisions (Locked)

| Decision | Choice | Why |
|----------|--------|-----|
| **Data** | yfinance (via mh_test cache) | Accept risks; M2 audit validates quality |
| **News** | SGX API only | Fast, simple; fallback if unreliable |
| **Broker** | Moomoo (manual) | No automation in Phase 1 |
| **Capital** | SGD 50,000 | Position sizing: 20% max, 4 concurrent |
| **Universe** | 42 securities (24 equities, 14 REITs, 4 ETFs) | Locked; data validated |
| **Shadow Mode** | 30–60 trading days | Gate before live |

---

## 🗺️ Roadmap (M3–M9)

| Milestone | Deliverable | Your Role | Duration | Blocker? |
|-----------|-------------|-----------|----------|----------|
| **M3** | Phase A Screener (5 signals, ranking, report) | Validate signals | 2–3 days | No |
| **M4** | News Pipeline (SGX API → SQLite) | Monitor API | 1 day | No |
| **M5** | AI Thesis Agent (evidence → thesis) | Test prompt | 2–3 days | No |
| **M6** | Portfolio Ledger (holdings, P&L, CSV) | Design UX | 1 day | No |
| **M7** | Phase B Validation (revalidation → tickets) | Spot-check | 1 day | No |
| **M8** | Daily Workflow (orchestration, reports) | Run pipeline | 1 day | No |
| **M9** | Shadow Mode (paper trading, 30–60 days) | Execute + record | 6–8 weeks | **Upstream fixes** |

---

## 🔑 Critical Path (Must-Dos)

| Item | Owner | Deadline | Impact |
|------|-------|----------|--------|
| M3 pass data audit | Codex | After M3 code | Gate: Must ≥90% before M4 |
| M3 run 1–2 weeks dry-run | Codex + You | After M3 test | Validate signal consistency |
| SGX API monitoring (M4) | You | Daily | Escalate if >5% downtime |
| 30–60 day shadow mode (M7–M9) | You | Weeks 5–12 | Gate: Success metrics must pass |

---

## 📈 Success Metrics (M7 Shadow Gate)

**Before proceeding to live trading**:

```
Signal Quality:        2–8 candidates per week ✅
Thesis Accuracy:       ≥50% correct direction ✅
False Breakouts:       <30% false signals ✅
Data Quality:          ≥98% yfinance coverage ✅
Price Gaps:            <2.0% drift (proposal → open) ✅
```

---

## 🚀 What's Next

### For Codex
1. M2 closure document (already created; record approval)
2. Start M3 (read full spec: `M3_PHASE_A_SCREENER_SPEC.md`)
3. Build 5 signals + screener + report generator
4. Test coverage >80%; self-review for look-ahead bias
5. Submit: code + tests + example outputs + dry-run metrics

### For You
1. Approve M2 closure
2. Monitor M3 progress (expect 2–3 days)
3. Prepare for M4–M7 reviews (weekly syncs)
4. Plan shadow-mode execution (weeks 5–12)

### For Me (Advisor)
1. Review M3 report (READY/BLOCKED)
2. Help debug if signals are noisy
3. Weekly check-ins during M4–M9
4. Shadow-mode metrics analysis

---

## ⚠️ Risk Summary

| Risk | Probability | Mitigation | Escalation |
|------|-------------|-----------|-----------|
| yfinance gaps | Medium | M2–M3 audit | If >10% universe |
| SGX API down | Low | Daily logs | If >5% downtime/month |
| Manual execution miss | Medium | Trade manifest | If >20% missed |
| AI thesis drifts | Low | Mechanical stops | If <50% accuracy |
| Upstream deps unfixed | Medium | — | Before M9 (not blocking M3–M8) |

---

## 📞 Communication

- **Weekly syncs**: Status, blockers, metrics
- **Per-milestone reports**: READY/BLOCKED + feedback loop
- **Escalation**: Yellow (investigate) → Red (pause) → Blocker (urgent)

---

## ✅ Approval Status

| Milestone | Status | Condition |
|-----------|--------|-----------|
| M0 | ✅ APPROVED | Foundation ready |
| M1 | ✅ APPROVED | Upstream flags noted (not blocking M0–M8) |
| M2 | ✅ APPROVED | Data quality gate passed; proceed to M3 |
| M3 | ⏳ READY | **Start now** ✅ |

---

**Build status**: On track for 8–10 week delivery to shadow-mode readiness.

**Next**: Codex starts M3. Expect report in 2–3 days.
