from __future__ import annotations

import json
from argparse import Namespace
from datetime import UTC, date
from datetime import datetime as DateTime
from pathlib import Path
from types import SimpleNamespace

import scripts.download_financials as downloader
from scripts.download_financials import (
    PRIMARY_CLASSIFICATION,
    REJECTED_CLASSIFICATION,
    REVIEW_CLASSIFICATION,
    SUPPLEMENTARY_CLASSIFICATION,
    attachment_is_financial,
    classify_attachment,
    classify_attachment_suite,
    cleanup_staging_directories,
    collect,
    discard_staged_attachment,
    flatten_attachment_paths,
    listing_is_target_report,
    merge_queried_date_range,
    next_collection_date,
    read_manifest,
    relocate_attachment_files,
    write_manifest,
)


def cached_pdf(tmp_path, name: str, text: str) -> dict:
    pdf = tmp_path / name
    extracted = pdf.with_suffix(".txt")
    pdf.write_bytes(b"pdf")
    extracted.write_text(f"--- PAGE 1 ---\n{text}\n", encoding="utf-8")
    return {
        "name": name,
        "source_url": f"https://links.sgx.com/{name}",
        "local_path": pdf.as_posix(),
        "url": pdf.as_posix(),
        "text_extraction": {
            "status": "extracted",
            "text_path": extracted.as_posix(),
            "page_count": 1,
            "pages_with_text": 1,
        },
    }


def test_attachment_filter_accepts_financial_document_names() -> None:
    assert attachment_is_financial("Keppel 1H2026 Financial Statements.pdf")
    assert attachment_is_financial("MIT 1QFY26 Results_Financial Statement.pdf")
    assert attachment_is_financial(
        "Download", "https://links.sgx.com/corporate/keppel-financial-reports.pdf"
    )
    assert not attachment_is_financial("Management Presentation.pdf")
    assert not attachment_is_financial("Results Release.pdf")


def test_content_classifier_accepts_z74_ccifs_as_primary(tmp_path) -> None:
    item = cached_pdf(
        tmp_path,
        "FY26-CCIFS.pdf",
        """
        CONDENSED CONSOLIDATED INTERIM FINANCIAL STATEMENTS
        CONSOLIDATED INCOME STATEMENT
        STATEMENTS OF FINANCIAL POSITION
        STATEMENTS OF CHANGES IN EQUITY
        CONSOLIDATED STATEMENT OF CASH FLOWS
        SELECTED NOTES TO THE FINANCIAL STATEMENTS
        """,
    )
    result = classify_attachment(item)
    assert result["classification"] == PRIMARY_CLASSIFICATION
    assert result["confidence"] == "high"


def test_content_classifier_accepts_z74_mda_as_supplementary(tmp_path) -> None:
    item = cached_pdf(
        tmp_path,
        "FY26-MDA.pdf",
        """
        MANAGEMENT DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION,
        RESULTS OF OPERATIONS AND CASH FLOWS
        GROUP SUMMARY INCOME STATEMENT
        SUMMARY STATEMENTS OF FINANCIAL POSITION
        GROUP CASH FLOW STATEMENT
        """,
    )
    result = classify_attachment(item)
    assert result["classification"] == SUPPLEMENTARY_CLASSIFICATION
    assert result["confidence"] == "high"


def test_content_classifier_rejects_z74_news_and_media_releases(tmp_path) -> None:
    news = cached_pdf(tmp_path, "FY26-NR-Singtel.pdf", "NEWS RELEASE\nFull-year results")
    media = cached_pdf(tmp_path, "FY26-MR-Optus.pdf", "OPTUS\nMEDIA RELEASE\nFY26 results")
    assert classify_attachment(news)["classification"] == REJECTED_CLASSIFICATION
    assert classify_attachment(media)["classification"] == REJECTED_CLASSIFICATION


def test_content_classifier_rejects_slide_filename_without_statement_content(tmp_path) -> None:
    item = cached_pdf(
        tmp_path,
        "FY26 slides.pdf",
        "Singtel FY26 results\nFinancial highlights\nUnderlying profit and dividend",
    )
    result = classify_attachment(item)
    assert result["classification"] == REJECTED_CLASSIFICATION
    assert result["confidence"] == "medium"


def test_content_classifier_retains_unreadable_pdf_for_review(tmp_path) -> None:
    pdf = tmp_path / "unknown.pdf"
    pdf.write_bytes(b"pdf")
    result = classify_attachment(
        {
            "name": pdf.name,
            "source_url": "https://links.sgx.com/unknown.pdf",
            "local_path": pdf.as_posix(),
            "text_extraction": {"status": "extracted", "pages_with_text": 0},
        }
    )
    assert result["classification"] == REVIEW_CLASSIFICATION
    assert result["confidence"] == "low"


def test_suite_classifier_rejects_unreadable_media_abbreviation_with_primary(
    tmp_path,
) -> None:
    primary = cached_pdf(
        tmp_path,
        "FY26-CCIFS.pdf",
        """
        CONSOLIDATED INCOME STATEMENT
        STATEMENT OF FINANCIAL POSITION
        STATEMENT OF CHANGES IN EQUITY
        CONSOLIDATED STATEMENT OF CASH FLOWS
        """,
    )
    unreadable_media = {
        "name": "H1FY26-MS Optus.pdf",
        "source_url": "https://links.sgx.com/H1FY26-MS-Optus.pdf",
        "text_extraction": {"status": "extracted", "pages_with_text": 0},
    }
    results = classify_attachment_suite([primary, unreadable_media])
    assert results[0]["classification"] == PRIMARY_CLASSIFICATION
    assert results[1]["classification"] == REJECTED_CLASSIFICATION
    assert results[1]["confidence"] == "medium"


def test_suite_classifier_keeps_unreadable_media_abbreviation_without_primary_for_review(
    tmp_path,
) -> None:
    unreadable_media = {
        "name": "Standalone-MS.pdf",
        "source_url": "https://links.sgx.com/Standalone-MS.pdf",
        "text_extraction": {"status": "extracted", "pages_with_text": 0},
    }
    result = classify_attachment_suite([unreadable_media])[0]
    assert result["classification"] == REVIEW_CLASSIFICATION


def test_listing_filter_excludes_results_notifications() -> None:
    assert listing_is_target_report(
        {"main_title": "Financial Statements and Related Announcement::Full Yearly Results"}
    )
    assert listing_is_target_report(
        {"main_title": "Financial Statements and Related Announcement::Half Yearly Results"}
    )
    assert not listing_is_target_report(
        {
            "main_title": "Financial Statements and Related Announcement::{}".format(
                "Notification of Results Release"
            )
        }
    )
    assert listing_is_target_report(
        {"main_title": "Financial Statements and Related Announcement::First Quarter Results"}
    )
    assert listing_is_target_report(
        {"main_title": "Financial Statements and Related Announcement::Third Quarter Results"}
    )


def test_next_collection_date_is_incremental() -> None:
    manifest = [{"published_date": "2025-07-31"}, {"published_date": "2026-02-05"}]
    assert next_collection_date(manifest, date(2021, 8, 14)) == date(2021, 8, 14)
    assert next_collection_date(manifest, date(2026, 3, 1)) == date(2026, 3, 1)
    assert next_collection_date(manifest, date(2025, 8, 1)) == date(2026, 2, 6)


def test_manifest_round_trip(tmp_path) -> None:
    path = tmp_path / "d05" / "manifest.jsonl"
    records = [{"source_id": "ABC", "published_date": "2026-02-05"}]
    write_manifest(path, records)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["records"] == records
    assert read_manifest(path) == records


def test_legacy_jsonl_manifest_is_read_for_migration(tmp_path) -> None:
    path = tmp_path / "d05" / "manifest.json"
    legacy = path.with_suffix(".jsonl")
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"source_id":"OLD"}\n', encoding="utf-8")
    assert read_manifest(path) == [{"source_id": "OLD"}]


def test_flatten_attachment_paths_removes_source_id_directory(tmp_path) -> None:
    year_dir = tmp_path / "2026"
    staged = year_dir / "attachments" / "SOURCE1"
    staged.mkdir(parents=True)
    pdf = staged / "01-financial.pdf"
    txt = staged / "01-financial.txt"
    pdf.write_bytes(b"pdf")
    txt.write_text("text", encoding="utf-8")
    attachments = [
        {
            "local_path": pdf.as_posix(),
            "url": pdf.as_posix(),
            "text_extraction": {"text_path": txt.as_posix()},
        }
    ]
    flatten_attachment_paths(attachments, year_dir, "SOURCE1")
    assert (year_dir / "01-financial.pdf").exists()
    assert (year_dir / "01-financial.txt").exists()
    assert not (year_dir / "attachments").exists()


def test_relocate_and_discard_only_modify_source_staging_directory(tmp_path) -> None:
    year_dir = tmp_path / "2026"
    staging_dir = year_dir / "attachments" / "SOURCE1"
    staging_dir.mkdir(parents=True)
    primary = cached_pdf(staging_dir, "FY26-CCIFS.pdf", "financial statements")
    rejected = cached_pdf(staging_dir, "FY26-NR.pdf", "NEWS RELEASE")

    relocated = relocate_attachment_files(primary, staging_dir, year_dir, "2026-05-21_SOURCE1")
    discarded = discard_staged_attachment(rejected, staging_dir)
    cleanup_staging_directories(staging_dir, year_dir / "attachments")

    assert Path(relocated["local_path"]).parent == year_dir
    assert Path(relocated["local_path"]).exists()
    assert Path(relocated["text_extraction"]["text_path"]).exists()
    assert discarded["retained"] is False
    assert "local_path" not in discarded
    assert "text_path" not in discarded["text_extraction"]
    assert not (year_dir / "attachments").exists()


def test_queried_date_range_expands_without_shrinking() -> None:
    existing = {"from_date": "2024-08-14", "to_date": "2026-08-14"}
    assert merge_queried_date_range(existing, date(2021, 8, 4), date(2026, 8, 14)) == {
        "from_date": "2021-08-04",
        "to_date": "2026-08-14",
    }


def test_collect_classifies_archives_manifests_and_skips_repeat(tmp_path, monkeypatch) -> None:
    task = {
        "main_title": "Financial Statements and Related Announcement::Full Yearly Results",
        "category": "Financial Statements",
        "raw_dt": "21 May 2026 07:45:32",
        "source_url": "https://links.sgx.com/SOURCE1",
    }
    raw_attachments = [
        {"name": "FY26-CCIFS.pdf", "source_url": "https://links/ccifs.pdf"},
        {"name": "FY26-MDA.pdf", "source_url": "https://links/mda.pdf"},
        {"name": "FY26-NR.pdf", "source_url": "https://links/nr.pdf"},
        {"name": "FY26-MS.pdf", "source_url": "https://links/ms.pdf"},
    ]
    text_by_name = {
        "FY26-CCIFS.pdf": """
            CONSOLIDATED INCOME STATEMENT
            STATEMENT OF FINANCIAL POSITION
            STATEMENT OF CHANGES IN EQUITY
            CONSOLIDATED STATEMENT OF CASH FLOWS
        """,
        "FY26-MDA.pdf": "MANAGEMENT DISCUSSION AND ANALYSIS",
        "FY26-NR.pdf": "NEWS RELEASE",
        "FY26-MS.pdf": "",
    }

    class FakeAnnouncement:
        @staticmethod
        def inner_html() -> str:
            return "<div>attachments</div>"

    class FakePage:
        context = SimpleNamespace(request=object())

        @staticmethod
        def wait_for_selector(selector: str, timeout: int) -> None:
            assert selector == "div.announcement"
            assert timeout == 15_000

        @staticmethod
        def query_selector(selector: str):
            assert selector == "div.announcement"
            return FakeAnnouncement()

    class FakeBrowser:
        @staticmethod
        def new_page() -> FakePage:
            return FakePage()

        @staticmethod
        def close() -> None:
            return None

    class FakeFirefox:
        executable_path = "fake-firefox"

        @staticmethod
        def launch(**kwargs) -> FakeBrowser:
            assert kwargs["headless"] is True
            return FakeBrowser()

    class FakePlaywright:
        firefox = FakeFirefox()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

    class FakeExtractor:
        SGT = UTC
        SGX_BASE_URL = ""

        def __init__(self) -> None:
            self.policy = SimpleNamespace(
                base_url="https://www.sgx.com/stock-exchange/company-announcements",
                page_size=100,
                mappings={
                    "Z74": SimpleNamespace(
                        filter_value="SINGAPORE TELECOMMUNICATIONS LIMITED",
                        filter_type="company",
                    )
                },
            )

        def load_filter_policy(self, path: Path):
            return self.policy

        @staticmethod
        def build_list_url(*args, **kwargs) -> str:
            return "https://www.sgx.com/targeted"

        @staticmethod
        def _listing_tasks(page, url):
            return [task]

        @staticmethod
        def task_matches_target(candidate, mapping) -> bool:
            return True

        @staticmethod
        def task_is_in_range(candidate, from_date, to_date) -> bool:
            return True

        @staticmethod
        def canonical_announcement_url(url: str) -> str:
            return url

        @staticmethod
        def announcement_url_id(url: str) -> str:
            return url.rsplit("/", 1)[-1]

        @staticmethod
        def _navigate(page, url: str) -> None:
            return None

        @staticmethod
        def extract_attachments(soup, source_url: str):
            return raw_attachments

        @staticmethod
        def parse_published_at(raw: str) -> DateTime:
            return DateTime(2026, 5, 21, tzinfo=UTC)

        @staticmethod
        def cache_attachments(
            attachments, source_id: str, output_root: Path, request_context, referer: str
        ):
            folder = output_root / "attachments" / source_id
            folder.mkdir(parents=True)
            cached = []
            for index, attachment in enumerate(attachments, start=1):
                pdf = folder / f"{index:02d}-{attachment['name']}"
                text = pdf.with_suffix(".txt")
                pdf.write_bytes(b"pdf")
                body = text_by_name[attachment["name"]]
                text.write_text(f"--- PAGE 1 ---\n{body}\n", encoding="utf-8")
                cached.append(
                    {
                        **attachment,
                        "url": pdf.as_posix(),
                        "local_path": pdf.as_posix(),
                        "cache_status": "cached",
                        "bytes": 3,
                        "sha256": f"hash-{index}",
                        "text_extraction": {
                            "status": "extracted",
                            "text_path": text.as_posix(),
                            "page_count": 1,
                            "pages_with_text": bool(body.strip()),
                        },
                    }
                )
            return cached, []

    monkeypatch.setattr(downloader, "sync_playwright", FakePlaywright)
    args = Namespace(
        symbol="z74",
        from_date="20210814",
        to_date="20260814",
        output_root=tmp_path / "financials",
        filters=tmp_path / "filters.json",
        max_pages=10,
        pacing_seconds=0,
        show_browser=False,
        debug=False,
    )

    first = collect(args, extractor=FakeExtractor())
    assert first["status"] == "success"
    assert first["announcements_downloaded"] == 1
    assert first["attachments_downloaded"] == 4
    assert first["attachments_archived"] == 2
    assert first["primary_financial_statements"] == 1
    assert first["supplementary_financial_analysis"] == 1
    assert first["rejected_non_reports"] == 2
    assert first["needs_review"] == 0

    manifest_path = args.output_root / "z74" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["records"]) == 1
    assert len(manifest["records"][0]["attachments"]) == 2
    assert len(manifest["records"][0]["attachment_decisions"]) == 4
    assert len(list((args.output_root / "z74" / "2026").glob("*.pdf"))) == 2
    assert not (args.output_root / "z74" / "2026" / "attachments").exists()

    second = collect(args, extractor=FakeExtractor())
    assert second["announcements_downloaded"] == 0
    assert second["attachments_downloaded"] == 0
    assert second["skipped_existing"] == 1
