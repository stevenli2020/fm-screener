from __future__ import annotations

from typing import Any


def generate_json_feed(result: dict[str, Any]) -> dict[str, Any]:
    """Return the authoritative machine-readable M5 input."""
    return {
        "run_date": result["run_date"],
        "period_start": result.get("period_start", result["run_date"]),
        "period_end": result.get("period_end", result["run_date"]),
        "candidate_count": result["candidate_count"],
        "announcements_fetched": result["announcements_fetched"],
        "candidate_announcements": result["candidate_announcements"],
        "announcements_stored": result["announcements_stored"],
        "announcements_replaced": result.get("announcements_replaced", 0),
        "announcements_skipped": result["announcements_skipped"],
        "api_status": result["api_status"],
        "api_error": result.get("api_error"),
        "records": result["records"],
    }


def generate_markdown_report(result: dict[str, Any]) -> str:
    """Render a concise human review report derived from the JSON result."""
    availability = result["api_availability"]
    lines = [
        f"# News collection report — {result['run_date']}",
        "",
        "## Summary",
        "",
        f"- Inclusive period: {result.get('period_start', result['run_date'])} to "
        f"{result.get('period_end', result['run_date'])}",
        f"- Candidate symbols checked: {result['candidate_count']}",
        f"- Announcements fetched from SGX: {result['announcements_fetched']}",
        f"- Candidate announcements: {result['candidate_announcements']}",
        f"- New records stored: {result['announcements_stored']}",
        f"- Replacement records updated: {result.get('announcements_replaced', 0)}",
        f"- Duplicate records skipped: {result['announcements_skipped']}",
        f"- API status: {result['api_status']}",
        f"- Seven-day call availability: {availability['success_rate_pct']}% "
        f"({availability['successful_calls']}/{availability['total_calls']})",
    ]
    if result.get("api_error"):
        lines.append(f"- API error: {result['api_error']}")
    lines += [
        "",
        "## Announcements by symbol",
        "",
        "| Symbol | Published | Type | Event | Attachments | Title | URL |",
        "| --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for record in result["records"]:
        url = f"[link]({record['url']})" if record.get("url") else "—"
        lines.append(
            f"| {record['symbol']} | {record['published_at']} | "
            f"{record.get('type') or '—'} | {record.get('event_type', 'unclassified')} | "
            f"{len(record.get('attachments', []))} | {_cell(record['title'])} | {url} |"
        )
    if not result["records"]:
        lines.append("| — | — | — | — | 0 | No candidate announcements returned | — |")
    lines += [
        "",
        "## Candidates with no announcements",
        "",
        ", ".join(result["symbols_without_news"]) or "None",
        "",
        "## API availability log",
        "",
        "| Run date | Status | HTTP | Fetched | Attempts | Duration (ms) | Error |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for entry in result["api_log"]:
        lines.append(
            f"| {entry['run_date']} | {entry['status']} | {entry['http_code'] or '—'} | "
            f"{entry['announcements_fetched']} | {entry['attempt_count']} | "
            f"{entry['execution_time_ms']} | {_cell(entry['error_message'] or '')} |"
        )
    return "\n".join(lines) + "\n"


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
