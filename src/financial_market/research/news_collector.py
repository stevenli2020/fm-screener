from __future__ import annotations

import importlib.util
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from financial_market.config import Settings


class SGXNewsError(RuntimeError):
    """Raised when an SGX announcement fetch cannot produce a valid result."""

    def __init__(
        self,
        message: str,
        *,
        status: str = "error",
        http_code: int | None = None,
        execution_time_ms: int = 0,
        attempt_count: int = 1,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.http_code = http_code
        self.execution_time_ms = execution_time_ms
        self.attempt_count = attempt_count


@dataclass(frozen=True, slots=True)
class Announcement:
    sgxnet_id: str
    symbol: str
    title: str
    announcement_type: str | None
    published_at: str
    url: str | None
    document_type: str | None
    content_hash: str | None = None
    source: str = "sgx_api"
    announcement_sections: dict[str, str] | None = None
    event_type: str = "unclassified"
    event_data: dict[str, str] | None = None
    attachments: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Announcement:
        sgxnet_id = _required_string(payload, "id")
        symbol = _required_string(payload, "symbol").upper()
        title = _required_string(payload, "title")
        published_at = _normalise_timestamp(_required_string(payload, "publishedAt"))
        announcement_type = _optional_string(payload, "type")
        url = _optional_string(payload, "url")
        document_type = _optional_string(payload, "documentType")
        return cls(
            sgxnet_id=sgxnet_id,
            symbol=symbol,
            title=title,
            announcement_type=announcement_type,
            published_at=published_at,
            url=url,
            document_type=document_type,
        )


@dataclass(frozen=True, slots=True)
class FetchResult:
    announcements: tuple[Announcement, ...]
    http_code: int
    execution_time_ms: int
    attempt_count: int
    status: str = "success"
    error_message: str | None = None


class SGXNewsClient:
    """Small, fail-closed HTTP adapter for the configured SGX announcement endpoint."""

    _RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        settings: Settings,
        *,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._session = session or requests.Session()
        self._owns_session = session is None
        self._sleep = sleep
        self._monotonic = monotonic

    def __enter__(self) -> SGXNewsClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    def fetch_announcements(
        self,
        period_start: datetime,
        period_end: datetime,
        target_symbols: tuple[str, ...] | None = None,
    ) -> FetchResult:
        if period_start > period_end:
            raise ValueError("period_start cannot be after period_end")
        params = {
            "periodstart": _sgx_timestamp(period_start),
            "periodend": _sgx_timestamp(period_end),
            "limit": self._settings.sgx_news_limit,
        }
        attempts = self._settings.sgx_news_max_retries + 1
        started = self._monotonic()
        last_error = "unknown SGX API error"
        last_code: int | None = None
        last_status = "error"
        for attempt in range(1, attempts + 1):
            try:
                response = self._session.get(
                    self._settings.sgx_news_api_url,
                    params=params,
                    timeout=self._settings.sgx_news_timeout_seconds,
                    headers={"Accept": "application/json", "User-Agent": "FinancialMarket-SGX/0.1"},
                )
                last_code = response.status_code
                if response.status_code in self._RETRYABLE_STATUS_CODES:
                    last_error = f"SGX API returned retryable HTTP {response.status_code}"
                elif response.status_code >= 400:
                    raise SGXNewsError(
                        f"SGX API returned HTTP {response.status_code}",
                        http_code=response.status_code,
                        execution_time_ms=_elapsed_ms(started, self._monotonic()),
                        attempt_count=attempt,
                    )
                else:
                    try:
                        payload = response.json()
                        announcements = _parse_response(payload)
                    except (ValueError, requests.JSONDecodeError) as exc:
                        raise SGXNewsError(
                            f"SGX API returned a malformed response: {exc}",
                            status="malformed",
                            http_code=response.status_code,
                            execution_time_ms=_elapsed_ms(started, self._monotonic()),
                            attempt_count=attempt,
                        ) from exc
                    return FetchResult(
                        announcements=announcements,
                        http_code=response.status_code,
                        execution_time_ms=_elapsed_ms(started, self._monotonic()),
                        attempt_count=attempt,
                    )
            except requests.Timeout:
                last_error = "SGX API request timed out"
                last_status = "timeout"
            except requests.ConnectionError as exc:
                last_error = f"SGX API connection failed: {exc}"
            if attempt < attempts:
                self._sleep(self._settings.sgx_news_retry_backoff_seconds * (2 ** (attempt - 1)))
        raise SGXNewsError(
            last_error,
            status=last_status,
            http_code=last_code,
            execution_time_ms=_elapsed_ms(started, self._monotonic()),
            attempt_count=attempts,
        )


class SGXPublicPageClient:
    """Adapt the targeted public-page extractor to the M4 announcement contract."""

    def __init__(
        self,
        *,
        filters_path: Path,
        extraction_dir: Path,
        max_pages: int = 10,
        pacing_seconds: float = 0.5,
        extractor_module: Any | None = None,
    ) -> None:
        self._filters_path = filters_path
        self._extraction_dir = extraction_dir
        self._max_pages = max_pages
        self._pacing_seconds = pacing_seconds
        self._extractor = extractor_module or _load_extractor(filters_path.parent / "run.py")
        self.endpoint = self._extractor.load_filter_policy(filters_path).base_url

    def __enter__(self) -> SGXPublicPageClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def fetch_announcements(
        self,
        period_start: datetime,
        period_end: datetime,
        target_symbols: tuple[str, ...] | None = None,
    ) -> FetchResult:
        if not target_symbols:
            raise ValueError("public-page extraction requires target symbols")
        started = time.monotonic()
        try:
            policy = self._extractor.load_filter_policy(self._filters_path)
            result = self._extractor.extract_targeted(
                self._extraction_dir,
                target_symbols,
                policy=policy,
                from_date=period_start.date(),
                to_date=period_end.date(),
                max_pages=self._max_pages,
                request_pacing_seconds=self._pacing_seconds,
            )
        except Exception as exc:
            raise SGXNewsError(
                f"SGX public-page extraction failed: {exc}",
                execution_time_ms=round((time.monotonic() - started) * 1000),
            ) from exc
        announcements = tuple(_from_extractor_record(record) for record in result.records)
        status = "success" if not result.failures else "partial_failure"
        errors = (
            "; ".join(f"{item.get('stage')}: {item.get('error')}" for item in result.failures)
            or None
        )
        return FetchResult(
            announcements=announcements,
            http_code=200 if status == "success" else 0,
            execution_time_ms=round((time.monotonic() - started) * 1000),
            attempt_count=result.requests_attempted,
            status=status,
            error_message=errors,
        )


def _load_extractor(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("financial_market_sgx_extractor", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load SGX extractor: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _from_extractor_record(record: dict[str, Any]) -> Announcement:
    symbols = record.get("symbols")
    target_symbol = record.get("target_symbol")
    if not isinstance(symbols, list) or any(not isinstance(item, str) for item in symbols):
        raise ValueError("extractor record symbols must be a string list")
    if target_symbol is None and len(symbols) == 1:
        target_symbol = symbols[0]
    if not isinstance(target_symbol, str) or target_symbol not in symbols:
        raise ValueError("extractor record must resolve its target symbol")
    source_id = record.get("source_id")
    title = record.get("title")
    published_at = record.get("published_at")
    if not all(isinstance(value, str) and value for value in (source_id, title, published_at)):
        raise ValueError("extractor record is missing source_id, title, or published_at")
    attachments = record.get("attachments")
    if not isinstance(attachments, list) or any(not isinstance(item, dict) for item in attachments):
        raise ValueError("extractor record attachments must be an object list")
    sections = record.get("announcement_sections")
    event_data = record.get("event_data")
    if not isinstance(sections, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in sections.items()
    ):
        raise ValueError("extractor record announcement_sections must map strings to strings")
    if not isinstance(event_data, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in event_data.items()
    ):
        raise ValueError("extractor record event_data must map strings to strings")
    document_type = None
    if attachments:
        first_url = attachments[0].get("source_url") or attachments[0].get("url")
        if isinstance(first_url, str) and "." in first_url:
            document_type = first_url.rsplit(".", maxsplit=1)[-1].split("?", maxsplit=1)[0].upper()
    return Announcement(
        sgxnet_id=source_id,
        symbol=target_symbol.upper(),
        title=title,
        announcement_type=(
            record.get("category") if isinstance(record.get("category"), str) else None
        ),
        published_at=_normalise_timestamp(published_at),
        url=record.get("source_url") if isinstance(record.get("source_url"), str) else None,
        document_type=document_type,
        content_hash=(
            record.get("content_hash") if isinstance(record.get("content_hash"), str) else None
        ),
        source="sgx_public_website",
        announcement_sections=sections,
        event_type=(
            record.get("event_type")
            if isinstance(record.get("event_type"), str)
            else "unclassified"
        ),
        event_data=event_data,
        attachments=tuple(attachments),
    )


def _parse_response(payload: Any) -> tuple[Announcement, ...]:
    if not isinstance(payload, dict):
        raise ValueError("response root must be an object")
    values = payload.get("announcements")
    if not isinstance(values, list):
        raise ValueError("announcements must be a list")
    if any(not isinstance(value, dict) for value in values):
        raise ValueError("every announcement must be an object")
    return tuple(Announcement.from_payload(value) for value in values)


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"announcement {key} must be a non-empty string")
    return value.strip()


def _optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"announcement {key} must be a string or null")
    return value.strip() or None


def _normalise_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("announcement publishedAt must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("announcement publishedAt must include a timezone")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _sgx_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y%m%d_%H%M%S")


def _elapsed_ms(started: float, finished: float) -> int:
    return max(0, round((finished - started) * 1000))
