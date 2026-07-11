from __future__ import annotations

from io import BytesIO

import pandas as pd

from .models import PortfolioAnalysis, PortfolioWorkbook
from .workbook import build_upload_template_bytes


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def build_analysis_workbook_bytes(workbook: PortfolioWorkbook, analysis: PortfolioAnalysis) -> bytes:
    output = BytesIO()
    sheets = {
        "Portfolio Composition": workbook.composition,
        "Historical Prices": workbook.prices,
        "Transactions": workbook.transactions,
        "Daily Portfolio": analysis.daily_portfolio,
        "Daily Positions": analysis.daily_asset,
        "Annual Performance": analysis.annual,
        "Rolling Performance": analysis.rolling,
        "Allocation Analysis": analysis.allocation,
        "Risk By Asset": analysis.risk_by_asset,
        "Validation Report": workbook.validation_frame(),
    }
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            safe = _safe_sheet_name(sheet_name)
            df.to_excel(writer, index=False, sheet_name=safe)
            ws = writer.book[safe]
            ws.freeze_panes = "A2"
            for column_cells in ws.columns:
                values = [str(cell.value) for cell in column_cells[:100] if cell.value is not None]
                width = min(max([len(v) for v in values] + [10]) + 2, 42)
                ws.column_dimensions[column_cells[0].column_letter].width = width
    output.seek(0)
    return output.getvalue()


def blank_template_bytes() -> bytes:
    return build_upload_template_bytes(include_examples=False)


def sample_template_bytes() -> bytes:
    return build_upload_template_bytes(include_examples=True)


def _safe_sheet_name(name: str) -> str:
    return name[:31].replace(":", " ").replace("/", " ").replace("\\", " ")
