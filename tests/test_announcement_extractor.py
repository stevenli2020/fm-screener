from datetime import date, datetime
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest

from scripts import run as extractor

SGT = ZoneInfo("Asia/Singapore")


def sample_task() -> dict[str, str]:
    return {
        "raw_dt": "13 Aug 2026 12:51 PM",
        "issuer_name": "CHINA AVIATION OIL (SINGAPORE) CORPORATION LTD",
        "security_name": "CHINA AVIATION OIL(S) CORP LTD",
        "securities_text": "CHINA AVIATION OIL(S) CORP LTD",
        "main_title": "Financial Statements and Related Announcement::Half Yearly Results",
        "category": "Financial Statements",
        "source_url": (
            "https://links.sgx.com/1.0.0/corporate-announcements/0RHXJZ9K6BC33NUJ/abc123"
        ),
    }


def sample_html() -> str:
    return """
    <div>
      <dl>
        <dt>Securities</dt><dd>CHINA AVIATION OIL(S) CORP LTD - G92</dd>
        <dt>Status</dt><dd>New</dd>
        <dt>Announcement Reference</dt><dd>SG260813OTHRZIWX</dd>
        <dt>Submitted By</dt><dd>Liang Fei</dd>
        <dt>Designation</dt><dd>Company Secretary</dd>
        <dt>Description</dt><dd><p>First paragraph.</p><p>Second paragraph.</p></dd>
      </dl>
      <a href="900782_CAO_Results_1H2026.pdf">CAO Results.pdf</a>
    </div>
    """


def test_parse_timestamp_is_singapore_timezone():
    parsed = extractor.parse_published_at("13 Aug 2026 12:51 PM")

    assert parsed.isoformat() == "2026-08-13T12:51:00+08:00"
    assert extractor.parse_datetime_to_yymmddhhmmss("13 Aug 2026 12:51 PM") == "260813125100"


def test_invalid_timestamp_is_rejected():
    with pytest.raises(ValueError, match="Unsupported SGX publication timestamp"):
        extractor.parse_published_at("not a date")


def test_canonical_url_retains_stable_announcement_id():
    raw_url = (
        "https://links.sgx.com/1.0.0/corporate-announcements/E7UF7N37B12FHZHP/98df1010?download=1"
    )

    canonical = extractor.canonical_announcement_url(raw_url)

    assert canonical.endswith("/corporate-announcements/E7UF7N37B12FHZHP/")
    assert extractor.announcement_url_id(canonical) == "E7UF7N37B12FHZHP"


def test_tickers_are_structured_and_unresolved_is_empty():
    assert extractor.extract_ticker_symbol_list("Company - KKGB\nTrust - LHIB") == [
        "KKGB",
        "LHIB",
    ]
    assert extractor.extract_ticker_symbol_list("MULTIPLE") == []
    assert extractor.extract_ticker_symbols("MULTIPLE") == "UNKNOWN"


def test_normalize_record_preserves_required_contract():
    retrieved_at = datetime(2026, 8, 13, 13, 5, tzinfo=SGT)

    record = extractor.normalize_record(sample_task(), sample_html(), retrieved_at)

    assert record["schema_version"] == 1
    assert record["published_at"] == "2026-08-13T12:51:00+08:00"
    assert record["symbols"] == ["G92"]
    assert record["symbol_match_status"] == "resolved"
    assert record["category"] == "Financial Statements"
    assert record["announcement_reference"] == "SG260813OTHRZIWX"
    assert record["source_id"] == "0RHXJZ9K6BC33NUJ"
    assert record["submitted_by"] == "Liang Fei, Company Secretary"
    assert "First paragraph." in record["details"]
    assert record["attachments"][0]["name"] == "CAO Results.pdf"
    assert "Unsectioned" in record["announcement_sections"]
    assert "page_capture" not in record
    assert len(record["content_hash"]) == 64


def test_render_and_write_record_produce_json_and_markdown(tmp_path):
    record = extractor.normalize_record(
        sample_task(), sample_html(), datetime(2026, 8, 13, 13, 5, tzinfo=SGT)
    )

    markdown_path, json_path = extractor.write_record(record, tmp_path)
    markdown = markdown_path.read_text(encoding="utf-8")

    assert markdown_path.stem == json_path.stem
    assert markdown_path.parent.name == "records"
    assert "SG260813OTHRZIWX" in markdown_path.name
    assert "**Published At:** 2026-08-13T12:51:00+08:00" in markdown
    assert "**Category:** Financial Statements" in markdown
    assert "## Provenance" in markdown
    assert "## Announcement Sections" in markdown
    assert '"symbols": [' in json_path.read_text(encoding="utf-8")
    assert not (tmp_path / "page_snapshots").exists()


def test_date_range_and_list_url():
    task = sample_task()

    assert extractor.task_is_in_range(
        task,
        datetime(2026, 8, 13).date(),
        datetime(2026, 8, 13).date(),
    )
    assert not extractor.task_is_in_range(task, datetime(2026, 8, 14).date(), None)
    assert extractor.build_list_url(2, 100).endswith("pagesize=100&page=2")


def test_policy_mapping_and_target_url_preserve_authoritative_order():
    policy = extractor.load_filter_policy()
    mapping = policy.mappings["D05"]

    url = extractor.build_list_url(
        1,
        100,
        mapping=mapping,
        from_date=date(2026, 8, 11),
        to_date=date(2026, 8, 12),
        category_groups=policy.kept_categories,
        base_url=policy.base_url,
    )
    query = parse_qs(urlparse(url).query)

    assert mapping.filter_type == "company"
    assert policy.mappings["A17U"].filter_type == "securityname"
    assert query["value"] == ["DBS GROUP HOLDINGS LTD"]
    assert "DBS%20GROUP%20HOLDINGS%20LTD" in url
    assert "%2C" in url
    assert query["from"] == ["20260811"]
    assert query["to"] == ["20260812"]
    assert query["ANNC"][0].split(",")[:3] == ["ANNC02", "ANNC03", "ANNC04"]
    assert "PLST" not in query

    security_url = extractor.build_list_url(
        1,
        100,
        mapping=policy.mappings["ME8U"],
        from_date=date(2026, 8, 11),
        to_date=date(2026, 8, 12),
        category_groups={"ANNC": ("ANNC17",)},
        base_url=policy.base_url,
    )
    assert parse_qs(urlparse(security_url).query)["type"] == ["securityname"]


def test_load_targets_deduplicates_and_missing_mapping_is_detectable(tmp_path):
    candidates = tmp_path / "pending.json"
    candidates.write_text(
        '{"ranked_candidates":[{"symbol":"D05"},{"symbol":"O39"}]}',
        encoding="utf-8",
    )
    assert extractor.load_target_symbols(candidates, ["d05", "MISSING"]) == (
        "D05",
        "MISSING",
        "O39",
    )


class FakeDetail:
    def inner_html(self):
        return sample_html()


class FakeAttachmentResponse:
    ok = True
    status = 200
    headers = {"content-type": "application/pdf"}

    def body(self):
        return b"%PDF-1.4\n%%EOF\n"


class FakeAttachmentRequest:
    def get(self, *_args, **_kwargs):
        return FakeAttachmentResponse()


class FakePage:
    def __init__(self):
        self.detail_visits = 0
        self.context = type("FakePageContext", (), {"request": FakeAttachmentRequest()})()

    def goto(self, *_args, **_kwargs):
        self.detail_visits += 1

    def wait_for_selector(self, *_args, **_kwargs):
        return None

    def query_selector(self, _selector):
        return FakeDetail()


class FakeBrowser:
    def __init__(self):
        self.pages = [FakePage(), FakePage()]

    def new_page(self):
        return self.pages.pop(0)

    def close(self):
        return None


class FakePlaywright:
    def __init__(self):
        self.firefox = self
        self.executable_path = "/fake/firefox"

    def launch(self, **_kwargs):
        return FakeBrowser()


class FakeContext:
    def __enter__(self):
        return FakePlaywright()

    def __exit__(self, *_args):
        return None


def targeted_policy(page_size=2):
    mapping = extractor.TargetMapping("G92", "CHINA AVIATION OIL", "company")
    return extractor.FilterPolicy(
        extractor.SGX_LIST_URL,
        page_size,
        {"ANNC": ("ANNC17",), "CACT": (), "PLST": (), "TRAD": ()},
        {"G92": mapping},
    )


def test_targeted_extraction_paginates_and_deduplicates_source_ids(tmp_path, monkeypatch):
    first = sample_task()
    duplicate = {**first, "main_title": "Same source from another row"}
    second = {
        **sample_task(),
        "source_url": "https://links.sgx.com/1.0.0/corporate-announcements/SECOND/source",
    }
    calls = []

    def listing(_page, url):
        calls.append(url)
        page = parse_qs(urlparse(url).query).get("page", ["1"])[0]
        return [first, duplicate] if page == "1" else [second]

    monkeypatch.setattr(extractor, "sync_playwright", lambda: FakeContext())
    monkeypatch.setattr(extractor, "_listing_tasks", listing)
    monkeypatch.setattr(extractor.time, "sleep", lambda _seconds: None)
    result = extractor.extract_targeted(
        tmp_path,
        ("G92",),
        policy=targeted_policy(),
        from_date=date(2026, 8, 13),
        to_date=date(2026, 8, 13),
    )
    assert len(calls) == 2
    assert len(result.records) == 2
    assert result.failures == ()


def test_targeted_extraction_stops_when_sgx_repeats_a_page(tmp_path, monkeypatch):
    first = sample_task()
    duplicate = {**first, "main_title": "Repeated page result"}
    calls = []

    def listing(_page, url):
        calls.append(url)
        return [first, duplicate]

    monkeypatch.setattr(extractor, "sync_playwright", lambda: FakeContext())
    monkeypatch.setattr(extractor, "_listing_tasks", listing)
    monkeypatch.setattr(extractor.time, "sleep", lambda _seconds: None)
    result = extractor.extract_targeted(
        tmp_path,
        ("G92",),
        policy=targeted_policy(),
        from_date=date(2026, 8, 13),
        to_date=date(2026, 8, 13),
        max_pages=10,
    )

    assert len(calls) == 2
    assert len(result.records) == 1
    assert result.failures == ()


def test_targeted_empty_and_missing_mapping_are_auditable(tmp_path, monkeypatch):
    monkeypatch.setattr(extractor, "sync_playwright", lambda: FakeContext())
    monkeypatch.setattr(extractor, "_listing_tasks", lambda *_args: [])
    monkeypatch.setattr(extractor.time, "sleep", lambda _seconds: None)
    result = extractor.extract_targeted(
        tmp_path,
        ("G92", "MISSING"),
        policy=targeted_policy(),
        from_date=date(2026, 8, 13),
        to_date=date(2026, 8, 13),
    )
    assert result.records == ()
    assert result.unresolved_symbols == ("MISSING",)
    assert result.failures[0]["stage"] == "mapping"
    summary = (tmp_path / "extraction_run.json").read_text(encoding="utf-8")
    assert '"status": "partial_failure"' in summary


def test_targeted_malformed_detail_is_partial_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(extractor, "sync_playwright", lambda: FakeContext())
    monkeypatch.setattr(extractor, "_listing_tasks", lambda *_args: [sample_task()])
    monkeypatch.setattr(
        extractor,
        "normalize_record",
        lambda *_args: (_ for _ in ()).throw(ValueError("bad detail")),
    )
    monkeypatch.setattr(extractor.time, "sleep", lambda _seconds: None)
    result = extractor.extract_targeted(
        tmp_path,
        ("G92",),
        policy=targeted_policy(page_size=100),
        from_date=date(2026, 8, 13),
        to_date=date(2026, 8, 13),
    )
    assert result.records == ()
    assert result.failures[0]["stage"] == "detail"
    assert "bad detail" in result.failures[0]["error"]


def test_targeted_attachment_failure_does_not_emit_partial_record(tmp_path, monkeypatch):
    monkeypatch.setattr(extractor, "sync_playwright", lambda: FakeContext())
    monkeypatch.setattr(extractor, "_listing_tasks", lambda *_args: [sample_task()])
    monkeypatch.setattr(
        extractor,
        "cache_attachments",
        lambda *_args, **_kwargs: (
            [{"source_url": "https://links.sgx.com/report.pdf", "cache_status": "failed"}],
            [{"source_url": "https://links.sgx.com/report.pdf", "error": "HTTP 503"}],
        ),
    )
    monkeypatch.setattr(extractor.time, "sleep", lambda _seconds: None)

    result = extractor.extract_targeted(
        tmp_path,
        ("G92",),
        policy=targeted_policy(page_size=100),
        from_date=date(2026, 8, 13),
        to_date=date(2026, 8, 13),
    )

    assert result.records == ()
    assert result.failures[0]["stage"] == "attachment"
    assert "HTTP 503" in result.failures[0]["error"]
    assert [path.name for path in tmp_path.glob("*.json")] == ["extraction_run.json"]


class EmptyListingPage:
    def __init__(self, body_text):
        self.body_text = body_text

    def goto(self, *_args, **_kwargs):
        return None

    def wait_for_selector(self, *_args, **_kwargs):
        raise TimeoutError("no rows")

    def query_selector_all(self, _selector):
        return []

    def query_selector(self, selector):
        if selector == "table":
            return object()
        if selector == "body":
            return self
        return None

    def inner_text(self):
        return self.body_text


def test_listing_empty_state_is_success_but_access_denied_is_failure():
    assert extractor._listing_tasks(EmptyListingPage("No data to display"), "https://sgx") == []
    with pytest.raises(PermissionError, match="Access Denied"):
        extractor._listing_tasks(EmptyListingPage("Access Denied"), "https://sgx")


def test_navigation_retries_from_blank_and_never_reuses_stale_dom(monkeypatch):
    class FlakyPage:
        def __init__(self):
            self.urls = []
            self.failures = 1

        def goto(self, url, **_kwargs):
            self.urls.append(url)
            if url != "about:blank" and self.failures:
                self.failures -= 1
                raise TimeoutError("temporary navigation failure")

    page = FlakyPage()
    monkeypatch.setattr(extractor.time, "sleep", lambda _seconds: None)
    extractor._navigate(page, "https://sgx")
    assert page.urls == ["about:blank", "https://sgx", "about:blank", "https://sgx"]


def test_irrelevant_full_listing_page_does_not_trigger_broad_pagination(tmp_path, monkeypatch):
    irrelevant = {**sample_task(), "issuer_name": "UNRELATED ISSUER", "security_name": "OTHER"}
    calls = []

    def listing(_page, url):
        calls.append(url)
        return [irrelevant, irrelevant]

    monkeypatch.setattr(extractor, "sync_playwright", lambda: FakeContext())
    monkeypatch.setattr(extractor, "_listing_tasks", listing)
    monkeypatch.setattr(extractor.time, "sleep", lambda _seconds: None)
    result = extractor.extract_targeted(
        tmp_path,
        ("G92",),
        policy=targeted_policy(page_size=2),
        from_date=date(2026, 8, 13),
        to_date=date(2026, 8, 13),
    )
    assert len(calls) == 1
    assert result.records == ()


def test_out_of_range_full_target_page_does_not_trigger_historical_crawl(tmp_path, monkeypatch):
    old_target = {**sample_task(), "raw_dt": "01 Jan 2020 09:00:00"}
    calls = []

    def listing(_page, url):
        calls.append(url)
        return [old_target, old_target]

    monkeypatch.setattr(extractor, "sync_playwright", lambda: FakeContext())
    monkeypatch.setattr(extractor, "_listing_tasks", listing)
    monkeypatch.setattr(extractor.time, "sleep", lambda _seconds: None)
    result = extractor.extract_targeted(
        tmp_path,
        ("G92",),
        policy=targeted_policy(page_size=2),
        from_date=date(2026, 8, 13),
        to_date=date(2026, 8, 13),
    )
    assert len(calls) == 1
    assert result.records == ()
