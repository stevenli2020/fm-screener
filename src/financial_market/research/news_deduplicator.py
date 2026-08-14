from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from financial_market.storage import connect_database

from .news_collector import Announcement


@dataclass(frozen=True, slots=True)
class StoredAnnouncement:
    announcement: Announcement
    document_hash: str
    retrieved_at: str
    disposition: str


def compute_document_hash(symbol: str, title: str, published_at: str) -> str:
    canonical = "\x1f".join((symbol.strip().upper(), title.strip(), published_at.strip()))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def store_announcements(
    database_path: Path,
    announcements: tuple[Announcement, ...],
    retrieved_at: datetime,
) -> tuple[StoredAnnouncement, ...]:
    retrieved_value = retrieved_at.isoformat().replace("+00:00", "Z")
    connection = connect_database(database_path)
    stored: list[StoredAnnouncement] = []
    try:
        with connection:
            for announcement in announcements:
                document_hash = announcement.content_hash or compute_document_hash(
                    announcement.symbol, announcement.title, announcement.published_at
                )
                existing = connection.execute(
                    "SELECT document_hash FROM news_records WHERE sgxnet_id = ?",
                    (announcement.sgxnet_id,),
                ).fetchone()
                cursor = connection.execute(
                    """
                    INSERT INTO news_records (
                        sgxnet_id, symbol, title, type, published_at, retrieved_at,
                        url, document_type, document_hash, source,
                        announcement_sections_json, event_type, event_data_json,
                        attachments_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(sgxnet_id) DO UPDATE SET
                        symbol = excluded.symbol,
                        title = excluded.title,
                        type = excluded.type,
                        published_at = excluded.published_at,
                        retrieved_at = excluded.retrieved_at,
                        url = excluded.url,
                        document_type = excluded.document_type,
                        document_hash = excluded.document_hash,
                        source = excluded.source,
                        announcement_sections_json = excluded.announcement_sections_json,
                        event_type = excluded.event_type,
                        event_data_json = excluded.event_data_json,
                        attachments_json = excluded.attachments_json
                    WHERE news_records.document_hash != excluded.document_hash
                    """,
                    (
                        announcement.sgxnet_id,
                        announcement.symbol,
                        announcement.title,
                        announcement.announcement_type,
                        announcement.published_at,
                        retrieved_value,
                        announcement.url,
                        announcement.document_type,
                        document_hash,
                        announcement.source,
                        json.dumps(
                            announcement.announcement_sections or {},
                            ensure_ascii=False,
                        ),
                        announcement.event_type,
                        json.dumps(announcement.event_data or {}, ensure_ascii=False),
                        json.dumps(announcement.attachments, ensure_ascii=False),
                    ),
                )
                row = connection.execute(
                    "SELECT retrieved_at FROM news_records "
                    "WHERE document_hash = ? OR sgxnet_id = ?",
                    (document_hash, announcement.sgxnet_id),
                ).fetchone()
                stored.append(
                    StoredAnnouncement(
                        announcement=announcement,
                        document_hash=document_hash,
                        retrieved_at=row[0] if row else retrieved_value,
                        disposition=(
                            "new"
                            if existing is None
                            else "replacement"
                            if existing[0] != document_hash and cursor.rowcount == 1
                            else "duplicate"
                        ),
                    )
                )
    except sqlite3.Error as exc:
        raise ValueError(f"cannot store SGX announcements: {exc}") from exc
    finally:
        connection.close()
    return tuple(stored)
