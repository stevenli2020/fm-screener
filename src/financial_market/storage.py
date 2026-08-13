from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "db" / "schema.sql"


def connect_database(database_path: Path) -> sqlite3.Connection:
    """Open an application SQLite connection with integrity constraints enabled."""
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(database_path: Path) -> None:
    """Create the Phase 1 SQLite schema without destroying existing records."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    connection = connect_database(database_path)
    try:
        connection.executescript(schema)
        connection.commit()
    finally:
        connection.close()
