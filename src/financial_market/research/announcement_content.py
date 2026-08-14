from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
import subprocess
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

ATTACHMENT_EXTENSIONS = (".pdf", ".xlsx", ".xls", ".docx", ".doc", ".zip", ".csv")


def clean_text(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line for line in lines if line)).strip()


def _nearest_heading(node: Tag) -> str:
    heading = node.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
    return clean_text(heading.get_text(" ", strip=True)) if heading else "Unsectioned"


def _node_links(node: Tag, base_url: str) -> list[dict[str, str]]:
    return [
        {
            "text": clean_text(anchor.get_text(" ", strip=True)) or "Link",
            "url": urljoin(base_url, str(anchor["href"])),
        }
        for anchor in node.find_all("a", href=True)
    ]


def extract_page_data(html: str, base_url: str) -> dict[str, Any]:
    """Parse SGX fields and tables losslessly in memory."""
    soup = BeautifulSoup(html, "html.parser")
    for unwanted in soup(["script", "style", "noscript"]):
        unwanted.decompose()

    fields: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str, str]] = set()
    for term in soup.find_all("dt"):
        definition = term.find_next_sibling("dd")
        if not definition:
            continue
        label = clean_text(term.get_text(" ", strip=True)).rstrip(":")
        value = clean_text(definition.get_text("\n", strip=True))
        section = _nearest_heading(term)
        key = (section, label, value)
        if label and key not in seen_pairs:
            seen_pairs.add(key)
            fields.append(
                {
                    "section": section,
                    "label": label,
                    "value": value,
                    "links": _node_links(definition, base_url),
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
        section = _nearest_heading(table)
        tables.append({"index": table_index, "section": section, "rows": rows})
        for row in rows:
            if len(row) != 2 or not row[0]:
                continue
            key = (section, row[0].rstrip(":"), row[1])
            if key not in seen_pairs:
                seen_pairs.add(key)
                fields.append({"section": section, "label": key[1], "value": key[2], "links": []})
    visible_text = clean_text((soup.body or soup).get_text("\n", strip=True))
    return {"fields": fields, "tables": tables, "visible_text": visible_text}


def extract_attachment_links(html: str, base_url: str, source_id: str) -> list[dict[str, str]]:
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
                "url": url,
            }
        )
    return results


def _field_text(field: dict[str, Any]) -> str:
    value = str(field.get("value", "")).strip()
    links = field.get("links", []) or []
    link_text = ", ".join(
        f"{link.get('text', 'Link')} ({link.get('url', '')})" for link in links if link.get("url")
    )
    if value and link_text and link_text not in value:
        return f"{value}; Links: {link_text}"
    return value or link_text


def table_row_items(rows: list[list[str]]) -> list[tuple[str, str]]:
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
        nonempty = [(index, value) for index, value in enumerate(row[1:], start=1) if value]
        if not nonempty:
            continue
        if len(nonempty) == 1:
            column_index, value = nonempty[0]
            header = (
                column_headers[column_index]
                if column_headers and column_index < len(column_headers)
                else ""
            )
            items.append((f"{header} {label}" if header else label, value))
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
    grouped: OrderedDict[str, list[str]] = OrderedDict()
    seen: dict[str, set[str]] = {}

    def add(section: str, label: str, value: str) -> None:
        section = section.strip() or "Unsectioned"
        label = label.strip().rstrip(":")
        value = value.strip()
        if not label or not value:
            return
        item = f"{label}: {value}"
        if item not in seen.setdefault(section, set()):
            seen[section].add(item)
            grouped.setdefault(section, []).append(item)

    for field in page_data["fields"]:
        add(field["section"], field["label"], _field_text(field))
    for table in page_data["tables"]:
        for label, value in table_row_items(table["rows"]):
            add(table["section"], label, value)
    return {section: "; ".join(items) for section, items in grouped.items() if items}


def _field_lookup(page_data: dict[str, Any], *patterns: str) -> str | None:
    for pattern in patterns:
        regex = re.compile(pattern, re.IGNORECASE)
        for field in page_data["fields"]:
            if regex.search(field["label"]):
                return field["value"]
        for table in page_data["tables"]:
            for label, value in table_row_items(table["rows"]):
                if regex.search(label):
                    return value
    return None


def normalize_event(category: str, page_data: dict[str, Any]) -> tuple[str, dict[str, str]]:
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
            if (value := _field_lookup(page_data, *patterns)) is not None
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
            if (value := _field_lookup(page_data, *patterns)) is not None
        }
    return "unclassified", {}


def _safe_name(value: str, fallback: str, max_length: int = 130) -> str:
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", unquote(value)).strip(" ._")
    return name[:max_length].rstrip(" .") or fallback


def _attachment_filename(item: dict[str, str], content_type: str, index: int) -> str:
    url_name = Path(unquote(urlparse(item["source_url"]).path)).name
    candidate = url_name or item.get("name", "")
    suffix = Path(candidate).suffix
    if not suffix:
        suffix = mimetypes.guess_extension(content_type.split(";", 1)[0]) or ".bin"
    return f"{index:02d}-{_safe_name(Path(candidate).stem, f'attachment-{index}')}{suffix.lower()}"


def _extract_pdf_text(pdf_path: Path, text_path: Path) -> dict[str, Any]:
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
    pages = completed.stdout.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    output = "\n\n".join(
        f"--- PAGE {number} ---\n{page.rstrip()}" for number, page in enumerate(pages, start=1)
    )
    text_path.write_text(output.rstrip() + "\n", encoding="utf-8")
    pages_with_text = sum(bool(page.strip()) for page in pages)
    return {
        "status": "extracted",
        "text_path": text_path.as_posix(),
        "page_count": len(pages),
        "pages_with_text": pages_with_text,
        "quality": "text_present" if pages_with_text else "no_extractable_text",
    }


def cache_attachments(
    attachments: list[dict[str, str]],
    source_id: str,
    output_root: Path,
    request_context: Any,
    referer: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    cached: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for index, item in enumerate(attachments, start=1):
        source_url = item.get("source_url") or item.get("url") or ""
        result: dict[str, Any] = {"name": item.get("name", "Attachment"), "source_url": source_url}
        try:
            response = request_context.get(source_url, timeout=60_000, headers={"Referer": referer})
            if not response.ok:
                raise RuntimeError(f"HTTP {response.status}")
            payload = response.body()
            content_type = response.headers.get("content-type", "application/octet-stream")
            folder = output_root / "attachments" / source_id
            folder.mkdir(parents=True, exist_ok=True)
            local_path = folder / _attachment_filename(result, content_type, index)
            local_path.write_bytes(payload)
            result.update(
                {
                    "url": local_path.as_posix(),
                    "local_path": local_path.as_posix(),
                    "cache_status": "cached",
                    "content_type": content_type,
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "retrieved_at": datetime.now(UTC).isoformat(),
                }
            )
            if local_path.suffix.casefold() == ".pdf":
                result["text_extraction"] = _extract_pdf_text(
                    local_path, local_path.with_suffix(".txt")
                )
        except Exception as exc:  # noqa: BLE001 - preserve the announcement and audit failure
            error = f"{type(exc).__name__}: {exc}"
            result.update({"url": source_url, "cache_status": "failed", "error": error})
            failures.append({"source_url": source_url, "error": error})
        cached.append(result)
    return cached, failures


def compute_content_hash(record: dict[str, Any]) -> str:
    attachments = [
        {
            "source_url": item.get("source_url"),
            "sha256": item.get("sha256"),
            "cache_status": item.get("cache_status"),
        }
        for item in record.get("attachments", [])
    ]
    identity = {
        "source_id": record.get("source_id"),
        "title": record.get("title"),
        "published_at": record.get("published_at"),
        "details": record.get("details"),
        "announcement_sections": record.get("announcement_sections", {}),
        "event_type": record.get("event_type"),
        "event_data": record.get("event_data", {}),
        "attachments": attachments,
    }
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
