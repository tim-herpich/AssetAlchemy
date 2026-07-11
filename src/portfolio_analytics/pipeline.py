from __future__ import annotations

from io import BytesIO

from .engine import build_analysis
from .models import AnalysisSettings, PortfolioAnalysis, PortfolioWorkbook
from .workbook import parse_workbook


def analyze_uploaded_workbook(file_bytes: bytes, settings: AnalysisSettings) -> tuple[PortfolioWorkbook, PortfolioAnalysis]:
    workbook = parse_workbook(BytesIO(file_bytes))
    analysis = build_analysis(
        workbook,
        annual_risk_free_rate=settings.annual_risk_free_rate,
        forward_fill_prices=settings.forward_fill_prices,
    )
    return workbook, analysis

