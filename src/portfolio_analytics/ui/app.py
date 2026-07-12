from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from portfolio_analytics.charts import (
    allocation_donut,
    annual_return_bar,
    correlation_heatmap,
    daily_returns_chart,
    drawdown_chart,
    drift_bar,
    fees_bar,
    monthly_heatmap,
    portfolio_value_chart,
    position_value_chart,
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
    to_csv_bytes,
    to_xlsx_bytes,
)
from portfolio_analytics.models import (
    AnalysisSettings,
    PortfolioAnalysis,
    PortfolioWorkbook,
)
from portfolio_analytics.pipeline import analyze_uploaded_workbook
from portfolio_analytics.workbook import REQUIRED_SHEETS, build_upload_template_bytes

from .design import inject_css
from .formatting import fmt_eur, fmt_num, fmt_pct, ordered_columns


def render_app() -> None:
    st.set_page_config(page_title="Asset Alchemy", page_icon="◈", layout="wide")
    inject_css()
    _initialize_session_state()

    uploaded, analyze_clicked = _render_sidebar()
    if uploaded is not None:
        _register_upload(uploaded)
    if analyze_clicked:
        _run_analysis()

    if st.session_state.uploaded_file is None:
        _render_empty_state()
        return

    if not st.session_state.analysis_has_run:
        _render_ready_state()
        return

    if st.session_state.analysis_error:
        st.error("Analysis failed")
        st.caption(st.session_state.analysis_error)
        st.info(
            "Check that the workbook is a valid .xlsx or .xlsm file, then upload it again."
        )
        return

    workbook = st.session_state.validation_results
    analysis = st.session_state.analysis_results
    if workbook is None or analysis is None:
        st.warning("The workbook is ready, but analysis results are not available yet.")
        return

    _render_dashboard(workbook, analysis)


def _initialize_session_state() -> None:
    defaults = {
        "uploaded_file": None,
        "workbook_loaded": False,
        "validation_results": None,
        "analysis_has_run": False,
        "analysis_results": None,
        "analysis_error": None,
        "selected_settings": {"forward_fill_prices": True, "text_date_mode": "strict"},
        "upload_signature": None,
        "workbook_inspection": {"sheets": [], "error": None},
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _render_sidebar():
    with st.sidebar:
        st.markdown(
            "<div class='brand-mark'>Asset Alchemy</div>", unsafe_allow_html=True
        )
        st.caption("Upload your completed workbook, then run the analysis.")
        st.download_button(
            "Download prefilled template",
            data=build_upload_template_bytes(include_examples=True),
            file_name="asset_alchemy_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        st.divider()
        uploaded = st.file_uploader(
            "Upload completed template",
            type=["xlsx", "xlsm"],
            help="Use the three-sheet Asset Alchemy template. Drag a file here or browse to select it.",
            key="workbook_upload",
        )
        st.caption("Accepted formats: .xlsx and .xlsm")

        analyze_clicked = st.button(
            "Analyze portfolio", type="primary", use_container_width=True
        )
        _render_analysis_status()

        with st.expander("Settings", expanded=False):
            st.session_state.selected_settings["forward_fill_prices"] = st.toggle(
                "Forward-fill missing prices",
                value=st.session_state.selected_settings["forward_fill_prices"],
                help="Carries the latest available price forward between observations.",
            )
            date_mode = st.radio(
                "Text transaction dates",
                ["Strict", "Permissive day-first"],
                index=(
                    0
                    if st.session_state.selected_settings.get(
                        "text_date_mode", "strict"
                    )
                    == "strict"
                    else 1
                ),
                help="Strict rejects text dates; permissive parses them as day-first and keeps a warning.",
                horizontal=True,
                key="text_date_mode",
            )
            st.session_state.selected_settings["text_date_mode"] = (
                "strict" if date_mode == "Strict" else "permissive"
            )

    return uploaded, analyze_clicked


def _render_analysis_status() -> None:
    if st.session_state.uploaded_file is None:
        st.caption("Status · No workbook uploaded")
    elif st.session_state.analysis_error:
        st.caption("Status · Analysis failed")
    elif st.session_state.analysis_has_run:
        st.caption("Status · Analysis complete")
    elif st.session_state.workbook_loaded:
        st.caption("Status · Workbook uploaded, ready to analyze")
    else:
        st.caption("Status · Validating workbook")


def _register_upload(uploaded) -> None:
    file_bytes = uploaded.getvalue()
    signature = (uploaded.name, len(file_bytes), hash(file_bytes))
    if signature == st.session_state.upload_signature:
        return
    st.session_state.upload_signature = signature
    st.session_state.uploaded_file = {
        "name": uploaded.name,
        "size": len(file_bytes),
        "bytes": file_bytes,
    }
    st.session_state.workbook_inspection = _inspect_workbook(file_bytes)
    st.session_state.workbook_loaded = True
    st.session_state.validation_results = None
    st.session_state.analysis_results = None
    st.session_state.analysis_has_run = False
    st.session_state.analysis_error = None


@st.cache_data(show_spinner=False)
def _inspect_workbook(file_bytes: bytes) -> dict[str, object]:
    try:
        sheets = pd.ExcelFile(BytesIO(file_bytes)).sheet_names
        return {"sheets": sheets, "error": None}
    except Exception as exc:  # pandas normalizes the details in the user-facing state
        return {"sheets": [], "error": str(exc)}


def _run_analysis() -> None:
    upload = st.session_state.uploaded_file
    if upload is None:
        st.sidebar.warning("Upload a completed template before running analysis.")
        return

    settings = AnalysisSettings(
        forward_fill_prices=st.session_state.selected_settings["forward_fill_prices"],
        text_date_mode=st.session_state.selected_settings.get(
            "text_date_mode", "strict"
        ),
    )
    try:
        with st.status("Analyzing portfolio", expanded=True) as status:
            st.write("Reading workbook")
            st.write("Validating template")
            st.write("Parsing transactions")
            st.write("Parsing historical prices")
            st.write("Parsing portfolio composition")
            workbook, analysis = _load_workbook_and_analysis(upload["bytes"], settings)
            st.write("Building daily performance")
            st.write("Computing risk and rolling metrics")
            st.write("Preparing dashboard")
            status.update(label="Analysis complete", state="complete", expanded=False)
        st.session_state.validation_results = workbook
        st.session_state.analysis_results = analysis
        st.session_state.analysis_has_run = True
        st.session_state.analysis_error = None
    except Exception as exc:
        st.session_state.validation_results = None
        st.session_state.analysis_results = None
        st.session_state.analysis_has_run = True
        st.session_state.analysis_error = str(exc)


@st.cache_data(show_spinner=False)
def _load_workbook_and_analysis(
    file_bytes: bytes, settings: AnalysisSettings
) -> tuple[PortfolioWorkbook, PortfolioAnalysis]:
    return analyze_uploaded_workbook(file_bytes, settings)


def _render_empty_state() -> None:
    st.markdown(
        "<div class='eyebrow'>Portfolio intelligence</div>", unsafe_allow_html=True
    )
    st.title("Asset Alchemy")
    st.markdown(
        "<p class='lead'>Transform your workbook into portfolio intelligence.</p>",
        unsafe_allow_html=True,
    )
    st.write(
        "Start with the prefilled template, add your own transactions, prices, and target allocation, then run a focused analysis when you are ready."
    )
    st.markdown("<div class='workflow'>", unsafe_allow_html=True)
    columns = st.columns(3)
    for column, number, title, detail in [
        (
            columns[0],
            "01",
            "Download template",
            "Use the prefilled workbook as your starting point.",
        ),
        (
            columns[1],
            "02",
            "Complete the data",
            "Fill transactions, prices, and composition.",
        ),
        (
            columns[2],
            "03",
            "Upload and analyze",
            "Review the dashboard and export the results.",
        ),
    ]:
        with column:
            st.markdown(
                f"<div class='workflow-step'><span>{number}</span><h3>{title}</h3><p>{detail}</p></div>",
                unsafe_allow_html=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_ready_state() -> None:
    upload = st.session_state.uploaded_file
    inspection = st.session_state.workbook_inspection
    st.markdown("<div class='eyebrow'>Workbook ready</div>", unsafe_allow_html=True)
    st.title("Ready to analyze")
    st.write(
        "Your workbook is uploaded. Review the quick intake check, then select **Analyze portfolio** in the sidebar."
    )
    c1, c2, c3 = st.columns([1.35, 0.8, 1.5])
    c1.metric("File", upload["name"])
    c2.metric("Size", _format_file_size(upload["size"]))
    if inspection["error"]:
        c3.metric("Workbook check", "Could not inspect")
        st.warning(
            "The workbook could not be inspected. You can still try analysis after checking the file format."
        )
        return

    detected = set(inspection["sheets"])
    missing = [sheet for sheet in REQUIRED_SHEETS if sheet not in detected]
    c3.metric(
        "Required sheets",
        f"{len(REQUIRED_SHEETS) - len(missing)} / {len(REQUIRED_SHEETS)}",
    )
    if missing:
        st.warning("Missing required sheets: " + ", ".join(missing))
    else:
        st.success(
            "All required sheets detected. The workbook is ready for full validation."
        )
    st.caption("Detected sheets: " + ", ".join(inspection["sheets"]))


def _render_dashboard(workbook: PortfolioWorkbook, analysis: PortfolioAnalysis) -> None:
    st.markdown("<div class='eyebrow'>Asset Alchemy</div>", unsafe_allow_html=True)
    st.title("Portfolio intelligence")
    if workbook.has_errors:
        st.warning(
            "Validation found errors. Review Data Quality before relying on the analytics."
        )
    _render_risk_free_source(workbook)

    tabs = st.tabs(
        [
            "Overview",
            "Performance",
            "Positions",
            "Allocation",
            "Risk",
            "Rolling",
            "Transactions",
            "Data Quality",
            "Export",
        ]
    )
    with tabs[0]:
        _render_overview(analysis, workbook)
    with tabs[1]:
        _render_performance(analysis)
    with tabs[2]:
        _render_positions(analysis)
    with tabs[3]:
        _render_allocation(analysis)
    with tabs[4]:
        _render_risk(analysis)
    with tabs[5]:
        _render_rolling(analysis)
    with tabs[6]:
        _render_transactions(workbook, analysis)
    with tabs[7]:
        _render_data_quality(workbook, analysis)
    with tabs[8]:
        _render_export(workbook, analysis)


def _render_risk_free_source(workbook: PortfolioWorkbook) -> None:
    if workbook.risk_free_rates.empty:
        st.caption("Risk-free rates: not found, using 0% fallback.")
    else:
        countries = (
            workbook.risk_free_rates["country"].replace("", pd.NA).dropna().unique()
        )
        suffix = f" ({', '.join(countries[:2])})" if len(countries) else ""
        st.caption(
            "Risk-free rates: parsed from Historical Prices → Risk-Free Government Bonds"
            + suffix
        )


def _render_overview(analysis: PortfolioAnalysis, workbook: PortfolioWorkbook) -> None:
    if analysis.daily_portfolio.empty:
        st.error("Portfolio value could not be computed from the uploaded workbook.")
        _render_data_quality(workbook, analysis)
        return
    metrics = analysis.metrics
    st.subheader("Overview", anchor=False)
    _summary_metrics(metrics)
    c1, c2 = st.columns([1.65, 1])
    with c1:
        st.plotly_chart(
            portfolio_value_chart(analysis.daily_portfolio),
            use_container_width=True,
            key="overview_portfolio_value_chart",
        )
    with c2:
        st.plotly_chart(
            allocation_donut(
                analysis.allocation, "current_value_eur", "Current allocation"
            ),
            use_container_width=True,
            key="overview_allocation_chart",
        )
    _overview_insights(analysis, workbook)


def _summary_metrics(metrics: dict[str, float]) -> None:
    columns = st.columns(6)
    values = [
        ("Portfolio value", fmt_eur(metrics.get("portfolio_value_eur"))),
        ("Total invested", fmt_eur(metrics.get("total_invested_eur"))),
        ("Total return", fmt_eur(metrics.get("total_return_eur"))),
        ("Total return %", fmt_pct(metrics.get("total_return_pct"))),
        ("Time-weighted return", fmt_pct(metrics.get("twr"))),
        ("Current drawdown", fmt_pct(metrics.get("current_drawdown"))),
    ]
    for column, (label, value) in zip(columns, values):
        column.metric(label, value)


def _overview_insights(
    analysis: PortfolioAnalysis, workbook: PortfolioWorkbook
) -> None:
    best_asset = "—"
    if not analysis.risk_by_asset.empty:
        row = analysis.risk_by_asset.sort_values("twr", ascending=False).iloc[0]
        best_asset = f"{row['product']} · {fmt_pct(row['twr'])}"
    largest_position = "—"
    highest_drift = "—"
    if not analysis.allocation.empty:
        largest = analysis.allocation.sort_values(
            "current_value_eur", ascending=False
        ).iloc[0]
        drift = analysis.allocation.sort_values("absolute_drift", ascending=False).iloc[
            0
        ]
        largest_position = f"{largest['product']} · {fmt_pct(largest['actual_weight'])}"
        highest_drift = f"{drift['product']} · {fmt_pct(drift['drift'])}"
    risk_free = (
        "Workbook block" if not workbook.risk_free_rates.empty else "0% fallback"
    )
    items = [
        ("Best performing asset", best_asset),
        ("Largest position", largest_position),
        ("Highest drift from target", highest_drift),
        ("Total fees", fmt_eur(analysis.metrics.get("total_fees_eur"))),
        ("Risk-free source", risk_free),
    ]
    st.markdown("<div class='section-label'>At a glance</div>", unsafe_allow_html=True)
    columns = st.columns(5)
    for column, (label, value) in zip(columns, items):
        column.metric(label, value)


def _render_performance(analysis: PortfolioAnalysis) -> None:
    st.subheader("Performance", anchor=False)
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            portfolio_value_chart(analysis.daily_portfolio),
            use_container_width=True,
            key="performance_portfolio_value_chart",
        )
    with c2:
        st.plotly_chart(
            twr_chart(analysis.daily_portfolio),
            use_container_width=True,
            key="performance_twr_chart",
        )
    c3, c4 = st.columns(2)
    with c3:
        st.plotly_chart(
            annual_return_bar(analysis.annual),
            use_container_width=True,
            key="performance_annual_return_chart",
        )
    with c4:
        st.plotly_chart(
            monthly_heatmap(analysis.monthly_returns),
            use_container_width=True,
            key="performance_monthly_heatmap_chart",
        )
    st.plotly_chart(
        daily_returns_chart(analysis.daily_portfolio),
        use_container_width=True,
        key="performance_daily_returns_chart",
    )
    st.markdown(
        "<div class='section-label'>Annual performance</div>", unsafe_allow_html=True
    )
    _dataframe(
        ordered_columns(
            analysis.annual,
            [
                "year",
                "end_value_eur",
                "invested_eur",
                "return_eur",
                "twr",
                "risk_free_rate",
                "annualized_volatility",
                "sharpe_ratio",
                "max_drawdown",
                "win_rate",
            ],
        ),
        height=340,
    )


def _render_positions(analysis: PortfolioAnalysis) -> None:
    st.subheader("Positions", anchor=False)
    options = (
        sorted(analysis.daily_asset["product"].dropna().unique())
        if not analysis.daily_asset.empty
        else []
    )
    selected = st.multiselect(
        "Assets", options, default=options, key="positions_assets"
    )
    data = analysis.daily_asset[analysis.daily_asset["product"].isin(selected)].copy()
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            position_value_chart(data),
            use_container_width=True,
            key="positions_value_chart",
        )
    with c2:
        st.plotly_chart(
            weights_area_chart(data),
            use_container_width=True,
            key="positions_weights_chart",
        )
    st.plotly_chart(
        quantity_chart(data), use_container_width=True, key="positions_quantity_chart"
    )
    st.markdown(
        "<div class='section-label'>Position performance</div>", unsafe_allow_html=True
    )
    _dataframe(_format_holdings_table(analysis.holdings), height=360)


def _render_allocation(analysis: PortfolioAnalysis) -> None:
    st.subheader("Allocation", anchor=False)
    new_cash = st.number_input(
        "New cash to invest",
        min_value=0.0,
        value=0.0,
        step=100.0,
        key="allocation_new_cash",
    )
    allocation = rebalance_with_new_cash(analysis.allocation, new_cash)
    out_of_tolerance = (
        allocation[allocation["out_of_tolerance"]]
        if not allocation.empty
        else allocation
    )
    if not out_of_tolerance.empty:
        st.warning(
            f"{len(out_of_tolerance)} position(s) are outside the workbook tolerance."
        )
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            allocation_donut(
                allocation, "current_value_eur", "Current actual allocation"
            ),
            use_container_width=True,
            key="allocation_current_donut_chart",
        )
    with c2:
        st.plotly_chart(
            target_actual_bar(allocation),
            use_container_width=True,
            key="allocation_target_actual_chart",
        )
    st.plotly_chart(
        drift_bar(allocation), use_container_width=True, key="allocation_drift_chart"
    )
    st.markdown(
        "<div class='section-label'>Rebalance suggestions</div>", unsafe_allow_html=True
    )
    columns = [
        "product",
        "actual_weight",
        "target_weight",
        "drift",
        "tolerance",
        "out_of_tolerance",
        "current_value_eur",
        "rebalance_amount_eur",
        "new_cash_buy_eur",
    ]
    _dataframe(ordered_columns(allocation, columns), height=380)


def _render_risk(analysis: PortfolioAnalysis) -> None:
    st.subheader("Risk", anchor=False)
    metrics = analysis.metrics
    columns = st.columns(6)
    values = [
        ("Annual volatility", fmt_pct(metrics.get("annualized_volatility"))),
        ("Sharpe ratio", fmt_num(metrics.get("sharpe_ratio"))),
        ("Sortino ratio", fmt_num(metrics.get("sortino_ratio"))),
        ("Calmar ratio", fmt_num(metrics.get("calmar_ratio"))),
        ("Maximum drawdown", fmt_pct(metrics.get("max_drawdown"))),
        (
            "VaR / CVaR 95%",
            f"{fmt_pct(metrics.get('value_at_risk_95'))} / {fmt_pct(metrics.get('conditional_var_95'))}",
        ),
    ]
    for column, (label, value) in zip(columns, values):
        column.metric(label, value)
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            drawdown_chart(analysis.daily_portfolio),
            use_container_width=True,
            key="risk_drawdown_chart",
        )
    with c2:
        st.plotly_chart(
            return_distribution(
                analysis.daily_portfolio, metrics.get("value_at_risk_95")
            ),
            use_container_width=True,
            key="risk_return_distribution_chart",
        )
    c3, c4 = st.columns(2)
    with c3:
        st.plotly_chart(
            correlation_heatmap(analysis.correlation),
            use_container_width=True,
            key="risk_correlation_chart",
        )
    with c4:
        st.plotly_chart(
            risk_return_scatter(analysis.risk_by_asset),
            use_container_width=True,
            key="risk_return_scatter_chart",
        )
    diversification = analysis.diversification
    st.markdown(
        "<div class='section-label'>Concentration</div>", unsafe_allow_html=True
    )
    concentration = st.columns(4)
    concentration[0].metric(
        "Herfindahl-Hirschman Index", fmt_num(diversification.get("hhi"))
    )
    concentration[1].metric(
        "Inverse HHI", fmt_num(diversification.get("effective_positions"))
    )
    concentration[2].metric(
        "Effective positions", fmt_num(diversification.get("effective_positions"))
    )
    concentration[3].metric(
        "Top position concentration", fmt_pct(diversification.get("largest_weight"))
    )
    _dataframe(analysis.risk_by_asset, height=300)


def _render_rolling(analysis: PortfolioAnalysis) -> None:
    st.subheader("Rolling analysis", anchor=False)
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            rolling_metric_chart(
                analysis.rolling, "annualized_twr", "Rolling annualized TWR"
            ),
            use_container_width=True,
            key="rolling_annualized_twr_chart",
        )
    with c2:
        st.plotly_chart(
            rolling_metric_chart(
                analysis.rolling, "sharpe_ratio", "Rolling Sharpe ratio"
            ),
            use_container_width=True,
            key="rolling_sharpe_ratio_chart",
        )
    c3, c4 = st.columns(2)
    with c3:
        st.plotly_chart(
            rolling_metric_chart(
                analysis.rolling,
                "annualized_volatility",
                "Rolling annualized volatility",
            ),
            use_container_width=True,
            key="rolling_annualized_volatility_chart",
        )
    with c4:
        st.plotly_chart(
            rolling_metric_chart(
                analysis.rolling, "max_drawdown", "Rolling maximum drawdown"
            ),
            use_container_width=True,
            key="rolling_max_drawdown_chart",
        )
    st.caption(
        "Only calendar-year windows supported by the uploaded history are shown."
    )
    _dataframe(
        ordered_columns(
            analysis.rolling,
            [
                "period",
                "start_year",
                "end_year",
                "trading_days",
                "start_value_eur",
                "end_value_eur",
                "invested_eur",
                "return_eur",
                "period_twr",
                "annualized_twr",
                "risk_free_rate",
                "period_volatility",
                "annualized_volatility",
                "sharpe_ratio",
                "sortino_ratio",
                "max_drawdown",
                "calmar_ratio",
                "best_day",
                "worst_day",
                "win_rate",
                "end_allocation_weights",
                "allocation_drift",
            ],
        ),
        height=460,
    )


def _render_transactions(
    workbook: PortfolioWorkbook, analysis: PortfolioAnalysis
) -> None:
    st.subheader("Transactions", anchor=False)
    tx = workbook.transactions.copy()
    if tx.empty:
        st.info("No transactions were parsed from the workbook.")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total buys", int(tx["action"].eq("Buy").sum()))
    c2.metric("Total sells", int(tx["action"].eq("Sell").sum()))
    c3.metric("Total fees", fmt_eur(tx["fee_eur"].sum()))
    c4.metric("Transactions", len(tx))
    _render_transaction_validation_findings(workbook)
    filters = st.columns(4)
    brokers = filters[0].multiselect(
        "Broker", sorted(tx["broker"].dropna().unique()), key="tx_brokers"
    )
    assets = filters[1].multiselect(
        "Asset", sorted(tx["product"].dropna().unique()), key="tx_assets"
    )
    actions = filters[2].multiselect(
        "Action", sorted(tx["action"].dropna().unique()), key="tx_actions"
    )
    dates = filters[3].date_input(
        "Date range",
        value=(tx["date"].min().date(), tx["date"].max().date()),
        key="tx_dates",
    )
    if brokers:
        tx = tx[tx["broker"].isin(brokers)]
    if assets:
        tx = tx[tx["product"].isin(assets)]
    if actions:
        tx = tx[tx["action"].isin(actions)]
    if isinstance(dates, tuple) and len(dates) == 2:
        tx = tx[tx["date"].between(pd.Timestamp(dates[0]), pd.Timestamp(dates[1]))]
    st.plotly_chart(
        transaction_timeline(tx),
        use_container_width=True,
        key="transactions_timeline_chart",
    )
    c5, c6 = st.columns(2)
    with c5:
        st.plotly_chart(
            fees_bar(analysis.fees_by_broker, "broker", "Fees by broker"),
            use_container_width=True,
            key="transactions_fees_by_broker_chart",
        )
    with c6:
        st.plotly_chart(
            fees_bar(analysis.fees_by_asset, "product", "Fees by asset"),
            use_container_width=True,
            key="transactions_fees_by_asset_chart",
        )
    _dataframe(tx.sort_values("date", ascending=False), height=440)


def _render_transaction_validation_findings(workbook: PortfolioWorkbook) -> None:
    report = workbook.validation_frame()
    if report.empty or "message" not in report.columns:
        return
    message = report["message"].astype(str)
    sheet = report["sheet"].astype(str)
    severity = report["severity"].astype(str)
    is_transaction_related = (
        sheet.eq("Transactions")
        | message.str.contains("Transaction row", case=False, na=False)
        | message.str.contains("Transactions for asset_id", case=False, na=False)
        | message.str.contains("Transaction ISIN", case=False, na=False)
    )
    findings = report[
        is_transaction_related & severity.isin(["Error", "Warning"])
    ].copy()
    if findings.empty:
        return
    errors = int(findings["severity"].eq("Error").sum())
    warnings = int(findings["severity"].eq("Warning").sum())
    st.warning(
        f"{errors} transaction error(s) and {warnings} transaction warning(s) need review before relying on transaction analytics."
    )
    with st.expander("Transaction validation findings", expanded=True):
        _dataframe(findings, height=min(360, 96 + 42 * len(findings)))


def _render_data_quality(
    workbook: PortfolioWorkbook, analysis: PortfolioAnalysis
) -> None:
    st.subheader("Data quality", anchor=False)
    report = workbook.validation_frame()
    counts = report["severity"].value_counts().to_dict()
    c1, c2, c3 = st.columns(3)
    c1.metric("Errors", int(counts.get("Error", 0)))
    c2.metric("Warnings", int(counts.get("Warning", 0)))
    c3.metric("Info", int(counts.get("Info", 0)))
    for severity in ["Error", "Warning", "Info"]:
        findings = report[report["severity"].eq(severity)]
        if not findings.empty:
            with st.expander(
                f"{severity} · {len(findings)}", expanded=severity == "Error"
            ):
                _dataframe(findings, height=min(320, 90 + 42 * len(findings)))
    if not analysis.reconciliation.empty:
        mismatches = analysis.reconciliation[
            ~analysis.reconciliation["Status"].eq("Match")
        ]
        if not mismatches.empty:
            st.warning(
                "App output does not match workbook Daily Performance. Check date parsing, asset matching, and transaction validation."
            )
        with st.expander(
            "Daily Performance reconciliation", expanded=not mismatches.empty
        ):
            _dataframe(analysis.reconciliation, height=420)
    with st.expander("Normalized workbook data"):
        tabs = st.tabs(
            [
                "Transactions",
                "Prices",
                "Composition",
                "Risk-free rates",
                "Daily Performance",
                "Assets",
            ]
        )
        with tabs[0]:
            _dataframe(workbook.transactions, height=320)
        with tabs[1]:
            _dataframe(workbook.prices, height=320)
        with tabs[2]:
            _dataframe(workbook.composition, height=320)
        with tabs[3]:
            _dataframe(workbook.risk_free_rates, height=240)
        with tabs[4]:
            _dataframe(workbook.daily_performance_reference, height=180)
        with tabs[5]:
            _dataframe(analysis.asset_master, height=320)


def _render_export(workbook: PortfolioWorkbook, analysis: PortfolioAnalysis) -> None:
    st.subheader("Export", anchor=False)
    st.download_button(
        "Download prefilled template",
        data=build_upload_template_bytes(include_examples=True),
        file_name="asset_alchemy_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=False,
    )
    st.download_button(
        "Download full analysis workbook",
        data=build_analysis_workbook_bytes(workbook, analysis),
        file_name="asset_alchemy_analysis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=False,
    )
    exports = [
        ("Daily performance", "daily_performance", analysis.daily_portfolio),
        ("Position performance", "position_performance", analysis.daily_asset),
        ("Annual performance", "annual_performance", analysis.annual),
        ("Rolling performance", "rolling_performance", analysis.rolling),
        ("Allocation and rebalancing", "allocation_rebalancing", analysis.allocation),
        (
            "Daily Performance reconciliation",
            "daily_performance_reconciliation",
            analysis.reconciliation,
        ),
        ("Data quality report", "data_quality_report", workbook.validation_frame()),
    ]
    st.markdown("<div class='section-label'>Data exports</div>", unsafe_allow_html=True)
    for label, stem, frame in exports:
        c1, c2 = st.columns([1, 1])
        c1.download_button(
            f"{label} · CSV",
            data=to_csv_bytes(frame),
            file_name=f"{stem}.csv",
            mime="text/csv",
            key=f"{stem}_csv",
            use_container_width=True,
        )
        c2.download_button(
            f"{label} · XLSX",
            data=to_xlsx_bytes(frame, label),
            file_name=f"{stem}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{stem}_xlsx",
            use_container_width=True,
        )


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


def _format_file_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"
