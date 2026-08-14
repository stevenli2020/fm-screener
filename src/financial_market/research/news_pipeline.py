from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from financial_market.storage import connect_database, initialize_database

from .news_collector import FetchResult, SGXNewsError
from .news_deduplicator import StoredAnnouncement, store_announcements


class NewsPipelineError(ValueError):
    """Raised when M4 input or local persistence is invalid."""


def load_candidate_symbols(path: Path) -> tuple[str, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise NewsPipelineError(f"cannot read M3 candidate file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise NewsPipelineError(f"M3 candidate file is not valid JSON: {path}") from exc
    candidates = payload.get("ranked_candidates") if isinstance(payload, dict) else None
    if not isinstance(candidates, list):
        raise NewsPipelineError("M3 candidate file ranked_candidates must be a list")
    symbols: list[str] = []
    for candidate in candidates:
        symbol = candidate.get("symbol") if isinstance(candidate, dict) else None
        if not isinstance(symbol, str) or not symbol.strip():
            raise NewsPipelineError("every ranked candidate must have a non-empty symbol")
        symbols.append(symbol.strip().upper())
    if len(symbols) != len(set(symbols)):
        raise NewsPipelineError("M3 candidate file contains duplicate symbols")
    return tuple(symbols)


def collect_news(
    input_path: Path,
    database_path: Path,
    client: Any,
    api_endpoint: str,
    run_date: date | None = None,
    retrieved_at: datetime | None = None,
    lookback_days: int = 0,
) -> dict[str, Any]:
    if not 0 <= lookback_days <= 30:
        raise NewsPipelineError("lookback_days must be between 0 and 30")
    collection_date = run_date or date.today()
    retrieved = retrieved_at or datetime.now(UTC)
    candidates = load_candidate_symbols(input_path)
    initialize_database(database_path)
    collection_start = collection_date - timedelta(days=lookback_days)
    period_start = datetime.combine(collection_start, time.min, tzinfo=UTC)
    period_end = datetime.combine(collection_date, time.max, tzinfo=UTC)
    try:
        fetched = client.fetch_announcements(period_start, period_end, candidates)
    except SGXNewsError as exc:
        _log_api_call(
            database_path,
            api_endpoint,
            collection_date,
            exc.status,
            exc.http_code,
            str(exc),
            0,
            exc.execution_time_ms,
            exc.attempt_count,
        )
        return _build_result(
            database_path=database_path,
            run_date=collection_date,
            period_start=collection_start,
            candidates=candidates,
            fetched_count=0,
            stored=(),
            api_status=exc.status,
            api_error=str(exc),
        )
    _log_fetch(database_path, api_endpoint, collection_date, fetched)
    candidate_set = set(candidates)
    relevant = tuple(
        sorted(
            (item for item in fetched.announcements if item.symbol in candidate_set),
            key=lambda item: (item.symbol, item.published_at, item.sgxnet_id),
        )
    )
    stored = store_announcements(database_path, relevant, retrieved)
    return _build_result(
        database_path=database_path,
        run_date=collection_date,
        period_start=collection_start,
        candidates=candidates,
        fetched_count=len(fetched.announcements),
        stored=stored,
        api_status=fetched.status,
        api_error=fetched.error_message,
    )


def _build_result(
    *,
    database_path: Path,
    run_date: date,
    period_start: date,
    candidates: tuple[str, ...],
    fetched_count: int,
    stored: tuple[StoredAnnouncement, ...],
    api_status: str,
    api_error: str | None,
) -> dict[str, Any]:
    unique: dict[str, dict[str, Any]] = {}
    symbols_with_news: set[str] = set()
    for item in stored:
        announcement = item.announcement
        symbols_with_news.add(announcement.symbol)
        unique[item.document_hash] = {
            "sgxnet_id": announcement.sgxnet_id,
            "symbol": announcement.symbol,
            "title": announcement.title,
            "type": announcement.announcement_type,
            "published_at": announcement.published_at,
            "url": announcement.url,
            "document_type": announcement.document_type,
            "document_hash": item.document_hash,
            "retrieved_at": item.retrieved_at,
            "source": announcement.source,
            "announcement_sections": announcement.announcement_sections or {},
            "event_type": announcement.event_type,
            "event_data": announcement.event_data or {},
            "attachments": list(announcement.attachments),
        }
    records = sorted(
        unique.values(), key=lambda item: (item["symbol"], item["published_at"], item["sgxnet_id"])
    )
    api_log, availability = _availability(database_path, run_date)
    return {
        "run_date": run_date.isoformat(),
        "period_start": period_start.isoformat(),
        "period_end": run_date.isoformat(),
        "candidate_count": len(candidates),
        "candidate_symbols": list(candidates),
        "announcements_fetched": fetched_count,
        "candidate_announcements": len(stored),
        "announcements_stored": sum(item.disposition == "new" for item in stored),
        "announcements_replaced": sum(item.disposition == "replacement" for item in stored),
        "announcements_skipped": sum(item.disposition == "duplicate" for item in stored),
        "candidates_with_news": len(symbols_with_news),
        "symbols_without_news": [
            symbol for symbol in candidates if symbol not in symbols_with_news
        ],
        "api_status": api_status,
        "api_error": api_error,
        "records": records,
        "api_log": api_log,
        "api_availability": availability,
    }


def _log_fetch(database_path: Path, endpoint: str, run_date: date, result: FetchResult) -> None:
    _log_api_call(
        database_path,
        endpoint,
        run_date,
        "error" if result.status == "partial_failure" else result.status,
        result.http_code,
        result.error_message,
        len(result.announcements),
        result.execution_time_ms,
        result.attempt_count,
    )


def _log_api_call(
    database_path: Path,
    endpoint: str,
    run_date: date,
    status: str,
    http_code: int | None,
    error_message: str | None,
    fetched: int,
    execution_time_ms: int,
    attempt_count: int,
) -> None:
    connection = connect_database(database_path)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO news_api_log (
                    api_endpoint, run_date, status, http_code, error_message,
                    announcements_fetched, execution_time_ms, attempt_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    endpoint,
                    run_date.isoformat(),
                    status,
                    http_code,
                    error_message,
                    fetched,
                    execution_time_ms,
                    attempt_count,
                ),
            )
    except sqlite3.Error as exc:
        raise NewsPipelineError(f"cannot log SGX API availability: {exc}") from exc
    finally:
        connection.close()


def _availability(
    database_path: Path, run_date: date
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    first_date = (run_date - timedelta(days=6)).isoformat()
    connection = connect_database(database_path)
    try:
        rows = connection.execute(
            """
            SELECT run_date, status, http_code, announcements_fetched,
                   execution_time_ms, attempt_count, error_message
            FROM news_api_log
            WHERE run_date BETWEEN ? AND ?
            ORDER BY id DESC
            """,
            (first_date, run_date.isoformat()),
        ).fetchall()
    finally:
        connection.close()
    values = [
        {
            "run_date": row[0],
            "status": row[1],
            "http_code": row[2],
            "announcements_fetched": row[3],
            "execution_time_ms": row[4],
            "attempt_count": row[5],
            "error_message": row[6],
        }
        for row in rows
    ]
    successes = sum(item["status"] == "success" for item in values)
    total = len(values)
    return values, {
        "window_days": 7,
        "successful_calls": successes,
        "failed_calls": total - successes,
        "total_calls": total,
        "success_rate_pct": round(successes / total * 100, 2) if total else 0.0,
    }
