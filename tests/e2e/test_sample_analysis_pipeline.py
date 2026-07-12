from portfolio_analytics.models import AnalysisSettings
from portfolio_analytics.pipeline import analyze_uploaded_workbook
from portfolio_analytics.workbook import build_upload_template_bytes


def test_generated_sample_workbook_runs_through_analysis_pipeline():
    workbook, analysis = analyze_uploaded_workbook(
        build_upload_template_bytes(include_examples=True),
        AnalysisSettings(),
    )

    assert not workbook.transactions.empty
    assert not workbook.prices.empty
    assert not workbook.composition.empty
    assert not analysis.daily_portfolio.empty
