import sqlite3
from pathlib import Path

import pytest

from financial_market.storage import connect_database, initialize_database


def test_initialize_database_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "market.sqlite3"

    initialize_database(database_path)
    initialize_database(database_path)

    connection = connect_database(database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        version = connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    finally:
        connection.close()

    assert {
        "securities",
        "screening_runs",
        "screening_results",
        "research_documents",
        "trade_proposals",
        "portfolio_transactions",
        "cash_ledger_entries",
        "portfolio_snapshots",
        "portfolio_positions",
        "trade_tickets",
        "audit_events",
        "news_records",
        "news_api_log",
    }.issubset(tables)
    assert version == 3
    assert foreign_keys == 1


def test_executed_manual_ticket_requires_manifest(tmp_path: Path) -> None:
    database_path = tmp_path / "market.sqlite3"
    initialize_database(database_path)
    connection = connect_database(database_path)
    try:
        connection.execute(
            """
            INSERT INTO securities (symbol, provider_symbol, company_name)
            VALUES ('D05', 'D05.SI', 'DBS Group Holdings Ltd')
            """
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO trade_tickets (symbol, side, quantity, status)
                VALUES ('D05', 'buy', 100, 'executed_manual')
                """
            )
        connection.execute(
            """
            INSERT INTO trade_tickets (
                symbol, side, quantity, status, execution_manifest_json
            ) VALUES ('D05', 'buy', 100, 'executed_manual', '{"source":"manual"}')
            """
        )
        count = connection.execute("SELECT COUNT(*) FROM trade_tickets").fetchone()[0]
    finally:
        connection.close()

    assert count == 1


def test_schema_v3_migrates_existing_news_table(tmp_path: Path) -> None:
    database_path = tmp_path / "market.sqlite3"
    initialize_database(database_path)
    connection = connect_database(database_path)
    try:
        with connection:
            connection.execute("DROP TABLE news_records")
            connection.execute(
                """
                CREATE TABLE news_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sgxnet_id TEXT NOT NULL UNIQUE,
                    symbol TEXT NOT NULL REFERENCES securities(symbol),
                    title TEXT NOT NULL,
                    type TEXT,
                    published_at TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    url TEXT,
                    document_type TEXT,
                    document_hash TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL DEFAULT 'sgx_api',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute("DELETE FROM schema_versions WHERE version = 3")
    finally:
        connection.close()

    initialize_database(database_path)
    connection = connect_database(database_path)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(news_records)")}
        version = connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
    finally:
        connection.close()

    assert {
        "announcement_sections_json",
        "event_type",
        "event_data_json",
        "attachments_json",
    }.issubset(columns)
    assert version == 3
