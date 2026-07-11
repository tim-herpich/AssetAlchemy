from __future__ import annotations

from io import BytesIO
import sys
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from portfolio_analytics.engine import build_analysis, build_rolling_performance
from portfolio_analytics.models import PortfolioWorkbook
from portfolio_analytics.workbook import (
    REQUIRED_SHEETS,
    TRANSACTION_EXCEL_HEADERS,
    build_upload_template_bytes,
    parse_workbook,
)


def test_template_contains_exact_required_sheets_and_headers():
    data = build_upload_template_bytes(include_examples=False)
    workbook = load_workbook(BytesIO(data))

    assert workbook.sheetnames == REQUIRED_SHEETS
    tx = workbook["Transactions"]
    assert tx["A1"].value == "All Transactions"
    assert "A1:J1" in {str(rng) for rng in tx.merged_cells.ranges}
    assert [tx.cell(2, col).value for col in range(1, 11)] == TRANSACTION_EXCEL_HEADERS


def test_sample_template_parses_and_builds_dynamic_analysis():
    parsed = parse_workbook(BytesIO(build_upload_template_bytes(include_examples=True)))
    analysis = build_analysis(parsed)

    assert not any(message.severity == "Error" for message in parsed.validation)
    assert set(parsed.workbook_sheets) == set(REQUIRED_SHEETS)
    assert parsed.transactions["asset_id"].nunique() == 3
    assert parsed.prices["asset_id"].nunique() == 3
    assert not analysis.daily_portfolio.empty
    assert analysis.daily_portfolio.iloc[0]["is_baseline"]
    assert analysis.daily_portfolio.iloc[0]["value_eur"] == 0
    assert analysis.allocation["target_weight"].sum() > 0


def test_transfer_is_preserved_but_ignored_for_quantity():
    workbook = _workbook_from_frames(
        transactions=[
            ["Broker", "Asset A", "IE0000000001", "2020-01-01", "XETRA", "Buy", 10, 10, 100, 1, 3],
            ["Broker", "Asset A", "IE0000000001", "2020-01-02", "XETRA", "Transfer", 100, 10, 1000, 0, 4],
        ],
        prices=[
            ["Asset A", "IE0000000001", "2020-01-01", 10, 3, 1],
            ["Asset A", "IE0000000001", "2020-01-02", 11, 4, 1],
        ],
    )
    analysis = build_analysis(workbook)

    latest = analysis.holdings.iloc[0]
    assert latest["quantity"] == 10
    assert latest["value_eur"] == 110


def test_sell_decreases_quantity_and_invested_capital():
    workbook = _workbook_from_frames(
        transactions=[
            ["Broker", "Asset A", "IE0000000001", "2020-01-01", "XETRA", "Buy", 10, 10, 100, 0, 3],
            ["Broker", "Asset A", "IE0000000001", "2020-01-02", "XETRA", "Sell", 4, 12, 48, 1, 4],
        ],
        prices=[
            ["Asset A", "IE0000000001", "2020-01-01", 10, 3, 1],
            ["Asset A", "IE0000000001", "2020-01-02", 12, 4, 1],
        ],
    )
    analysis = build_analysis(workbook)

    latest = analysis.holdings.iloc[0]
    assert latest["quantity"] == 6
    assert latest["total_investment_eur"] == 53
    assert latest["total_fees_eur"] == 1


def test_rolling_5y_uses_inclusive_end_year():
    dates = pd.to_datetime([f"{year}-12-31" for year in range(2019, 2024)])
    daily = pd.DataFrame(
        {
            "date": dates,
            "value_eur": [100, 110, 125, 130, 150],
            "total_investment_eur": [100, 100, 100, 100, 100],
            "total_fees_eur": [0, 0, 0, 0, 0],
            "cash_flow_eur": [0, 0, 0, 0, 0],
            "return_eur": [0, 10, 15, 5, 20],
            "total_return_eur": [0, 10, 25, 30, 50],
            "hpr": [0, 0.10, 0.13636, 0.04, 0.15384],
            "one_plus_hpr": [1, 1.10, 1.13636, 1.04, 1.15384],
            "twr": [0, 0.10, 0.25, 0.30, 0.50],
            "drawdown": [0, 0, 0, 0, 0],
            "drawdown_pct": [0, 0, 0, 0, 0],
            "is_baseline": [False, False, False, False, False],
        }
    )

    rolling = build_rolling_performance(daily, annual_risk_free_rate=0.0)

    assert "2019-2023" in set(rolling["period"])
    row = rolling[rolling["period"] == "2019-2023"].iloc[0]
    assert row["start_year"] == 2019
    assert row["end_year"] == 2023


def _workbook_from_frames(transactions: list[list], prices: list[list]) -> PortfolioWorkbook:
    tx = pd.DataFrame(
        transactions,
        columns=[
            "broker",
            "product",
            "isin",
            "date",
            "exchange",
            "action",
            "quantity",
            "price_eur",
            "cash_flow_eur",
            "fee_eur",
            "source_row",
        ],
    )
    tx["date"] = pd.to_datetime(tx["date"])
    tx["asset_id"] = tx["isin"]
    px = pd.DataFrame(prices, columns=["product", "isin", "date", "price", "source_row", "block"])
    px["date"] = pd.to_datetime(px["date"])
    px["asset_id"] = px["isin"]
    composition = pd.DataFrame(
        [
            {
                "year": 2020,
                "product": "Asset A",
                "asset_id": "Asset A",
                "target_weight": 1.0,
                "tolerance": 0.05,
                "source_row": 3,
                "target_column": "C",
            }
        ]
    )
    return PortfolioWorkbook(
        transactions=tx,
        prices=px,
        composition=composition,
        validation=[],
        workbook_sheets=REQUIRED_SHEETS,
    )
