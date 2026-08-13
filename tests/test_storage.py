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
    }.issubset(tables)
    assert version == 1
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
