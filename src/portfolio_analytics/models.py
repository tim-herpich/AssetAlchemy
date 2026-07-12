from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class ValidationMessage:
    severity: str
    sheet: str
    message: str
    rows: str = ""


@dataclass
class PortfolioWorkbook:
    transactions: pd.DataFrame
    prices: pd.DataFrame
    composition: pd.DataFrame
    validation: list[ValidationMessage]
    workbook_sheets: list[str]
    risk_free_rates: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(
            columns=[
                "year",
                "country",
                "yield_1y",
                "yield_3y",
                "yield_5y",
                "yield_10y",
                "yield_20y",
                "yield_30y",
            ]
        )
    )
    daily_performance_reference: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(
            columns=[
                "date",
                "portfolio_value_eur",
                "total_investment_eur",
                "total_fees_eur",
                "cash_flow_eur",
                "return_eur",
                "total_return_eur",
                "hpr",
                "one_plus_hpr",
                "twr",
                "source_row",
            ]
        )
    )

    @property
    def has_errors(self) -> bool:
        return any(msg.severity == "Error" for msg in self.validation)

    def validation_frame(self) -> pd.DataFrame:
        if not self.validation:
            return pd.DataFrame(
                [{"severity": "Info", "sheet": "Workbook", "message": "No validation findings.", "rows": ""}]
            )
        return pd.DataFrame([msg.__dict__ for msg in self.validation])


@dataclass
class PortfolioAnalysis:
    asset_master: pd.DataFrame
    daily_asset: pd.DataFrame
    daily_portfolio: pd.DataFrame
    annual: pd.DataFrame
    rolling: pd.DataFrame
    allocation: pd.DataFrame
    holdings: pd.DataFrame
    monthly_returns: pd.DataFrame
    correlation: pd.DataFrame
    risk_by_asset: pd.DataFrame
    diversification: dict[str, float]
    transaction_summary: pd.DataFrame
    fees_by_broker: pd.DataFrame
    fees_by_asset: pd.DataFrame
    metrics: dict[str, float]
    reconciliation: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass(frozen=True)
class AnalysisSettings:
    forward_fill_prices: bool = True
    text_date_mode: str = "strict"
