from __future__ import annotations

from types import SimpleNamespace

from financial_market.research import announcement_content as content

BUYBACK_HTML = """
<div class="announcement">
  <h2>Issuer &amp; Securities</h2>
  <dl>
    <dt>Issuer/ Manager</dt><dd>KEPPEL LTD.</dd>
    <dt>Securities</dt><dd>KEPPEL LTD. - SG1U68934629 - BN4</dd>
  </dl>
  <h2>Additional Details</h2>
  <dl><dt>Start date for mandate of daily share buy-back</dt><dd>17/04/2026</dd></dl>
  <h2>Section A</h2>
  <dl>
    <dt>Maximum number of shares authorised for purchase</dt><dd>90,646,698</dd>
    <dt>Purchase made by way of market acquisition</dt><dd>Yes</dd>
  </dl>
  <table>
    <tr><td></td><td>Singapore Exchange</td><td>Overseas Exchange</td></tr>
    <tr><td>Date of Purchase</td><td>12/08/2026</td><td></td></tr>
    <tr><td>Total Number of shares purchased</td><td>200,000</td><td></td></tr>
  </table>
  <table>
    <tr><td>Highest Price per share</td><td>SGD 11.3</td><td></td></tr>
    <tr><td>Lowest Price per share</td><td>SGD 11.15</td><td></td></tr>
    <tr><td>Total Consideration</td><td>SGD 2,250,250.11</td><td></td></tr>
  </table>
  <h2>Section C</h2>
  <table>
    <tr><td>Cumulative No. of shares purchased to date^</td><td>Number</td><td>Percentage#</td></tr>
    <tr><td>By way of Market Acquisition</td><td>14,828,000</td><td>0.8179</td></tr>
  </table>
  <h2>Section D</h2>
  <dl>
    <dt>Number of issued shares excluding treasury shares after purchase</dt>
    <dd>1,798,121,509</dd>
    <dt>Number of treasury shares held after purchase</dt><dd>22,436,258</dd>
  </dl>
  <h2>Attachments</h2>
  <a href="report.pdf">Daily notice</a>
  <a href="https://links.sgx.com/1.0.0/corporate-announcements/SOURCE1/">Page</a>
</div>
"""


def test_page_compaction_and_buyback_normalization_preserve_tables() -> None:
    base = "https://links.sgx.com/1.0.0/corporate-announcements/SOURCE1/"
    page = content.extract_page_data(BUYBACK_HTML, base)
    sections = content.compact_announcement_sections(page)
    event_type, event_data = content.normalize_event("Share Buy Back-On Market", page)

    assert "Singapore Exchange Date of Purchase: 12/08/2026" in sections["Section A"]
    assert "Highest Price per share: SGD 11.3" in sections["Section A"]
    assert "Number: 14,828,000, Percentage#: 0.8179" in sections["Section C"]
    assert event_type == "share_buyback"
    assert event_data["mandate_start_date"] == "17/04/2026"
    assert event_data["purchase_date"] == "12/08/2026"
    assert event_data["shares_purchased"] == "200,000"
    assert event_data["treasury_shares_after_purchase"] == "22,436,258"


def test_attachment_discovery_and_dividend_normalization() -> None:
    base = "https://links.sgx.com/1.0.0/corporate-announcements/SOURCE1/"
    attachments = content.extract_attachment_links(BUYBACK_HTML, base, "SOURCE1")
    dividend = content.extract_page_data(
        """
        <h2>Dividend Details</h2><dl>
          <dt>Dividend/Distribution Number</dt><dd>39</dd>
          <dt>Dividend/Distribution Type</dt><dd>Interim</dd>
          <dt>Declared Dividend/Distribution Rate</dt><dd>SGD 0.05</dd>
          <dt>Record Date</dt><dd>20/08/2026</dd>
          <dt>Pay Date</dt><dd>02/09/2026</dd>
        </dl>
        """,
        base,
    )
    event_type, event_data = content.normalize_event("Cash Dividend/ Distribution", dividend)

    assert len(attachments) == 1
    assert attachments[0]["source_url"].endswith("/SOURCE1/report.pdf")
    assert event_type == "cash_dividend"
    assert event_data["distribution_number"] == "39"
    assert event_data["declared_rate"] == "SGD 0.05"
    assert event_data["pay_date"] == "02/09/2026"


class AttachmentResponse:
    def __init__(self, *, ok: bool = True) -> None:
        self.ok = ok
        self.status = 403 if not ok else 200
        self.headers = {"content-type": "application/pdf"}

    def body(self) -> bytes:
        return b"%PDF-1.4\n%%EOF\n"


class AttachmentRequest:
    def __init__(self, response: AttachmentResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_attachment_cache_records_local_provenance_without_pdftotext(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(content.shutil, "which", lambda _name: None)
    request = AttachmentRequest(AttachmentResponse())
    items = [
        {
            "name": "Results Presentation",
            "source_url": "https://links.sgx.com/source/results.pdf",
        }
    ]

    cached, failures = content.cache_attachments(
        items, "SOURCE1", tmp_path, request, "https://links.sgx.com/source/"
    )

    assert failures == []
    assert cached[0]["cache_status"] == "cached"
    assert cached[0]["sha256"]
    assert cached[0]["text_extraction"] == {
        "status": "skipped",
        "reason": "pdftotext_not_installed",
    }
    assert (tmp_path / "attachments" / "SOURCE1" / "01-results.pdf").exists()
    assert request.calls[0][1]["headers"]["Referer"].endswith("/source/")


def test_attachment_failure_is_audited_and_hash_tracks_content(tmp_path) -> None:
    items = [{"name": "Blocked", "source_url": "https://links.sgx.com/source/blocked.pdf"}]
    cached, failures = content.cache_attachments(
        items,
        "SOURCE1",
        tmp_path,
        AttachmentRequest(AttachmentResponse(ok=False)),
        "https://links.sgx.com/source/",
    )
    record = {
        "source_id": "SOURCE1",
        "title": "Results",
        "published_at": "2026-08-13T00:00:00Z",
        "details": "Details",
        "announcement_sections": {"Details": "Status: New"},
        "event_type": "unclassified",
        "event_data": {},
        "attachments": cached,
    }
    first = content.compute_content_hash(record)
    record["attachments"][0]["sha256"] = "f" * 64

    assert cached[0]["cache_status"] == "failed"
    assert failures[0]["error"].startswith("RuntimeError: HTTP 403")
    assert content.compute_content_hash(record) != first


def test_pdf_text_extraction_preserves_page_markers(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "report.pdf"
    text = tmp_path / "report.txt"
    pdf.write_bytes(b"pdf")
    monkeypatch.setattr(content.shutil, "which", lambda _name: "/usr/bin/pdftotext")
    monkeypatch.setattr(
        content.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout="First page\fSecond page\f", stderr=""
        ),
    )

    result = content._extract_pdf_text(pdf, text)

    assert result["page_count"] == 2
    assert result["pages_with_text"] == 2
    assert "--- PAGE 2 ---" in text.read_text(encoding="utf-8")
