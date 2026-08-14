import importlib.util
from pathlib import Path
from types import SimpleNamespace

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "m4_extraction_trial.py"
SPEC = importlib.util.spec_from_file_location("m4_extraction_trial", SCRIPT_PATH)
assert SPEC and SPEC.loader
trial = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trial)


DETAIL_HTML = """
<html><body><div class="announcement">
  <h2>Announcement Details</h2>
  <dl>
    <dt>Status:</dt><dd>New</dd>
    <dt>Dividend/Distribution Number:</dt><dd>39</dd>
    <dt>Dividend/Distribution Type:</dt><dd>Interim</dd>
    <dt>Declared Dividend/Distribution Rate:</dt><dd>SGD 0.05</dd>
  </dl>
  <h2>Event Dates</h2>
  <table>
    <tr><th>Record Date</th><th>20/08/2026</th></tr>
    <tr><td>Ex Date</td><td>19/08/2026</td></tr>
    <tr><td>Pay Date</td><td>02/09/2026</td></tr>
  </table>
  <h2>Attachments</h2>
  <a href="/1.0.0/corporate-announcements/TESTSOURCE/report.pdf">Report PDF</a>
  <a href="/1.0.0/corporate-announcements/TESTSOURCE/">Announcement page</a>
</div></body></html>
"""


def test_lossless_page_and_dividend_normalization():
    page = trial.extract_lossless_page(
        DETAIL_HTML, "https://links.sgx.com/1.0.0/corporate-announcements/TESTSOURCE/"
    )

    assert [section["name"] for section in page["sections"]] == [
        "Announcement Details",
        "Event Dates",
    ]
    assert any(field["label"] == "Declared Dividend/Distribution Rate" for field in page["fields"])
    assert page["tables"][0]["rows"][1] == ["Ex Date", "19/08/2026"]

    event_type, event_data = trial.normalize_event("Cash Dividend/ Distribution", page)

    assert event_type == "cash_dividend"
    assert event_data["distribution_number"] == "39"
    assert event_data["declared_rate"] == "SGD 0.05"
    assert event_data["record_date"] == "20/08/2026"
    assert event_data["pay_date"] == "02/09/2026"


def test_attachment_discovery_excludes_canonical_announcement_page():
    attachments = trial.extract_attachments(
        DETAIL_HTML,
        "https://links.sgx.com/1.0.0/corporate-announcements/TESTSOURCE/",
        "TESTSOURCE",
    )

    assert attachments == [
        {
            "name": "Report PDF",
            "source_url": (
                "https://links.sgx.com/1.0.0/corporate-announcements/TESTSOURCE/report.pdf"
            ),
        }
    ]


def test_compact_sections_merge_fields_and_multicolumn_tables():
    page = {
        "fields": [
            {
                "section": "Section A",
                "label": "Maximum number of shares authorised for purchase",
                "value": "90,646,698",
                "links": [],
            },
            {
                "section": "Section A",
                "label": "Purchase made by way of market acquisition",
                "value": "Yes",
                "links": [],
            },
            {
                "section": "Section D",
                "label": "Number of issued shares excluding treasury shares after purchase",
                "value": "1,798,121,509",
                "links": [],
            },
            {
                "section": "Section D",
                "label": "Number of treasury shares held after purchase",
                "value": "22,436,258",
                "links": [],
            },
        ],
        "tables": [
            {
                "section": "Section A",
                "rows": [
                    ["", "Singapore Exchange", "Overseas Exchange"],
                    ["Date of Purchase", "12/08/2026", ""],
                    ["Total Number of shares purchased", "200,000", ""],
                    ["Highest Price per share", "SGD 11.3", ""],
                ],
            },
            {
                "section": "Section C",
                "rows": [
                    ["Cumulative No. of shares purchased to date^", "Number", "Percentage#"],
                    ["By way of Market Acquisition", "14,828,000", "0.8179"],
                ],
            },
        ],
    }

    sections = trial.compact_announcement_sections(page)

    assert sections["Section A"] == (
        "Maximum number of shares authorised for purchase: 90,646,698; "
        "Purchase made by way of market acquisition: Yes; "
        "Singapore Exchange Date of Purchase: 12/08/2026; "
        "Singapore Exchange Total Number of shares purchased: 200,000; "
        "Singapore Exchange Highest Price per share: SGD 11.3"
    )
    assert sections["Section C"] == (
        "Cumulative No. of shares purchased to date^ - By way of Market Acquisition: "
        "Number: 14,828,000, Percentage#: 0.8179"
    )

    event_type, event_data = trial.normalize_event("Share Buy Back-On Market", page)
    assert event_type == "share_buyback"
    assert event_data["purchase_date"] == "12/08/2026"
    assert event_data["treasury_shares_after_purchase"] == "22,436,258"


def test_create_live_record_validates_candidate_symbol():
    class FakeListing:
        @staticmethod
        def normalize_record(_task, _html, _retrieved_at):
            return {
                "symbols": ["F34"],
                "source_url": ("https://links.sgx.com/1.0.0/corporate-announcements/TESTSOURCE/"),
            }

    record, snapshot, visible_text = trial.create_live_record(
        FakeListing,
        {"task": {}, "target_symbols": ["F34"]},
        DETAIL_HTML,
        trial.datetime.now(trial.UTC),
    )

    assert record["target_symbols"] == ["F34"]
    assert 'class="announcement"' in snapshot
    assert "Declared Dividend/Distribution Rate" in visible_text


def test_live_discovery_uses_mapped_candidate():
    mapping = SimpleNamespace(symbol="F34", filter_value="WILMAR", filter_type="company")
    policy = SimpleNamespace(
        mappings={"F34": mapping},
        kept_categories={"ANNC": ("ANNC01",), "CACT": ("CACT22",)},
        page_size=100,
        base_url="https://www.sgx.com/stock-exchange/company-announcements",
    )
    task = {
        "source_url": "https://links.sgx.com/1.0.0/corporate-announcements/SOURCE1/hash",
        "raw_dt": "12 Aug 2026 05:20 PM",
    }

    class FakeListing:
        @staticmethod
        def build_list_url(*_args, **_kwargs):
            return "https://example.test/list"

        @staticmethod
        def _listing_tasks(_page, _url):
            return [task]

        @staticmethod
        def task_matches_target(_task, _mapping):
            return True

        @staticmethod
        def task_is_in_range(_task, _from_date, _to_date):
            return True

        @staticmethod
        def canonical_announcement_url(_url):
            return "https://links.sgx.com/1.0.0/corporate-announcements/SOURCE1/"

        @staticmethod
        def announcement_url_id(_url):
            return "SOURCE1"

    tasks, failures, metrics = trial.discover_live_announcements(
        FakeListing,
        SimpleNamespace(page=object()),
        ("F34",),
        policy,
        trial.date(2026, 8, 11),
        trial.date(2026, 8, 13),
        max_pages=1,
        pacing_seconds=0,
        debug_enabled=False,
    )

    assert list(tasks) == ["SOURCE1"]
    assert tasks["SOURCE1"]["target_symbols"] == ["F34"]
    assert failures == []
    assert metrics["listing_requests_succeeded"] == 1
