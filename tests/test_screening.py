from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from financial_market.market_data.models import OHLCVBar, OHLCVSeries
from financial_market.risk import RiskRules
from financial_market.screening.eligibility import EligibilityPolicy, eligibility_reasons
from financial_market.screening.ranker import rank_candidates
from financial_market.screening.reporter import render_report
from financial_market.screening.screener import run_screening
from financial_market.screening.signals import (
    signal_52week_extremes,
    signal_donchian_breakout,
    signal_price_move_60d,
    signal_volatility_20d,
    signal_volume_spike,
)
from financial_market.storage import connect_database, initialize_database

ROOT = Path(__file__).parents[1]


def bars(count: int = 120, flat: bool = False) -> tuple[OHLCVBar, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return tuple(
        OHLCVBar(
            start + timedelta(days=i),
            10 if flat else 10 + i / 10,
            10 if flat else 11 + i / 10,
            10 if flat else 9 + i / 10,
            10 if flat else 10 + i / 10,
            1000 if i < count - 1 else 3000,
        )
        for i in range(count)
    )


def test_signals_and_edges() -> None:
    values = bars()
    assert signal_price_move_60d(values)["move_pct"] == 36.87
    assert signal_volume_spike(values)["spike_multiple"] == 3.0
    assert signal_52week_extremes(values)["pct_below_52w_high"] == 4.37
    assert signal_volatility_20d(values)["volatility_annual_pct"] is not None
    assert signal_donchian_breakout(values)["pct_of_range"] == 86.5
    assert signal_price_move_60d(values[:59])["reason"] == "insufficient_bars"
    assert signal_volume_spike(values[:19])["reason"] == "insufficient_bars"
    assert signal_donchian_breakout(bars(55, True))["reason"] == "zero_range"


def test_eligibility_reasons() -> None:
    policy = EligibilityPolicy.from_file(ROOT / "config" / "screening_eligibility_sgx.json")
    security = {
        "instrument_type": "etf",
        "metadata": {
            "data_coverage": {
                "bar_count": 119,
                "candle_repair_count": 6,
                "price_adjustment": "raw",
                "last_date": "2026-01-01",
            }
        },
    }
    assert eligibility_reasons(security, policy, date(2026, 1, 10)) == [
        "instrument_type_excluded",
        "insufficient_history",
        "excessive_candle_repairs",
        "invalid_price_adjustment",
        "stale_data",
    ]


def test_ranker_and_report() -> None:
    weak = {
        "symbol": "ZZZ",
        "matched_signals": ["a"],
        "signals": {
            "52wk_extremes": {"pct_below_52w_high": 5, "pct_above_52w_low": 1},
            "volume_spike": {"spike_multiple": 2},
        },
    }
    strong = {
        "symbol": "AAA",
        "matched_signals": ["a", "b"],
        "signals": {
            "52wk_extremes": {"pct_below_52w_high": 1, "pct_above_52w_low": 10},
            "volume_spike": {"spike_multiple": 1},
        },
    }
    ranked = rank_candidates([weak, strong])
    assert [x["symbol"] for x in ranked] == ["AAA", "ZZZ"]
    report = render_report(
        {
            "run_date": "2026-04-30",
            "universe_count": 2,
            "eligible_count": 2,
            "candidates_screened": 2,
            "candidates_matched": 1,
            "ranked_candidates": [
                {
                    **strong,
                    "rank": 1,
                    "signals": {
                        "price_move_60d": {"move_pct": 10},
                        "volume_spike": {"spike_multiple": 2},
                        "52wk_extremes": {"pct_below_52w_high": 1},
                        "donchian_55d": {"pct_of_range": 90},
                    },
                }
            ],
            "rejected": [{"symbol": "ZZZ", "reason": "no_signal_match", "rejection_reasons": []}],
        }
    )
    assert "| 1 | AAA |  | a, b |" in report and "ZZZ" in report


class Client:
    def __init__(self, series: OHLCVSeries) -> None:
        self.series = series

    def get_ohlcv(self, ticker: str, **_: object) -> OHLCVSeries:
        return self.series


def test_screener_persists_every_security(tmp_path: Path) -> None:
    db = tmp_path / "screen.sqlite3"
    initialize_database(db)
    metadata = json.dumps(
        {
            "data_coverage": {
                "bar_count": 120,
                "candle_repair_count": 0,
                "price_adjustment": "split_and_dividend_adjusted",
                "last_date": "2026-04-30",
            }
        }
    )
    con = connect_database(db)
    try:
        with con:
            for symbol, kind in (("AAA", "equity"), ("ETF", "etf")):
                con.execute(
                    "INSERT INTO securities (symbol, provider_symbol, company_name, sector, "
                    "instrument_type, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (symbol, f"{symbol}.SI", symbol, "test", kind, metadata),
                )
    finally:
        con.close()
    result = run_screening(
        db,
        Client(OHLCVSeries("AAA.SI", "1d", "split_and_dividend_adjusted", bars())),
        RiskRules.from_file(ROOT / "config" / "risk_rules_sgx.json"),
        EligibilityPolicy.from_file(ROOT / "config" / "screening_eligibility_sgx.json"),
        date(2026, 4, 30),
    )
    assert result["universe_count"] == 2 and result["eligible_count"] == 1
    con = connect_database(db)
    try:
        assert con.execute("SELECT COUNT(*) FROM screening_results").fetchone()[0] == 2
    finally:
        con.close()
