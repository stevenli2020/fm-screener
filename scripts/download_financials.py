"""Incrementally archive selected SGX financial-statement attachments."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
EXTRACTOR_PATH = SCRIPT_DIR / "run.py"
DEFAULT_FILTERS = SCRIPT_DIR / "sgx_announcement_filters.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "reports" / "financials"
ATTACHMENT_TERMS = ("financial statement", "financial report")
PRIMARY_CLASSIFICATION = "primary_financial_statement"
SUPPLEMENTARY_CLASSIFICATION = "supplementary_financial_analysis"
REJECTED_CLASSIFICATION = "presentation_or_release"
REVIEW_CLASSIFICATION = "needs_review"
ARCHIVED_CLASSIFICATIONS = {PRIMARY_CLASSIFICATION, SUPPLEMENTARY_CLASSIFICATION}

PRIMARY_HEADING_PATTERNS = {
    "income_statement": (
        r"\b(?:consolidated |group |summary )?(?:income statement|"
        r"statement of (?:profit|comprehensive income)|profit and loss)\b"
    ),
    "financial_position": (r"\b(?:statements? of financial position|balance sheets?)\b"),
    "cash_flow": r"\b(?:consolidated |group )?(?:statements? of )?cash flows?\b",
    "changes_in_equity": r"\bstatements? of changes in equity\b",
    "financial_notes": (
        r"\b(?:selected )?notes to (?:the )?(?:condensed )?(?:interim )?"
        r"financial statements\b"
    ),
}
SUPPLEMENTARY_PATTERNS = {
    "management_discussion_analysis": (
        r"\bmanagement discussion (?:and|&) analysis\b",
        r"\bmanagement.?s discussion (?:and|&) analysis\b",
    ),
    "operating_financial_review": r"\boperating and financial review\b",
}
RELEASE_PATTERNS = {
    "news_release": r"\bnews release\b",
    "media_release": r"\bmedia release\b",
    "press_release": r"\bpress release\b",
}
PRESENTATION_PATTERNS = {
    "results_presentation": (
        r"\b(?:financial |full year |half year |quarterly |results )*presentation\b"
    ),
    "presentation_slides": r"\bpresentation slides?\b",
}


def _load_extractor() -> Any:
    spec = importlib.util.spec_from_file_location("financial_market_sgx_extractor", EXTRACTOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load SGX extractor: {EXTRACTOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def attachment_is_financial(name: str, source_url: str = "") -> bool:
    url_name = Path(source_url.split("?", 1)[0]).name
    haystack = re.sub(r"[^a-z0-9]+", " ", f"{name} {url_name}".casefold())
    return any(term in haystack for term in ATTACHMENT_TERMS)


def _attachment_text(item: dict[str, Any], max_pages: int = 12) -> str | None:
    extraction = item.get("text_extraction")
    if not isinstance(extraction, dict) or extraction.get("status") != "extracted":
        return None
    raw_path = extraction.get("text_path")
    if not isinstance(raw_path, str):
        return None
    text_path = Path(raw_path)
    if not text_path.is_file():
        return None
    text = text_path.read_text(encoding="utf-8", errors="replace")
    pages = re.split(r"(?m)^--- PAGE \d+ ---\s*$", text)
    if len(pages) > 1:
        text = "\f".join(pages[1 : max_pages + 1])
    return text.strip() or None


def _matched_patterns(text: str, patterns: dict[str, str | tuple[str, ...]]) -> list[str]:
    matches: list[str] = []
    for name, expressions in patterns.items():
        candidates = (expressions,) if isinstance(expressions, str) else expressions
        if any(re.search(expression, text, re.IGNORECASE) for expression in candidates):
            matches.append(name)
    return matches


def _filename_nonreport_hint(name: str, source_url: str) -> str | None:
    filename = f"{name} {Path(source_url.split('?', 1)[0]).name}".casefold()
    if re.search(r"(?:^|[-_. ])(?:nr|mr|ms)(?:[-_. ]|$)", filename):
        return "release_filename"
    if re.search(r"\b(?:news|media|press)[-_ ]?(?:release|statement)\b", filename):
        return "release_filename"
    if re.search(r"\b(?:slides?|presentation)\b", filename):
        return "presentation_filename"
    return None


def classify_attachment(item: dict[str, Any]) -> dict[str, Any]:
    """Classify a cached attachment from extracted content, using its name only as a hint."""
    name = str(item.get("name", ""))
    source_url = str(item.get("source_url", ""))
    text = _attachment_text(item)
    if text is None:
        return {
            "classification": REVIEW_CLASSIFICATION,
            "confidence": "low",
            "signals": [],
            "reason": "PDF text was unavailable or empty; manual review is required",
        }

    first_pages = "\n".join(text.split("\f")[:3])
    supplementary = _matched_patterns(first_pages, SUPPLEMENTARY_PATTERNS)
    releases = _matched_patterns(first_pages, RELEASE_PATTERNS)
    presentations = _matched_patterns(first_pages, PRESENTATION_PATTERNS)
    primary = _matched_patterns(text, PRIMARY_HEADING_PATTERNS)

    if releases:
        return {
            "classification": REJECTED_CLASSIFICATION,
            "confidence": "high",
            "signals": releases,
            "reason": "Document identifies itself as a news, media, or press release",
        }
    if presentations:
        return {
            "classification": REJECTED_CLASSIFICATION,
            "confidence": "high",
            "signals": presentations,
            "reason": "Document identifies itself as a presentation or slide deck",
        }
    if supplementary:
        return {
            "classification": SUPPLEMENTARY_CLASSIFICATION,
            "confidence": "high",
            "signals": supplementary,
            "reason": "Document is management discussion or operating and financial analysis",
        }
    if len(primary) >= 3:
        return {
            "classification": PRIMARY_CLASSIFICATION,
            "confidence": "high",
            "signals": primary,
            "reason": "Document contains at least three core financial-statement sections",
        }
    if attachment_is_financial(name, source_url) and primary:
        return {
            "classification": PRIMARY_CLASSIFICATION,
            "confidence": "medium",
            "signals": primary + ["explicit_financial_filename"],
            "reason": "Financial-statement filename is supported by statement content",
        }

    filename_hint = _filename_nonreport_hint(name, source_url)
    if filename_hint and len(primary) < 3:
        return {
            "classification": REJECTED_CLASSIFICATION,
            "confidence": "medium",
            "signals": primary + [filename_hint],
            "reason": (
                "Filename indicates release/presentation and core statement content is absent"
            ),
        }
    return {
        "classification": REVIEW_CLASSIFICATION,
        "confidence": "low",
        "signals": primary,
        "reason": "Content does not meet a deterministic financial-document rule",
    }


def classify_attachment_suite(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Classify an announcement package, resolving unreadable non-report filename hints safely."""
    results = [classify_attachment(item) for item in items]
    has_primary = any(result["classification"] == PRIMARY_CLASSIFICATION for result in results)
    if not has_primary:
        return results
    for item, result in zip(items, results, strict=True):
        if result["classification"] != REVIEW_CLASSIFICATION:
            continue
        hint = _filename_nonreport_hint(str(item.get("name", "")), str(item.get("source_url", "")))
        if not hint:
            continue
        result.update(
            {
                "classification": REJECTED_CLASSIFICATION,
                "confidence": "medium",
                "signals": [hint, "primary_statement_present_in_same_announcement"],
                "reason": (
                    "Unreadable attachment has a release/presentation filename and the "
                    "announcement separately contains a proven primary statement"
                ),
            }
        )
    return results


def listing_is_target_report(task: dict[str, str]) -> bool:
    title = task.get("main_title", "").casefold()
    return "financial statements" in title and "notification of results release" not in title


def next_collection_date(manifest: list[dict[str, Any]], requested: date) -> date:
    dates = []
    for item in manifest:
        raw = item.get("published_date")
        if isinstance(raw, str):
            try:
                dates.append(date.fromisoformat(raw))
            except ValueError:
                continue
    if not dates:
        return requested
    # When the user expands the historical window, query from the newly requested
    # earlier date. Existing announcements are skipped by stable SGX source ID before
    # opening detail pages or downloading attachments.
    if requested < min(dates):
        return requested
    return max(requested, max(dates) + timedelta(days=1))


def read_manifest_document(path: Path) -> dict[str, Any]:
    """Read the valid JSON manifest, migrating the prior JSONL format if present."""
    legacy_path = path.with_suffix(".jsonl")
    source = path if path.exists() else legacy_path
    if not source.exists():
        return {"schema_version": 2, "records": []}
    payload = json.loads(source.read_text(encoding="utf-8")) if source == path else None
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        payload["records"] = [item for item in payload["records"] if isinstance(item, dict)]
        return payload
    if isinstance(payload, list):
        return {
            "schema_version": 2,
            "records": [item for item in payload if isinstance(item, dict)],
        }
    if source == path:
        raise ValueError(f"manifest must contain a JSON object with records: {path}")
    records: list[dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                records.append(value)
    return {"schema_version": 2, "records": records}


def read_manifest(path: Path) -> list[dict[str, Any]]:
    return read_manifest_document(path)["records"]


def write_manifest(
    path: Path,
    records: list[dict[str, Any]],
    *,
    queried_date_range: dict[str, str] | None = None,
    last_collection: dict[str, Any] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "updated_at": datetime.now().astimezone().isoformat(),
                "queried_date_range": queried_date_range,
                "last_collection": last_collection,
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def merge_queried_date_range(
    existing: Any, requested_from: date, requested_to: date
) -> dict[str, str]:
    starts = [requested_from]
    ends = [requested_to]
    if isinstance(existing, dict):
        try:
            starts.append(date.fromisoformat(existing["from_date"]))
            ends.append(date.fromisoformat(existing["to_date"]))
        except (KeyError, TypeError, ValueError):
            pass
    return {"from_date": min(starts).isoformat(), "to_date": max(ends).isoformat()}


def _debug(args: argparse.Namespace, message: str) -> None:
    if args.debug:
        print(f"[financials] {message}", file=sys.stderr, flush=True)


def flatten_attachment_paths(
    attachments: list[dict[str, Any]], year_dir: Path, source_id: str
) -> list[dict[str, Any]]:
    """Move cached files out of the extractor's source-ID staging directory."""
    staging_dir = year_dir / "attachments" / source_id
    for item in attachments:
        local = item.get("local_path")
        if not isinstance(local, str):
            continue
        staged_path = Path(local)
        final_path = year_dir / staged_path.name
        final_path.parent.mkdir(parents=True, exist_ok=True)
        if staged_path.exists() and staged_path != final_path:
            shutil.move(str(staged_path), str(final_path))
        item["local_path"] = final_path.as_posix()
        item["url"] = final_path.as_posix()
        extraction = item.get("text_extraction")
        if isinstance(extraction, dict) and isinstance(extraction.get("text_path"), str):
            staged_text = Path(extraction["text_path"])
            final_text = year_dir / staged_text.name
            if staged_text.exists() and staged_text != final_text:
                shutil.move(str(staged_text), str(final_text))
            extraction["text_path"] = final_text.as_posix()
    if staging_dir.exists() and not any(staging_dir.iterdir()):
        staging_dir.rmdir()
    attachments_dir = year_dir / "attachments"
    if attachments_dir.exists() and not any(attachments_dir.iterdir()):
        attachments_dir.rmdir()
    return attachments


def _assert_staged_path(path: Path, staging_dir: Path) -> None:
    try:
        path.resolve().relative_to(staging_dir.resolve())
    except ValueError as exc:
        message = f"refusing to modify attachment outside staging directory: {path}"
        raise ValueError(message) from exc


def _unique_destination(source: Path, target_dir: Path, prefix: str) -> Path:
    candidate = target_dir / f"{prefix}_{source.name}"
    if not candidate.exists():
        return candidate
    counter = 2
    while True:
        candidate = target_dir / f"{prefix}_{source.stem}_{counter}{source.suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def relocate_attachment_files(
    item: dict[str, Any], staging_dir: Path, target_dir: Path, prefix: str
) -> dict[str, Any]:
    """Move a cached attachment and extracted text to an archive/review directory."""
    target_dir.mkdir(parents=True, exist_ok=True)
    local = item.get("local_path")
    if not isinstance(local, str):
        return item
    source = Path(local)
    _assert_staged_path(source, staging_dir)
    destination = _unique_destination(source, target_dir, prefix)
    if source.exists():
        shutil.move(str(source), str(destination))
    item["local_path"] = destination.as_posix()
    item["url"] = destination.as_posix()

    extraction = item.get("text_extraction")
    if isinstance(extraction, dict) and isinstance(extraction.get("text_path"), str):
        text_source = Path(extraction["text_path"])
        _assert_staged_path(text_source, staging_dir)
        text_destination = destination.with_suffix(".txt")
        if text_source.exists():
            shutil.move(str(text_source), str(text_destination))
        extraction["text_path"] = text_destination.as_posix()
    item["retained"] = True
    return item


def discard_staged_attachment(item: dict[str, Any], staging_dir: Path) -> dict[str, Any]:
    """Delete a confirmed non-report only from the source-specific staging directory."""
    paths: list[Path] = []
    local = item.get("local_path")
    if isinstance(local, str):
        paths.append(Path(local))
    extraction = item.get("text_extraction")
    if isinstance(extraction, dict) and isinstance(extraction.get("text_path"), str):
        paths.append(Path(extraction["text_path"]))
    for path in paths:
        _assert_staged_path(path, staging_dir)
        if path.is_file():
            path.unlink()
    item.pop("local_path", None)
    item["url"] = item.get("source_url", "")
    if isinstance(extraction, dict):
        extraction.pop("text_path", None)
    item["retained"] = False
    return item


def cleanup_staging_directories(staging_dir: Path, attachments_dir: Path) -> None:
    for directory in (staging_dir, attachments_dir):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True, help="SGX universe symbol, for example BN4")
    parser.add_argument("--from-date", required=True, help="inclusive YYYYMMDD start date")
    parser.add_argument("--to-date", help="inclusive YYYYMMDD end date; defaults to today")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--filters", type=Path, default=DEFAULT_FILTERS)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--pacing-seconds", type=float, default=0.5)
    parser.add_argument("--show-browser", action="store_true")
    parser.add_argument("--debug", action="store_true", help="print collection progress to stderr")
    return parser


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError(f"invalid date {value!r}; expected YYYYMMDD") from exc


def collect(args: argparse.Namespace, extractor: Any | None = None) -> dict[str, Any]:
    extractor = extractor or _load_extractor()
    symbol = args.symbol.strip().upper()
    requested_from = _parse_date(args.from_date)
    requested_to = _parse_date(args.to_date) if args.to_date else date.today()
    if requested_to < requested_from:
        raise ValueError("--to-date must not be earlier than --from-date")
    policy = extractor.load_filter_policy(args.filters)
    mapping = policy.mappings.get(symbol)
    if mapping is None:
        raise ValueError(f"no authoritative SGX mapping for symbol {symbol}")

    symbol_dir = args.output_root / symbol.casefold()
    symbol_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = symbol_dir / "manifest.json"
    manifest_document = read_manifest_document(manifest_path)
    manifest = manifest_document["records"]
    from_date = next_collection_date(manifest, requested_from)
    existing_ids = {item.get("source_id") for item in manifest}
    _debug(args, f"mapping: {symbol} -> {mapping.filter_value} ({mapping.filter_type})")
    _debug(args, f"date window: {from_date} to {requested_to}; existing records: {len(manifest)}")
    manifest_dates = []
    for item in manifest:
        if isinstance(item.get("published_date"), str):
            try:
                manifest_dates.append(date.fromisoformat(item["published_date"]))
            except ValueError:
                continue
    if manifest_dates and requested_from < min(manifest_dates):
        _debug(
            args,
            "historical range expanded; existing source IDs will be skipped before download",
        )
    if from_date > requested_to:
        result = {
            "status": "success",
            "symbol": symbol,
            "from_date": from_date.isoformat(),
            "to_date": requested_to.isoformat(),
            "announcements_found": 0,
            "announcements_downloaded": 0,
            "attachments_downloaded": 0,
            "attachments_archived": 0,
            "primary_financial_statements": 0,
            "supplementary_financial_analysis": 0,
            "rejected_non_reports": 0,
            "needs_review": 0,
            "skipped_existing": 0,
            "message": "manifest is already current for the requested date range",
        }
        queried_range = merge_queried_date_range(
            manifest_document.get("queried_date_range"), requested_from, requested_to
        )
        write_manifest(
            manifest_path,
            manifest,
            queried_date_range=queried_range,
            last_collection={
                **result,
                "requested_from_date": requested_from.isoformat(),
                "requested_to_date": requested_to.isoformat(),
                "completed_at": datetime.now().astimezone().isoformat(),
            },
        )
        return result

    active_categories = {"ANNC": ("ANNC17",)}
    tasks_by_id: dict[str, dict[str, str]] = {}
    failures: list[dict[str, Any]] = []
    requests_attempted = 0
    filter_mismatch = False
    skipped_existing_count = 0
    attachments_downloaded_count = 0
    announcements_without_attachments = 0
    classification_counts = {
        PRIMARY_CLASSIFICATION: 0,
        SUPPLEMENTARY_CLASSIFICATION: 0,
        REJECTED_CLASSIFICATION: 0,
        REVIEW_CLASSIFICATION: 0,
    }
    extractor.SGX_BASE_URL = policy.base_url.rsplit("/stock-exchange", 1)[0]
    with sync_playwright() as playwright:
        browser = playwright.firefox.launch(
            headless=not args.show_browser,
            executable_path=playwright.firefox.executable_path,
        )
        page = browser.new_page()
        try:
            for page_number in range(1, args.max_pages + 1):
                list_url = extractor.build_list_url(
                    page_number,
                    policy.page_size,
                    mapping=mapping,
                    from_date=from_date,
                    to_date=requested_to,
                    category_groups=active_categories,
                    base_url=policy.base_url,
                )
                requests_attempted += 1
                _debug(args, f"listing page {page_number}: {list_url}")
                tasks = extractor._listing_tasks(page, list_url)
                _debug(args, f"listing page {page_number}: {len(tasks)} rows returned")
                target_rows = [
                    task for task in tasks if extractor.task_matches_target(task, mapping)
                ]
                matched = [
                    task
                    for task in target_rows
                    if extractor.task_is_in_range(task, from_date, requested_to)
                    and listing_is_target_report(task)
                ]
                if page_number == 1 and tasks and not target_rows:
                    filter_mismatch = True
                    message = (
                        "SGX returned listing rows but none matched the exact target mapping; "
                        "the selected filter may not have been applied"
                    )
                    failures.append(
                        {
                            "symbol": symbol,
                            "stage": "listing_filter",
                            "error": message,
                            "url": list_url,
                        }
                    )
                    _debug(args, message)
                    break
                _debug(args, f"listing page {page_number}: {len(matched)} target financial rows")
                for task in matched:
                    source_id = extractor.announcement_url_id(
                        extractor.canonical_announcement_url(task["source_url"])
                    )
                    if source_id:
                        tasks_by_id.setdefault(source_id, task)
                if len(matched) < policy.page_size:
                    break
                time.sleep(args.pacing_seconds)

            request_context = page.context.request
            for source_id, task in tasks_by_id.items():
                if source_id in existing_ids:
                    skipped_existing_count += 1
                    _debug(args, f"skip existing source {source_id}")
                    continue
                source_url = extractor.canonical_announcement_url(task["source_url"])
                requests_attempted += 1
                try:
                    _debug(args, f"open {source_id}: {task['main_title']}")
                    extractor._navigate(page, source_url)
                    page.wait_for_selector("div.announcement", timeout=15_000)
                    announcement = page.query_selector("div.announcement")
                    if announcement is None:
                        raise ValueError("announcement detail container was not found")
                    soup = BeautifulSoup(announcement.inner_html(), "html.parser")
                    raw_attachments = extractor.extract_attachments(soup, source_url)
                    published_date = extractor.parse_published_at(task["raw_dt"]).date()
                    year_dir = symbol_dir / str(published_date.year)
                    if not raw_attachments:
                        announcements_without_attachments += 1
                        manifest.append(
                            {
                                "symbol": symbol,
                                "source_id": source_id,
                                "title": task["main_title"],
                                "category": task["category"],
                                "published_date": published_date.isoformat(),
                                "announcement_url": source_url,
                                "attachments": [],
                                "attachment_decisions": [],
                                "processing_status": "needs_review_no_attachments",
                                "retrieved_at": datetime.now(extractor.SGT).isoformat(),
                            }
                        )
                        _debug(args, f"{source_id}: no attachments found; recorded for review")
                        continue
                    _debug(args, f"{source_id}: staging {len(raw_attachments)} attachment(s)")
                    cached, attachment_failures = extractor.cache_attachments(
                        raw_attachments,
                        source_id,
                        year_dir,
                        request_context,
                        source_url,
                    )
                    if attachment_failures:
                        raise ValueError(f"attachment failures: {attachment_failures}")
                    attachments_downloaded_count += len(cached)
                    staging_dir = year_dir / "attachments" / source_id
                    archived: list[dict[str, Any]] = []
                    decisions: list[dict[str, Any]] = []
                    suite_classifications = classify_attachment_suite(cached)
                    for item, classification in zip(cached, suite_classifications, strict=True):
                        item.update(classification)
                        classification_name = classification["classification"]
                        classification_counts[classification_name] += 1
                        if classification_name in ARCHIVED_CLASSIFICATIONS:
                            item = relocate_attachment_files(
                                item,
                                staging_dir,
                                year_dir,
                                f"{published_date.isoformat()}_{source_id}",
                            )
                            archived.append(item)
                        elif classification_name == REVIEW_CLASSIFICATION:
                            item = relocate_attachment_files(
                                item,
                                staging_dir,
                                symbol_dir / "_review" / str(published_date.year) / source_id,
                                published_date.isoformat(),
                            )
                        else:
                            item = discard_staged_attachment(item, staging_dir)
                        decisions.append(item)
                        _debug(
                            args,
                            f"{source_id}: {item['name']} -> {classification_name} "
                            f"({classification['confidence']})",
                        )
                    cleanup_staging_directories(staging_dir, year_dir / "attachments")
                    published_date_text = published_date.isoformat()
                    manifest.append(
                        {
                            "symbol": symbol,
                            "source_id": source_id,
                            "title": task["main_title"],
                            "category": task["category"],
                            "published_date": published_date_text,
                            "announcement_url": source_url,
                            "attachments": archived,
                            "attachment_decisions": decisions,
                            "processing_status": (
                                "archived" if archived else "processed_no_archived_report"
                            ),
                            "retrieved_at": datetime.now(extractor.SGT).isoformat(),
                        }
                    )
                    _debug(
                        args,
                        f"{source_id}: archived {len(archived)} of {len(cached)} attachment(s)",
                    )
                except Exception as exc:  # noqa: BLE001 - preserve per-document failures
                    _debug(args, f"{source_id}: FAILED: {type(exc).__name__}: {exc}")
                    failures.append(
                        {
                            "symbol": symbol,
                            "source_id": source_id,
                            "title": task.get("main_title", ""),
                            "stage": "detail_or_attachment",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                time.sleep(args.pacing_seconds)
        finally:
            browser.close()

    failure_path = symbol_dir / "failures.jsonl"
    failure_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in failures),
        encoding="utf-8",
    )
    archived_count = (
        classification_counts[PRIMARY_CLASSIFICATION]
        + classification_counts[SUPPLEMENTARY_CLASSIFICATION]
    )
    result = {
        "status": "success" if not failures else "partial_failure",
        "symbol": symbol,
        "from_date": from_date.isoformat(),
        "to_date": requested_to.isoformat(),
        "announcements_found": len(tasks_by_id),
        "announcements_downloaded": len(manifest) - len(existing_ids),
        "attachments_downloaded": attachments_downloaded_count,
        "attachments_archived": archived_count,
        "primary_financial_statements": classification_counts[PRIMARY_CLASSIFICATION],
        "supplementary_financial_analysis": classification_counts[SUPPLEMENTARY_CLASSIFICATION],
        "rejected_non_reports": classification_counts[REJECTED_CLASSIFICATION],
        "needs_review": classification_counts[REVIEW_CLASSIFICATION],
        "announcements_without_attachments": announcements_without_attachments,
        "skipped_existing": skipped_existing_count,
        "requests_attempted": requests_attempted,
        "failures": len(failures),
        "filter_mismatch": filter_mismatch,
        "manifest": manifest_path.as_posix(),
        "failure_log": failure_path.as_posix(),
    }
    queried_range = manifest_document.get("queried_date_range")
    if not failures:
        queried_range = merge_queried_date_range(queried_range, requested_from, requested_to)
    write_manifest(
        manifest_path,
        manifest,
        queried_date_range=queried_range,
        last_collection={
            **result,
            "requested_from_date": requested_from.isoformat(),
            "requested_to_date": requested_to.isoformat(),
            "completed_at": datetime.now().astimezone().isoformat(),
        },
    )
    return result


def main() -> int:
    try:
        result = collect(_parser().parse_args())
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
