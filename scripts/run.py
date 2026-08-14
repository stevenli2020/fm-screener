"""Extract SGX corporate announcements into machine and human-readable artifacts."""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urljoin, urlparse, urlunparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from financial_market.research.announcement_content import (
    cache_attachments,
    compact_announcement_sections,
    compute_content_hash,
    extract_attachment_links,
    extract_page_data,
    normalize_event,
)

SGT = ZoneInfo("Asia/Singapore")
SGX_BASE_URL = "https://www.sgx.com"
SGX_LIST_URL = "https://www.sgx.com/stock-exchange/company-announcements"
SCHEMA_VERSION = 1
DEFAULT_FILTERS_PATH = Path(__file__).with_name("sgx_announcement_filters.json")


@dataclass(frozen=True, slots=True)
class TargetMapping:
    symbol: str
    filter_value: str
    filter_type: str


@dataclass(frozen=True, slots=True)
class FilterPolicy:
    base_url: str
    page_size: int
    kept_categories: dict[str, tuple[str, ...]]
    mappings: dict[str, TargetMapping]


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    records: tuple[dict[str, Any], ...]
    failures: tuple[dict[str, Any], ...]
    requests_attempted: int
    requests_succeeded: int
    unresolved_symbols: tuple[str, ...]


def load_filter_policy(path: Path = DEFAULT_FILTERS_PATH) -> FilterPolicy:
    """Load and validate the authoritative category policy and symbol mapping."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load SGX announcement filters: {path}") from exc
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported SGX announcement filter schema")
    groups = payload.get("category_groups")
    raw_mappings = payload.get("universe_mappings")
    if not isinstance(groups, dict) or not isinstance(raw_mappings, list):
        raise ValueError("SGX announcement filters have an invalid structure")
    kept: dict[str, tuple[str, ...]] = {}
    for group in ("ANNC", "CACT", "PLST", "TRAD"):
        values = groups.get(group)
        if not isinstance(values, list):
            raise ValueError(f"category group {group} must be a list")
        kept[group] = tuple(
            item["code"]
            for item in values
            if isinstance(item, dict) and str(item.get("policy", "")).startswith("keep")
        )
    mappings: dict[str, TargetMapping] = {}
    for item in raw_mappings:
        if not isinstance(item, dict):
            raise ValueError("every SGX universe mapping must be an object")
        symbol = str(item.get("symbol", "")).strip().upper()
        filter_value = str(item.get("sgx_filter_value", "")).strip()
        filter_type = str(item.get("sgx_filter_type", "")).strip()
        if not symbol or not filter_value or filter_type not in {"company", "security"}:
            raise ValueError(f"invalid SGX universe mapping for {symbol or 'UNKNOWN'}")
        if symbol in mappings:
            raise ValueError(f"duplicate SGX universe mapping: {symbol}")
        mappings[symbol] = TargetMapping(symbol, filter_value, filter_type)
    protocol = payload.get("url_protocol", {})
    page_size = protocol.get("default_page_size", 100)
    base_url = payload.get("base_url")
    if not isinstance(page_size, int) or not 1 <= page_size <= 100:
        raise ValueError("default_page_size must be between 1 and 100")
    if not isinstance(base_url, str) or not base_url.startswith("https://"):
        raise ValueError("base_url must be an HTTPS URL")
    return FilterPolicy(base_url, page_size, kept, mappings)


def load_target_symbols(candidate_path: Path | None, symbols: list[str] | None) -> tuple[str, ...]:
    """Combine explicit symbols and M3 candidates while preserving first-seen order."""
    values = list(symbols or [])
    if candidate_path is not None:
        try:
            payload = json.loads(candidate_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot load candidate file: {candidate_path}") from exc
        candidates = payload.get("ranked_candidates") if isinstance(payload, dict) else None
        if not isinstance(candidates, list):
            raise ValueError("candidate file ranked_candidates must be a list")
        for item in candidates:
            if not isinstance(item, dict) or not isinstance(item.get("symbol"), str):
                raise ValueError("every candidate must have a symbol")
            values.append(item["symbol"])
    targets: list[str] = []
    for value in values:
        symbol = value.strip().upper()
        if symbol and symbol not in targets:
            targets.append(symbol)
    if not targets:
        raise ValueError("at least one target symbol is required")
    return tuple(targets)


def canonical_announcement_url(raw_url: str, base_url: str = SGX_BASE_URL) -> str:
    """Return the stable SGX announcement page URL without its listing asset suffix."""
    if not raw_url:
        return ""
    full_url = urljoin(base_url, raw_url)
    parsed = urlparse(full_url)
    marker = "/corporate-announcements/"
    if marker not in parsed.path:
        return urlunparse(parsed._replace(query="", fragment=""))

    prefix, remainder = parsed.path.split(marker, maxsplit=1)
    announcement_id = remainder.strip("/").split("/", maxsplit=1)[0]
    stable_path = f"{prefix}{marker}{announcement_id}/"
    return urlunparse(parsed._replace(path=stable_path, query="", fragment=""))


# Keep the old name for callers that already import it.
clean_sgx_url = canonical_announcement_url


def announcement_url_id(url: str) -> str:
    """Extract the stable identifier embedded in an SGX corporate-announcement URL."""
    match = re.search(r"/corporate-announcements/([^/?#]+)", url)
    return match.group(1) if match else ""


def sanitize_filename_part(text: str, max_len: int = 80) -> str:
    """Remove path-unsafe characters, collapse whitespace, and truncate."""
    if not text:
        return ""
    text = re.sub(r'[\\/*?:"<>|\r\n\t]', " ", text)
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    return text[:max_len].strip().rstrip(".")


def parse_published_at(raw_dt: str) -> datetime:
    """Parse an SGX listing timestamp and attach the Singapore timezone."""
    formats = (
        "%d %b %Y %I:%M %p",
        "%d-%b-%Y %I:%M %p",
        "%d %b %Y %H:%M:%S",
        "%d-%b-%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    )
    clean_value = re.sub(r"\s+", " ", raw_dt.strip())
    for datetime_format in formats:
        try:
            return datetime.strptime(clean_value, datetime_format).replace(tzinfo=SGT)
        except ValueError:
            continue
    raise ValueError(f"Unsupported SGX publication timestamp: {raw_dt!r}")


def parse_datetime_to_yymmddhhmmss(raw_dt: str) -> str:
    """Compatibility helper returning the timestamp used in artifact filenames."""
    return parse_published_at(raw_dt).strftime("%y%m%d%H%M%S")


def extract_securities_from_detail_soup(soup: BeautifulSoup) -> str:
    """Find the Security/Securities metadata field inside announcement HTML."""
    for label in soup.find_all(["dt", "th", "td", "span", "div"]):
        label_text = label.get_text(strip=True).replace(":", "").strip()
        if label_text not in {"Security", "Securities"}:
            continue

        value_node = label.find_next_sibling(["dd", "td", "span", "div"])
        if value_node:
            value_text = value_node.get_text(separator="\n").strip()
            if value_text and len(value_text) < 1000:
                return value_text

        parent = label.find_parent("tr")
        if parent:
            cells = parent.find_all(["th", "td"])
            if len(cells) >= 2 and label_text in cells[0].get_text():
                return cells[1].get_text(separator="\n").strip()
    return ""


def extract_ticker_symbol_list(securities_text: str) -> list[str]:
    """Extract unique ticker symbols from SGX detail-page security lines."""
    if not securities_text:
        return []

    symbols: list[str] = []
    for line in re.split(r"[\r\n]+", securities_text):
        cleaned_line = re.sub(r"\s+", " ", line).strip()
        if "-" not in cleaned_line:
            continue
        candidate = cleaned_line.rsplit("-", maxsplit=1)[-1].strip()
        token = re.sub(r"[^A-Za-z0-9]", "", candidate).upper()
        if 2 <= len(token) <= 10 and not token.isdigit() and token not in symbols:
            symbols.append(token)
    return symbols[:5]


def extract_ticker_symbols(securities_text: str) -> str:
    """Compatibility helper returning comma-separated symbols or UNKNOWN."""
    symbols = extract_ticker_symbol_list(securities_text)
    return ",".join(symbols) if symbols else "UNKNOWN"


def parse_value_node(node: Any, base_url: str) -> str:
    """Extract text from an HTML node while preserving links and line breaks."""
    node = BeautifulSoup(str(node), "html.parser")
    for anchor in node.find_all("a"):
        href = anchor.get("href", "")
        if href:
            absolute_url = urljoin(base_url, href)
            link_text = anchor.get_text(strip=True) or "Link"
            anchor.replace_with(f"[{link_text}]({absolute_url})")

    for break_node in node.find_all("br"):
        break_node.replace_with("\n")
    for paragraph in node.find_all("p"):
        paragraph.insert_before("\n\n")
        paragraph.unwrap()

    text = node.get_text(separator="")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def extract_sgx_fields(soup: BeautifulSoup, base_url: str) -> dict[str, str]:
    """Parse SGX definition lists or tables into a key-value dictionary."""
    fields: dict[str, str] = {}
    for term in soup.find_all("dt"):
        label = term.get_text(strip=True).replace(":", "").strip()
        definition = term.find_next_sibling("dd")
        if definition:
            fields[label] = parse_value_node(definition, base_url)

    if not fields:
        for row in soup.find_all("tr"):
            heading = row.find(["th", "td"])
            value = heading.find_next_sibling("td") if heading else None
            if heading and value:
                label = heading.get_text(strip=True).replace(":", "").strip()
                if label:
                    fields[label] = parse_value_node(value, base_url)
    return fields


def extract_attachments(soup: BeautifulSoup, base_url: str) -> list[dict[str, str]]:
    """Extract unique downloadable announcement assets."""
    return extract_attachment_links(str(soup), base_url, announcement_url_id(base_url))


def pop_matching_field(fields: dict[str, str], *fragments: str) -> str:
    for fragment in fragments:
        for key in list(fields):
            if fragment.casefold() in key.casefold():
                return fields.pop(key)
    return ""


def normalize_record(
    task: dict[str, str], detail_html: str, retrieved_at: datetime
) -> dict[str, Any]:
    """Convert one listing row and detail page into the versioned ingestion contract."""
    published_at = parse_published_at(task["raw_dt"])
    source_url = canonical_announcement_url(task["source_url"])
    soup = BeautifulSoup(detail_html, "html.parser")
    attachments = extract_attachments(soup, source_url)
    fields = extract_sgx_fields(soup, source_url)
    page_data = extract_page_data(detail_html, source_url)
    announcement_sections = compact_announcement_sections(page_data)
    event_type, event_data = normalize_event(task["category"], page_data)

    detail_securities = extract_securities_from_detail_soup(soup)
    effective_securities = detail_securities or task["securities_text"]
    symbols = extract_ticker_symbol_list(effective_securities)

    status = pop_matching_field(fields, "Status") or "N/A"
    announcement_reference = pop_matching_field(fields, "Announcement Reference") or "N/A"
    submitted_by = pop_matching_field(fields, "Submitted By")
    designation = pop_matching_field(fields, "Designation")
    if designation:
        submitted_by = f"{submitted_by}, {designation}" if submitted_by else designation
    details = pop_matching_field(fields, "Description", "Event Narrative", "Additional Text")

    source_id = announcement_url_id(source_url)
    record = {
        "schema_version": SCHEMA_VERSION,
        "published_at": published_at.isoformat(),
        "symbols": symbols,
        "symbol_match_status": "resolved" if symbols else "unresolved",
        "issuer_name": task["issuer_name"],
        "security_name": task["security_name"],
        "title": task["main_title"],
        "category": task["category"],
        "status": status,
        "announcement_reference": announcement_reference,
        "source_id": source_id,
        "source_url": source_url,
        "listing_url": task["source_url"],
        "submitted_by": submitted_by or "N/A",
        "details": details,
        "announcement_sections": announcement_sections,
        "event_type": event_type,
        "event_data": event_data,
        "attachments": attachments,
        "retrieved_at": retrieved_at.astimezone(SGT).isoformat(),
        "source": "sgx_public_website",
    }
    record["content_hash"] = compute_content_hash(record)
    return record


def artifact_stem(record: dict[str, Any]) -> str:
    published_at = datetime.fromisoformat(record["published_at"])
    timestamp = published_at.strftime("%y%m%d%H%M%S")
    symbols = ",".join(record["symbols"]) if record["symbols"] else "UNKNOWN"
    stable_id = record["announcement_reference"]
    if stable_id == "N/A":
        stable_id = record["source_id"] or record["content_hash"][:16]
    title = sanitize_filename_part(record["title"], max_len=70) or "Untitled"
    stem = f"{timestamp}-{symbols}-{sanitize_filename_part(stable_id, 32)}-{title}"
    return stem[:190].rstrip(" .")


def render_markdown(record: dict[str, Any]) -> str:
    symbols = ", ".join(record["symbols"]) if record["symbols"] else "UNKNOWN"
    lines = [
        f"# {record['title']}",
        "",
        "## Issuer & Securities",
        f"**Ticker Symbol:** {symbols}",
        f"**Symbol Match Status:** {record['symbol_match_status']}",
        f"**Issuer:** {record['issuer_name']}",
        f"**Security:** {record['security_name']}",
        f"**Published At:** {record['published_at']}",
        f"**Category:** {record['category']}",
        f"**Source URL:** {record['source_url']}",
        "",
        "## Normalized Event Data",
        f"**Event Type:** {record.get('event_type', 'unclassified')}",
        "",
        "```json",
        json.dumps(record.get("event_data", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## Announcement Sections",
    ]
    for section, content in record.get("announcement_sections", {}).items():
        lines.extend(["", f"### {section}", "", content])
    if record["attachments"]:
        lines.extend(["", "## Attachments"])
        for attachment in record["attachments"]:
            if attachment.get("cache_status") == "cached":
                filename = Path(attachment["local_path"]).name
                local_link = f"../attachments/{record['source_id']}/{filename}"
                lines.append(
                    f"* [{attachment['name']}]({local_link}) "
                    f"([original SGX file]({attachment['source_url']}))"
                )
            else:
                lines.append(
                    f"* [{attachment['name']}]({attachment.get('source_url', '')}) "
                    f"(cache failed: {attachment.get('error', 'unknown error')})"
                )
    lines.extend(
        [
            "",
            "## Provenance",
            f"**Source ID:** {record['source_id'] or 'N/A'}",
            f"**Retrieved At:** {record['retrieved_at']}",
            f"**Content Hash:** {record['content_hash']}",
            "",
        ]
    )
    return "\n".join(lines)


def write_record(record: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    """Write one idempotently named Markdown/JSON artifact pair."""
    records_dir = output_dir / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    stem = artifact_stem(record)
    markdown_path = records_dir / f"{stem}.md"
    json_path = records_dir / f"{stem}.json"
    markdown_path.write_text(render_markdown(record), encoding="utf-8")
    json_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return markdown_path, json_path


def parse_cli_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def build_list_url(
    page_number: int,
    page_size: int,
    *,
    mapping: TargetMapping | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    category_groups: dict[str, tuple[str, ...]] | None = None,
    base_url: str = SGX_LIST_URL,
) -> str:
    """Build a targeted SGX listing URL with stable parameter and category order."""
    params: list[tuple[str, str | int]] = [("pagesize", page_size)]
    if page_number > 1:
        params.append(("page", page_number))
    if mapping:
        params.extend((("value", mapping.filter_value), ("type", mapping.filter_type)))
    if from_date:
        params.append(("from", from_date.strftime("%Y%m%d")))
    if to_date:
        params.append(("to", to_date.strftime("%Y%m%d")))
    for group in ("ANNC", "CACT", "PLST", "TRAD"):
        codes = (category_groups or {}).get(group, ())
        if codes:
            params.append((group, ",".join(codes)))
    return f"{base_url}?{urlencode(params, quote_via=quote)}"


def listing_task_from_row(row: Any) -> dict[str, str] | None:
    columns = row.query_selector_all("td")
    if len(columns) < 5:
        return None
    title_element = columns[3].query_selector("a")
    source_url = title_element.get_attribute("href") if title_element else ""
    return {
        "raw_dt": columns[0].inner_text().strip(),
        "issuer_name": re.sub(r"\s+", " ", columns[1].inner_text()).strip(),
        "security_name": re.sub(r"\s+", " ", columns[2].inner_text()).strip(),
        "securities_text": columns[2].inner_text().strip(),
        "main_title": (
            title_element.inner_text().strip() if title_element else columns[3].inner_text().strip()
        ),
        "category": re.sub(r"\s+", " ", columns[4].inner_text()).strip(),
        "source_url": urljoin(SGX_BASE_URL, source_url),
    }


def task_is_in_range(task: dict[str, str], from_date: date | None, to_date: date | None) -> bool:
    published_date = parse_published_at(task["raw_dt"]).date()
    before_range = from_date and published_date < from_date
    after_range = to_date and published_date > to_date
    return not (before_range or after_range)


def task_matches_target(task: dict[str, str], mapping: TargetMapping) -> bool:
    """Reject leaked listing rows that do not belong to the targeted SGX identity."""
    haystack = f"{task['issuer_name']} {task['security_name']}".casefold()
    return mapping.filter_value.casefold() in haystack


def _navigate(page: Any, url: str, *, attempts: int = 2) -> None:
    """Navigate without allowing a failed request to expose a previous page's DOM."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            page.goto("about:blank", wait_until="domcontentloaded", timeout=10_000)
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            return
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(float(attempt))
    assert last_error is not None
    raise last_error


def _listing_tasks(page: Any, list_url: str) -> list[dict[str, str]]:
    _navigate(page, list_url)
    try:
        page.wait_for_selector("table tbody tr", timeout=15_000)
    except Exception as exc:
        rows = page.query_selector_all("table tbody tr")
        if rows:
            return [task for row in rows if (task := listing_task_from_row(row)) is not None]
        table = page.query_selector("table")
        body = page.query_selector("body")
        body_text = body.inner_text().strip() if body else ""
        explicit_empty = any(
            marker in body_text.casefold()
            for marker in ("showing 0 to 0 of 0 records", "no data to display", "no records found")
        )
        if table is not None and explicit_empty:
            return []
        diagnostic = re.sub(r"\s+", " ", body_text)[:300] or "empty response body"
        error_type = PermissionError if "access denied" in diagnostic.casefold() else ValueError
        raise error_type(f"SGX listing table did not render: {diagnostic}") from exc
    return [
        task
        for row in page.query_selector_all("table tbody tr")
        if (task := listing_task_from_row(row)) is not None
    ]


def probe_category_semantics(
    mapping: TargetMapping,
    from_date: date,
    to_date: date,
    policy: FilterPolicy,
    *,
    headless: bool = True,
) -> dict[str, Any]:
    """Compare combined category groups with separate requests using stable source IDs."""
    active = {key: value for key, value in policy.kept_categories.items() if value}
    with sync_playwright() as playwright:
        browser = playwright.firefox.launch(
            headless=headless, executable_path=playwright.firefox.executable_path
        )
        page = browser.new_page()

        def ids(groups: dict[str, tuple[str, ...]]) -> set[str]:
            url = build_list_url(
                1,
                policy.page_size,
                mapping=mapping,
                from_date=from_date,
                to_date=to_date,
                category_groups=groups,
                base_url=policy.base_url,
            )
            return {
                announcement_url_id(canonical_announcement_url(task["source_url"]))
                for task in _listing_tasks(page, url)
                if task_matches_target(task, mapping)
            }

        unfiltered = ids({})
        combined = ids(active)
        separate_by_group = {group: ids({group: codes}) for group, codes in active.items()}
        browser.close()
    separate_union = set().union(*separate_by_group.values()) if separate_by_group else set()
    return {
        "unfiltered_ids": sorted(unfiltered),
        "combined_ids": sorted(combined),
        "separate_ids": {key: sorted(value) for key, value in separate_by_group.items()},
        "separate_union_ids": sorted(separate_union),
        "semantics": (
            "inconclusive_no_results"
            if not unfiltered and not separate_union
            else "union"
            if combined == separate_union
            else "not_union_use_separate_requests"
        ),
    }


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def extract_targeted(
    output_dir: Path,
    symbols: tuple[str, ...],
    *,
    policy: FilterPolicy,
    from_date: date,
    to_date: date,
    max_pages: int = 10,
    headless: bool = True,
    request_pacing_seconds: float = 0.5,
) -> ExtractionResult:
    """Extract only mapped targets over a short inclusive window.

    Kept category groups are combined in one request. Live verification on 2026-08-13
    showed combined groups equal the union of separate group requests by stable source ID.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    mappings = [policy.mappings[symbol] for symbol in symbols if symbol in policy.mappings]
    unresolved = tuple(symbol for symbol in symbols if symbol not in policy.mappings)
    failures: list[dict[str, Any]] = [
        {
            "stage": "mapping",
            "symbol": symbol,
            "error": "no authoritative SGX mapping",
            "recorded_at": datetime.now(SGT).isoformat(),
        }
        for symbol in unresolved
    ]
    tasks_by_id: dict[str, tuple[TargetMapping, dict[str, str]]] = {}
    requests_attempted = 0
    requests_succeeded = 0
    active_groups = {group: codes for group, codes in policy.kept_categories.items() if codes}
    abort_all = False
    with sync_playwright() as playwright:
        browser = playwright.firefox.launch(
            headless=headless, executable_path=playwright.firefox.executable_path
        )
        page = browser.new_page()
        for mapping in mappings:
            target_page_ids: set[str] = set()
            for page_number in range(1, max_pages + 1):
                list_url = build_list_url(
                    page_number,
                    policy.page_size,
                    mapping=mapping,
                    from_date=from_date,
                    to_date=to_date,
                    category_groups=active_groups,
                    base_url=policy.base_url,
                )
                requests_attempted += 1
                try:
                    page_tasks = _listing_tasks(page, list_url)
                    requests_succeeded += 1
                except Exception as exc:
                    failures.append(
                        {
                            "stage": "listing",
                            "symbol": mapping.symbol,
                            "category_group": "combined_union",
                            "page": page_number,
                            "url": list_url,
                            "error": str(exc),
                            "recorded_at": datetime.now(SGT).isoformat(),
                        }
                    )
                    if isinstance(exc, PermissionError):
                        abort_all = True
                    break
                matched_tasks = [
                    task
                    for task in page_tasks
                    if task_matches_target(task, mapping)
                    and task_is_in_range(task, from_date, to_date)
                ]
                page_ids = {
                    source_id
                    for task in matched_tasks
                    if (
                        source_id := announcement_url_id(
                            canonical_announcement_url(task["source_url"])
                        )
                    )
                }
                # SGX can ignore an unsupported page number and return page 1 again.
                # Stop before a repeated result set turns one targeted query into a
                # needless sequence of identical requests.
                if page_number > 1 and page_ids and page_ids <= target_page_ids:
                    break
                for task in matched_tasks:
                    source_id = announcement_url_id(canonical_announcement_url(task["source_url"]))
                    if source_id:
                        tasks_by_id.setdefault(source_id, (mapping, task))
                target_page_ids.update(page_ids)
                # Pagination is based on target-relevant rows. A full page of leaked/global
                # rows must not trigger an accidental broad crawl.
                if len(matched_tasks) < policy.page_size:
                    break
                time.sleep(request_pacing_seconds)
            time.sleep(request_pacing_seconds)
            if abort_all:
                break

        detail_page = browser.new_page()
        records: list[dict[str, Any]] = []
        for source_id, (mapping, task) in tasks_by_id.items():
            source_url = canonical_announcement_url(task["source_url"])
            requests_attempted += 1
            try:
                _navigate(detail_page, source_url)
                detail_page.wait_for_selector("div.announcement", timeout=15_000)
                announcement_div = detail_page.query_selector("div.announcement")
                if announcement_div is None:
                    raise ValueError("announcement detail container was not found")
                record = normalize_record(task, announcement_div.inner_html(), datetime.now(SGT))
                if mapping.symbol not in record["symbols"]:
                    raise ValueError(
                        f"detail symbols {record['symbols']} do not include target {mapping.symbol}"
                    )
                record["target_symbol"] = mapping.symbol
                raw_attachments = record["attachments"]
                requests_attempted += len(raw_attachments)
                cached_attachments, attachment_failures = cache_attachments(
                    raw_attachments,
                    source_id,
                    output_dir,
                    detail_page.context.request,
                    source_url,
                )
                record["attachments"] = cached_attachments
                record["content_hash"] = compute_content_hash(record)
                requests_succeeded += 1
                requests_succeeded += sum(
                    item.get("cache_status") == "cached" for item in cached_attachments
                )
                failures.extend(
                    {
                        "stage": "attachment",
                        "symbol": mapping.symbol,
                        "source_id": source_id,
                        "source_url": failure["source_url"],
                        "error": failure["error"],
                        "recorded_at": datetime.now(SGT).isoformat(),
                    }
                    for failure in attachment_failures
                )
                # Do not let a partial attachment response replace a previously
                # complete authoritative record in SQLite or the M5 feed. The failure
                # remains durable and the next collection can retry the whole record.
                if not attachment_failures:
                    write_record(record, output_dir)
                    records.append(record)
            except Exception as exc:
                failures.append(
                    {
                        "stage": "detail",
                        "symbol": mapping.symbol,
                        "source_id": source_id,
                        "source_url": source_url,
                        "error": str(exc),
                        "recorded_at": datetime.now(SGT).isoformat(),
                    }
                )
            time.sleep(request_pacing_seconds)
        browser.close()

    records.sort(key=lambda item: (item["published_at"], item["source_id"]))
    manifest_path = output_dir / "manifest.jsonl"
    manifest_path.write_text(
        "".join(
            json.dumps(
                {
                    "source_id": record["source_id"],
                    "symbols": record["symbols"],
                    "title": record["title"],
                    "published_at": record["published_at"],
                    "content_hash": record["content_hash"],
                    "attachment_count": len(record["attachments"]),
                    "record_stem": artifact_stem(record),
                },
                ensure_ascii=False,
            )
            + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    failure_path = output_dir / "extraction_failures.jsonl"
    failure_path.write_text(
        "".join(json.dumps(failure, ensure_ascii=False) + "\n" for failure in failures),
        encoding="utf-8",
    )
    summary = {
        "schema_version": SCHEMA_VERSION,
        "completed_at": datetime.now(SGT).isoformat(),
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "target_symbols": list(symbols),
        "mapped_targets": len(mappings),
        "unresolved_symbols": list(unresolved),
        "category_request_mode": "combined_groups_verified_union",
        "pages_per_target_group_limit": max_pages,
        "requests_attempted": requests_attempted,
        "requests_succeeded": requests_succeeded,
        "announcements_selected": len(tasks_by_id),
        "announcements_written": len(records),
        "failures": len(failures),
        "status": "success" if not failures else "partial_failure",
    }
    (output_dir / "extraction_run.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return ExtractionResult(
        tuple(records), tuple(failures), requests_attempted, requests_succeeded, unresolved
    )


def run(
    output_dir: Path,
    *,
    max_pages: int = 1,
    page_size: int = 100,
    from_date: date | None = None,
    to_date: date | None = None,
    headless: bool = True,
) -> int:
    """Collect SGX announcements and return zero only when all selected records succeed."""
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(SGT)
    tasks_by_url: dict[str, dict[str, str]] = {}
    failures: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.firefox.launch(
            headless=headless, executable_path=playwright.firefox.executable_path
        )
        context = browser.new_context()
        listing_page = context.new_page()

        for page_number in range(1, max_pages + 1):
            list_url = build_list_url(page_number, page_size)
            print(f"Fetching announcement list from: {list_url}")
            try:
                listing_page.goto(list_url, wait_until="networkidle")
                listing_page.wait_for_selector("table tbody tr", timeout=15_000)
                page_tasks = [
                    task
                    for row in listing_page.query_selector_all("table tbody tr")
                    if (task := listing_task_from_row(row)) is not None
                ]
            except Exception as exc:
                failures.append(
                    {
                        "stage": "listing",
                        "page": page_number,
                        "url": list_url,
                        "error": str(exc),
                        "recorded_at": datetime.now(SGT).isoformat(),
                    }
                )
                break

            for task in page_tasks:
                try:
                    if task_is_in_range(task, from_date, to_date):
                        key = canonical_announcement_url(task["source_url"])
                        tasks_by_url[key or task["source_url"]] = task
                except ValueError as exc:
                    failures.append(
                        {
                            "stage": "listing_validation",
                            "url": task["source_url"],
                            "error": str(exc),
                            "recorded_at": datetime.now(SGT).isoformat(),
                        }
                    )

            if from_date and page_tasks:
                valid_dates = []
                for task in page_tasks:
                    with contextlib.suppress(ValueError):
                        valid_dates.append(parse_published_at(task["raw_dt"]).date())
                if valid_dates and min(valid_dates) < from_date:
                    break

        print(f"Found {len(tasks_by_url)} in-range announcements. Starting processing...\n")
        detail_page = context.new_page()
        records: list[dict[str, Any]] = []
        for index, task in enumerate(tasks_by_url.values(), start=1):
            source_url = canonical_announcement_url(task["source_url"])
            print(
                f"[{index}/{len(tasks_by_url)}] Processing "
                f"{task['issuer_name']} / {task['security_name']} ... ",
                end="",
                flush=True,
            )
            try:
                detail_page.goto(source_url, wait_until="networkidle")
                detail_page.wait_for_selector("div.announcement", timeout=15_000)
                announcement_div = detail_page.query_selector("div.announcement")
                if announcement_div is None:
                    raise ValueError("announcement detail container was not found")
                record = normalize_record(task, announcement_div.inner_html(), datetime.now(SGT))
                write_record(record, output_dir)
                records.append(record)
                print("done")
            except Exception as exc:
                failure = {
                    "stage": "detail",
                    "source_url": source_url,
                    "issuer_name": task["issuer_name"],
                    "title": task["main_title"],
                    "error": str(exc),
                    "recorded_at": datetime.now(SGT).isoformat(),
                }
                failures.append(failure)
                print(f"failed ({exc})")
        browser.close()

    manifest_path = output_dir / "manifest.jsonl"
    manifest_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    for failure in failures:
        append_jsonl(output_dir / "extraction_failures.jsonl", failure)

    completed_at = datetime.now(SGT)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "from_date": from_date.isoformat() if from_date else None,
        "to_date": to_date.isoformat() if to_date else None,
        "pages_requested": max_pages,
        "page_size": page_size,
        "announcements_selected": len(tasks_by_url),
        "announcements_written": len(records),
        "unresolved_symbols": sum(not record["symbols"] for record in records),
        "failures": len(failures),
        "status": "success" if not failures else "partial_failure",
    }
    (output_dir / "extraction_run.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nExtraction {summary['status']}: {len(records)} written, {len(failures)} failures.")
    return 0 if not failures else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "announcements",
    )
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--from-date", type=parse_cli_date)
    parser.add_argument("--to-date", type=parse_cli_date)
    parser.add_argument("--candidate-file", type=Path)
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--filters", type=Path, default=DEFAULT_FILTERS_PATH)
    parser.add_argument("--probe-category-semantics", action="store_true")
    parser.add_argument("--show-browser", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.max_pages < 1:
        raise SystemExit("--max-pages must be at least 1")
    if not 1 <= args.page_size <= 100:
        raise SystemExit("--page-size must be between 1 and 100")
    if args.from_date and args.to_date and args.from_date > args.to_date:
        raise SystemExit("--from-date cannot be after --to-date")
    if args.probe_category_semantics:
        if not args.from_date or not args.to_date:
            raise SystemExit("category probe requires --from-date and --to-date")
        policy = load_filter_policy(args.filters)
        symbols = load_target_symbols(args.candidate_file, args.symbol)
        missing = [symbol for symbol in symbols if symbol not in policy.mappings]
        if missing:
            raise SystemExit(f"missing SGX mapping(s): {', '.join(missing)}")
        results = {
            symbol: probe_category_semantics(
                policy.mappings[symbol],
                args.from_date,
                args.to_date,
                policy,
                headless=not args.show_browser,
            )
            for symbol in symbols
        }
        print(json.dumps(results, indent=2))
        return 0
    if args.candidate_file or args.symbol:
        if not args.from_date or not args.to_date:
            raise SystemExit("targeted extraction requires --from-date and --to-date")
        policy = load_filter_policy(args.filters)
        symbols = load_target_symbols(args.candidate_file, args.symbol)
        result = extract_targeted(
            args.output_dir,
            symbols,
            policy=policy,
            from_date=args.from_date,
            to_date=args.to_date,
            max_pages=args.max_pages,
            headless=not args.show_browser,
        )
        print(
            f"Targeted extraction: {len(result.records)} records, {len(result.failures)} failures."
        )
        return 0 if not result.failures else 1
    raise SystemExit("targeted extraction requires --candidate-file or --symbol")


if __name__ == "__main__":
    raise SystemExit(main())
