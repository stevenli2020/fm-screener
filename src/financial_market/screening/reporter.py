from __future__ import annotations

from typing import Any


def render_report(result: dict[str, Any]) -> str:
    lines = [
        f"# Phase A screening report — {result['run_date']}",
        "",
        "## Summary",
        "",
        f"- Universe: {result['universe_count']}",
        f"- Eligible: {result['eligible_count']}",
        f"- Screened: {result['candidates_screened']}",
        f"- Matched: {result['candidates_matched']}",
        "",
        "## Ranked candidates",
        "",
        "| Rank | Symbol | Company | Matches | 60d move | Volume | 52wk below high | Donchian |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in result["ranked_candidates"]:
        s = item["signals"]
        lines.append(
            (
                "| {rank} | {symbol} | {company} | {matches} | {move} | {volume} | "
                "{distance} | {donchian} |"
            ).format(
                rank=item["rank"],
                symbol=item["symbol"],
                company=item.get("company_name", ""),
                matches=", ".join(item["matched_signals"]),
                move=_value(s["price_move_60d"].get("move_pct"), "%"),
                volume=_value(s["volume_spike"].get("spike_multiple"), "x"),
                distance=_value(s["52wk_extremes"].get("pct_below_52w_high"), "%"),
                donchian=_value(s["donchian_55d"].get("pct_of_range"), "%"),
            )
        )
    if not result["ranked_candidates"]:
        lines.append("| — | No candidates | — | — | — | — | — |")
    lines += [
        "",
        "## Exclusions and rejections",
        "",
        "| Symbol | Company | Status | Reasons |",
        "| --- | --- | --- | --- |",
    ]
    for item in result["rejected"]:
        lines.append(
            "| {symbol} | {company} | {reason} | {reasons} |".format(
                symbol=item["symbol"],
                company=item.get("company_name", ""),
                reason=item["reason"],
                reasons=", ".join(item.get("rejection_reasons", [])),
            )
        )
    return "\n".join(lines) + "\n"


def _value(value: Any, suffix: str) -> str:
    return "—" if value is None else f"{value}{suffix}"
