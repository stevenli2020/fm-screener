from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from financial_market.market_data.client import DataServerClient
from financial_market.market_data.errors import MarketDataError
from financial_market.risk import RiskRules
from financial_market.storage import connect_database

from .eligibility import EligibilityPolicy, eligibility_reasons
from .ranker import rank_candidates
from .signals import (
    signal_52week_extremes,
    signal_donchian_breakout,
    signal_price_move_60d,
    signal_volatility_20d,
    signal_volume_spike,
)

STRATEGY_VERSION = "phase-a-v1"


def run_screening(
    database_path: Path,
    client: DataServerClient,
    rules: RiskRules,
    policy: EligibilityPolicy,
    as_of: date | None = None,
) -> dict[str, Any]:
    run_date = as_of or date.today()
    securities = _load_securities(database_path)
    results: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for security in securities:
        reasons = eligibility_reasons(security, policy, run_date)
        if reasons:
            results.append(
                {
                    "symbol": security["symbol"],
                    "company_name": security["company_name"],
                    "reason": "ineligible",
                    "rejection_reasons": reasons,
                    "eligible": False,
                    "signals": {},
                }
            )
            continue
        try:
            series = client.get_ohlcv(
                security["provider_symbol"], frequency="1d", end_date=run_date
            )
        except (MarketDataError, ValueError) as exc:
            results.append(
                {
                    "symbol": security["symbol"],
                    "company_name": security["company_name"],
                    "reason": "data_fetch_failed",
                    "rejection_reasons": [str(exc)],
                    "eligible": True,
                    "signals": {},
                }
            )
            continue
        live_reasons = _series_quality_reasons(series, policy, run_date)
        if live_reasons:
            results.append(
                {
                    "symbol": security["symbol"],
                    "company_name": security["company_name"],
                    "reason": "ineligible",
                    "rejection_reasons": live_reasons,
                    "eligible": False,
                    "signals": {},
                }
            )
            continue
        signals = {
            "price_move_60d": signal_price_move_60d(series.rows),
            "volume_spike": signal_volume_spike(series.rows),
            "52wk_extremes": signal_52week_extremes(series.rows),
            "volatility_20d": signal_volatility_20d(
                series.rows, rules.screening.volatility_lookback_days
            ),
            "donchian_55d": signal_donchian_breakout(
                series.rows, rules.screening.donchian_lookback_days
            ),
        }
        matches = _evaluate(signals, rules)
        record = {
            "symbol": security["symbol"],
            "company_name": security["company_name"],
            "provider_symbol": security["provider_symbol"],
            "eligible": True,
            "signals": signals,
            "matched_signals": matches,
        }
        if matches:
            candidates.append(record)
        else:
            record.update({"reason": "no_signal_match", "rejection_reasons": []})
            results.append(record)
    ranked = rank_candidates(candidates)
    result = {
        "run_date": run_date.isoformat(),
        "strategy_version": STRATEGY_VERSION,
        "universe_count": len(securities),
        "eligible_count": sum(item.get("eligible", False) for item in results) + len(candidates),
        "candidates_screened": len(candidates)
        + sum(item.get("reason") == "no_signal_match" for item in results),
        "candidates_matched": len(ranked),
        "ranked_candidates": ranked,
        "rejected": results,
    }
    _persist_run(database_path, result, rules)
    return result


def _evaluate(signals: dict[str, dict[str, Any]], rules: RiskRules) -> list[str]:
    threshold = rules.screening
    move = signals["price_move_60d"].get("move_pct")
    volume = signals["volume_spike"].get("spike_multiple")
    high_distance = signals["52wk_extremes"].get("pct_below_52w_high")
    channel = signals["donchian_55d"].get("pct_of_range")
    matches = []
    if (
        isinstance(move, (int, float))
        and threshold.price_move_60d_min_pct <= move <= threshold.price_move_60d_max_pct
    ):
        matches.append("price_move_60d")
    if isinstance(volume, (int, float)) and volume >= threshold.volume_spike_min_multiple:
        matches.append("volume_spike")
    # Long-only Phase A treats the configured 5% as proximity to the 52-week high.
    if (
        isinstance(high_distance, (int, float))
        and high_distance <= threshold.pct_from_52wk_extreme_min_pct
    ):
        matches.append("pct_from_52wk_extreme")
    if isinstance(channel, (int, float)) and channel >= threshold.donchian_breakout_threshold_pct:
        matches.append("donchian_breakout")
    return matches


def _load_securities(database_path: Path) -> list[dict[str, Any]]:
    connection = connect_database(database_path)
    try:
        rows = connection.execute(
            "SELECT symbol, company_name, provider_symbol, instrument_type, metadata_json "
            "FROM securities WHERE is_active = 1 ORDER BY symbol"
        ).fetchall()
    finally:
        connection.close()
    return [
        {
            "symbol": row[0],
            "company_name": row[1],
            "provider_symbol": row[2],
            "instrument_type": row[3],
            "metadata": json.loads(row[4]),
        }
        for row in rows
    ]


def _series_quality_reasons(series: Any, policy: EligibilityPolicy, as_of: date) -> list[str]:
    reasons = []
    if len(series.rows) < policy.minimum_daily_bars:
        reasons.append("insufficient_history")
    if series.candle_repair_count > policy.maximum_candle_repairs:
        reasons.append("excessive_candle_repairs")
    if series.price_adjustment != policy.required_price_adjustment:
        reasons.append("invalid_price_adjustment")
    if (
        not series.rows
        or (as_of - series.rows[-1].timestamp.date()).days > policy.maximum_staleness_calendar_days
    ):
        reasons.append("stale_data")
    return reasons


def _persist_run(database_path: Path, result: dict[str, Any], rules: RiskRules) -> None:
    connection = connect_database(database_path)
    try:
        with connection:
            run_id = connection.execute(
                "INSERT INTO screening_runs (as_of_date, strategy_version, status, "
                "parameters_json, "
                "completed_at) VALUES (?, ?, 'completed', ?, CURRENT_TIMESTAMP)",
                (
                    result["run_date"],
                    STRATEGY_VERSION,
                    json.dumps(
                        rules.screening.__dict__
                        if hasattr(rules.screening, "__dict__")
                        else {
                            name: getattr(rules.screening, name)
                            for name in rules.screening.__slots__
                        },
                        sort_keys=True,
                    ),
                ),
            ).lastrowid
            for item in [*result["ranked_candidates"], *result["rejected"]]:
                connection.execute(
                    "INSERT INTO screening_results (run_id, symbol, eligible, rank, score, "
                    "signals_json, "
                    "rejection_reasons_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        item["symbol"],
                        int(item.get("eligible", False)),
                        item.get("rank"),
                        len(item.get("matched_signals", [])),
                        json.dumps(item.get("signals", {}), sort_keys=True),
                        json.dumps(item.get("rejection_reasons", [])),
                    ),
                )
    except sqlite3.Error as exc:
        raise ValueError(f"cannot persist screening run: {exc}") from exc
    finally:
        connection.close()
