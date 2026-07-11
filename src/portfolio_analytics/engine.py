from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .models import PortfolioAnalysis, PortfolioWorkbook
from .workbook import _canonical, _clean_text


TRADING_DAYS = 252
PORTFOLIO_ID = "PORTFOLIO"


def build_analysis(
    workbook: PortfolioWorkbook,
    annual_risk_free_rate: float = 0.0,
    forward_fill_prices: bool = True,
) -> PortfolioAnalysis:
    transactions = workbook.transactions.copy()
    prices = workbook.prices.copy()
    composition = workbook.composition.copy()

    asset_master = build_asset_master(transactions, prices, composition)
    composition = map_composition_assets(composition, asset_master)
    daily_asset, daily_portfolio = build_daily_performance(transactions, prices, asset_master, forward_fill_prices)
    annual = build_annual_performance(daily_portfolio, annual_risk_free_rate)
    rolling = build_rolling_performance(daily_portfolio, annual_risk_free_rate)
    holdings = build_holdings_snapshot(daily_asset, asset_master)
    allocation = build_allocation(daily_asset, daily_portfolio, composition, asset_master)
    monthly_returns = build_monthly_returns(daily_portfolio)
    correlation = build_correlation(prices)
    risk_by_asset = build_asset_risk(daily_asset, annual_risk_free_rate)
    diversification = build_diversification_metrics(allocation, correlation)
    transaction_summary, fees_by_broker, fees_by_asset = build_transaction_analytics(transactions)
    metrics = build_summary_metrics(daily_portfolio, holdings, transactions, annual_risk_free_rate)

    return PortfolioAnalysis(
        asset_master=asset_master,
        daily_asset=daily_asset,
        daily_portfolio=daily_portfolio,
        annual=annual,
        rolling=rolling,
        allocation=allocation,
        holdings=holdings,
        monthly_returns=monthly_returns,
        correlation=correlation,
        risk_by_asset=risk_by_asset,
        diversification=diversification,
        transaction_summary=transaction_summary,
        fees_by_broker=fees_by_broker,
        fees_by_asset=fees_by_asset,
        metrics=metrics,
    )


def build_asset_master(transactions: pd.DataFrame, prices: pd.DataFrame, composition: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    if not transactions.empty:
        for asset_id, group in transactions.groupby("asset_id"):
            rows.append(
                {
                    "asset_id": asset_id,
                    "product": _first_non_empty(group["product"]),
                    "isin": _first_non_empty(group["isin"]),
                    "has_transactions": True,
                    "has_prices": False,
                    "has_target": False,
                }
            )
    if not prices.empty:
        for asset_id, group in prices.groupby("asset_id"):
            rows.append(
                {
                    "asset_id": asset_id,
                    "product": _first_non_empty(group["product"]),
                    "isin": _first_non_empty(group["isin"]),
                    "has_transactions": False,
                    "has_prices": True,
                    "has_target": False,
                }
            )
    if not composition.empty:
        for asset_id, group in composition.groupby("asset_id"):
            rows.append(
                {
                    "asset_id": asset_id,
                    "product": _first_non_empty(group["product"]),
                    "isin": "",
                    "has_transactions": False,
                    "has_prices": False,
                    "has_target": True,
                }
            )
    if not rows:
        return pd.DataFrame(columns=["asset_id", "product", "isin", "has_transactions", "has_prices", "has_target"])

    master = pd.DataFrame(rows)
    master = (
        master.groupby("asset_id", as_index=False)
        .agg(
            product=("product", _first_non_empty),
            isin=("isin", _first_non_empty),
            has_transactions=("has_transactions", "max"),
            has_prices=("has_prices", "max"),
            has_target=("has_target", "max"),
        )
        .sort_values("product")
        .reset_index(drop=True)
    )
    return master


def map_composition_assets(composition: pd.DataFrame, asset_master: pd.DataFrame) -> pd.DataFrame:
    if composition.empty:
        return composition.copy()
    mapped = composition.copy()
    if asset_master.empty:
        return mapped

    by_asset = {row.asset_id: row.asset_id for row in asset_master.itertuples()}
    by_isin = {str(row.isin).upper(): row.asset_id for row in asset_master.itertuples() if _clean_text(row.isin)}
    by_product = {_canonical(row.product): row.asset_id for row in asset_master.itertuples() if _clean_text(row.product)}

    def choose_asset(row) -> str:
        raw = _clean_text(row["asset_id"])
        product = _clean_text(row["product"])
        return (
            by_asset.get(raw)
            or by_isin.get(raw.upper())
            or by_product.get(_canonical(product))
            or by_product.get(_canonical(raw))
            or raw
        )

    mapped["asset_id"] = mapped.apply(choose_asset, axis=1)
    return mapped


def build_daily_performance(
    transactions: pd.DataFrame,
    prices: pd.DataFrame,
    asset_master: pd.DataFrame,
    forward_fill_prices: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    asset_cols = [
        "date",
        "asset_id",
        "product",
        "isin",
        "price",
        "quantity",
        "value_eur",
        "weight",
        "average_price_eur",
        "total_investment_eur",
        "total_fees_eur",
        "cash_flow_eur",
        "return_eur",
        "total_return_eur",
        "hpr",
        "one_plus_hpr",
        "twr",
        "is_baseline",
    ]
    portfolio_cols = [
        "date",
        "value_eur",
        "total_investment_eur",
        "total_fees_eur",
        "cash_flow_eur",
        "return_eur",
        "total_return_eur",
        "hpr",
        "one_plus_hpr",
        "twr",
        "drawdown",
        "drawdown_pct",
        "is_baseline",
    ]
    if transactions.empty or prices.empty or asset_master.empty:
        return pd.DataFrame(columns=asset_cols), pd.DataFrame(columns=portfolio_cols)

    tx = transactions.copy()
    px = prices.copy()
    tx["date"] = pd.to_datetime(tx["date"]).dt.normalize()
    px["date"] = pd.to_datetime(px["date"]).dt.normalize()
    first_tx_date = tx["date"].min()

    assets = sorted(set(asset_master["asset_id"].dropna()) | set(tx["asset_id"].dropna()) | set(px["asset_id"].dropna()))
    dates = sorted(set(tx.loc[tx["date"] >= first_tx_date, "date"]) | set(px.loc[px["date"] >= first_tx_date, "date"]))
    if first_tx_date not in dates:
        dates = [first_tx_date] + dates
    dates = sorted(pd.to_datetime(dates))
    if not dates:
        return pd.DataFrame(columns=asset_cols), pd.DataFrame(columns=portfolio_cols)

    price_grid = (
        px.sort_values(["asset_id", "date"])
        .drop_duplicates(["date", "asset_id"], keep="last")
        .pivot(index="date", columns="asset_id", values="price")
        .reindex(dates)
    )
    if forward_fill_prices:
        price_grid = price_grid.ffill()
    price_grid = price_grid.reindex(columns=assets)
    price_long = price_grid.reset_index().melt(id_vars="date", var_name="asset_id", value_name="price")

    tx_calc = tx.copy()
    buy = tx_calc["action"].eq("Buy")
    sell = tx_calc["action"].eq("Sell")
    tx_calc["quantity_delta"] = np.select([buy, sell], [tx_calc["quantity"].abs(), -tx_calc["quantity"].abs()], default=0.0)
    tx_calc["buy_cash_flow_eur"] = np.where(buy, tx_calc["cash_flow_eur"].abs(), 0.0)
    tx_calc["sell_cash_flow_eur"] = np.where(sell, tx_calc["cash_flow_eur"].abs(), 0.0)
    tx_calc["fee_delta_eur"] = tx_calc["fee_eur"].fillna(0.0)
    tx_daily = (
        tx_calc.groupby(["date", "asset_id"], as_index=False)
        .agg(
            quantity_delta=("quantity_delta", "sum"),
            buy_cash_flow_eur=("buy_cash_flow_eur", "sum"),
            sell_cash_flow_eur=("sell_cash_flow_eur", "sum"),
            fee_delta_eur=("fee_delta_eur", "sum"),
        )
    )

    grid = pd.MultiIndex.from_product([dates, assets], names=["date", "asset_id"]).to_frame(index=False)
    out = grid.merge(price_long, on=["date", "asset_id"], how="left").merge(tx_daily, on=["date", "asset_id"], how="left")
    for col in ["quantity_delta", "buy_cash_flow_eur", "sell_cash_flow_eur", "fee_delta_eur"]:
        out[col] = out[col].fillna(0.0)

    out = out.sort_values(["asset_id", "date"]).reset_index(drop=True)
    out["quantity"] = out.groupby("asset_id")["quantity_delta"].cumsum()
    out["total_fees_eur"] = out.groupby("asset_id")["fee_delta_eur"].cumsum()
    out["investment_delta_eur"] = out["buy_cash_flow_eur"] - out["sell_cash_flow_eur"] + out["fee_delta_eur"]
    out["total_investment_eur"] = out.groupby("asset_id")["investment_delta_eur"].cumsum()
    out["value_eur"] = np.where(out["quantity"].abs() > 1e-12, out["quantity"] * out["price"], 0.0)
    out["average_price_eur"] = np.where(out["quantity"].abs() > 1e-12, out["total_investment_eur"] / out["quantity"], 0.0)
    out["previous_value_eur"] = out.groupby("asset_id")["value_eur"].shift().fillna(0.0)
    out["previous_investment_eur"] = out.groupby("asset_id")["total_investment_eur"].shift().fillna(0.0)
    out["cash_flow_eur"] = out["total_investment_eur"] - out["previous_investment_eur"]
    out["return_eur"] = out["value_eur"] - out["previous_value_eur"] - out["cash_flow_eur"]
    out["hpr"] = np.where(out["previous_value_eur"].abs() > 1e-12, out["return_eur"] / out["previous_value_eur"], 0.0)
    out["hpr"] = pd.Series(out["hpr"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    out["one_plus_hpr"] = 1.0 + out["hpr"]
    out["twr"] = out.groupby("asset_id")["one_plus_hpr"].cumprod() - 1.0
    out["total_return_eur"] = out.groupby("asset_id")["return_eur"].cumsum()
    out["is_baseline"] = out["date"].eq(first_tx_date)

    baseline_mask = out["is_baseline"]
    baseline_cols = [
        "quantity",
        "value_eur",
        "average_price_eur",
        "total_investment_eur",
        "total_fees_eur",
        "cash_flow_eur",
        "return_eur",
        "total_return_eur",
        "hpr",
        "twr",
    ]
    out.loc[baseline_mask, baseline_cols] = 0.0
    out.loc[baseline_mask, "one_plus_hpr"] = 1.0
    out.loc[baseline_mask, "price"] = np.nan

    # Recompute path-dependent fields after forcing the Excel-style zero baseline.
    out["previous_value_eur"] = out.groupby("asset_id")["value_eur"].shift().fillna(0.0)
    out["previous_investment_eur"] = out.groupby("asset_id")["total_investment_eur"].shift().fillna(0.0)
    out["cash_flow_eur"] = out["total_investment_eur"] - out["previous_investment_eur"]
    out["return_eur"] = out["value_eur"] - out["previous_value_eur"] - out["cash_flow_eur"]
    out["hpr"] = np.where(out["previous_value_eur"].abs() > 1e-12, out["return_eur"] / out["previous_value_eur"], 0.0)
    out["hpr"] = out["hpr"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    out["one_plus_hpr"] = 1.0 + out["hpr"]
    out["twr"] = out.groupby("asset_id")["one_plus_hpr"].cumprod() - 1.0
    out["total_return_eur"] = out.groupby("asset_id")["return_eur"].cumsum()
    out.loc[baseline_mask, ["cash_flow_eur", "return_eur", "total_return_eur", "hpr", "twr"]] = 0.0
    out.loc[baseline_mask, "one_plus_hpr"] = 1.0

    out = out.merge(asset_master[["asset_id", "product", "isin"]], on="asset_id", how="left")

    portfolio = (
        out.groupby("date", as_index=False)
        .agg(
            value_eur=("value_eur", "sum"),
            total_investment_eur=("total_investment_eur", "sum"),
            total_fees_eur=("total_fees_eur", "sum"),
            cash_flow_eur=("cash_flow_eur", "sum"),
            is_baseline=("is_baseline", "max"),
        )
        .sort_values("date")
    )
    portfolio["previous_value_eur"] = portfolio["value_eur"].shift().fillna(0.0)
    portfolio["return_eur"] = portfolio["value_eur"] - portfolio["previous_value_eur"] - portfolio["cash_flow_eur"]
    portfolio["hpr"] = np.where(
        portfolio["previous_value_eur"].abs() > 1e-12,
        portfolio["return_eur"] / portfolio["previous_value_eur"],
        0.0,
    )
    portfolio["hpr"] = portfolio["hpr"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    portfolio["one_plus_hpr"] = 1.0 + portfolio["hpr"]
    portfolio["twr"] = portfolio["one_plus_hpr"].cumprod() - 1.0
    portfolio["total_return_eur"] = portfolio["return_eur"].cumsum()
    peak = portfolio["value_eur"].cummax()
    portfolio["drawdown"] = portfolio["value_eur"] - peak
    portfolio["drawdown_pct"] = np.where(peak.abs() > 1e-12, portfolio["value_eur"] / peak - 1.0, 0.0)
    portfolio.loc[portfolio["is_baseline"], ["return_eur", "total_return_eur", "hpr", "twr", "drawdown", "drawdown_pct"]] = 0.0
    portfolio.loc[portfolio["is_baseline"], "one_plus_hpr"] = 1.0

    out = out.merge(portfolio[["date", "value_eur"]].rename(columns={"value_eur": "portfolio_value_eur"}), on="date", how="left")
    out["weight"] = np.where(out["portfolio_value_eur"].abs() > 1e-12, out["value_eur"] / out["portfolio_value_eur"], 0.0)

    return out[asset_cols].sort_values(["date", "asset_id"]).reset_index(drop=True), portfolio[portfolio_cols].reset_index(drop=True)


def build_holdings_snapshot(daily_asset: pd.DataFrame, asset_master: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "asset_id",
        "product",
        "isin",
        "price",
        "quantity",
        "value_eur",
        "weight",
        "average_price_eur",
        "total_investment_eur",
        "total_fees_eur",
        "total_return_eur",
        "twr",
    ]
    if daily_asset.empty:
        return pd.DataFrame(columns=cols)
    latest_date = daily_asset["date"].max()
    holdings = daily_asset[daily_asset["date"].eq(latest_date)].copy()
    holdings = holdings[cols].sort_values("value_eur", ascending=False).reset_index(drop=True)
    return holdings


def build_annual_performance(daily_portfolio: pd.DataFrame, annual_risk_free_rate: float) -> pd.DataFrame:
    if daily_portfolio.empty:
        return pd.DataFrame()
    years = sorted(daily_portfolio["date"].dt.year.unique())
    rows = []
    for year in years:
        rows.append(_period_metrics(daily_portfolio, pd.Timestamp(year=year, month=1, day=1), pd.Timestamp(year=year, month=12, day=31), 1.0, annual_risk_free_rate, year=year))
    return pd.DataFrame(rows)


def build_rolling_performance(daily_portfolio: pd.DataFrame, annual_risk_free_rate: float) -> pd.DataFrame:
    if daily_portfolio.empty:
        return pd.DataFrame()
    years = sorted(daily_portfolio["date"].dt.year.unique())
    if not years:
        return pd.DataFrame()
    rows = []
    min_year = int(min(years))
    max_year = int(max(years))
    for period_years in [1, 2, 3, 4, 5, 10]:
        if max_year - min_year + 1 < period_years:
            continue
        for start_year in range(min_year, max_year - period_years + 2):
            end_year = start_year + period_years - 1
            period_rows = daily_portfolio[(daily_portfolio["date"].dt.year >= start_year) & (daily_portfolio["date"].dt.year <= end_year)]
            if period_rows.empty:
                continue
            if start_year not in set(period_rows["date"].dt.year) or end_year not in set(period_rows["date"].dt.year):
                continue
            if not (period_rows["value_eur"] > 0).any():
                continue
            metrics = _period_metrics(
                daily_portfolio,
                pd.Timestamp(year=start_year, month=1, day=1),
                pd.Timestamp(year=end_year, month=12, day=31),
                float(period_years),
                annual_risk_free_rate,
            )
            metrics.update(
                {
                    "period_years": period_years,
                    "start_year": start_year,
                    "end_year": end_year,
                    "period": f"{start_year}-{end_year}",
                    "asset_id": PORTFOLIO_ID,
                }
            )
            rows.append(metrics)

    first_date = daily_portfolio["date"].min()
    last_date = daily_portfolio["date"].max()
    elapsed_years = max((last_date - first_date).days / 365.25, 1 / TRADING_DAYS)
    metrics = _period_metrics(daily_portfolio, first_date, last_date, elapsed_years, annual_risk_free_rate)
    metrics.update(
        {
            "period_years": elapsed_years,
            "start_year": int(first_date.year),
            "end_year": int(last_date.year),
            "period": "Since inception",
            "asset_id": PORTFOLIO_ID,
        }
    )
    rows.append(metrics)
    return pd.DataFrame(rows)


def _period_metrics(
    daily_portfolio: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    period_years: float,
    annual_risk_free_rate: float,
    year: int | None = None,
) -> dict[str, float | int | str]:
    rows = daily_portfolio[(daily_portfolio["date"] >= start_date) & (daily_portfolio["date"] <= end_date)].copy()
    prior = daily_portfolio[daily_portfolio["date"] < start_date].tail(1)
    start_value = float(prior["value_eur"].iloc[0]) if not prior.empty else (float(rows["value_eur"].iloc[0]) if not rows.empty else 0.0)
    end_value = float(rows["value_eur"].iloc[-1]) if not rows.empty else start_value
    returns = rows["hpr"].replace([np.inf, -np.inf], np.nan).dropna()
    trading_days = int(len(rows))
    period_twr = float((1.0 + returns).prod() - 1.0) if not returns.empty else 0.0
    annualized_twr = _annualize_return(period_twr, period_years)
    sample_sd = float(returns.std(ddof=1)) if len(returns) > 1 else np.nan
    period_volatility = sample_sd * math.sqrt(trading_days) if pd.notna(sample_sd) else np.nan
    annualized_volatility = sample_sd * math.sqrt(trading_days / max(period_years, 1 / TRADING_DAYS)) if pd.notna(sample_sd) else np.nan
    downside = returns[returns < 0]
    downside_sd = float(downside.std(ddof=1)) if len(downside) > 1 else np.nan
    downside_volatility = downside_sd * math.sqrt(trading_days / max(period_years, 1 / TRADING_DAYS)) if pd.notna(downside_sd) else np.nan
    sharpe = _safe_ratio(annualized_twr - annual_risk_free_rate, annualized_volatility)
    sortino = _safe_ratio(annualized_twr - annual_risk_free_rate, downside_volatility)
    period_drawdown = _max_drawdown_from_values(rows["value_eur"]) if not rows.empty else np.nan
    calmar = _safe_ratio(annualized_twr, abs(period_drawdown))
    positive_days = int((returns > 0).sum())
    negative_days = int((returns < 0).sum())
    row = {
        "asset_id": PORTFOLIO_ID,
        "trading_days": trading_days,
        "start_value_eur": start_value,
        "end_value_eur": end_value,
        "change_in_value_eur": end_value - start_value,
        "invested_eur": float(rows["cash_flow_eur"].sum()) if not rows.empty else 0.0,
        "fees_eur": _period_fee_change(daily_portfolio, rows, start_date),
        "return_eur": float(rows["return_eur"].sum()) if not rows.empty else 0.0,
        "period_twr": period_twr,
        "twr": period_twr,
        "annualized_return": annualized_twr,
        "annualized_twr": annualized_twr,
        "period_volatility": period_volatility,
        "annualized_volatility": annualized_volatility,
        "downside_volatility": downside_volatility,
        "max_drawdown": period_drawdown,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "best_day": float(returns.max()) if not returns.empty else np.nan,
        "worst_day": float(returns.min()) if not returns.empty else np.nan,
        "win_rate": positive_days / len(returns) if len(returns) else np.nan,
        "positive_days": positive_days,
        "negative_days": negative_days,
        "average_daily_return": float(returns.mean()) if not returns.empty else np.nan,
        "median_daily_return": float(returns.median()) if not returns.empty else np.nan,
        "skewness": float(returns.skew()) if len(returns) > 2 else np.nan,
        "kurtosis": float(returns.kurt()) if len(returns) > 3 else np.nan,
    }
    if year is not None:
        row["year"] = year
    return row


def _period_fee_change(daily_portfolio: pd.DataFrame, rows: pd.DataFrame, start_date: pd.Timestamp) -> float:
    if rows.empty:
        return 0.0
    prior = daily_portfolio[daily_portfolio["date"] < start_date].tail(1)
    start_fees = float(prior["total_fees_eur"].iloc[0]) if not prior.empty else 0.0
    end_fees = float(rows["total_fees_eur"].iloc[-1])
    return end_fees - start_fees


def build_allocation(
    daily_asset: pd.DataFrame,
    daily_portfolio: pd.DataFrame,
    composition: pd.DataFrame,
    asset_master: pd.DataFrame,
    selected_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    cols = [
        "date",
        "year",
        "asset_id",
        "product",
        "actual_weight",
        "target_weight",
        "drift",
        "absolute_drift",
        "tolerance",
        "out_of_tolerance",
        "current_value_eur",
        "target_value_eur",
        "rebalance_amount_eur",
    ]
    if daily_asset.empty or daily_portfolio.empty:
        return pd.DataFrame(columns=cols)
    if selected_date is None:
        selected_date = daily_portfolio["date"].max()
    selected_date = pd.Timestamp(selected_date).normalize()
    available_dates = daily_portfolio[daily_portfolio["date"] <= selected_date]["date"]
    if available_dates.empty:
        return pd.DataFrame(columns=cols)
    selected_date = available_dates.max()
    portfolio_value = float(daily_portfolio.loc[daily_portfolio["date"].eq(selected_date), "value_eur"].iloc[0])
    current = daily_asset[daily_asset["date"].eq(selected_date)][["asset_id", "product", "value_eur", "weight"]].copy()
    current = current.rename(columns={"value_eur": "current_value_eur", "weight": "actual_weight"})

    target = _target_for_year(composition, int(selected_date.year))
    all_assets = sorted(set(current["asset_id"]) | set(target["asset_id"] if not target.empty else []))
    base = pd.DataFrame({"asset_id": all_assets})
    product_map = dict(zip(asset_master["asset_id"], asset_master["product"])) if not asset_master.empty else {}
    base["product"] = base["asset_id"].map(product_map).fillna(base["asset_id"])
    allocation = base.merge(current[["asset_id", "current_value_eur", "actual_weight"]], on="asset_id", how="left")
    allocation = allocation.merge(target[["asset_id", "target_weight", "tolerance"]], on="asset_id", how="left") if not target.empty else allocation
    allocation["current_value_eur"] = allocation["current_value_eur"].fillna(0.0)
    allocation["actual_weight"] = allocation["actual_weight"].fillna(0.0)
    allocation["target_weight"] = allocation["target_weight"].fillna(0.0)
    allocation["tolerance"] = allocation["tolerance"].fillna(0.0)
    allocation["date"] = selected_date
    allocation["year"] = int(selected_date.year)
    allocation["target_value_eur"] = allocation["target_weight"] * portfolio_value
    allocation["rebalance_amount_eur"] = allocation["target_value_eur"] - allocation["current_value_eur"]
    allocation["drift"] = allocation["actual_weight"] - allocation["target_weight"]
    allocation["absolute_drift"] = allocation["drift"].abs()
    allocation["out_of_tolerance"] = allocation["absolute_drift"] > allocation["tolerance"]
    return allocation[cols].sort_values("absolute_drift", ascending=False).reset_index(drop=True)


def _target_for_year(composition: pd.DataFrame, year: int) -> pd.DataFrame:
    if composition.empty:
        return pd.DataFrame(columns=["asset_id", "target_weight", "tolerance"])
    eligible_years = sorted(y for y in composition["year"].dropna().unique() if y <= year)
    if not eligible_years:
        eligible_years = sorted(composition["year"].dropna().unique())
    if not eligible_years:
        return pd.DataFrame(columns=["asset_id", "target_weight", "tolerance"])
    selected_year = eligible_years[-1]
    target = composition[composition["year"].eq(selected_year)].copy()
    target = target.groupby("asset_id", as_index=False).agg(target_weight=("target_weight", "sum"), tolerance=("tolerance", "max"))
    return target


def build_monthly_returns(daily_portfolio: pd.DataFrame) -> pd.DataFrame:
    if daily_portfolio.empty:
        return pd.DataFrame(columns=["month_end", "year", "month", "monthly_return"])
    series = daily_portfolio.set_index("date")["hpr"].resample("ME").apply(lambda x: (1.0 + x).prod() - 1.0)
    out = series.reset_index().rename(columns={"date": "month_end", "hpr": "monthly_return"})
    out["year"] = out["month_end"].dt.year
    out["month"] = out["month_end"].dt.month
    return out[["month_end", "year", "month", "monthly_return"]]


def build_correlation(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()
    pivot = prices.sort_values("date").drop_duplicates(["date", "asset_id"], keep="last").pivot(index="date", columns="asset_id", values="price")
    returns = pivot.pct_change(fill_method=None).dropna(how="all")
    if returns.empty:
        return pd.DataFrame()
    return returns.corr()


def build_asset_risk(daily_asset: pd.DataFrame, annual_risk_free_rate: float) -> pd.DataFrame:
    if daily_asset.empty:
        return pd.DataFrame()
    rows = []
    for asset_id, group in daily_asset.groupby("asset_id"):
        returns = group["hpr"].replace([np.inf, -np.inf], np.nan).dropna()
        if returns.empty:
            continue
        twr = float((1 + returns).prod() - 1)
        elapsed_years = max((group["date"].max() - group["date"].min()).days / 365.25, 1 / TRADING_DAYS)
        annualized_return = _annualize_return(twr, elapsed_years)
        vol = float(returns.std(ddof=1) * math.sqrt(TRADING_DAYS)) if len(returns) > 1 else np.nan
        drawdown = _max_drawdown_from_values(group["value_eur"])
        rows.append(
            {
                "asset_id": asset_id,
                "product": _first_non_empty(group["product"]),
                "twr": twr,
                "annualized_return": annualized_return,
                "annualized_volatility": vol,
                "sharpe_ratio": _safe_ratio(annualized_return - annual_risk_free_rate, vol),
                "max_drawdown": drawdown,
                "current_weight": float(group["weight"].iloc[-1]),
                "current_value_eur": float(group["value_eur"].iloc[-1]),
            }
        )
    return pd.DataFrame(rows)


def build_diversification_metrics(allocation: pd.DataFrame, correlation: pd.DataFrame) -> dict[str, float]:
    if allocation.empty:
        return {
            "hhi": np.nan,
            "effective_positions": np.nan,
            "largest_weight": np.nan,
            "top3_weight": np.nan,
            "top5_weight": np.nan,
            "average_correlation": np.nan,
        }
    weights = allocation["actual_weight"].clip(lower=0.0)
    hhi = float(np.square(weights).sum())
    effective = 1.0 / hhi if hhi > 0 else np.nan
    sorted_weights = weights.sort_values(ascending=False).to_numpy()
    avg_corr = np.nan
    if correlation is not None and not correlation.empty and correlation.shape[0] > 1:
        corr_values = correlation.where(~np.eye(correlation.shape[0], dtype=bool)).stack()
        avg_corr = float(corr_values.mean()) if not corr_values.empty else np.nan
    return {
        "hhi": hhi,
        "effective_positions": effective,
        "largest_weight": float(sorted_weights[0]) if len(sorted_weights) else np.nan,
        "top3_weight": float(sorted_weights[:3].sum()) if len(sorted_weights) else np.nan,
        "top5_weight": float(sorted_weights[:5].sum()) if len(sorted_weights) else np.nan,
        "average_correlation": avg_corr,
    }


def build_transaction_analytics(transactions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if transactions.empty:
        empty = pd.DataFrame()
        return empty, empty, empty
    tx = transactions.copy()
    tx["gross_amount_eur"] = tx["quantity"].abs() * tx["price_eur"]
    summary = (
        tx.groupby("action", as_index=False)
        .agg(
            transactions=("action", "size"),
            quantity=("quantity", "sum"),
            cash_flow_eur=("cash_flow_eur", "sum"),
            gross_amount_eur=("gross_amount_eur", "sum"),
            fees_eur=("fee_eur", "sum"),
        )
        .sort_values("cash_flow_eur", ascending=False)
    )
    fees_by_broker = tx.groupby("broker", as_index=False)["fee_eur"].sum().sort_values("fee_eur", ascending=False)
    fees_by_asset = tx.groupby(["asset_id", "product"], as_index=False)["fee_eur"].sum().sort_values("fee_eur", ascending=False)
    return summary, fees_by_broker, fees_by_asset


def build_summary_metrics(
    daily_portfolio: pd.DataFrame,
    holdings: pd.DataFrame,
    transactions: pd.DataFrame,
    annual_risk_free_rate: float,
) -> dict[str, float]:
    if daily_portfolio.empty:
        return {}
    latest = daily_portfolio.iloc[-1]
    returns = daily_portfolio["hpr"].replace([np.inf, -np.inf], np.nan).dropna()
    twr = float(latest["twr"])
    elapsed_years = max((daily_portfolio["date"].max() - daily_portfolio["date"].min()).days / 365.25, 1 / TRADING_DAYS)
    annualized_return = _annualize_return(twr, elapsed_years)
    annualized_volatility = float(returns.std(ddof=1) * math.sqrt(TRADING_DAYS)) if len(returns) > 1 else np.nan
    downside = returns[returns < 0]
    downside_volatility = float(downside.std(ddof=1) * math.sqrt(TRADING_DAYS)) if len(downside) > 1 else np.nan
    max_drawdown = float(daily_portfolio["drawdown_pct"].min())
    current_drawdown = float(daily_portfolio["drawdown_pct"].iloc[-1])
    money_weighted = xirr_from_transactions(transactions, float(latest["value_eur"]), pd.Timestamp(latest["date"]))
    var_95 = float(np.percentile(returns, 5)) if len(returns) >= 20 else np.nan
    cvar_95 = float(returns[returns <= var_95].mean()) if pd.notna(var_95) else np.nan
    best_month, worst_month = _best_worst_month(daily_portfolio)
    return {
        "portfolio_value_eur": float(latest["value_eur"]),
        "total_invested_eur": float(latest["total_investment_eur"]),
        "net_contributions_eur": float(daily_portfolio["cash_flow_eur"].sum()),
        "total_fees_eur": float(latest["total_fees_eur"]),
        "total_return_eur": float(latest["value_eur"] - latest["total_investment_eur"]),
        "twr": twr,
        "money_weighted_return": money_weighted,
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "downside_volatility": downside_volatility,
        "sharpe_ratio": _safe_ratio(annualized_return - annual_risk_free_rate, annualized_volatility),
        "sortino_ratio": _safe_ratio(annualized_return - annual_risk_free_rate, downside_volatility),
        "calmar_ratio": _safe_ratio(annualized_return, abs(max_drawdown)),
        "max_drawdown": max_drawdown,
        "current_drawdown": current_drawdown,
        "value_at_risk_95": var_95,
        "conditional_var_95": cvar_95,
        "best_day": float(returns.max()) if not returns.empty else np.nan,
        "worst_day": float(returns.min()) if not returns.empty else np.nan,
        "win_rate": float((returns > 0).sum() / len(returns)) if len(returns) else np.nan,
        "average_daily_return": float(returns.mean()) if not returns.empty else np.nan,
        "median_daily_return": float(returns.median()) if not returns.empty else np.nan,
        "best_month": best_month,
        "worst_month": worst_month,
        "positions": float((holdings["value_eur"] > 0).sum()) if not holdings.empty else 0.0,
    }


def xirr_from_transactions(transactions: pd.DataFrame, terminal_value: float, terminal_date: pd.Timestamp) -> float:
    if transactions.empty:
        return np.nan
    cash_flows: list[tuple[pd.Timestamp, float]] = []
    for row in transactions.itertuples():
        if row.action == "Buy":
            cash_flows.append((pd.Timestamp(row.date), -abs(float(row.cash_flow_eur)) - abs(float(row.fee_eur))))
        elif row.action == "Sell":
            cash_flows.append((pd.Timestamp(row.date), abs(float(row.cash_flow_eur)) - abs(float(row.fee_eur))))
        elif float(row.fee_eur or 0.0) != 0.0:
            cash_flows.append((pd.Timestamp(row.date), -abs(float(row.fee_eur))))
    cash_flows.append((pd.Timestamp(terminal_date), float(terminal_value)))
    amounts = np.array([amount for _, amount in cash_flows], dtype=float)
    if not (np.any(amounts > 0) and np.any(amounts < 0)):
        return np.nan
    dates = [date for date, _ in cash_flows]
    day0 = min(dates)
    years = np.array([(date - day0).days / 365.25 for date in dates], dtype=float)

    def npv(rate: float) -> float:
        if rate <= -0.999999:
            return 1e18
        return float(np.sum(amounts / np.power(1.0 + rate, years)))

    low, high = -0.999, 10.0
    f_low, f_high = npv(low), npv(high)
    if np.sign(f_low) == np.sign(f_high):
        return np.nan
    for _ in range(100):
        mid = (low + high) / 2.0
        f_mid = npv(mid)
        if abs(f_mid) < 1e-8:
            return mid
        if np.sign(f_low) == np.sign(f_mid):
            low, f_low = mid, f_mid
        else:
            high = mid
    return (low + high) / 2.0


def rebalance_with_new_cash(allocation: pd.DataFrame, new_cash_eur: float) -> pd.DataFrame:
    if allocation.empty:
        return allocation.copy()
    out = allocation.copy()
    current_portfolio_value = float(out["current_value_eur"].sum())
    out["trade_existing_eur"] = out["rebalance_amount_eur"]
    out["new_cash_buy_eur"] = 0.0
    if new_cash_eur and new_cash_eur > 0:
        after_cash = current_portfolio_value + float(new_cash_eur)
        raw_buy = (out["target_weight"] * after_cash - out["current_value_eur"]).clip(lower=0.0)
        total_raw = float(raw_buy.sum())
        scale = min(1.0, float(new_cash_eur) / total_raw) if total_raw > 1e-12 else 0.0
        out["new_cash_buy_eur"] = raw_buy * scale
    return out


def _first_non_empty(values) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator is None or pd.isna(denominator) or abs(float(denominator)) < 1e-12:
        return np.nan
    if numerator is None or pd.isna(numerator):
        return np.nan
    return float(numerator) / float(denominator)


def _annualize_return(period_return: float, years: float) -> float:
    if pd.isna(period_return) or years <= 0:
        return np.nan
    if period_return <= -1.0:
        return -1.0
    return float((1.0 + period_return) ** (1.0 / years) - 1.0)


def _max_drawdown_from_values(values: pd.Series) -> float:
    if values.empty:
        return np.nan
    values = values.astype(float)
    peak = values.cummax()
    drawdown = np.where(peak.abs() > 1e-12, values / peak - 1.0, 0.0)
    return float(np.nanmin(drawdown)) if len(drawdown) else np.nan


def _best_worst_month(daily_portfolio: pd.DataFrame) -> tuple[float, float]:
    if daily_portfolio.empty:
        return np.nan, np.nan
    monthly = daily_portfolio.set_index("date")["hpr"].resample("ME").apply(lambda x: (1.0 + x).prod() - 1.0)
    monthly = monthly.dropna()
    if monthly.empty:
        return np.nan, np.nan
    return float(monthly.max()), float(monthly.min())
