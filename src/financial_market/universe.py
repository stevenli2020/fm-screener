from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from financial_market.market_data.client import DataServerClient
from financial_market.market_data.errors import MarketDataError
from financial_market.storage import connect_database, initialize_database


class UniverseError(ValueError):
    """Raised when the configured SGX universe is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class SecurityDefinition:
    symbol: str
    provider_symbol: str
    company_name: str
    sector: str
    notes: str
    instrument_type: str


@dataclass(frozen=True, slots=True)
class DataCoverage:
    bar_count: int
    first_date: date | None
    last_date: date | None
    candle_repair_count: int


@dataclass(frozen=True, slots=True)
class UniverseLoadResult:
    source_path: Path
    loaded_count: int
    validated_count: int


def read_universe_csv(path: Path) -> tuple[SecurityDefinition, ...]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as source:
            reader = csv.DictReader(source)
            _validate_headers(reader.fieldnames)
            definitions = tuple(
                _parse_row(row, row_number) for row_number, row in enumerate(reader, 2)
            )
    except OSError as exc:
        raise UniverseError(f"cannot read universe file: {path}") from exc
    if not definitions:
        raise UniverseError("universe file must contain at least one security")
    duplicates = _duplicates(definition.symbol for definition in definitions)
    if duplicates:
        raise UniverseError(
            f"universe contains duplicate symbol(s): {', '.join(sorted(duplicates))}"
        )
    return definitions


def validate_data_coverage(
    definitions: tuple[SecurityDefinition, ...], client: DataServerClient
) -> dict[str, DataCoverage]:
    coverage: dict[str, DataCoverage] = {}
    for definition in definitions:
        try:
            series = client.get_ohlcv(definition.provider_symbol, frequency="1d")
        except (MarketDataError, ValueError) as exc:
            raise UniverseError(
                f"data validation failed for {definition.provider_symbol}: {exc}"
            ) from exc
        if not series.rows:
            raise UniverseError(f"provider returned no data for {definition.provider_symbol}")
        coverage[definition.symbol] = DataCoverage(
            bar_count=len(series.rows),
            first_date=series.rows[0].timestamp.date(),
            last_date=series.rows[-1].timestamp.date(),
            candle_repair_count=series.candle_repair_count,
        )
    return coverage


def persist_universe(
    database_path: Path,
    definitions: tuple[SecurityDefinition, ...],
    coverage: dict[str, DataCoverage] | None = None,
) -> int:
    initialize_database(database_path)
    connection = connect_database(database_path)
    try:
        with connection:
            for definition in definitions:
                metadata = {"notes": definition.notes, "source": "config/universe_sgx.csv"}
                if coverage and definition.symbol in coverage:
                    value = coverage[definition.symbol]
                    metadata["data_coverage"] = {
                        "frequency": "1d",
                        "bar_count": value.bar_count,
                        "first_date": value.first_date.isoformat() if value.first_date else None,
                        "last_date": value.last_date.isoformat() if value.last_date else None,
                        "price_adjustment": "split_and_dividend_adjusted",
                        "candle_repair_count": value.candle_repair_count,
                    }
                connection.execute(
                    """
                    INSERT INTO securities (
                        symbol, provider_symbol, company_name, sector,
                        instrument_type, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        provider_symbol = excluded.provider_symbol,
                        company_name = excluded.company_name,
                        sector = excluded.sector,
                        instrument_type = excluded.instrument_type,
                        metadata_json = excluded.metadata_json,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        definition.symbol,
                        definition.provider_symbol,
                        definition.company_name,
                        definition.sector,
                        definition.instrument_type,
                        json.dumps(metadata, sort_keys=True),
                    ),
                )
        return len(definitions)
    except sqlite3.Error as exc:
        raise UniverseError(f"cannot persist universe: {exc}") from exc
    finally:
        connection.close()


def load_universe(
    source_path: Path,
    database_path: Path,
    *,
    client: DataServerClient | None = None,
    validate_data: bool = True,
) -> UniverseLoadResult:
    definitions = read_universe_csv(source_path)
    if validate_data and client is None:
        raise UniverseError("a data-server client is required when data validation is enabled")
    coverage = validate_data_coverage(definitions, client) if validate_data and client else None
    loaded_count = persist_universe(database_path, definitions, coverage)
    return UniverseLoadResult(
        source_path=source_path,
        loaded_count=loaded_count,
        validated_count=len(coverage) if coverage is not None else 0,
    )


def _validate_headers(headers: list[str] | None) -> None:
    required = {"symbol", "company_name", "sector", "notes"}
    available = set(headers or [])
    missing = sorted(required.difference(available))
    if missing:
        raise UniverseError(f"universe file is missing column(s): {', '.join(missing)}")


def _parse_row(row: dict[str, str | None], row_number: int) -> SecurityDefinition:
    values = {
        key: (row.get(key) or "").strip() for key in ("symbol", "company_name", "sector", "notes")
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise UniverseError(f"universe row {row_number} is missing: {', '.join(missing)}")
    symbol = values["symbol"].upper()
    if not symbol.replace("-", "").isalnum():
        raise UniverseError(f"universe row {row_number} has invalid symbol: {values['symbol']!r}")
    notes = values["notes"]
    instrument_type = (
        "reit" if "reit" in notes.lower() else "etf" if "etf" in notes.lower() else "equity"
    )
    return SecurityDefinition(
        symbol=symbol,
        provider_symbol=f"{symbol}.SI",
        company_name=values["company_name"],
        sector=values["sector"],
        notes=notes,
        instrument_type=instrument_type,
    )


def _duplicates(values: object) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates
