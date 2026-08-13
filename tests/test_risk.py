import json
from pathlib import Path

import pytest

from financial_market.risk import RiskRules, RiskRulesError

PROJECT_ROOT = Path(__file__).parents[1]


def test_repository_sgx_risk_rules_match_approved_defaults() -> None:
    rules = RiskRules.from_file(PROJECT_ROOT / "config" / "risk_rules_sgx.json")

    assert rules.position_sizing.max_position_pct_of_account == 0.20
    assert rules.position_sizing.max_concurrent_positions == 4
    assert rules.position_sizing.min_cash_buffer_pct == 0.10
    assert rules.loss_limits.daily_loss_limit_pct_of_account == 0.05
    assert rules.loss_limits.weekly_loss_limit_pct_of_account == 0.10
    assert rules.universe_filters.minimum_average_daily_volume == 100000
    assert rules.universe_filters.minimum_median_daily_value_sgd == 1000000
    assert rules.execution_mode == "manual_only"
    assert rules.screening.donchian_lookback_days == 55


def test_live_execution_mode_is_rejected(tmp_path: Path) -> None:
    source = PROJECT_ROOT / "config" / "risk_rules_sgx.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["execution"]["mode"] = "live"
    target = tmp_path / "invalid.json"
    target.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RiskRulesError, match="manual_only"):
        RiskRules.from_file(target)


def test_daily_loss_limit_cannot_exceed_weekly_limit() -> None:
    payload = {
        "schema_version": 1,
        "currency": "SGD",
        "position_sizing": {
            "max_position_pct_of_account": 0.2,
            "max_concurrent_positions": 4,
            "min_cash_buffer_pct": 0.1,
        },
        "loss_limits": {
            "daily_loss_limit_pct_of_account": 0.2,
            "weekly_loss_limit_pct_of_account": 0.1,
        },
        "universe_filters": {
            "minimum_average_daily_volume": 100000,
            "minimum_median_daily_value_sgd": 1000000,
            "liquidity_lookback_trading_days": 20,
        },
        "screening": {
            "signals": {
                "price_move_60d_min_pct": 10.0,
                "price_move_60d_max_pct": 50.0,
                "volume_spike_min_multiple": 1.5,
                "pct_from_52wk_extreme_min_pct": 5.0,
                "donchian_breakout_threshold_pct": 85.0,
                "volatility_lookback_days": 20,
                "donchian_lookback_days": 55,
            }
        },
        "execution": {"mode": "manual_only"},
    }

    with pytest.raises(RiskRulesError, match="daily loss limit"):
        RiskRules.from_payload(payload)
