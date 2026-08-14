from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from financial_market.config import ConfigurationError, Settings
from financial_market.market_data.client import DataServerClient
from financial_market.market_data.errors import MarketDataError
from financial_market.research.news_collector import SGXPublicPageClient
from financial_market.research.news_pipeline import NewsPipelineError, collect_news
from financial_market.research.news_reporter import generate_json_feed, generate_markdown_report
from financial_market.risk import RiskRules
from financial_market.screening.eligibility import EligibilityPolicy, EligibilityPolicyError
from financial_market.screening.reporter import render_report
from financial_market.screening.screener import run_screening
from financial_market.storage import initialize_database
from financial_market.universe import UniverseError, load_universe, read_universe_csv


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fm", description="Financial Market SGX CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health", help="check the FinancialMarket data server")

    ohlcv = subparsers.add_parser("ohlcv", help="fetch adjusted OHLCV from the data server")
    ohlcv.add_argument("ticker")
    ohlcv.add_argument("--frequency", default="1d")
    ohlcv.add_argument("--start-date", type=_date)
    ohlcv.add_argument("--end-date", type=_date)
    ohlcv.add_argument("--force-refresh", action="store_true")

    init_db = subparsers.add_parser("init-db", help="initialize the SQLite database")
    init_db.add_argument("--path", type=Path)
    subparsers.add_parser("validate-config", help="validate settings and SGX risk rules")

    universe = subparsers.add_parser("universe", help="validate or load the SGX universe")
    universe_commands = universe.add_subparsers(dest="universe_command", required=True)
    universe_validate = universe_commands.add_parser("validate", help="validate the universe CSV")
    universe_validate.add_argument("--path", type=Path)
    universe_load = universe_commands.add_parser("load", help="validate data and load securities")
    universe_load.add_argument("--path", type=Path)
    universe_load.add_argument("--database", type=Path)
    universe_load.add_argument(
        "--skip-data-validation",
        action="store_true",
        help="load only after CSV validation; intended for offline database setup",
    )
    universe_reload = universe_commands.add_parser(
        "reload", help="backup and rebuild the database from the current universe CSV"
    )
    universe_reload.add_argument("--path", type=Path)
    universe_reload.add_argument("--database", type=Path)
    universe_reload.add_argument("--skip-data-validation", action="store_true")
    screening = subparsers.add_parser("screening", help="run deterministic Phase A screening")
    screening_commands = screening.add_subparsers(dest="screening_command", required=True)
    screening_run = screening_commands.add_parser("run", help="screen the current SGX universe")
    screening_run.add_argument("--as-of-date", type=_date)
    screening_run.add_argument("--database", type=Path)
    screening_run.add_argument("--output-dir", type=Path, default=Path("reports/generated"))
    dry_run = screening_commands.add_parser(
        "dry-run", help="replay recent dates; this is not a backtest"
    )
    dry_run.add_argument("--days", type=int, default=5)
    dry_run.add_argument("--database", type=Path)
    dry_run.add_argument("--output-dir", type=Path, default=Path("reports/generated"))
    news = subparsers.add_parser("news", help="collect SGX announcements for M3 candidates")
    news_commands = news.add_subparsers(dest="news_command", required=True)
    news_collect = news_commands.add_parser("collect", help="fetch, deduplicate, and report news")
    news_collect.add_argument(
        "--input", type=Path, default=Path("reports/generated/pending_candidates.json")
    )
    news_collect.add_argument("--run-date", type=_date)
    news_collect.add_argument("--lookback-days", type=int, default=2)
    news_collect.add_argument("--database", type=Path)
    news_collect.add_argument("--output-dir", type=Path, default=Path("reports/generated"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
        if args.command == "validate-config":
            rules = RiskRules.from_file(settings.risk_rules_path)
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "risk_rules": str(settings.risk_rules_path),
                        "schema_version": rules.schema_version,
                        "execution_mode": rules.execution_mode,
                    }
                )
            )
            return 0
        if args.command == "init-db":
            database_path = args.path or settings.database_path
            initialize_database(database_path)
            print(json.dumps({"status": "ok", "database": str(database_path)}))
            return 0
        if args.command == "universe":
            source_path = args.path or settings.universe_path
            if args.universe_command == "validate":
                definitions = read_universe_csv(source_path)
                print(
                    json.dumps(
                        {
                            "status": "ok",
                            "universe": str(source_path),
                            "security_count": len(definitions),
                        }
                    )
                )
                return 0
            database_path = args.database or settings.database_path
            if args.universe_command == "reload":
                backup_path = None
                if database_path.exists():
                    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
                    backup_path = database_path.with_name(
                        f"{database_path.name}.before-reload-{stamp}"
                    )
                    shutil.copy2(database_path, backup_path)
                    database_path.unlink()
                if args.skip_data_validation:
                    result = load_universe(source_path, database_path, validate_data=False)
                else:
                    with DataServerClient(settings) as client:
                        result = load_universe(source_path, database_path, client=client)
                print(
                    json.dumps(
                        {
                            "status": "ok",
                            "universe": str(result.source_path),
                            "loaded_count": result.loaded_count,
                            "validated_count": result.validated_count,
                            "database": str(database_path),
                            "backup": str(backup_path) if backup_path else None,
                        }
                    )
                )
                return 0
            if args.skip_data_validation:
                result = load_universe(
                    source_path,
                    database_path,
                    validate_data=False,
                )
            else:
                with DataServerClient(settings) as client:
                    result = load_universe(source_path, database_path, client=client)
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "universe": str(result.source_path),
                        "loaded_count": result.loaded_count,
                        "validated_count": result.validated_count,
                        "database": str(database_path),
                    }
                )
            )
            return 0
        if args.command == "screening":
            rules = RiskRules.from_file(settings.risk_rules_path)
            policy = EligibilityPolicy.from_file(settings.screening_eligibility_path)
            database_path = args.database or settings.database_path
            if args.screening_command == "run":
                with DataServerClient(settings) as client:
                    result = run_screening(database_path, client, rules, policy, args.as_of_date)
                paths = _write_screening_outputs(result, args.output_dir)
                print(json.dumps({"status": "ok", **result, "outputs": paths}))
                return 0
            if args.days < 1:
                raise ValueError("--days must be at least 1")
            # A historical replay verifies deterministic operation; it does not compute returns.
            summaries = []
            for offset in range(args.days - 1, -1, -1):
                with DataServerClient(settings) as client:
                    result = run_screening(
                        database_path, client, rules, policy, date.today() - timedelta(days=offset)
                    )
                summaries.append(
                    {
                        "run_date": result["run_date"],
                        "matched": result["candidates_matched"],
                        "eligible": result["eligible_count"],
                        "screened": result["candidates_screened"],
                    }
                )
            args.output_dir.mkdir(parents=True, exist_ok=True)
            metrics_path = args.output_dir / "dry_run_metrics.json"
            metrics_path.write_text(
                json.dumps(
                    {
                        "mode": "historical_replay_not_backtest",
                        "days": args.days,
                        "runs": summaries,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "mode": "historical_replay_not_backtest",
                        "runs": summaries,
                        "metrics": str(metrics_path),
                    }
                )
            )
            return 0
        if args.command == "news":
            database_path = args.database or settings.database_path
            with SGXPublicPageClient(
                filters_path=settings.sgx_announcement_filters_path,
                extraction_dir=args.output_dir / "extraction",
                max_pages=settings.sgx_news_max_pages_per_target,
                pacing_seconds=settings.sgx_news_request_pacing_seconds,
            ) as client:
                result = collect_news(
                    args.input,
                    database_path,
                    client,
                    client.endpoint,
                    args.run_date,
                    lookback_days=args.lookback_days,
                )
            paths = _write_news_outputs(result, args.output_dir)
            successful = result["api_status"] == "success"
            print(
                json.dumps({"status": "ok" if successful else "error", **result, "outputs": paths})
            )
            return 0 if successful else 1

        with DataServerClient(settings) as client:
            if args.command == "health":
                status = client.health()
                print(
                    json.dumps(
                        {
                            "status": status.status,
                            "engine": status.engine,
                            "supports_date_range": status.supports_date_range,
                            "pid": status.pid,
                        }
                    )
                )
                return 0 if status.status == "ok" else 1
            series = client.get_ohlcv(
                args.ticker,
                frequency=args.frequency,
                start_date=args.start_date,
                end_date=args.end_date,
                force_refresh=args.force_refresh,
            )
            print(
                json.dumps(
                    {
                        "ticker": series.ticker,
                        "frequency": series.frequency,
                        "bar_count": len(series.rows),
                        "first_timestamp": series.rows[0].timestamp.isoformat()
                        if series.rows
                        else None,
                        "last_timestamp": series.rows[-1].timestamp.isoformat()
                        if series.rows
                        else None,
                    }
                )
            )
            return 0
    except (
        ConfigurationError,
        EligibilityPolicyError,
        MarketDataError,
        NewsPipelineError,
        UniverseError,
        ValueError,
    ) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 2


def _write_screening_outputs(result: dict[str, object], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "pending_candidates.json"
    report_path = output_dir / f"screening_report_{result['run_date']}.md"
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(render_report(result), encoding="utf-8")
    return {"json": str(json_path), "report": str(report_path)}


def _write_news_outputs(result: dict[str, object], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "news_feed.json"
    report_path = output_dir / f"news_report_{result['run_date']}.md"
    json_path.write_text(
        json.dumps(generate_json_feed(result), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(generate_markdown_report(result), encoding="utf-8")
    return {"json": str(json_path), "report": str(report_path)}


if __name__ == "__main__":
    raise SystemExit(main())
