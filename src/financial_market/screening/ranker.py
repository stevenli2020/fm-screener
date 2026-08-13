from __future__ import annotations

from typing import Any


def rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(candidate: dict[str, Any]) -> tuple[float, float, float, str]:
        extremes = candidate["signals"]["52wk_extremes"]
        distances = [extremes.get("pct_below_52w_high"), extremes.get("pct_above_52w_low")]
        extreme = max(
            (value for value in distances if isinstance(value, (int, float))), default=0.0
        )
        volume = candidate["signals"]["volume_spike"].get("spike_multiple") or 0.0
        return (-len(candidate["matched_signals"]), -extreme, -volume, candidate["symbol"])

    ranked = sorted(candidates, key=key)
    for rank, candidate in enumerate(ranked, 1):
        candidate["rank"] = rank
    return ranked
