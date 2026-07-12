from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


PLOT_TEMPLATE = "plotly_white"
QUALITATIVE = [
    "#2457c5",
    "#007c89",
    "#1b7f5f",
    "#c47a23",
    "#b43b45",
    "#6953b8",
    "#8a5a44",
    "#536579",
]


def _empty_figure(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(template=PLOT_TEMPLATE, title=title, height=320)
    fig.add_annotation(text="No data available", x=0.5, y=0.5, showarrow=False, xref="paper", yref="paper")
    return fig


def portfolio_value_chart(daily_portfolio: pd.DataFrame) -> go.Figure:
    if daily_portfolio.empty:
        return _empty_figure("Portfolio Value")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=daily_portfolio["date"], y=daily_portfolio["value_eur"], mode="lines", name="Portfolio value", line=dict(color=QUALITATIVE[0], width=3)))
    fig.add_trace(go.Scatter(x=daily_portfolio["date"], y=daily_portfolio["total_investment_eur"], mode="lines", name="Invested capital", line=dict(color=QUALITATIVE[2], width=2, dash="dot")))
    fig.update_layout(template=PLOT_TEMPLATE, height=390, title="Portfolio Value vs Invested Capital", legend=dict(orientation="h"), margin=dict(l=16, r=16, t=48, b=16))
    fig.update_yaxes(tickprefix="EUR ")
    return fig


def twr_chart(daily_portfolio: pd.DataFrame) -> go.Figure:
    if daily_portfolio.empty:
        return _empty_figure("Time-Weighted Return")
    fig = px.line(daily_portfolio, x="date", y="twr", template=PLOT_TEMPLATE, title="Time-Weighted Return")
    fig.update_traces(line=dict(color=QUALITATIVE[1], width=3))
    fig.update_layout(height=340, margin=dict(l=16, r=16, t=48, b=16))
    fig.update_yaxes(tickformat=".1%")
    return fig


def cash_flow_chart(daily_portfolio: pd.DataFrame) -> go.Figure:
    if daily_portfolio.empty:
        return _empty_figure("Cash Flows")
    data = daily_portfolio[daily_portfolio["cash_flow_eur"].abs() > 1e-9]
    if data.empty:
        return _empty_figure("Cash Flows")
    fig = px.bar(data, x="date", y="cash_flow_eur", template=PLOT_TEMPLATE, title="Cash Flows")
    fig.update_traces(marker_color=np.where(data["cash_flow_eur"] >= 0, QUALITATIVE[0], QUALITATIVE[3]))
    fig.update_layout(height=300, margin=dict(l=16, r=16, t=48, b=16), showlegend=False)
    fig.update_yaxes(tickprefix="EUR ")
    return fig


def drawdown_chart(daily_portfolio: pd.DataFrame) -> go.Figure:
    if daily_portfolio.empty:
        return _empty_figure("Drawdown")
    fig = px.area(daily_portfolio, x="date", y="drawdown_pct", template=PLOT_TEMPLATE, title="Drawdown")
    fig.update_traces(line=dict(color=QUALITATIVE[3], width=1.5), fillcolor="rgba(220, 38, 38, 0.18)")
    fig.update_layout(height=320, margin=dict(l=16, r=16, t=48, b=16))
    fig.update_yaxes(tickformat=".1%")
    return fig


def daily_returns_chart(daily_portfolio: pd.DataFrame) -> go.Figure:
    if daily_portfolio.empty:
        return _empty_figure("Daily Returns")
    fig = px.bar(daily_portfolio, x="date", y="hpr", template=PLOT_TEMPLATE, title="Daily Holding-Period Returns")
    fig.update_traces(marker_color=np.where(daily_portfolio["hpr"] >= 0, QUALITATIVE[1], QUALITATIVE[3]))
    fig.update_layout(height=320, margin=dict(l=16, r=16, t=48, b=16), showlegend=False)
    fig.update_yaxes(tickformat=".2%")
    return fig


def monthly_heatmap(monthly_returns: pd.DataFrame) -> go.Figure:
    if monthly_returns.empty:
        return _empty_figure("Monthly Returns")
    pivot = monthly_returns.pivot(index="year", columns="month", values="monthly_return").reindex(columns=range(1, 13))
    labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=labels,
            y=pivot.index.astype(str),
            colorscale="RdYlGn",
            zmid=0,
            hovertemplate="%{y} %{x}<br>%{z:.2%}<extra></extra>",
        )
    )
    fig.update_layout(template=PLOT_TEMPLATE, height=340, title="Monthly Return Heatmap", margin=dict(l=16, r=16, t=48, b=16))
    return fig


def annual_return_bar(annual: pd.DataFrame) -> go.Figure:
    if annual.empty or "year" not in annual.columns:
        return _empty_figure("Annual Performance")
    fig = px.bar(annual, x="year", y="twr", template=PLOT_TEMPLATE, title="Calendar-Year TWR")
    fig.update_traces(marker_color=np.where(annual["twr"] >= 0, QUALITATIVE[1], QUALITATIVE[3]))
    fig.update_layout(height=320, margin=dict(l=16, r=16, t=48, b=16), showlegend=False)
    fig.update_yaxes(tickformat=".1%")
    return fig


def position_value_chart(daily_asset: pd.DataFrame) -> go.Figure:
    if daily_asset.empty:
        return _empty_figure("Position Values")
    fig = px.line(daily_asset, x="date", y="value_eur", color="product", template=PLOT_TEMPLATE, title="Position Values", color_discrete_sequence=QUALITATIVE)
    fig.update_layout(height=390, margin=dict(l=16, r=16, t=48, b=16), legend=dict(orientation="h"))
    fig.update_yaxes(tickprefix="EUR ")
    return fig


def quantity_chart(daily_asset: pd.DataFrame) -> go.Figure:
    if daily_asset.empty:
        return _empty_figure("Position Quantities")
    fig = px.line(daily_asset, x="date", y="quantity", color="product", template=PLOT_TEMPLATE, title="Position Quantities", color_discrete_sequence=QUALITATIVE)
    fig.update_layout(height=320, margin=dict(l=16, r=16, t=48, b=16), legend=dict(orientation="h"))
    return fig


def weights_area_chart(daily_asset: pd.DataFrame) -> go.Figure:
    if daily_asset.empty:
        return _empty_figure("Asset Weights")
    fig = px.area(daily_asset, x="date", y="weight", color="product", template=PLOT_TEMPLATE, title="Asset Weights Over Time", color_discrete_sequence=QUALITATIVE)
    fig.update_layout(height=340, margin=dict(l=16, r=16, t=48, b=16), legend=dict(orientation="h"))
    fig.update_yaxes(tickformat=".0%")
    return fig


def allocation_donut(allocation: pd.DataFrame, value_col: str, title: str) -> go.Figure:
    if allocation.empty or value_col not in allocation.columns or allocation[value_col].sum() <= 0:
        return _empty_figure(title)
    fig = px.pie(allocation, values=value_col, names="product", hole=0.58, template=PLOT_TEMPLATE, title=title, color_discrete_sequence=QUALITATIVE)
    fig.update_layout(height=350, margin=dict(l=16, r=16, t=48, b=16), legend=dict(orientation="h"))
    fig.update_traces(textposition="inside", texttemplate="%{percent:.1%}")
    return fig


def target_actual_bar(allocation: pd.DataFrame) -> go.Figure:
    if allocation.empty:
        return _empty_figure("Actual vs Target")
    plot = allocation.melt(id_vars=["product"], value_vars=["actual_weight", "target_weight"], var_name="series", value_name="weight")
    plot["series"] = plot["series"].replace({"actual_weight": "Actual", "target_weight": "Target"})
    fig = px.bar(plot, x="product", y="weight", color="series", barmode="group", template=PLOT_TEMPLATE, title="Actual vs Target Allocation", color_discrete_sequence=[QUALITATIVE[0], QUALITATIVE[2]])
    fig.update_layout(height=360, margin=dict(l=16, r=16, t=48, b=16), legend=dict(orientation="h"))
    fig.update_yaxes(tickformat=".0%")
    return fig


def drift_bar(allocation: pd.DataFrame) -> go.Figure:
    if allocation.empty:
        return _empty_figure("Allocation Drift")
    fig = px.bar(allocation.sort_values("drift"), x="drift", y="product", orientation="h", template=PLOT_TEMPLATE, title="Allocation Drift")
    fig.update_traces(marker_color=np.where(allocation.sort_values("drift")["out_of_tolerance"], QUALITATIVE[3], QUALITATIVE[1]))
    fig.update_layout(height=360, margin=dict(l=16, r=16, t=48, b=16), showlegend=False)
    fig.update_xaxes(tickformat=".1%")
    return fig


def rolling_metric_chart(rolling: pd.DataFrame, metric: str, title: str) -> go.Figure:
    if rolling.empty or metric not in rolling.columns:
        return _empty_figure(title)
    data = rolling[rolling["period"] != "Since inception"].copy()
    if data.empty:
        return _empty_figure(title)
    data["period_years_label"] = data["period_years"].map(_format_period_years)
    fig = px.line(
        data,
        x="period",
        y=metric,
        color="period_years_label",
        markers=True,
        template=PLOT_TEMPLATE,
        title=title,
        color_discrete_sequence=QUALITATIVE,
        labels={"period_years_label": "Window"},
    )
    fig.update_layout(height=340, margin=dict(l=16, r=16, t=48, b=16), legend=dict(orientation="h"))
    if "ratio" not in metric and "days" not in metric:
        fig.update_yaxes(tickformat=".1%")
    return fig


def _format_period_years(value) -> str:
    if pd.isna(value):
        return "Unknown"
    years = float(value)
    if years.is_integer():
        return f"{int(years)}Y"
    return f"{years:.1f}Y"


def correlation_heatmap(correlation: pd.DataFrame) -> go.Figure:
    if correlation.empty:
        return _empty_figure("Correlation Matrix")
    fig = go.Figure(
        data=go.Heatmap(
            z=correlation.values,
            x=correlation.columns,
            y=correlation.index,
            colorscale="RdBu",
            zmid=0,
            zmin=-1,
            zmax=1,
            hovertemplate="%{y} vs %{x}<br>%{z:.2f}<extra></extra>",
        )
    )
    fig.update_layout(template=PLOT_TEMPLATE, height=380, title="Asset Return Correlation", margin=dict(l=16, r=16, t=48, b=16))
    return fig


def return_distribution(daily_portfolio: pd.DataFrame, var_95: float | None = None) -> go.Figure:
    if daily_portfolio.empty:
        return _empty_figure("Return Distribution")
    fig = px.histogram(daily_portfolio, x="hpr", nbins=60, template=PLOT_TEMPLATE, title="Daily Return Distribution", color_discrete_sequence=[QUALITATIVE[0]])
    if var_95 is not None and pd.notna(var_95):
        fig.add_vline(x=var_95, line_dash="dash", line_color=QUALITATIVE[3], annotation_text="VaR 95%")
    fig.update_layout(height=320, margin=dict(l=16, r=16, t=48, b=16))
    fig.update_xaxes(tickformat=".2%")
    return fig


def risk_return_scatter(risk_by_asset: pd.DataFrame) -> go.Figure:
    if risk_by_asset.empty:
        return _empty_figure("Risk/Return by Asset")
    fig = px.scatter(
        risk_by_asset,
        x="annualized_volatility",
        y="annualized_return",
        size="current_value_eur",
        color="product",
        hover_name="product",
        template=PLOT_TEMPLATE,
        title="Risk and Return by Asset",
        color_discrete_sequence=QUALITATIVE,
    )
    fig.update_layout(height=340, margin=dict(l=16, r=16, t=48, b=16), legend=dict(orientation="h"))
    fig.update_xaxes(tickformat=".1%")
    fig.update_yaxes(tickformat=".1%")
    return fig


def transaction_timeline(transactions: pd.DataFrame) -> go.Figure:
    if transactions.empty:
        return _empty_figure("Transactions")
    tx = transactions.copy()
    tx["amount_eur"] = tx["cash_flow_eur"].abs()
    fig = px.scatter(
        tx,
        x="date",
        y="price_eur",
        color="product",
        symbol="action",
        size="amount_eur",
        hover_data=["broker", "exchange", "quantity", "cash_flow_eur", "fee_eur"],
        template=PLOT_TEMPLATE,
        title="Transaction Timeline",
        color_discrete_sequence=QUALITATIVE,
    )
    fig.update_layout(height=360, margin=dict(l=16, r=16, t=48, b=16), legend=dict(orientation="h"))
    fig.update_yaxes(tickprefix="EUR ")
    return fig


def fees_bar(df: pd.DataFrame, label_col: str, title: str) -> go.Figure:
    if df.empty or "fee_eur" not in df.columns:
        return _empty_figure(title)
    fig = px.bar(df, x=label_col, y="fee_eur", template=PLOT_TEMPLATE, title=title, color_discrete_sequence=[QUALITATIVE[2]])
    fig.update_layout(height=300, margin=dict(l=16, r=16, t=48, b=16))
    fig.update_yaxes(tickprefix="EUR ")
    return fig


def price_history_chart(prices: pd.DataFrame) -> go.Figure:
    if prices.empty:
        return _empty_figure("Historical Prices")
    fig = px.line(prices, x="date", y="price", color="product", template=PLOT_TEMPLATE, title="Historical Prices", color_discrete_sequence=QUALITATIVE)
    fig.update_layout(height=420, margin=dict(l=16, r=16, t=48, b=16), legend=dict(orientation="h"))
    fig.update_yaxes(tickprefix="EUR ")
    return fig
