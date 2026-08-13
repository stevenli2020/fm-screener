from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


class EligibilityPolicyError(ValueError):
    """Raised when the screening eligibility policy is unsafe or invalid."""


@dataclass(frozen=True, slots=True)
class EligibilityPolicy:
    minimum_daily_bars: int
    maximum_candle_repairs: int
    maximum_staleness_calendar_days: int
    required_price_adjustment: str
    instrument_policy: dict[str, str]

    @classmethod
    def from_file(cls, path: Path) -> EligibilityPolicy:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EligibilityPolicyError(f"cannot read eligibility policy: {path}") from exc
        quality, instrument = payload.get("data_quality"), payload.get("instrument_policy")
        if (
            payload.get("schema_version") != 1
            or not isinstance(quality, dict)
            or not isinstance(instrument, dict)
        ):
            raise EligibilityPolicyError("eligibility policy has invalid schema")
        values = ("minimum_daily_bars", "maximum_candle_repairs", "maximum_staleness_calendar_days")
        if any(
            isinstance(quality.get(key), bool)
            or not isinstance(quality.get(key), int)
            or quality[key] < 0
            for key in values
        ):
            raise EligibilityPolicyError(
                "eligibility data quality limits must be non-negative integers"
            )
        adjustment = quality.get("required_price_adjustment")
        if not isinstance(adjustment, str) or not adjustment:
            raise EligibilityPolicyError("required_price_adjustment must be a non-empty string")
        return cls(*(quality[key] for key in values), adjustment, dict(instrument))


def eligibility_reasons(
    security: dict[str, Any], policy: EligibilityPolicy, as_of: date
) -> list[str]:
    metadata = security.get("metadata", {})
    coverage = metadata.get("data_coverage", {}) if isinstance(metadata, dict) else {}
    reasons: list[str] = []
    if policy.instrument_policy.get(security["instrument_type"], "exclude").startswith("exclude"):
        reasons.append("instrument_type_excluded")
    if coverage.get("bar_count", 0) < policy.minimum_daily_bars:
        reasons.append("insufficient_history")
    if coverage.get("candle_repair_count", 0) > policy.maximum_candle_repairs:
        reasons.append("excessive_candle_repairs")
    if coverage.get("price_adjustment") != policy.required_price_adjustment:
        reasons.append("invalid_price_adjustment")
    last_date = coverage.get("last_date")
    try:
        if (
            last_date
            and (as_of - date.fromisoformat(last_date)).days
            > policy.maximum_staleness_calendar_days
        ):
            reasons.append("stale_data")
    except ValueError:
        reasons.append("invalid_last_date")
    return reasons
