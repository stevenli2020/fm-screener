"""Isolated M4 full-page and attachment extraction trial.

This program deliberately does not modify the production M4 pipeline. It loads
M3 candidates, reuses M4's SGX filter/mapping rules for live discovery, visits
each relevant detail page, and writes richer artifacts to a separate directory.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import mimetypes
import re
import shutil
import subprocess
import sys
import time
from collections import OrderedDict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

USER_AGENT = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:141.0) Gecko/20100101 Firefox/141.0"
ATTACHMENT_EXTENSIONS = (".pdf", ".xlsx", ".xls", ".docx", ".doc", ".zip", ".csv")
DEFAULT_CANDIDATE_FILE = Path("reports/generated/pending_candidates.json")
DEFAULT_FILTER_FILE = Path(__file__).with_name("sgx_announcement_filters.json")


def log(message: str) -> None:
    print(f"[M4-TRIAL] {message}", flush=True)


def debug(enabled: bool, message: str) -> None:
    if enabled:
        print(f"[M4-TRIAL][DEBUG] {message}", flush=True)


def clean_text(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line for line in lines if line)).strip()


def safe_name(value: str, fallback: str, max_length: int = 150) -> str:
    value = unquote(value)
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", value).strip(" ._")
    return name[:max_length].rstrip(" .") or fallback


def load_listing_module() -> Any:
    """Load the existing listing/filter implementation without changing it."""
    path = Path(__file__).with_name("run.py")
    spec = importlib.util.spec_from_file_location("m4_trial_listing", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load listing implementation: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def nearest_heading(node: Tag) -> str:
    heading = node.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
    return clean_text(heading.get_text(" ", strip=True)) if heading else "Unsectioned"


def node_links(node: Tag, base_url: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for anchor in node.find_all("a", href=True):
        links.append(
            {
                "text": clean_text(anchor.get_text(" ", strip=True)) or "Link",
                "url": urljoin(base_url, str(anchor["href"])),
            }
        )
    return links


def extract_lossless_page(html: str, base_url: str) -> dict[str, Any]:
    """Preserve visible text, headings, ordered fields and table rows."""
    soup = BeautifulSoup(html, "html.parser")
    for unwanted in soup(["script", "style", "noscript"]):
        unwanted.decompose()

    headings = [
        {"level": int(node.name[1]), "text": clean_text(node.get_text(" ", strip=True))}
        for node in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        if clean_text(node.get_text(" ", strip=True))
    ]

    fields: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str, str]] = set()
    for term in soup.find_all("dt"):
        definition = term.find_next_sibling("dd")
        if not definition:
            continue
        label = clean_text(term.get_text(" ", strip=True)).rstrip(":")
        value = clean_text(definition.get_text("\n", strip=True))
        section = nearest_heading(term)
        key = (section, label, value)
        if label and key not in seen_pairs:
            seen_pairs.add(key)
            fields.append(
                {
                    "section": section,
                    "label": label,
                    "value": value,
                    "links": node_links(definition, base_url),
                }
            )

    tables: list[dict[str, Any]] = []
    for table_index, table in enumerate(soup.find_all("table"), start=1):
        rows: list[list[str]] = []
        for row in table.find_all("tr"):
            cells = [
                clean_text(cell.get_text("\n", strip=True)) for cell in row.find_all(["th", "td"])
            ]
            if cells and any(cells):
                rows.append(cells)
        if not rows:
            continue
        headers = [clean_text(cell.get_text("\n", strip=True)) for cell in table.find_all("th")]
        tables.append(
            {
                "index": table_index,
                "section": nearest_heading(table),
                "headers": headers,
                "rows": rows,
            }
        )
        # Capture two-cell layout tables as fields too, without losing duplicate labels.
        for row in rows:
            if len(row) != 2 or not row[0]:
                continue
            key = (nearest_heading(table), row[0].rstrip(":"), row[1])
            if key not in seen_pairs:
                seen_pairs.add(key)
                fields.append(
                    {
                        "section": key[0],
                        "label": key[1],
                        "value": key[2],
                        "links": [],
                    }
                )

    sections: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for field in fields:
        section = sections.setdefault(field["section"], {"name": field["section"], "fields": []})
        section["fields"].append({key: value for key, value in field.items() if key != "section"})

    body = soup.body or soup
    visible_text = clean_text(body.get_text("\n", strip=True))
    return {
        "headings": headings,
        "sections": list(sections.values()),
        "fields": fields,
        "tables": tables,
        "visible_text": visible_text,
    }


def extract_attachments(html: str, base_url: str, source_id: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, str(anchor["href"]))
        path = urlparse(url).path.lower()
        is_file = path.endswith(ATTACHMENT_EXTENSIONS)
        is_source_asset = (
            f"/corporate-announcements/{source_id.lower()}/" in path
            and path.rstrip("/").split("/")[-1] != source_id.lower()
        )
        if not (is_file or is_source_asset) or url in seen:
            continue
        seen.add(url)
        fallback = Path(unquote(urlparse(url).path)).name or "attachment"
        results.append(
            {
                "name": clean_text(anchor.get_text(" ", strip=True)) or fallback,
                "source_url": url,
            }
        )
    return results


def field_lookup(page_data: dict[str, Any], *patterns: str) -> str | None:
    for pattern in patterns:
        regex = re.compile(pattern, re.IGNORECASE)
        for field in page_data["fields"]:
            if regex.search(field["label"]):
                return field["value"]
        for table in page_data["tables"]:
            for label, value in _table_row_items(table["rows"]):
                if regex.search(label):
                    return value
    return None


def normalize_event(category: str, page_data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Create a small deterministic event view while retaining all raw fields."""
    category_key = category.casefold()
    if "dividend" in category_key or "distribution" in category_key:
        mapping = {
            "distribution_number": (r"Dividend/Distribution Number",),
            "distribution_type": (r"Dividend/Distribution Type",),
            "financial_year_end": (r"Financial Year End",),
            "declared_rate": (r"Declared Dividend/Distribution Rate",),
            "record_date": (r"Record Date",),
            "ex_date": (r"Ex Date",),
            "pay_date": (r"Pay Date",),
            "payment_type": (r"Payment Type",),
            "gross_rate": (r"Gross Rate(?! Status)",),
            "net_rate": (r"Net Rate",),
            "gross_rate_status": (r"Gross Rate Status",),
            "event_narrative": (r"Event Narrative",),
        }
        return "cash_dividend", {
            key: value
            for key, patterns in mapping.items()
            if (value := field_lookup(page_data, *patterns)) is not None
        }
    if "share buy" in category_key or "buy-back" in category_key or "buyback" in category_key:
        mapping = {
            "mandate_start_date": (r"Start date.*mandate", r"Mandate.*Start"),
            "maximum_authorised_shares": (r"Maximum.*Author",),
            "purchase_date": (r"Date.*Purchase", r"Purchase Date"),
            "shares_purchased": (r"Total Number.*Purchased", r"Number.*Shares.*Purchased"),
            "highest_price": (r"Highest Price",),
            "lowest_price": (r"Lowest Price",),
            "total_consideration": (r"Total Consideration",),
            "cumulative_shares_purchased": (r"Cumulative.*Purchased",),
            "issued_shares_after_purchase": (
                r"^Number of issued shares excluding treasury shares after purchase$",
            ),
            "treasury_shares_after_purchase": (r"^Number of treasury shares held after purchase$",),
        }
        return "share_buyback", {
            key: value
            for key, patterns in mapping.items()
            if (value := field_lookup(page_data, *patterns)) is not None
        }
    return "unclassified", {}


def _field_text(field: dict[str, Any]) -> str:
    value = str(field.get("value", "")).strip()
    links = field.get("links", []) or []
    link_text = ", ".join(
        f"{link.get('text', 'Link')} ({link.get('url', '')})" for link in links if link.get("url")
    )
    if value and link_text and link_text not in value:
        return f"{value}; Links: {link_text}"
    return value or link_text


def _table_row_items(rows: list[list[str]]) -> list[tuple[str, str]]:
    """Convert an SGX table into unambiguous label/value pairs."""
    if not rows:
        return []
    column_headers: list[str] = []
    table_context = ""
    start_index = 0
    first = rows[0]
    header_terms = {"number", "percentage", "percentage#", "amount", "currency", "value"}
    has_named_columns = any(cell.strip().casefold() in header_terms for cell in first[1:])
    if len(first) > 1 and (not first[0] or has_named_columns):
        column_headers = first
        table_context = first[0]
        start_index = 1

    items: list[tuple[str, str]] = []
    for row in rows[start_index:]:
        if not row or not row[0]:
            continue
        label = f"{table_context} - {row[0]}" if table_context else row[0]
        values = row[1:]
        nonempty = [(index, value) for index, value in enumerate(values, start=1) if value]
        if not nonempty:
            continue
        if len(nonempty) == 1:
            column_index, value = nonempty[0]
            header = (
                column_headers[column_index]
                if column_headers and column_index < len(column_headers)
                else ""
            )
            qualified_label = f"{header} {label}" if header else label
            items.append((qualified_label, value))
            continue
        rendered: list[str] = []
        for column_index, value in nonempty:
            header = (
                column_headers[column_index]
                if column_headers and column_index < len(column_headers)
                else ""
            )
            rendered.append(f"{header}: {value}" if header else value)
        items.append((label, ", ".join(rendered)))
    return items


def compact_announcement_sections(page_data: dict[str, Any]) -> dict[str, str]:
    """Collapse the lossless in-memory parse into one concise persisted representation."""
    grouped: OrderedDict[str, list[str]] = OrderedDict()
    seen: dict[str, set[str]] = {}

    def add(section: str, label: str, value: str) -> None:
        section = section.strip() or "Unsectioned"
        label = label.strip().rstrip(":")
        value = value.strip()
        if not label or not value:
            return
        item = f"{label}: {value}"
        section_items = grouped.setdefault(section, [])
        section_seen = seen.setdefault(section, set())
        if item not in section_seen:
            section_seen.add(item)
            section_items.append(item)

    for field in page_data["fields"]:
        add(field["section"], field["label"], _field_text(field))
    for table in page_data["tables"]:
        for label, value in _table_row_items(table["rows"]):
            add(table["section"], label, value)
    return {section: "; ".join(items) for section, items in grouped.items() if items}


class FirefoxFetcher:
    def __init__(self, *, headless: bool, debug_enabled: bool) -> None:
        self.headless = headless
        self.debug_enabled = debug_enabled
        self.playwright: Any = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def __enter__(self) -> FirefoxFetcher:
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.firefox.launch(headless=self.headless)
        self.context = self.browser.new_context(user_agent=USER_AGENT, accept_downloads=True)
        self.page = self.context.new_page()
        log(f"Firefox started ({'headless' if self.headless else 'visible'} mode)")
        return self

    def __exit__(self, *_: Any) -> None:
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        log("Firefox stopped")

    def page_html(self, url: str) -> str:
        assert self.page is not None
        debug(self.debug_enabled, f"GET page: {url}")
        response = self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        if response and response.status >= 400:
            raise RuntimeError(f"SGX page returned HTTP {response.status}: {url}")
        try:
            self.page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:  # noqa: BLE001 - some SGX pages keep background requests open
            debug(self.debug_enabled, "networkidle timeout ignored; DOM is available")
        self.page.wait_for_timeout(750)
        body_text = self.page.locator("body").inner_text().strip()
        if "access denied" in body_text.casefold():
            raise PermissionError(f"SGX/Akamai access denied: {url}")
        return self.page.content()

    def binary(self, url: str) -> tuple[bytes, str]:
        assert self.context is not None
        debug(self.debug_enabled, f"GET attachment: {url}")
        response = self.context.request.get(url, timeout=60_000, headers={"Referer": url})
        if not response.ok:
            raise RuntimeError(f"attachment returned HTTP {response.status}: {url}")
        return response.body(), response.headers.get("content-type", "application/octet-stream")


def extract_pdf_text(pdf_path: Path, text_path: Path) -> dict[str, Any]:
    """Use WSL's pdftotext, preserving explicit page boundaries."""
    executable = shutil.which("pdftotext")
    if not executable:
        return {"status": "skipped", "reason": "pdftotext_not_installed"}
    completed = subprocess.run(
        [executable, "-layout", str(pdf_path), "-"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        return {"status": "failed", "reason": completed.stderr.strip() or "pdftotext failed"}
    raw_pages = completed.stdout.split("\f")
    if raw_pages and not raw_pages[-1].strip():
        raw_pages.pop()
    output = "\n\n".join(
        f"--- PAGE {number} ---\n{page.rstrip()}" for number, page in enumerate(raw_pages, start=1)
    )
    text_path.write_text(output.rstrip() + "\n", encoding="utf-8")
    pages_with_text = sum(bool(page.strip()) for page in raw_pages)
    return {
        "status": "extracted",
        "text_path": str(text_path),
        "page_count": len(raw_pages),
        "pages_with_text": pages_with_text,
        "quality": "text_present" if pages_with_text else "no_extractable_text",
    }


def attachment_filename(item: dict[str, str], content_type: str, index: int) -> str:
    url_name = Path(unquote(urlparse(item["source_url"]).path)).name
    candidate = url_name or item.get("name", "")
    suffix = Path(candidate).suffix
    if not suffix:
        suffix = mimetypes.guess_extension(content_type.split(";", 1)[0]) or ".bin"
    stem = safe_name(Path(candidate).stem, f"attachment-{index}", 130)
    return f"{index:02d}-{stem}{suffix.lower()}"


def cache_attachment(
    fetcher: FirefoxFetcher,
    item: dict[str, str],
    source_id: str,
    output_root: Path,
    index: int,
    total: int,
    debug_enabled: bool,
) -> dict[str, Any]:
    log(f"    attachment {index}/{total}: {item['name']}")
    folder = output_root / "attachments" / source_id
    folder.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = dict(item)
    try:
        payload, content_type = fetcher.binary(item["source_url"])
        filename = attachment_filename(item, content_type, index)
        local_path = folder / filename
        local_path.write_bytes(payload)
        relative_path = local_path.relative_to(output_root).as_posix()
        digest = hashlib.sha256(payload).hexdigest()
        result.update(
            {
                "url": relative_path,
                "local_path": relative_path,
                "cache_status": "cached",
                "content_type": content_type,
                "bytes": len(payload),
                "sha256": digest,
                "retrieved_at": datetime.now(UTC).isoformat(),
            }
        )
        log(f"      cached: {relative_path} ({len(payload):,} bytes)")
        debug(debug_enabled, f"attachment sha256={digest}")
        if local_path.suffix.casefold() == ".pdf":
            text_result = extract_pdf_text(local_path, local_path.with_suffix(".txt"))
            if "text_path" in text_result:
                text_result["text_path"] = (
                    Path(text_result["text_path"]).relative_to(output_root).as_posix()
                )
            result["text_extraction"] = text_result
            if text_result["status"] == "extracted":
                log(
                    "      PDF text: "
                    f"{text_result['pages_with_text']}/{text_result['page_count']} pages"
                )
            else:
                log(f"      PDF text skipped/failed: {text_result['reason']}")
    except Exception as exc:  # noqa: BLE001 - record per-file failure and continue trial
        result.update(
            {
                "cache_status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        log(f"      ATTACHMENT FAILED: {result['error']}")
    return result


def render_markdown(record: dict[str, Any]) -> str:
    lines = [
        f"# {record.get('title', 'Untitled')}",
        "",
        f"- Source ID: `{record.get('source_id', 'N/A')}`",
        f"- Symbols: {', '.join(record.get('symbols', [])) or 'UNKNOWN'}",
        f"- Issuer: {record.get('issuer_name', 'N/A')}",
        f"- Security: {record.get('security_name', 'N/A')}",
        f"- Published: {record.get('published_at', 'N/A')}",
        f"- Category: {record.get('category', 'N/A')}",
        f"- Original SGX URL: {record.get('source_url', 'N/A')}",
        "",
        "## Normalized Event Data",
        "",
        f"Event type: `{record['event_type']}`",
        "",
        "```json",
        json.dumps(record["event_data"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Announcement Sections",
        "",
    ]
    for section, content in record["announcement_sections"].items():
        lines.extend([f"### {section}", "", content, ""])
    lines.extend(["## Attachments", ""])
    if record["attachments"]:
        for item in record["attachments"]:
            if item.get("cache_status") == "cached":
                lines.append(
                    f"- [{item['name']}](../{item['local_path']}) "
                    f"([original SGX file]({item['source_url']}))"
                )
            else:
                lines.append(
                    f"- {item['name']} — cache failed: {item.get('error', 'unknown error')}"
                )
    else:
        lines.append("No attachments detected.")
    lines.extend(
        [
            "",
            "## Trial Note",
            "",
            "No AI summary was produced in this M4 trial.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def discover_live_announcements(
    listing: Any,
    fetcher: FirefoxFetcher,
    symbols: tuple[str, ...],
    policy: Any,
    from_date: date,
    to_date: date,
    *,
    max_pages: int,
    pacing_seconds: float,
    debug_enabled: bool,
) -> tuple[OrderedDict[str, dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Run M3 candidate mapping, SGX filtered listing queries and pagination."""
    assert fetcher.page is not None
    tasks: OrderedDict[str, dict[str, Any]] = OrderedDict()
    failures: list[dict[str, Any]] = []
    requests_attempted = 0
    requests_succeeded = 0
    mappings = [policy.mappings[symbol] for symbol in symbols if symbol in policy.mappings]
    unresolved = [symbol for symbol in symbols if symbol not in policy.mappings]
    for symbol in unresolved:
        failures.append({"stage": "mapping", "symbol": symbol, "error": "no SGX mapping"})
    active_groups = {group: codes for group, codes in policy.kept_categories.items() if codes}
    log(f"M3 candidates: {len(symbols)}; mapped: {len(mappings)}; unresolved: {len(unresolved)}")
    debug(
        debug_enabled,
        "active category codes: "
        + json.dumps({key: list(value) for key, value in active_groups.items()}),
    )

    abort_all = False
    for target_index, mapping in enumerate(mappings, start=1):
        log(
            f"[LIST {target_index}/{len(mappings)}] {mapping.symbol} - "
            f"{mapping.filter_value} ({mapping.filter_type})"
        )
        target_page_ids: set[str] = set()
        for page_number in range(1, max_pages + 1):
            list_url = listing.build_list_url(
                page_number,
                policy.page_size,
                mapping=mapping,
                from_date=from_date,
                to_date=to_date,
                category_groups=active_groups,
                base_url=policy.base_url,
            )
            requests_attempted += 1
            debug(debug_enabled, f"listing GET page {page_number}: {list_url}")
            try:
                page_tasks = listing._listing_tasks(fetcher.page, list_url)
                requests_succeeded += 1
            except Exception as exc:  # noqa: BLE001 - preserve per-target failure
                error = f"{type(exc).__name__}: {exc}"
                log(f"    listing failed: {error}")
                failures.append(
                    {
                        "stage": "listing",
                        "symbol": mapping.symbol,
                        "page": page_number,
                        "url": list_url,
                        "error": error,
                    }
                )
                if isinstance(exc, PermissionError):
                    abort_all = True
                break

            matched = [
                task
                for task in page_tasks
                if listing.task_matches_target(task, mapping)
                and listing.task_is_in_range(task, from_date, to_date)
            ]
            page_ids = {
                source_id
                for task in matched
                if (
                    source_id := listing.announcement_url_id(
                        listing.canonical_announcement_url(task["source_url"])
                    )
                )
            }
            log(
                f"    page {page_number}: {len(page_tasks)} rows, "
                f"{len(matched)} matched announcements"
            )
            if page_number > 1 and page_ids and page_ids <= target_page_ids:
                log("    repeated SGX page detected; pagination stopped")
                break
            for task in matched:
                source_id = listing.announcement_url_id(
                    listing.canonical_announcement_url(task["source_url"])
                )
                if not source_id:
                    continue
                if source_id not in tasks:
                    tasks[source_id] = {"task": task, "target_symbols": []}
                if mapping.symbol not in tasks[source_id]["target_symbols"]:
                    tasks[source_id]["target_symbols"].append(mapping.symbol)
            target_page_ids.update(page_ids)
            if len(matched) < policy.page_size:
                break
            time.sleep(pacing_seconds)
        if abort_all:
            break
        time.sleep(pacing_seconds)

    metrics = {
        "mapped_targets": len(mappings),
        "unresolved_targets": len(unresolved),
        "listing_requests_attempted": requests_attempted,
        "listing_requests_succeeded": requests_succeeded,
    }
    return tasks, failures, metrics


def create_live_record(
    listing: Any,
    task_entry: dict[str, Any],
    detail_html: str,
    retrieved_at: datetime,
) -> tuple[dict[str, Any], str, str]:
    """Build the baseline M4 contract plus richer deterministic trial data."""
    task = task_entry["task"]
    soup = BeautifulSoup(detail_html, "html.parser")
    announcement_div = soup.select_one("div.announcement")
    if announcement_div is None:
        raise ValueError("announcement detail container was not found")
    announcement_html = str(announcement_div)
    baseline = listing.normalize_record(task, announcement_html, retrieved_at)
    expected_symbols = task_entry["target_symbols"]
    if not set(expected_symbols).intersection(baseline["symbols"]):
        raise ValueError(
            f"detail symbols {baseline['symbols']} do not include targets {expected_symbols}"
        )
    baseline["target_symbol"] = expected_symbols[0]
    baseline["target_symbols"] = expected_symbols
    page_data = extract_lossless_page(announcement_html, baseline["source_url"])
    if not page_data["fields"] and not page_data["tables"]:
        preview = page_data["visible_text"][:200].replace("\n", " ")
        raise ValueError(f"no structured SGX content detected; page begins: {preview}")
    visible_text = page_data.pop("visible_text")
    return baseline, announcement_html, visible_text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-file", type=Path, default=DEFAULT_CANDIDATE_FILE)
    parser.add_argument("--filters", type=Path, default=DEFAULT_FILTER_FILE)
    parser.add_argument("--from-date", type=parse_date, required=True)
    parser.add_argument("--to-date", type=parse_date, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--request-pacing", type=float, default=0.5, metavar="SECONDS")
    parser.add_argument("--show-browser", action="store_true", help="show Firefox while running")
    parser.add_argument("--debug", action="store_true", help="print URLs, field labels and hashes")
    args = parser.parse_args()
    if args.from_date > args.to_date:
        parser.error("--from-date cannot be after --to-date")
    if args.max_pages < 1:
        parser.error("--max-pages must be at least 1")
    if args.request_pacing < 0:
        parser.error("--request-pacing cannot be negative")

    listing = load_listing_module()
    try:
        policy = listing.load_filter_policy(args.filters)
        symbols = listing.load_target_symbols(args.candidate_file, None)
    except ValueError as exc:
        log(f"ERROR: {exc}")
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "records").mkdir(exist_ok=True)
    log(f"candidate file: {args.candidate_file}")
    log(f"date range: {args.from_date} through {args.to_date} (inclusive)")
    log(f"output directory: {args.output_dir}")

    manifest: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    metrics: dict[str, int] = {}
    with FirefoxFetcher(headless=not args.show_browser, debug_enabled=args.debug) as fetcher:
        tasks, listing_failures, metrics = discover_live_announcements(
            listing,
            fetcher,
            symbols,
            policy,
            args.from_date,
            args.to_date,
            max_pages=args.max_pages,
            pacing_seconds=args.request_pacing,
            debug_enabled=args.debug,
        )
        failures.extend(listing_failures)
        log(f"announcement discovery complete: {len(tasks)} unique announcements")
        for index, (source_id, task_entry) in enumerate(tasks.items(), start=1):
            task = task_entry["task"]
            source_url = listing.canonical_announcement_url(task["source_url"])
            source_id = safe_name(source_id, "unknown")
            log(f"[DETAIL {index}/{len(tasks)}] {source_id} - {task['main_title']}")
            try:
                html = fetcher.page_html(source_url)
                enriched, announcement_html, visible_text = create_live_record(
                    listing, task_entry, html, datetime.now(listing.SGT)
                )
                page_data = extract_lossless_page(announcement_html, source_url)
                page_data.pop("visible_text")
                log(
                    "    page parsed: "
                    f"{len(page_data['fields'])} fields, {len(page_data['tables'])} tables"
                )
                debug(
                    args.debug,
                    "field labels: " + ", ".join(field["label"] for field in page_data["fields"]),
                )

                found_attachments = extract_attachments(announcement_html, source_url, source_id)
                # Retain links from the earlier extractor if the live parser misses one.
                known_urls = {item["source_url"] for item in found_attachments}
                for old_item in enriched.get("attachments", []) or []:
                    old_url = str(old_item.get("source_url") or old_item.get("url") or "")
                    if old_url and old_url not in known_urls:
                        found_attachments.append(
                            {
                                "name": str(old_item.get("name") or "Attachment"),
                                "source_url": old_url,
                            }
                        )
                        known_urls.add(old_url)
                log(f"    attachments detected: {len(found_attachments)}")
                cached = [
                    cache_attachment(
                        fetcher,
                        item,
                        source_id,
                        args.output_dir,
                        item_index,
                        len(found_attachments),
                        args.debug,
                    )
                    for item_index, item in enumerate(found_attachments, start=1)
                ]
                event_type, event_data = normalize_event(
                    str(enriched.get("category", "")), page_data
                )
                announcement_sections = compact_announcement_sections(page_data)
                trial_identity = "\x1f".join(
                    [
                        source_id,
                        visible_text,
                        *(item["source_url"] for item in found_attachments),
                    ]
                )
                enriched.update(
                    {
                        "trial_schema_version": 1,
                        "event_type": event_type,
                        "event_data": event_data,
                        "announcement_sections": announcement_sections,
                        "attachments": cached,
                        "trial_retrieved_at": datetime.now(UTC).isoformat(),
                        "trial_content_hash": hashlib.sha256(
                            trial_identity.encode("utf-8")
                        ).hexdigest(),
                    }
                )
                json_name = f"{source_id}.json"
                md_name = f"{source_id}.md"
                (args.output_dir / "records" / json_name).write_text(
                    json.dumps(enriched, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )
                (args.output_dir / "records" / md_name).write_text(
                    render_markdown(enriched), encoding="utf-8"
                )
                manifest.append(
                    {
                        "source_id": source_id,
                        "status": "complete",
                        "event_type": event_type,
                        "record_json": f"records/{json_name}",
                        "record_markdown": f"records/{md_name}",
                        "field_count": len(page_data["fields"]),
                        "table_count": len(page_data["tables"]),
                        "attachment_count": len(cached),
                        "attachment_failures": sum(
                            item.get("cache_status") != "cached" for item in cached
                        ),
                    }
                )
                log(f"    record written: records/{json_name}")
            except Exception as exc:  # noqa: BLE001 - continue trial and expose record failure
                error = f"{type(exc).__name__}: {exc}"
                log(f"    RECORD FAILED: {error}")
                failures.append(
                    {
                        "stage": "detail",
                        "source_id": source_id,
                        "source_url": source_url,
                        "target_symbols": task_entry["target_symbols"],
                        "error": error,
                    }
                )
                manifest.append({"source_id": source_id, "status": "failed", "error": error})
            time.sleep(args.request_pacing)

    attachment_failures = sum(
        int(record.get("attachment_failures", 0))
        for record in manifest
        if record.get("status") == "complete"
    )
    summary = {
        "trial_schema_version": 1,
        "candidate_file": str(args.candidate_file),
        "filter_file": str(args.filters),
        "from_date": args.from_date.isoformat(),
        "to_date": args.to_date.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "target_symbols": list(symbols),
        **metrics,
        "announcements_discovered": len(tasks),
        "completed_records": sum(record.get("status") == "complete" for record in manifest),
        "failed_records": sum(failure.get("stage") == "detail" for failure in failures),
        "failed_attachments": attachment_failures,
        "failures": failures,
        "records": manifest,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    log(
        f"COMPLETE: {summary['completed_records']} records succeeded, "
        f"{len(failures)} flow failures; "
        f"attachment failures={attachment_failures}; "
        f"manifest={args.output_dir / 'manifest.json'}"
    )
    return 1 if failures or attachment_failures else 0


if __name__ == "__main__":
    sys.exit(main())
