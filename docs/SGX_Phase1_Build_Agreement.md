# SGX Trading Prototype — Phase 1 Build Agreement

**Date**: August 11, 2026  
**Status**: Ready to Build  
**Scope**: Research-only prototype, manual execution, yfinance + SGX API  

---

## Executive Summary

We are building a **research-only trading prototype** for Singapore equities (SGX cash equities + REITs) with the following stack:

- **Data**: yfinance (via mh_test cache; accept data quality risks)
- **News**: SGX API (Approach 1 only, no fallback)
- **Execution**: Manual trades via Moomoo
- **Capital**: SGD 50,000
- **Timeline**: Milestone-based, 30–60 trading days shadow mode before validation

This is **not** the live system. It's a testbed to validate signal quality, data reliability, and thesis consistency in a controlled environment.

---

## Part 1: Scope — In vs. Out

### In Scope (Phase 1)

| Component | Decision |
|-----------|----------|
| Asset class | SGX cash equities + REITs (long-only, no leverage) |
| Universe size | ~30–50 securities (STI constituents + liquid REITs) |
| Data source | yfinance (via mh_test cache) |
| News source | SGX API (Approach 1) |
| Execution | Manual trades via Moomoo |
| Screening | End-of-day, daily run |
| State | SQLite |
| Reports | Markdown + JSON |

### Out of Scope (Deferred)

- Illiquid REIT strategies
- Overnight/weekend news automation
- Broker API integration
- Live execution
- Hedging / shorting

---

## Part 2: Critical Decisions (Locked)

### 1. Data: yfinance via mh_test (Accept Risks)
- **Mitigation**: M2–M3 audit flags data quality issues; exclude bad stocks

### 2. News: SGX API Only
- **Mitigation**: Log API availability; fallback if >5% downtime/month

### 3. Broker: Moomoo Manual
- **Workflow**: You execute trades manually; record outcomes

### 4. Capital: SGD 50,000
- Position sizing: 20% max per position, 4 concurrent, 10% cash buffer
- Loss limits: 5% daily, 10% weekly

---

## Part 3: Milestones

| # | Milestone | Gate? |
|---|-----------|-------|
| 2 | SGX Universe | Data audit pass |
| 3 | Phase A Screener | Signal consistency |
| 4 | News Pipeline | API logging |
| 5 | AI Thesis Agent | Thesis consistency |
| 6 | Portfolio Ledger | Execution tracking |
| 7 | Phase B Validation | Revalidation logic |
| 8 | Daily Workflow | Orchestration |
| 9 | Shadow Mode | 30–60 day gate + success criteria |

---

## Part 4: Risk Acknowledgments

| Risk | Accept | Mitigate | Escalate |
|------|--------|----------|----------|
| yfinance data gaps | ✅ | M2–M3 audit | If >10% universe affected |
| SGX API downtime | ✅ | Daily logs | If >5% downtime/month |
| Manual execution errors | ✅ | Trade manifest | If >20% missed |
| AI thesis wrong | ✅ | Mechanical risk rules | If accuracy <50% |

---

## Part 5: Success Metrics (M7 Shadow Gate)

```json
{
  "signal_quality": {"proposals_per_week": [2, 8]},
  "thesis_accuracy": {"correct_direction_pct_min": 50},
  "false_breakouts": {"max_pct": 30},
  "data_quality": {"yfinance_coverage_pct_min": 98},
  "price_gaps": {"drift_pct_max": 2.0}
}
```

---

## Part 6: Timeline

| Milestone | Duration | Effort |
|-----------|----------|--------|
| 2–3. Universe + Screener + Data Audit | 2–3 weeks | M |
| 4–7. News + AI + Portfolio + Phase B | 2–3 weeks | M |
| 8–9. Workflow + Shadow Mode | 6–8 weeks | L |
| **Total** | ~8–10 weeks | — |

---

**Prepared by**: Claude (Advisor)  
**For**: Codex (Builder) + You (Operator)
