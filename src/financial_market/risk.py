from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RiskRulesError(ValueError):
    """Raised when mechanical SGX risk rules are missing or invalid."""


@dataclass(frozen=True, slots=True)
class PositionSizingRules:
    max_position_pct_of_account: float
    max_concurrent_positions: int
    min_cash_buffer_pct: float


@dataclass(frozen=True, slots=True)
class LossLimitRules:
    daily_loss_limit_pct_of_account: float
    weekly_loss_limit_pct_of_account: float


@dataclass(frozen=True, slots=True)
class UniverseFilterRules:
    minimum_average_daily_volume: int
    minimum_median_daily_value_sgd: float
    liquidity_lookback_trading_days: int


@dataclass(frozen=True, slots=True)
class ScreeningSignalRules:
    price_move_60d_min_pct: float
    price_move_60d_max_pct: float
    volume_spike_min_multiple: float
    pct_from_52wk_extreme_min_pct: float
    donchian_breakout_threshold_pct: float
    volatility_lookback_days: int
    donchian_lookback_days: int


@dataclass(frozen=True, slots=True)
class RiskRules:
    schema_version: int
    currency: str
    position_sizing: PositionSizingRules
    loss_limits: LossLimitRules
    universe_filters: UniverseFilterRules
    screening: ScreeningSignalRules
    execution_mode: str

    @classmethod
    def from_file(cls, path: Path) -> RiskRules:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise RiskRulesError(f"cannot read risk rules: {path}") from exc
        except json.JSONDecodeError as exc:
            raise RiskRulesError(f"risk rules are not valid JSON: {path}") from exc
        if not isinstance(payload, dict):
            raise RiskRulesError("risk rules root must be an object")
        return cls.from_payload(payload)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> RiskRules:
        version = _positive_int(payload, "schema_version")
        if version != 1:
            raise RiskRulesError(f"unsupported risk rules schema_version: {version}")
        currency = _required_string(payload, "currency")
        position = _required_object(payload, "position_sizing")
        losses = _required_object(payload, "loss_limits")
        universe = _required_object(payload, "universe_filters")
        screening = _required_object(payload, "screening")
        signals = _required_object(screening, "signals")
        execution = _required_object(payload, "execution")
        execution_mode = _required_string(execution, "mode")
        if execution_mode != "manual_only":
            raise RiskRulesError("Phase 1 execution.mode must be manual_only")

        position_rules = PositionSizingRules(
            max_position_pct_of_account=_percentage(position, "max_position_pct_of_account"),
            max_concurrent_positions=_positive_int(position, "max_concurrent_positions"),
            min_cash_buffer_pct=_percentage(position, "min_cash_buffer_pct"),
        )
        loss_rules = LossLimitRules(
            daily_loss_limit_pct_of_account=_percentage(losses, "daily_loss_limit_pct_of_account"),
            weekly_loss_limit_pct_of_account=_percentage(
                losses, "weekly_loss_limit_pct_of_account"
            ),
        )
        if loss_rules.daily_loss_limit_pct_of_account > loss_rules.weekly_loss_limit_pct_of_account:
            raise RiskRulesError("daily loss limit cannot exceed weekly loss limit")

        universe_rules = UniverseFilterRules(
            minimum_average_daily_volume=_positive_int(universe, "minimum_average_daily_volume"),
            minimum_median_daily_value_sgd=_positive_number(
                universe, "minimum_median_daily_value_sgd"
            ),
            liquidity_lookback_trading_days=_positive_int(
                universe, "liquidity_lookback_trading_days"
            ),
        )
        screening_rules = ScreeningSignalRules(
            price_move_60d_min_pct=_positive_number(signals, "price_move_60d_min_pct"),
            price_move_60d_max_pct=_positive_number(signals, "price_move_60d_max_pct"),
            volume_spike_min_multiple=_positive_number(signals, "volume_spike_min_multiple"),
            pct_from_52wk_extreme_min_pct=_positive_number(
                signals, "pct_from_52wk_extreme_min_pct"
            ),
            donchian_breakout_threshold_pct=_positive_number(
                signals, "donchian_breakout_threshold_pct"
            ),
            volatility_lookback_days=_positive_int(signals, "volatility_lookback_days"),
            donchian_lookback_days=_positive_int(signals, "donchian_lookback_days"),
        )
        if screening_rules.price_move_60d_min_pct > screening_rules.price_move_60d_max_pct:
            raise RiskRulesError("screening price move minimum cannot exceed maximum")
        if screening_rules.donchian_breakout_threshold_pct > 100:
            raise RiskRulesError("donchian breakout threshold must be at most 100")
        return cls(
            schema_version=version,
            currency=currency,
            position_sizing=position_rules,
            loss_limits=loss_rules,
            universe_filters=universe_rules,
            screening=screening_rules,
            execution_mode=execution_mode,
        )


def _required_object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise RiskRulesError(f"{key} must be an object")
    return value


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RiskRulesError(f"{key} must be a non-empty string")
    return value.strip()


def _positive_number(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise RiskRulesError(f"{key} must be greater than zero")
    return float(value)


def _percentage(payload: dict[str, Any], key: str) -> float:
    value = _positive_number(payload, key)
    if value > 1:
        raise RiskRulesError(f"{key} must be at most 1.0")
    return value


def _positive_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RiskRulesError(f"{key} must be a positive integer")
    return value
