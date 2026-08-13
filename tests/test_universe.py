from __future__ import annotations

import csv
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from financial_market.market_data.models import OHLCVBar, OHLCVSeries
from financial_market.universe import (
    DataCoverage,
    UniverseError,
    load_universe,
    persist_universe,
    read_universe_csv,
    validate_data_coverage,
)

PROJECT_ROOT = Path(__file__).parents[1]


class FakeDataClient:
    def __init__(self, *, fail_symbol: str | None = None) -> None:
        self.fail_symbol = fail_symbol
        self.requested: list[str] = []

    def get_ohlcv(self, ticker: str, *, frequency: str = "1d") -> OHLCVSeries:
        self.requested.append(ticker)
        if ticker == self.fail_symbol:
            raise UniverseError(f"simulated missing data for {ticker}")
        return OHLCVSeries(
            ticker=ticker,
            frequency=frequency,
            price_adjustment="split_and_dividend_adjusted",
            rows=(
                OHLCVBar(datetime(2024, 1, 2, tzinfo=UTC), 10, 11, 9, 10.5, 1000),
                OHLCVBar(datetime(2024, 1, 3, tzinfo=UTC), 10.5, 12, 10, 11.5, 1200),
            ),
        )


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=["symbol", "company_name", "sector", "notes"])
        writer.writeheader()
        writer.writerows(rows)


def test_repository_universe_parses_expected_security_types() -> None:
    definitions = read_universe_csv(PROJECT_ROOT / "config" / "universe_sgx.csv")
    by_symbol = {definition.symbol: definition for definition in definitions}

    assert len(definitions) == 42
    assert by_symbol["D05"].provider_symbol == "D05.SI"
    assert by_symbol["C38U"].instrument_type == "reit"
    assert by_symbol["ES3"].instrument_type == "etf"


def test_universe_rejects_duplicate_symbol(tmp_path: Path) -> None:
    source = tmp_path / "universe.csv"
    write_csv(
        source,
        [
            {"symbol": "D05", "company_name": "DBS", "sector": "Banking", "notes": "Blue chip"},
            {
                "symbol": "d05",
                "company_name": "Duplicate",
                "sector": "Banking",
                "notes": "Blue chip",
            },
        ],
    )

    with pytest.raises(UniverseError, match="duplicate"):
        read_universe_csv(source)


def test_universe_rejects_empty_file_and_missing_headers(tmp_path: Path) -> None:
    empty = tmp_path / "empty.csv"
    empty.write_text("symbol,company_name,sector,notes\n", encoding="utf-8")
    malformed = tmp_path / "malformed.csv"
    malformed.write_text("symbol,company_name\nD05,DBS\n", encoding="utf-8")

    with pytest.raises(UniverseError, match="at least one"):
        read_universe_csv(empty)
    with pytest.raises(UniverseError, match="missing column"):
        read_universe_csv(malformed)


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (
            {"symbol": "", "company_name": "DBS", "sector": "Banking", "notes": "Blue chip"},
            "missing: symbol",
        ),
        (
            {
                "symbol": "D05!",
                "company_name": "DBS",
                "sector": "Banking",
                "notes": "Blue chip",
            },
            "invalid symbol",
        ),
    ],
)
def test_universe_rejects_invalid_row(tmp_path: Path, row: dict[str, str], message: str) -> None:
    source = tmp_path / "invalid.csv"
    write_csv(source, [row])

    with pytest.raises(UniverseError, match=message):
        read_universe_csv(source)


def test_data_validation_maps_provider_symbols_and_returns_coverage(tmp_path: Path) -> None:
    source = tmp_path / "universe.csv"
    write_csv(
        source,
        [{"symbol": "D05", "company_name": "DBS", "sector": "Banking", "notes": "Blue chip"}],
    )
    definitions = read_universe_csv(source)
    client = FakeDataClient()

    coverage = validate_data_coverage(definitions, client)  # type: ignore[arg-type]

    assert client.requested == ["D05.SI"]
    assert coverage["D05"].bar_count == 2
    assert coverage["D05"].first_date is not None
    assert coverage["D05"].last_date is not None
    assert coverage["D05"].candle_repair_count == 0


def test_persist_universe_stores_metadata_and_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "universe.csv"
    database_path = tmp_path / "market.sqlite3"
    write_csv(
        source,
        [{"symbol": "C38U", "company_name": "CICT", "sector": "Real Estate", "notes": "REIT"}],
    )
    definitions = read_universe_csv(source)
    coverage = {
        "C38U": DataCoverage(2, datetime(2024, 1, 2).date(), datetime(2024, 1, 3).date(), 1)
    }

    assert persist_universe(database_path, definitions, coverage) == 1
    assert persist_universe(database_path, definitions, coverage) == 1

    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            """
            SELECT provider_symbol, instrument_type, metadata_json
            FROM securities WHERE symbol = 'C38U'
            """
        ).fetchone()
        count = connection.execute("SELECT COUNT(*) FROM securities").fetchone()[0]
    finally:
        connection.close()
    metadata = json.loads(row[2])
    assert row[0] == "C38U.SI"
    assert row[1] == "reit"
    assert metadata["data_coverage"]["bar_count"] == 2
    assert metadata["data_coverage"]["candle_repair_count"] == 1
    assert count == 1


def test_load_fails_before_database_write_when_data_validation_fails(tmp_path: Path) -> None:
    source = tmp_path / "universe.csv"
    database_path = tmp_path / "market.sqlite3"
    write_csv(
        source,
        [{"symbol": "D05", "company_name": "DBS", "sector": "Banking", "notes": "Blue chip"}],
    )

    with pytest.raises(UniverseError, match="simulated missing"):
        load_universe(source, database_path, client=FakeDataClient(fail_symbol="D05.SI"))  # type: ignore[arg-type]

    assert not database_path.exists()


def test_load_requires_client_when_data_validation_is_enabled(tmp_path: Path) -> None:
    source = tmp_path / "universe.csv"
    write_csv(
        source,
        [{"symbol": "D05", "company_name": "DBS", "sector": "Banking", "notes": "Blue chip"}],
    )

    with pytest.raises(UniverseError, match="client is required"):
        load_universe(source, tmp_path / "market.sqlite3")
