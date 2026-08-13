import json
import sqlite3
from pathlib import Path

from financial_market import cli


def test_init_db_command(tmp_path: Path, capsys) -> None:
    database_path = tmp_path / "cli.sqlite3"

    result = cli.main(["init-db", "--path", str(database_path)])

    output = json.loads(capsys.readouterr().out)
    assert result == 0
    assert output["status"] == "ok"
    assert database_path.exists()


def test_validate_config_command(capsys) -> None:
    result = cli.main(["validate-config"])

    output = json.loads(capsys.readouterr().out)
    assert result == 0
    assert output["status"] == "ok"
    assert output["execution_mode"] == "manual_only"


def test_universe_validate_and_offline_load(tmp_path: Path, capsys) -> None:
    database_path = tmp_path / "universe.sqlite3"

    validate_result = cli.main(["universe", "validate"])
    validate_output = json.loads(capsys.readouterr().out)
    load_result = cli.main(
        ["universe", "load", "--database", str(database_path), "--skip-data-validation"]
    )
    load_output = json.loads(capsys.readouterr().out)

    connection = sqlite3.connect(database_path)
    try:
        count = connection.execute("SELECT COUNT(*) FROM securities").fetchone()[0]
    finally:
        connection.close()
    assert validate_result == 0
    assert validate_output["security_count"] == 42
    assert load_result == 0
    assert load_output["loaded_count"] == 42
    assert load_output["validated_count"] == 0
    assert count == 42


def test_universe_reload_backs_up_existing_database(tmp_path: Path, capsys) -> None:
    database_path = tmp_path / "universe.sqlite3"
    cli.main(["init-db", "--path", str(database_path)])
    capsys.readouterr()
    connection = sqlite3.connect(database_path)
    connection.execute("insert into securities (symbol, provider_symbol, company_name, sector, instrument_type) values ('STALE', 'STALE.SI', 'Stale', 'Test', 'equity')")
    connection.commit()
    connection.close()

    result = cli.main(
        [
            "universe",
            "reload",
            "--database",
            str(database_path),
            "--skip-data-validation",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    connection = sqlite3.connect(database_path)
    count = connection.execute("select count(*) from securities").fetchone()[0]
    connection.close()
    assert result == 0
    assert output["loaded_count"] == 42
    assert output["backup"]
    assert count == 42
