from __future__ import annotations

import pandas as pd
import streamlit as st

from portfolio_analytics.charts import (
    allocation_donut,
    annual_return_bar,
    cash_flow_chart,
    correlation_heatmap,
    daily_returns_chart,
    drawdown_chart,
    drift_bar,
    fees_bar,
    monthly_heatmap,
    portfolio_value_chart,
    position_value_chart,
    price_history_chart,
    quantity_chart,
    return_distribution,
    risk_return_scatter,
    rolling_metric_chart,
    target_actual_bar,
    transaction_timeline,
    twr_chart,
    weights_area_chart,
)
from portfolio_analytics.engine import rebalance_with_new_cash
from portfolio_analytics.exports import (
    build_analysis_workbook_bytes,
    sample_template_bytes,
    to_csv_bytes,
)
from portfolio_analytics.models import (
    AnalysisSettings,
    PortfolioAnalysis,
    PortfolioWorkbook,
)
from portfolio_analytics.pipeline import analyze_uploaded_workbook
from portfolio_analytics.workbook import build_upload_template_bytes

from .design import inject_css
from .formatting import fmt_eur, fmt_num, fmt_pct, ordered_columns

NAV_ITEMS = [
    "Portfolio Overview",
    "Upload & Validation",
    "Performance",
    "Positions",
    "Allocation & Rebalancing",
    "Risk Metrics",
    "Rolling Analysis",
    "Transactions",
    "Historical Prices",
    "Export",
]


def render_app() -> None:
    st.set_page_config(page_title="Portfolio Tracker", layout="wide")
    inject_css()

    with st.sidebar:
        st.title("Portfolio Tracker")
        sidebar_upload = st.file_uploader(
            "Workbook", type=["xlsx", "xlsm"], key="sidebar_upload"
        )
        st.download_button(
            "Blank template",
            data=build_upload_template_bytes(include_examples=False),
            file_name="portfolio_tracker_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        st.download_button(
            "Sample workbook",
            data=sample_template_bytes(),
            file_name="portfolio_tracker_sample.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        st.divider()
        risk_free_rate = st.number_input(
            "Annual risk-free rate", value=0.0, step=0.0025, format="%.4f"
        )
        forward_fill_prices = st.toggle("Forward-fill prices", value=True)

    uploaded = sidebar_upload
    if uploaded is None:
        _render_start()
        return

    settings = AnalysisSettings(
        annual_risk_free_rate=risk_free_rate,
        forward_fill_prices=forward_fill_prices,
    )
    workbook, analysis = _load_workbook_and_analysis(uploaded.getvalue(), settings)

    with st.sidebar:
        st.divider()
        page = st.radio("View", NAV_ITEMS, label_visibility="collapsed")
        _render_validation_badge(workbook)

    if workbook.has_errors and page != "Upload & Validation":
        st.warning(
            "Validation errors were found. Review Upload & Validation before relying on the analytics."
        )

    if page == "Portfolio Overview":
        _render_overview(analysis, workbook)
    elif page == "Upload & Validation":
        _render_validation_page(workbook, analysis)
    elif page == "Performance":
        _render_performance(analysis)
    elif page == "Positions":
        _render_positions(analysis)
    elif page == "Allocation & Rebalancing":
        _render_allocation(analysis)
    elif page == "Risk Metrics":
        _render_risk(analysis)
    elif page == "Rolling Analysis":
        _render_rolling(analysis)
    elif page == "Transactions":
        _render_transactions(workbook, analysis)
    elif page == "Historical Prices":
        _render_prices(workbook)
    elif page == "Export":
        _render_export(workbook, analysis)


@st.cache_data(show_spinner=False)
def _load_workbook_and_analysis(
    file_bytes: bytes, settings: AnalysisSettings
) -> tuple[PortfolioWorkbook, PortfolioAnalysis]:
    return analyze_uploaded_workbook(file_bytes, settings)


def _render_start():
    st.markdown(
        """
        <div class="app-shell hero-grid">
            <div>
                <div class="section-kicker">Portfolio operations</div>
                <h1 class="hero-title">Analyze the portfolio workbook as a living dashboard.</h1>
                <p class="hero-copy">
                    Upload a completed workbook and the app builds holdings, cash-flow adjusted performance,
                    rolling windows, allocation drift, and rebalance suggestions from the workbook data.
                </p>
                <div class="status-row">
                    <span class="status-pill"><span class="status-dot"></span>Ready for upload</span>
                    <span class="status-pill"><span class="status-dot"></span>Dynamic asset universe</span>
                    <span class="status-pill"><span class="status-dot"></span>EUR analytics</span>
                </div>
                <div class="contract-grid">
                    <div class="contract-card">
                        <h3>Transactions</h3>
                        <p>Broker, product, ISIN, action, quantity, price, cash flow, and fees.</p>
                    </div>
                    <div class="contract-card">
                        <h3>Historical Prices</h3>
                        <p>Repeating Product / ISIN / Date / Price blocks for each asset.</p>
                    </div>
                    <div class="contract-card">
                        <h3>Portfolio Composition</h3>
                        <p>Yearly target weights and tolerance for drift and rebalancing.</p>
                    </div>
                </div>
            </div>
            <div class="start-panel">
                <div class="start-panel-topline">Input ready</div>
                <div class="start-panel-number">3</div>
                <div class="start-panel-label">required workbook sheets</div>
                <div class="start-panel-rule"></div>
                <p>Use the sidebar controls to download a template or upload a completed workbook.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")
    _render_static_preview()
    return None


def _render_static_preview() -> None:
    st.markdown(
        '<div class="section-kicker">What the dashboard will assemble</div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Performance path", "Daily", "Portfolio + assets")
    c2.metric("Rolling windows", "Dynamic", "Only possible periods")
    c3.metric("Allocation check", "Target aware", "Drift + tolerance")
    c4.metric("Exports", "Workbook + CSV", "Clean outputs")


def _render_validation_badge(workbook: PortfolioWorkbook) -> None:
    frame = workbook.validation_frame()
    counts = frame["severity"].value_counts().to_dict()
    errors = int(counts.get("Error", 0))
    warnings = int(counts.get("Warning", 0))
    infos = int(counts.get("Info", 0))
    if errors:
        st.error(f"{errors} errors, {warnings} warnings")
    elif warnings:
        st.warning(f"{warnings} warnings, {infos} notes")
    else:
        st.success("Validation passed")


def _render_validation_page(
    workbook: PortfolioWorkbook, analysis: PortfolioAnalysis
) -> None:
    st.markdown(
        '<div class="section-kicker">Workbook intake</div>', unsafe_allow_html=True
    )
    st.title("Upload & Validation")
    frame = workbook.validation_frame()
    counts = frame["severity"].value_counts().to_dict()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sheets", len(workbook.workbook_sheets))
    c2.metric("Errors", int(counts.get("Error", 0)))
    c3.metric("Warnings", int(counts.get("Warning", 0)))
    c4.metric("Notes", int(counts.get("Info", 0)))

    st.subheader("Validation Report")
    _dataframe(frame, height=340)

    st.subheader("Normalized Data")
    t1, t2, t3, t4 = st.tabs(
        ["Transactions", "Historical Prices", "Portfolio Composition", "Assets"]
    )
    with t1:
        _dataframe(workbook.transactions, height=360)
    with t2:
        _dataframe(workbook.prices, height=360)
    with t3:
        _dataframe(workbook.composition, height=360)
    with t4:
        _dataframe(analysis.asset_master, height=360)


def _render_overview(analysis: PortfolioAnalysis, workbook: PortfolioWorkbook) -> None:
    metrics = analysis.metrics
    st.markdown('<div class="section-kicker">Dashboard</div>', unsafe_allow_html=True)
    st.title("Portfolio Overview")

    if analysis.daily_portfolio.empty:
        st.error("Portfolio value cannot be computed from the uploaded workbook.")
        _render_validation_page(workbook, analysis)
        return

    latest_date = analysis.daily_portfolio["date"].max()
    first_date = analysis.daily_portfolio["date"].min()
    _summary_metrics(metrics)
    _overview_insights(analysis, workbook, first_date, latest_date)

    c1, c2 = st.columns([1.7, 1])
    with c1:
        st.plotly_chart(
            portfolio_value_chart(analysis.daily_portfolio), use_container_width=True
        )
    with c2:
        st.plotly_chart(
            allocation_donut(
                analysis.allocation, "current_value_eur", "Current Allocation"
            ),
            use_container_width=True,
        )

    c3, c4 = st.columns([1.2, 1])
    with c3:
        st.plotly_chart(twr_chart(analysis.daily_portfolio), use_container_width=True)
    with c4:
        st.plotly_chart(
            drawdown_chart(analysis.daily_portfolio), use_container_width=True
        )

    st.subheader("Portfolio Health")
    h1, h2 = st.columns([1.2, 1])
    with h1:
        watchlist = ordered_columns(
            analysis.allocation,
            [
                "product",
                "actual_weight",
                "target_weight",
                "drift",
                "tolerance",
                "out_of_tolerance",
                "rebalance_amount_eur",
            ],
        )
        _dataframe(watchlist, height=300)
    with h2:
        st.plotly_chart(
            cash_flow_chart(analysis.daily_portfolio), use_container_width=True
        )


def _overview_insights(
    analysis: PortfolioAnalysis,
    workbook: PortfolioWorkbook,
    first_date: pd.Timestamp,
    latest_date: pd.Timestamp,
) -> None:
    frame = workbook.validation_frame()
    counts = frame["severity"].value_counts().to_dict()
    out_of_tolerance = (
        int(analysis.allocation["out_of_tolerance"].sum())
        if not analysis.allocation.empty
        else 0
    )
    active_positions = (
        int((analysis.holdings["value_eur"] > 0).sum())
        if not analysis.holdings.empty
        else 0
    )
    observations = int(len(analysis.daily_portfolio))
    validation_text = (
        "Clean"
        if int(counts.get("Error", 0)) == 0 and int(counts.get("Warning", 0)) == 0
        else f"{int(counts.get('Error', 0))} errors / {int(counts.get('Warning', 0))} warnings"
    )

    st.markdown(
        f"""
        <div class="insight-grid">
            <div class="insight-card">
                <div class="small-label">Analysis date</div>
                <div class="big-value">{latest_date:%Y-%m-%d}</div>
                <p>From {first_date:%Y-%m-%d}</p>
            </div>
            <div class="insight-card">
                <div class="small-label">Active positions</div>
                <div class="big-value">{active_positions}</div>
                <p>{analysis.asset_master.shape[0]} assets detected</p>
            </div>
            <div class="insight-card">
                <div class="small-label">Daily rows</div>
                <div class="big-value">{observations:,}</div>
                <p>Portfolio performance observations</p>
            </div>
            <div class="insight-card">
                <div class="small-label">Validation</div>
                <div class="big-value">{validation_text}</div>
                <p>{out_of_tolerance} allocation lines outside tolerance</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_performance(analysis: PortfolioAnalysis) -> None:
    st.markdown('<div class="section-kicker">Returns</div>', unsafe_allow_html=True)
    st.title("Performance")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            daily_returns_chart(analysis.daily_portfolio), use_container_width=True
        )
    with c2:
        st.plotly_chart(
            monthly_heatmap(analysis.monthly_returns), use_container_width=True
        )
    st.plotly_chart(annual_return_bar(analysis.annual), use_container_width=True)

    t1, t2 = st.tabs(["Annual Metrics", "Daily Portfolio"])
    with t1:
        _dataframe(
            ordered_columns(
                analysis.annual,
                [
                    "year",
                    "end_value_eur",
                    "invested_eur",
                    "return_eur",
                    "twr",
                    "annualized_volatility",
                    "sharpe_ratio",
                    "max_drawdown",
                    "win_rate",
                ],
            ),
            height=360,
        )
    with t2:
        _dataframe(analysis.daily_portfolio.tail(500), height=420)


def _render_positions(analysis: PortfolioAnalysis) -> None:
    st.markdown('<div class="section-kicker">Holdings</div>', unsafe_allow_html=True)
    st.title("Positions")
    c1, c2 = st.columns([2, 1])
    with c1:
        st.plotly_chart(
            position_value_chart(analysis.daily_asset), use_container_width=True
        )
    with c2:
        st.plotly_chart(
            allocation_donut(
                analysis.allocation, "current_value_eur", "Current Allocation"
            ),
            use_container_width=True,
        )

    c3, c4 = st.columns(2)
    with c3:
        st.plotly_chart(quantity_chart(analysis.daily_asset), use_container_width=True)
    with c4:
        st.plotly_chart(
            weights_area_chart(analysis.daily_asset), use_container_width=True
        )

    st.subheader("Position Snapshot")
    _dataframe(_format_holdings_table(analysis.holdings), height=380)


def _render_allocation(analysis: PortfolioAnalysis) -> None:
    st.markdown('<div class="section-kicker">Targets</div>', unsafe_allow_html=True)
    st.title("Allocation & Rebalancing")
    new_cash = st.number_input(
        "New cash to invest", min_value=0.0, value=0.0, step=100.0
    )
    allocation = rebalance_with_new_cash(analysis.allocation, new_cash)

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            allocation_donut(allocation, "current_value_eur", "Actual Allocation"),
            use_container_width=True,
        )
    with c2:
        target_plot = allocation.copy()
        target_plot["target_value_for_chart"] = target_plot["target_weight"].clip(
            lower=0.0
        )
        st.plotly_chart(
            allocation_donut(
                target_plot, "target_value_for_chart", "Target Allocation"
            ),
            use_container_width=True,
        )

    c3, c4 = st.columns(2)
    with c3:
        st.plotly_chart(target_actual_bar(allocation), use_container_width=True)
    with c4:
        st.plotly_chart(drift_bar(allocation), use_container_width=True)

    if new_cash > 0:
        st.subheader("New-Cash Deployment")
        _dataframe(
            ordered_columns(
                allocation,
                [
                    "product",
                    "actual_weight",
                    "target_weight",
                    "drift",
                    "current_value_eur",
                    "new_cash_buy_eur",
                ],
            ),
            height=360,
        )
    else:
        st.subheader("Trade Existing Portfolio")
        _dataframe(
            ordered_columns(
                allocation,
                [
                    "product",
                    "actual_weight",
                    "target_weight",
                    "drift",
                    "tolerance",
                    "out_of_tolerance",
                    "current_value_eur",
                    "rebalance_amount_eur",
                ],
            ),
            height=360,
        )


def _render_risk(analysis: PortfolioAnalysis) -> None:
    st.markdown('<div class="section-kicker">Risk</div>', unsafe_allow_html=True)
    st.title("Risk Metrics")
    metrics = analysis.metrics
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Annual vol", fmt_pct(metrics.get("annualized_volatility")))
    c2.metric("Sharpe", fmt_num(metrics.get("sharpe_ratio")))
    c3.metric("Sortino", fmt_num(metrics.get("sortino_ratio")))
    c4.metric("VaR 95%", fmt_pct(metrics.get("value_at_risk_95")))
    c5.metric("CVaR 95%", fmt_pct(metrics.get("conditional_var_95")))

    c6, c7 = st.columns(2)
    with c6:
        st.plotly_chart(
            drawdown_chart(analysis.daily_portfolio), use_container_width=True
        )
    with c7:
        st.plotly_chart(
            return_distribution(
                analysis.daily_portfolio, metrics.get("value_at_risk_95")
            ),
            use_container_width=True,
        )

    c8, c9 = st.columns(2)
    with c8:
        st.plotly_chart(
            correlation_heatmap(analysis.correlation), use_container_width=True
        )
    with c9:
        st.plotly_chart(
            risk_return_scatter(analysis.risk_by_asset), use_container_width=True
        )

    st.subheader("Diversification")
    d = analysis.diversification
    d1, d2, d3, d4, d5 = st.columns(5)
    d1.metric("Effective positions", fmt_num(d.get("effective_positions")))
    d2.metric("HHI", fmt_num(d.get("hhi")))
    d3.metric("Largest weight", fmt_pct(d.get("largest_weight")))
    d4.metric("Top 3 weight", fmt_pct(d.get("top3_weight")))
    d5.metric("Avg correlation", fmt_num(d.get("average_correlation")))

    st.subheader("Asset Risk")
    _dataframe(analysis.risk_by_asset, height=340)


def _render_rolling(analysis: PortfolioAnalysis) -> None:
    st.markdown('<div class="section-kicker">Windows</div>', unsafe_allow_html=True)
    st.title("Rolling Analysis")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            rolling_metric_chart(
                analysis.rolling, "annualized_twr", "Rolling Annualized TWR"
            ),
            use_container_width=True,
        )
    with c2:
        st.plotly_chart(
            rolling_metric_chart(
                analysis.rolling,
                "annualized_volatility",
                "Rolling Annualized Volatility",
            ),
            use_container_width=True,
        )
    c3, c4 = st.columns(2)
    with c3:
        st.plotly_chart(
            rolling_metric_chart(
                analysis.rolling, "sharpe_ratio", "Rolling Sharpe Ratio"
            ),
            use_container_width=True,
        )
    with c4:
        st.plotly_chart(
            rolling_metric_chart(
                analysis.rolling, "max_drawdown", "Rolling Max Drawdown"
            ),
            use_container_width=True,
        )

    st.subheader("Rolling Periods")
    _dataframe(
        ordered_columns(
            analysis.rolling,
            [
                "period",
                "period_years",
                "trading_days",
                "end_value_eur",
                "invested_eur",
                "period_twr",
                "annualized_twr",
                "annualized_volatility",
                "sharpe_ratio",
                "sortino_ratio",
                "max_drawdown",
                "win_rate",
            ],
        ),
        height=460,
    )


def _render_transactions(
    workbook: PortfolioWorkbook, analysis: PortfolioAnalysis
) -> None:
    st.markdown('<div class="section-kicker">Activity</div>', unsafe_allow_html=True)
    st.title("Transactions")
    tx = workbook.transactions
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Transactions", len(tx))
    c2.metric("Buys", int((tx["action"] == "Buy").sum()) if not tx.empty else 0)
    c3.metric("Sells", int((tx["action"] == "Sell").sum()) if not tx.empty else 0)
    c4.metric("Fees", fmt_eur(tx["fee_eur"].sum()) if not tx.empty else fmt_eur(0))

    st.plotly_chart(transaction_timeline(tx), use_container_width=True)
    c5, c6 = st.columns(2)
    with c5:
        st.plotly_chart(
            fees_bar(analysis.fees_by_broker, "broker", "Fees by Broker"),
            use_container_width=True,
        )
    with c6:
        st.plotly_chart(
            fees_bar(analysis.fees_by_asset, "product", "Fees by Asset"),
            use_container_width=True,
        )

    t1, t2 = st.tabs(["Transaction Table", "Action Summary"])
    with t1:
        _dataframe(tx.sort_values("date", ascending=False), height=460)
    with t2:
        _dataframe(analysis.transaction_summary, height=300)


def _render_prices(workbook: PortfolioWorkbook) -> None:
    st.markdown('<div class="section-kicker">Market data</div>', unsafe_allow_html=True)
    st.title("Historical Prices")
    prices = workbook.prices
    st.plotly_chart(price_history_chart(prices), use_container_width=True)
    if prices.empty:
        st.info("No historical price rows were parsed.")
        return
    coverage = (
        prices.groupby(["asset_id", "product"], as_index=False)
        .agg(
            first_date=("date", "min"),
            last_date=("date", "max"),
            observations=("price", "size"),
            min_price=("price", "min"),
            max_price=("price", "max"),
        )
        .sort_values("product")
    )
    st.subheader("Coverage by Asset")
    _dataframe(coverage, height=300)
    st.subheader("Normalized Price Rows")
    _dataframe(prices, height=440)


def _render_export(workbook: PortfolioWorkbook, analysis: PortfolioAnalysis) -> None:
    st.markdown('<div class="section-kicker">Outputs</div>', unsafe_allow_html=True)
    st.title("Export")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "Download complete analysis workbook",
            data=build_analysis_workbook_bytes(workbook, analysis),
            file_name="portfolio_analysis_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with c2:
        st.download_button(
            "Download clean input template",
            data=build_upload_template_bytes(include_examples=False),
            file_name="portfolio_tracker_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    exports = [
        ("daily_portfolio.csv", analysis.daily_portfolio),
        ("daily_positions.csv", analysis.daily_asset),
        ("annual_performance.csv", analysis.annual),
        ("rolling_performance.csv", analysis.rolling),
        ("allocation_rebalancing.csv", analysis.allocation),
        ("validation_report.csv", workbook.validation_frame()),
    ]
    st.subheader("CSV Downloads")
    cols = st.columns(3)
    for idx, (filename, df) in enumerate(exports):
        with cols[idx % 3]:
            st.download_button(
                filename,
                data=to_csv_bytes(df),
                file_name=filename,
                mime="text/csv",
                use_container_width=True,
            )


def _summary_metrics(metrics: dict[str, float]) -> None:
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Portfolio value", fmt_eur(metrics.get("portfolio_value_eur")))
    c2.metric("Invested capital", fmt_eur(metrics.get("total_invested_eur")))
    c3.metric("Total return", fmt_eur(metrics.get("total_return_eur")))
    c4.metric("TWR", fmt_pct(metrics.get("twr")))
    c5.metric("MWR", fmt_pct(metrics.get("money_weighted_return")))
    c6.metric("Max drawdown", fmt_pct(metrics.get("max_drawdown")))


def _format_holdings_table(df: pd.DataFrame) -> pd.DataFrame:
    return ordered_columns(
        df,
        [
            "product",
            "isin",
            "quantity",
            "price",
            "value_eur",
            "weight",
            "average_price_eur",
            "total_investment_eur",
            "total_fees_eur",
            "total_return_eur",
            "twr",
        ],
    )


def _dataframe(df: pd.DataFrame, height: int = 320) -> None:
    st.dataframe(df, use_container_width=True, height=height, hide_index=True)
