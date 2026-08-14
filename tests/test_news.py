from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import requests

from financial_market.config import Settings
from financial_market.research.news_collector import (
    Announcement,
    FetchResult,
    SGXNewsClient,
    SGXNewsError,
    SGXPublicPageClient,
)
from financial_market.research.news_deduplicator import compute_document_hash
from financial_market.research.news_pipeline import (
    NewsPipelineError,
    collect_news,
    load_candidate_symbols,
)
from financial_market.research.news_reporter import generate_json_feed, generate_markdown_report
from financial_market.storage import connect_database, initialize_database


class Response:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class Session:
    def __init__(self, responses: list[Response | Exception]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> Response:
        self.calls.append({"url": url, **kwargs})
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def payload(symbol: str = "D05") -> dict[str, Any]:
    return {
        "id": f"SG-{symbol}",
        "symbol": symbol,
        "title": "Results Announcement",
        "type": "financial_results",
        "publishedAt": "2026-08-13T08:30:00+08:00",
        "url": "https://links.sgx.com/example",
        "documentType": "PDF",
    }


def test_client_parses_contract_and_formats_query() -> None:
    session = Session([Response(200, {"announcements": [payload()]})])
    settings = Settings(sgx_news_max_retries=0)
    client = SGXNewsClient(settings, session=session, monotonic=lambda: 1.0)

    result = client.fetch_announcements(
        datetime(2026, 8, 13, tzinfo=UTC), datetime(2026, 8, 13, 23, 59, tzinfo=UTC)
    )

    assert result.announcements[0].published_at == "2026-08-13T00:30:00Z"
    assert session.calls[0]["params"]["periodstart"] == "20260813_000000"
    assert session.calls[0]["params"]["limit"] == 50


def test_client_retries_retryable_response() -> None:
    session = Session([Response(503, {}), Response(200, {"announcements": []})])
    sleeps: list[float] = []
    client = SGXNewsClient(
        Settings(sgx_news_max_retries=1),
        session=session,
        sleep=sleeps.append,
        monotonic=lambda: 2.0,
    )

    result = client.fetch_announcements(
        datetime(2026, 8, 13, tzinfo=UTC), datetime(2026, 8, 13, 23, 59, tzinfo=UTC)
    )

    assert result.attempt_count == 2
    assert sleeps == [0.25]


@pytest.mark.parametrize(
    ("response", "expected_status"),
    [
        (Response(403, {}), "error"),
        (Response(200, {"wrong": []}), "malformed"),
        (requests.Timeout("slow"), "timeout"),
    ],
)
def test_client_reports_http_malformed_and_timeout(
    response: Response | Exception, expected_status: str
) -> None:
    client = SGXNewsClient(
        Settings(sgx_news_max_retries=0),
        session=Session([response]),
        monotonic=lambda: 3.0,
    )
    with pytest.raises(SGXNewsError) as caught:
        client.fetch_announcements(
            datetime(2026, 8, 13, tzinfo=UTC),
            datetime(2026, 8, 13, 23, 59, tzinfo=UTC),
        )
    assert caught.value.status == expected_status


class Client:
    def __init__(self, result: FetchResult | SGXNewsError) -> None:
        self.result = result

    def fetch_announcements(self, *_: object) -> FetchResult:
        if isinstance(self.result, SGXNewsError):
            raise self.result
        return self.result


def _database_with_securities(path: Path) -> None:
    initialize_database(path)
    connection = connect_database(path)
    try:
        with connection:
            for symbol in ("D05", "O39", "U11"):
                connection.execute(
                    "INSERT INTO securities (symbol, provider_symbol, company_name) "
                    "VALUES (?, ?, ?)",
                    (symbol, f"{symbol}.SI", symbol),
                )
    finally:
        connection.close()


def _candidates(path: Path) -> None:
    path.write_text(
        json.dumps({"ranked_candidates": [{"symbol": "D05"}, {"symbol": "O39"}]}),
        encoding="utf-8",
    )


def test_pipeline_filters_deduplicates_stores_and_logs(tmp_path: Path) -> None:
    database = tmp_path / "market.sqlite3"
    candidates = tmp_path / "pending_candidates.json"
    _database_with_securities(database)
    _candidates(candidates)
    announcements = tuple(Announcement.from_payload(value) for value in (payload(), payload("U11")))
    client = Client(FetchResult(announcements, 200, 12, 1))
    retrieved = datetime(2026, 8, 13, 1, tzinfo=UTC)

    first = collect_news(
        candidates, database, client, "https://api.example", date(2026, 8, 13), retrieved
    )
    second = collect_news(
        candidates, database, client, "https://api.example", date(2026, 8, 13), retrieved
    )

    assert first["announcements_fetched"] == 2
    assert first["candidate_announcements"] == 1
    assert first["announcements_stored"] == 1
    assert second["announcements_skipped"] == 1
    assert first["symbols_without_news"] == ["O39"]
    assert second["api_availability"]["success_rate_pct"] == 100.0
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT COUNT(*) FROM news_records").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM news_api_log").fetchone()[0] == 2
    finally:
        connection.close()


def test_replacement_with_same_source_id_updates_record(tmp_path: Path) -> None:
    database = tmp_path / "market.sqlite3"
    candidates = tmp_path / "pending_candidates.json"
    _database_with_securities(database)
    _candidates(candidates)
    original = Announcement.from_payload(payload())
    replacement = Announcement(
        sgxnet_id=original.sgxnet_id,
        symbol=original.symbol,
        title="Replacement Results Announcement",
        announcement_type=original.announcement_type,
        published_at=original.published_at,
        url=original.url,
        document_type=original.document_type,
        content_hash="f" * 64,
        source="sgx_public_website",
    )
    retrieved = datetime(2026, 8, 13, 1, tzinfo=UTC)
    collect_news(
        candidates,
        database,
        Client(FetchResult((original,), 200, 1, 1)),
        "https://www.sgx.com",
        date(2026, 8, 13),
        retrieved,
    )
    result = collect_news(
        candidates,
        database,
        Client(FetchResult((replacement,), 200, 1, 1)),
        "https://www.sgx.com",
        date(2026, 8, 13),
        retrieved,
    )
    assert result["announcements_replaced"] == 1
    connection = sqlite3.connect(database)
    try:
        assert (
            connection.execute("SELECT title FROM news_records")
            .fetchone()[0]
            .startswith("Replacement")
        )
        assert connection.execute("SELECT COUNT(*) FROM news_records").fetchone()[0] == 1
    finally:
        connection.close()


def test_public_page_adapter_normalizes_extractor_contract(tmp_path: Path, monkeypatch) -> None:
    from scripts import run as extractor

    record = {
        "symbols": ["D05"],
        "source_id": "ABC123",
        "title": "Results",
        "published_at": "2026-08-13T08:30:00+08:00",
        "category": "Financial Statements",
        "source_url": "https://links.sgx.com/ABC123/",
        "attachments": [{"url": "https://links.sgx.com/results.pdf"}],
        "announcement_sections": {"Announcement Details": "Status: New"},
        "event_type": "unclassified",
        "event_data": {},
        "content_hash": "a" * 64,
    }
    monkeypatch.setattr(
        extractor,
        "load_filter_policy",
        lambda _path: SimpleNamespace(base_url="https://www.sgx.com/announcements"),
    )
    monkeypatch.setattr(
        extractor,
        "extract_targeted",
        lambda *_args, **_kwargs: extractor.ExtractionResult((record,), (), 4, 4, ()),
    )
    client = SGXPublicPageClient(
        filters_path=tmp_path / "filters.json",
        extraction_dir=tmp_path / "extract",
        extractor_module=extractor,
    )
    result = client.fetch_announcements(
        datetime(2026, 8, 13, tzinfo=UTC),
        datetime(2026, 8, 13, 23, 59, tzinfo=UTC),
        ("D05",),
    )
    assert result.attempt_count == 4
    assert result.announcements[0].source == "sgx_public_website"
    assert result.announcements[0].document_type == "PDF"
    assert result.announcements[0].announcement_sections == {"Announcement Details": "Status: New"}


def test_rich_announcement_flows_to_sqlite_and_agent_feed(tmp_path: Path) -> None:
    database = tmp_path / "market.sqlite3"
    candidates = tmp_path / "pending_candidates.json"
    _database_with_securities(database)
    _candidates(candidates)
    announcement = Announcement(
        sgxnet_id="RICH1",
        symbol="D05",
        title="Interim Dividend",
        announcement_type="Cash Dividend/ Distribution",
        published_at="2026-08-13T00:30:00Z",
        url="https://links.sgx.com/RICH1/",
        document_type="PDF",
        content_hash="b" * 64,
        source="sgx_public_website",
        announcement_sections={"Event Dates": "Record Date: 20/08/2026"},
        event_type="cash_dividend",
        event_data={"gross_rate": "SGD 0.05"},
        attachments=(
            {
                "name": "Dividend notice",
                "source_url": "https://links.sgx.com/RICH1/notice.pdf",
                "local_path": "reports/generated/extraction/attachments/RICH1/notice.pdf",
                "cache_status": "cached",
                "sha256": "c" * 64,
            },
        ),
    )

    result = collect_news(
        candidates,
        database,
        Client(FetchResult((announcement,), 200, 1, 2)),
        "https://www.sgx.com",
        date(2026, 8, 13),
        datetime(2026, 8, 13, 1, tzinfo=UTC),
    )
    feed = generate_json_feed(result)

    assert feed["records"][0]["announcement_sections"]["Event Dates"].startswith("Record Date")
    assert feed["records"][0]["attachments"][0]["cache_status"] == "cached"
    connection = sqlite3.connect(database)
    try:
        row = connection.execute(
            "SELECT announcement_sections_json, event_type, event_data_json, attachments_json "
            "FROM news_records WHERE sgxnet_id = 'RICH1'"
        ).fetchone()
    finally:
        connection.close()
    assert json.loads(row[0]) == {"Event Dates": "Record Date: 20/08/2026"}
    assert row[1] == "cash_dividend"
    assert json.loads(row[2]) == {"gross_rate": "SGD 0.05"}
    assert json.loads(row[3])[0]["sha256"] == "c" * 64


def test_pipeline_logs_failed_api_and_report_is_readable(tmp_path: Path) -> None:
    database = tmp_path / "market.sqlite3"
    candidates = tmp_path / "pending_candidates.json"
    _database_with_securities(database)
    _candidates(candidates)
    error = SGXNewsError("forbidden", http_code=403, execution_time_ms=5)

    result = collect_news(
        candidates, database, Client(error), "https://api.example", date(2026, 8, 13)
    )
    feed = generate_json_feed(result)
    report = generate_markdown_report(result)

    assert result["api_status"] == "error"
    assert feed["api_error"] == "forbidden"
    assert "API error: forbidden" in report
    assert "D05, O39" in report


def test_candidate_contract_and_hash_are_deterministic(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"ranked_candidates":[{"rank":1}]}', encoding="utf-8")
    with pytest.raises(NewsPipelineError, match="non-empty symbol"):
        load_candidate_symbols(invalid)
    assert compute_document_hash("d05", " Results ", "2026-08-13T00:00:00Z") == (
        compute_document_hash("D05", "Results", "2026-08-13T00:00:00Z")
    )
