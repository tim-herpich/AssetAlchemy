from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from typing import Iterable

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .models import PortfolioWorkbook, ValidationMessage


SHEET_PORTFOLIO_COMPOSITION = "Portfolio Composition"
SHEET_HISTORICAL_PRICES = "Historical Prices"
SHEET_TRANSACTIONS = "Transactions"
SHEET_DAILY_PERFORMANCE = "Daily Performance"
REQUIRED_SHEETS = [
    SHEET_PORTFOLIO_COMPOSITION,
    SHEET_HISTORICAL_PRICES,
    SHEET_TRANSACTIONS,
]

TRANSACTION_EXCEL_HEADERS = [
    "Broker",
    "Product",
    "ISIN",
    "Date",
    "Exchange",
    "Action",
    "Quantity",
    "Price in \u20ac",
    "Cash Flow in \u20ac",
    "Fee in \u20ac",
]
TRANSACTION_COLUMNS = [
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
]
PRICE_HEADERS = ["Product", "ISIN", "Date", "Price"]
RISK_FREE_GROUP_HEADER = "Risk-Free Government Bonds"
RISK_FREE_EXCEL_HEADERS = [
    "Year",
    "Country",
    "1Y-Yield",
    "3Y-Yield",
    "5Y-Yield",
    "10Y-Yield",
    "20Y-Yield",
    "30Y-Yield",
]
RISK_FREE_COLUMNS = [
    "year",
    "country",
    "yield_1y",
    "yield_3y",
    "yield_5y",
    "yield_10y",
    "yield_20y",
    "yield_30y",
]
DAILY_PERFORMANCE_COLUMNS = [
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
]
COMPOSITION_TARGET_HEADER = "Target Weight in Portfolio"
COMPOSITION_TOLERANCE_HEADER = "Weight Deviation Tolerance"
SUPPORTED_ACTIONS = {"Buy", "Sell", "Transfer"}
PRICE_MISMATCH_WARNING_THRESHOLD = 0.20


def _clean_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _canonical(value) -> str:
    return " ".join(_clean_text(value).lower().replace("\u00a0", " ").split())


def _normalize_isin(value) -> str:
    text = _clean_text(value).upper().replace(" ", "")
    if text in {"", "NAN", "NONE"}:
        return ""
    return text


def _first_non_empty(values) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _asset_id_from_product(value) -> str:
    return _canonical(value)


def make_asset_id(product, isin) -> str:
    isin_text = _normalize_isin(isin)
    product_text = _asset_id_from_product(product)
    return isin_text or product_text


def _message(messages: list[ValidationMessage], severity: str, sheet: str, message: str, rows: Iterable[int] | None = None) -> None:
    row_text = ""
    if rows:
        row_text = ", ".join(str(r) for r in sorted(set(rows))[:20])
    messages.append(ValidationMessage(severity=severity, sheet=sheet, message=message, rows=row_text))


def _format_values(values: Iterable, max_items: int = 6) -> str:
    cleaned = sorted({text for text in (_clean_text(value) for value in values) if text})
    if not cleaned:
        return "blank"
    suffix = "" if len(cleaned) <= max_items else f", and {len(cleaned) - max_items} more"
    return ", ".join(cleaned[:max_items]) + suffix


def _format_pct_delta(value: float) -> str:
    return f"{value:.1%}"


def _most_common_non_empty(values: Iterable) -> str:
    counts: dict[str, int] = {}
    first_index: dict[str, int] = {}
    for index, value in enumerate(values):
        text = _normalize_isin(value)
        if not text:
            continue
        counts[text] = counts.get(text, 0) + 1
        first_index.setdefault(text, index)
    if not counts:
        return ""
    return min(counts, key=lambda item: (-counts[item], first_index[item]))


def _parse_number(value) -> float:
    if value is None or pd.isna(value):
        return np.nan
    if isinstance(value, str):
        text = value.strip().replace("\u20ac", "").replace(",", "")
        if text == "":
            return np.nan
        return pd.to_numeric(text, errors="coerce")
    return pd.to_numeric(value, errors="coerce")


def _parse_percent(value) -> tuple[float, bool]:
    if value is None or pd.isna(value):
        return np.nan, False
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        if not text:
            return np.nan, False
        if text.endswith("%"):
            parsed = pd.to_numeric(text[:-1], errors="coerce")
            return (float(parsed) / 100.0 if pd.notna(parsed) else np.nan), False
        parsed = pd.to_numeric(text, errors="coerce")
    else:
        parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return np.nan, False
    parsed = float(parsed)
    if 1.0 < abs(parsed) <= 100.0:
        return parsed / 100.0, True
    return parsed, False


def _normalize_action(value) -> str:
    text = _canonical(value)
    if text in {"buy", "bought", "purchase", "purchased"}:
        return "Buy"
    if text in {"sell", "sold", "sale"}:
        return "Sell"
    if text in {"transfer", "transfer in", "transfer out"}:
        return "Transfer"
    return _clean_text(value)


def _parse_transaction_date_value(
    value,
    source_row: int,
    messages: list[ValidationMessage],
    text_date_mode: str,
) -> pd.Timestamp | pd.NaT:
    if value is None or pd.isna(value):
        return pd.NaT
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return pd.NaT
        if text_date_mode == "permissive":
            parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
            if pd.isna(parsed):
                _message(messages, "Error", SHEET_TRANSACTIONS, f"Transactions row {source_row} has an invalid text date '{text}'.", [source_row])
                return pd.NaT
            _message(
                messages,
                "Warning",
                SHEET_TRANSACTIONS,
                f"Transactions row {source_row} has a text date '{text}'. Parsed day-first in permissive mode; convert it to a real Excel date to avoid mismatched calculations.",
                [source_row],
            )
            return pd.Timestamp(parsed).normalize()
        _message(
            messages,
            "Error",
            SHEET_TRANSACTIONS,
            f"Transactions row {source_row} has a text date '{text}'. Convert it to a real Excel date to avoid mismatched calculations.",
            [source_row],
        )
        return pd.NaT
    if isinstance(value, (pd.Timestamp, datetime, date, np.datetime64)):
        parsed = pd.to_datetime(value, errors="coerce")
        return pd.Timestamp(parsed).normalize() if pd.notna(parsed) else pd.NaT
    parsed = pd.to_datetime(value, errors="coerce")
    return pd.Timestamp(parsed).normalize() if pd.notna(parsed) else pd.NaT


def _read_excel_raw(file_obj) -> tuple[pd.ExcelFile, dict[str, pd.DataFrame]]:
    xls = pd.ExcelFile(file_obj)
    raw = {sheet: xls.parse(sheet, header=None) for sheet in xls.sheet_names}
    return xls, raw


def parse_workbook(file_obj, text_date_mode: str = "strict") -> PortfolioWorkbook:
    xls, raw_sheets = _read_excel_raw(file_obj)
    messages: list[ValidationMessage] = []

    missing = [sheet for sheet in REQUIRED_SHEETS if sheet not in raw_sheets]
    for sheet in missing:
        _message(messages, "Error", sheet, f"Required sheet '{sheet}' is missing.")
    optional_sheets = {SHEET_DAILY_PERFORMANCE}
    extra = [sheet for sheet in xls.sheet_names if sheet not in REQUIRED_SHEETS and sheet not in optional_sheets]
    if extra:
        _message(messages, "Warning", "Workbook", "Input workbook has extra sheets beyond the supported inputs; unsupported sheets are ignored.")

    prices = (
        _parse_prices(raw_sheets[SHEET_HISTORICAL_PRICES], messages)
        if SHEET_HISTORICAL_PRICES in raw_sheets
        else _empty_prices()
    )
    transactions = (
        _parse_transactions(raw_sheets[SHEET_TRANSACTIONS], messages, text_date_mode=text_date_mode)
        if SHEET_TRANSACTIONS in raw_sheets
        else _empty_transactions()
    )
    transactions = _map_transactions_to_price_assets(transactions, prices, messages)
    _flag_transaction_identity_findings(transactions, messages)
    risk_free_rates = (
        _parse_risk_free_rates(raw_sheets[SHEET_HISTORICAL_PRICES], messages)
        if SHEET_HISTORICAL_PRICES in raw_sheets
        else _empty_risk_free_rates()
    )
    composition = (
        _parse_composition(raw_sheets[SHEET_PORTFOLIO_COMPOSITION], messages)
        if SHEET_PORTFOLIO_COMPOSITION in raw_sheets
        else _empty_composition()
    )
    daily_performance_reference = (
        _parse_daily_performance(raw_sheets[SHEET_DAILY_PERFORMANCE], messages)
        if SHEET_DAILY_PERFORMANCE in raw_sheets
        else _empty_daily_performance_reference()
    )

    _flag_negative_quantities(transactions, messages)
    _flag_transaction_price_mismatches(transactions, prices, messages)
    _cross_validate(transactions, prices, composition, messages)

    return PortfolioWorkbook(
        transactions=transactions,
        prices=prices,
        composition=composition,
        validation=messages,
        workbook_sheets=xls.sheet_names,
        risk_free_rates=risk_free_rates,
        daily_performance_reference=daily_performance_reference,
    )


def _empty_transactions() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "broker",
            "product",
            "isin",
            "asset_id",
            "date",
            "exchange",
            "action",
            "quantity",
            "price_eur",
            "cash_flow_eur",
            "fee_eur",
            "source_row",
        ]
    )


def _empty_prices() -> pd.DataFrame:
    return pd.DataFrame(columns=["product", "isin", "asset_id", "date", "price", "source_row", "block"])


def _empty_risk_free_rates() -> pd.DataFrame:
    return pd.DataFrame(columns=RISK_FREE_COLUMNS)


def _empty_daily_performance_reference() -> pd.DataFrame:
    return pd.DataFrame(columns=DAILY_PERFORMANCE_COLUMNS + ["source_row"])


def _empty_composition() -> pd.DataFrame:
    return pd.DataFrame(columns=["year", "product", "isin", "asset_id", "target_weight", "tolerance", "source_row", "target_column"])


def _parse_transactions(
    raw: pd.DataFrame,
    messages: list[ValidationMessage],
    text_date_mode: str = "strict",
) -> pd.DataFrame:
    sheet = SHEET_TRANSACTIONS
    if raw.shape[0] < 2 or raw.shape[1] < 10:
        _message(messages, "Error", sheet, "Transactions sheet must contain A1:J2 with the All Transactions section and exact headers.")
        return _empty_transactions()

    group_header = _clean_text(raw.iat[0, 0])
    if group_header != "All Transactions":
        _message(messages, "Error", sheet, "Cell A1 must be 'All Transactions'.")

    row2 = [_clean_text(raw.iat[1, idx]) if idx < raw.shape[1] else "" for idx in range(10)]
    if row2 != TRANSACTION_EXCEL_HEADERS:
        _message(messages, "Error", sheet, "Row 2 headers must exactly match the required A:J Transactions labels.")

    body = raw.iloc[2:, :10].copy()
    body.columns = TRANSACTION_COLUMNS
    body["source_row"] = body.index + 1
    body = body.dropna(how="all").copy()
    if body.empty:
        _message(messages, "Warning", sheet, "Transactions sheet contains no data rows.")
        return _empty_transactions()

    for col in ["broker", "product", "isin", "exchange", "action"]:
        body[col] = body[col].map(_clean_text)
    body["isin"] = body["isin"].map(_normalize_isin)
    body["asset_id"] = [make_asset_id(p, i) for p, i in zip(body["product"], body["isin"])]
    parsed_dates = [
        _parse_transaction_date_value(value, int(source_row), messages, text_date_mode)
        for value, source_row in zip(body["date"], body["source_row"])
    ]
    body["date"] = pd.Series(pd.to_datetime(parsed_dates, errors="coerce"), index=body.index).dt.normalize()
    body["action"] = body["action"].map(_normalize_action)
    for col in ["quantity", "price_eur", "cash_flow_eur", "fee_eur"]:
        body[col] = body[col].map(_parse_number).astype(float)
    body["fee_eur"] = body["fee_eur"].fillna(0.0)

    _flag_rows(body, body["date"].isna(), messages, "Error", sheet, "Transaction dates must parse as dates.")
    _flag_rows(body, body["asset_id"].eq(""), messages, "Error", sheet, "Each transaction row needs an ISIN or Product.")

    unsupported = ~body["action"].isin(SUPPORTED_ACTIONS)
    _flag_rows(body, unsupported, messages, "Warning", sheet, "Unsupported actions are preserved but ignored by calculations.")

    cash_actions = body["action"].isin(["Buy", "Sell"])
    _flag_rows(body, cash_actions & body["quantity"].isna(), messages, "Error", sheet, "Buy/Sell rows require numeric Quantity.")
    _flag_rows(body, cash_actions & body["price_eur"].isna(), messages, "Warning", sheet, "Buy/Sell rows should include numeric Price in EUR.")
    _flag_rows(body, cash_actions & body["cash_flow_eur"].isna(), messages, "Error", sheet, "Buy/Sell rows require numeric Cash Flow in EUR.")
    _flag_rows(body, cash_actions & (body["quantity"] < 0), messages, "Warning", sheet, "Quantity should be entered as a positive amount; action controls direction.")
    _flag_rows(body, cash_actions & (body["cash_flow_eur"] < 0), messages, "Warning", sheet, "Cash Flow in EUR should be entered as a positive amount.")

    duplicates = body.duplicated(
        subset=["broker", "product", "isin", "date", "action", "quantity", "price_eur", "cash_flow_eur", "fee_eur"],
        keep=False,
    )
    _flag_rows(body, duplicates, messages, "Warning", sheet, "Potential duplicate transaction rows detected.")

    valid = body.dropna(subset=["date"]).copy()
    valid["quantity"] = valid["quantity"].fillna(0.0)
    valid["price_eur"] = valid["price_eur"].fillna(0.0)
    valid["cash_flow_eur"] = valid["cash_flow_eur"].fillna(0.0)

    return valid[_empty_transactions().columns].sort_values(["date", "source_row"]).reset_index(drop=True)


def _map_transactions_to_price_assets(
    transactions: pd.DataFrame,
    prices: pd.DataFrame,
    messages: list[ValidationMessage],
) -> pd.DataFrame:
    if transactions.empty or prices.empty:
        return transactions

    out = transactions.copy()
    product_to_asset = _unique_price_lookup(prices, "product", _canonical)
    isin_to_asset = _unique_price_lookup(prices, "isin", _normalize_isin)
    asset_labels = prices.groupby("asset_id")["product"].agg(_first_non_empty).to_dict()
    asset_isins = prices.groupby("asset_id")["isin"].agg(lambda values: sorted({isin for isin in values.map(_normalize_isin) if isin})).to_dict()
    mapped_ids: list[str] = []

    for row in out.itertuples():
        product_key = _canonical(row.product)
        isin_key = _normalize_isin(row.isin)
        product_asset = product_to_asset.get(product_key) if product_key else None
        isin_asset = isin_to_asset.get(isin_key) if isin_key else None
        selected_asset = _clean_text(row.asset_id)

        if isin_asset:
            selected_asset = isin_asset
            if product_asset and product_asset != isin_asset:
                _message(
                    messages,
                    "Warning",
                    "Cross-sheet",
                    f"Transaction row {int(row.source_row)} has a product/ISIN mismatch: ISIN {row.isin} matches Historical Prices asset '{asset_labels.get(isin_asset, isin_asset)}', but product '{row.product}' matches '{asset_labels.get(product_asset, product_asset)}'. ISIN matching was used.",
                    [int(row.source_row)],
                )
        elif product_asset:
            selected_asset = product_asset
            expected_isins = _format_values(asset_isins.get(product_asset, []))
            _message(
                messages,
                "Warning",
                "Cross-sheet",
                f"Transaction row {int(row.source_row)} could not be matched by ISIN {row.isin or 'blank'}. It was matched by product '{row.product}' to Historical Prices asset '{asset_labels.get(product_asset, product_asset)}'. Historical Prices ISIN values for that asset: {expected_isins}. Verify the missing or inconsistent ISIN.",
                [int(row.source_row)],
            )
        mapped_ids.append(selected_asset)

    out["asset_id"] = mapped_ids
    return out


def _flag_transaction_identity_findings(
    transactions: pd.DataFrame,
    messages: list[ValidationMessage],
) -> None:
    if transactions.empty:
        return

    tx = transactions.copy()
    tx["_product_key"] = tx["product"].map(_canonical)
    tx["_isin_key"] = tx["isin"].map(_normalize_isin)

    for product_key, group in tx[tx["_product_key"].astype(str).str.len() > 0].groupby("_product_key"):
        isins = sorted({isin for isin in group["_isin_key"] if isin})
        if len(isins) > 1:
            rows = group["source_row"].dropna().astype(int).tolist()
            product = _first_non_empty(group["product"])
            _message(
                messages,
                "Warning",
                SHEET_TRANSACTIONS,
                f"Transactions product '{product}' appears with multiple ISIN values: {_format_values(isins)}. ISIN is the primary asset key, so these rows may become separate assets unless the Product/ISIN values are corrected.",
                rows,
            )

    for isin, group in tx[tx["_isin_key"].astype(str).str.len() > 0].groupby("_isin_key"):
        products = sorted({_clean_text(product) for product in group["product"] if _clean_text(product)})
        if len(products) > 1:
            rows = group["source_row"].dropna().astype(int).tolist()
            _message(
                messages,
                "Warning",
                SHEET_TRANSACTIONS,
                f"Transactions ISIN {isin} appears with multiple Product names: {_format_values(products)}. ISIN matching keeps them under one asset, but verify the product labels for reporting clarity.",
                rows,
            )


def _unique_price_lookup(prices: pd.DataFrame, column: str, normalizer) -> dict[str, str]:
    if prices.empty or column not in prices.columns:
        return {}
    values = prices[[column, "asset_id"]].copy()
    values["_key"] = values[column].map(normalizer)
    values = values[values["_key"].astype(str).str.len() > 0]
    lookup: dict[str, str] = {}
    for key, group in values.groupby("_key"):
        asset_ids = sorted(set(group["asset_id"].dropna().map(_clean_text)))
        if len(asset_ids) == 1:
            lookup[key] = asset_ids[0]
    if column == "product":
        for asset_id in prices["asset_id"].dropna().map(_clean_text).unique():
            if asset_id:
                lookup.setdefault(_canonical(asset_id), asset_id)
    return lookup


def _flag_negative_quantities(transactions: pd.DataFrame, messages: list[ValidationMessage]) -> None:
    if transactions.empty:
        return
    valid = transactions.copy()
    signed = np.select(
        [valid["action"].eq("Buy"), valid["action"].eq("Sell")],
        [valid["quantity"].abs(), -valid["quantity"].abs()],
        default=0.0,
    )
    valid["_signed_quantity"] = signed
    quantity_check = valid.sort_values(["asset_id", "date", "source_row"]).copy()
    quantity_check["cumulative_quantity"] = quantity_check.groupby("asset_id")["_signed_quantity"].cumsum()
    _flag_rows(
        quantity_check,
        quantity_check["cumulative_quantity"] < -1e-9,
        messages,
        "Warning",
        SHEET_TRANSACTIONS,
        "Cumulative quantity becomes negative after a sell.",
    )


def _flag_transaction_price_mismatches(
    transactions: pd.DataFrame,
    prices: pd.DataFrame,
    messages: list[ValidationMessage],
) -> None:
    if transactions.empty or prices.empty:
        return
    price_history = {
        asset_id: group.sort_values("date").reset_index(drop=True)
        for asset_id, group in prices.groupby("asset_id")
    }
    cash_transactions = transactions[transactions["action"].isin(["Buy", "Sell"])].copy()
    for row in cash_transactions.itertuples():
        if pd.isna(row.date) or pd.isna(row.price_eur) or float(row.price_eur) <= 0:
            continue
        history = price_history.get(row.asset_id)
        if history is None or history.empty:
            continue
        prior = history[history["date"] <= pd.Timestamp(row.date)]
        if prior.empty:
            first_price_date = pd.Timestamp(history["date"].min()).date()
            _message(
                messages,
                "Warning",
                "Cross-sheet",
                f"Transaction row {int(row.source_row)} ({pd.Timestamp(row.date).date()}, {row.action}, '{row.product}') has no historical price on or before the transaction date. First available historical price for the matched asset is {first_price_date}; valuation before that date may be incomplete.",
                [int(row.source_row)],
            )
            continue
        reference_row = prior.iloc[-1]
        reference = float(reference_row["price"])
        reference_date = pd.Timestamp(reference_row["date"]).date()
        if reference <= 0:
            continue
        difference = abs(float(row.price_eur) - reference) / reference
        if difference > PRICE_MISMATCH_WARNING_THRESHOLD:
            _message(
                messages,
                "Warning",
                "Cross-sheet",
                f"Transaction row {int(row.source_row)} ({pd.Timestamp(row.date).date()}, {row.action}, '{row.product}') has transaction price {float(row.price_eur):.2f}, which differs by {_format_pct_delta(difference)} from the nearest prior historical price {reference:.2f} on {reference_date}. Threshold is {_format_pct_delta(PRICE_MISMATCH_WARNING_THRESHOLD)}. Check whether the transaction price or Product is swapped.",
                [int(row.source_row)],
            )


def _parse_prices(raw: pd.DataFrame, messages: list[ValidationMessage]) -> pd.DataFrame:
    sheet = SHEET_HISTORICAL_PRICES
    if raw.shape[0] < 2:
        _message(messages, "Error", sheet, "Historical Prices sheet must have row 1 group headers and row 2 block headers.")
        return _empty_prices()

    header_row = [_clean_text(v) for v in raw.iloc[1].tolist()]
    risk_free_start = _find_risk_free_start(raw)
    block_starts = [
        col
        for col in range(max(0, len(header_row) - len(PRICE_HEADERS) + 1))
        if header_row[col : col + len(PRICE_HEADERS)] == PRICE_HEADERS
        and not _column_is_in_risk_free_block(col, risk_free_start)
        and _canonical(raw.iat[0, col]) != _canonical(RISK_FREE_GROUP_HEADER)
    ]
    for col in block_starts:
        spacer_col = col + len(PRICE_HEADERS)
        if spacer_col < len(header_row) and _clean_text(raw.iat[1, spacer_col]) and header_row[spacer_col : spacer_col + len(RISK_FREE_EXCEL_HEADERS)] != RISK_FREE_EXCEL_HEADERS:
            _message(messages, "Warning", sheet, f"Expected a blank spacer column after price block starting at {get_column_letter(col + 1)}.")

    if not block_starts:
        _message(messages, "Error", sheet, "No valid Product/ISIN/Date/Price price blocks were found.")
        return _empty_prices()

    rows: list[dict] = []
    for block_number, start_col in enumerate(block_starts, start=1):
        group_header = _clean_text(raw.iat[0, start_col]) if raw.shape[0] else ""
        block_product = group_header or _first_block_product(raw, start_col)
        if not group_header:
            _message(messages, "Info", sheet, f"Price block {block_number} has no row-1 product/group header.")
        parsed_block_rows: list[dict] = []
        block_isins: list[str] = []
        block_products: list[str] = []
        block_rows: list[int] = []
        for row_idx in range(2, raw.shape[0]):
            product = _clean_text(raw.iat[row_idx, start_col]) if start_col < raw.shape[1] else ""
            isin = _normalize_isin(raw.iat[row_idx, start_col + 1]) if start_col + 1 < raw.shape[1] else ""
            date_raw = raw.iat[row_idx, start_col + 2] if start_col + 2 < raw.shape[1] else np.nan
            price_raw = raw.iat[row_idx, start_col + 3] if start_col + 3 < raw.shape[1] else np.nan
            if not product and not isin and pd.isna(date_raw) and pd.isna(price_raw):
                continue
            date = pd.to_datetime(date_raw, errors="coerce")
            price = _parse_number(price_raw)
            excel_row = row_idx + 1
            block_rows.append(excel_row)
            if isin:
                block_isins.append(isin)
            if product:
                block_products.append(product)
            if not product and not isin and not block_product:
                _message(messages, "Error", sheet, "Price rows need Product or ISIN.", [excel_row])
                continue
            if pd.isna(date):
                _message(messages, "Error", sheet, "Price dates must parse as dates.", [excel_row])
                continue
            if pd.isna(price):
                _message(messages, "Error", sheet, "Price rows need a numeric Price.", [excel_row])
                continue
            if float(price) <= 0:
                _message(messages, "Error", sheet, "Prices must be positive.", [excel_row])
                continue
            parsed_block_rows.append(
                {
                    "product": product,
                    "isin": isin,
                    "date": pd.Timestamp(date).normalize(),
                    "price": float(price),
                    "source_row": excel_row,
                    "block": block_number,
                }
            )
        if not parsed_block_rows:
            continue
        chosen_isin = _most_common_non_empty(block_isins)
        block_asset_id = chosen_isin or _asset_id_from_product(block_product)
        if not block_asset_id:
            block_asset_id = f"price_block_{block_number}"
            _message(messages, "Warning", sheet, f"Price block {block_number} has no usable ISIN or product name; using {block_asset_id} as its asset ID.")
        display_product = block_product or _first_non_empty([row["product"] for row in parsed_block_rows])
        distinct_isins = sorted(set(block_isins))
        if len(distinct_isins) > 1:
            _message(
                messages,
                "Warning",
                sheet,
                f"Historical Prices block {block_number} '{display_product or block_asset_id}' contains inconsistent ISIN values: {_format_values(distinct_isins)}. The block is kept as one asset_id '{block_asset_id}' using the most common non-empty ISIN '{chosen_isin or 'blank'}'; verify the ISIN column if the rows should not belong to the same asset.",
                block_rows,
            )
        product_names = sorted({_clean_text(product) for product in ([block_product] + block_products) if _clean_text(product)})
        if len(product_names) > 1 and chosen_isin:
            _message(
                messages,
                "Warning",
                sheet,
                f"Historical Prices block {block_number} uses ISIN {chosen_isin} with multiple product labels: {_format_values(product_names)}. ISIN matching keeps the rows together; verify the product labels for reporting clarity.",
                block_rows,
            )
        for row in parsed_block_rows:
            row["product"] = display_product or row["product"]
            row["isin"] = chosen_isin
            row["asset_id"] = block_asset_id
            rows.append(row)

    out = pd.DataFrame(rows, columns=_empty_prices().columns)
    if out.empty:
        _message(messages, "Error", sheet, "No usable historical price rows were found.")
        return out

    duplicate_mask = out.duplicated(subset=["asset_id", "date"], keep=False)
    _flag_rows(out, duplicate_mask, messages, "Warning", sheet, "Duplicate price rows for the same asset/date were found; the last row is used.")
    out = out.drop_duplicates(subset=["asset_id", "date"], keep="last")

    for asset_id, asset_prices in out.sort_values("date").groupby("asset_id"):
        gaps = asset_prices["date"].diff().dt.days.dropna()
        if not gaps.empty and gaps.max() > 14:
            _message(messages, "Info", sheet, f"{asset_id} has price-history gaps up to {int(gaps.max())} days.")

    return out.sort_values(["asset_id", "date"]).reset_index(drop=True)


def _parse_risk_free_rates(
    raw: pd.DataFrame, messages: list[ValidationMessage]
) -> pd.DataFrame:
    """Parse the optional government-bond yield block from Historical Prices."""
    sheet = SHEET_HISTORICAL_PRICES
    if raw.shape[0] < 2:
        _message(messages, "Warning", sheet, "No risk-free-rate block found. Risk-adjusted metrics use 0%.")
        return _empty_risk_free_rates()

    headers = [_clean_text(v) for v in raw.iloc[1].tolist()]
    header_starts = [
        col
        for col in range(max(0, len(headers) - len(RISK_FREE_EXCEL_HEADERS) + 1))
        if headers[col : col + len(RISK_FREE_EXCEL_HEADERS)] == RISK_FREE_EXCEL_HEADERS
    ]
    start = _find_risk_free_start(raw)
    if start is None:
        _message(messages, "Warning", sheet, "No risk-free-rate block found. Risk-adjusted metrics use 0%.")
        return _empty_risk_free_rates()
    if headers[start : start + len(RISK_FREE_EXCEL_HEADERS)] != RISK_FREE_EXCEL_HEADERS:
        _message(messages, "Error", sheet, "Risk-free-rate block was found, but its headers must be Year, Country, 1Y-Yield, 3Y-Yield, 5Y-Yield, 10Y-Yield, 20Y-Yield, 30Y-Yield.")
        return _empty_risk_free_rates()

    group_header = _clean_text(raw.iat[0, start])
    if _canonical(group_header) != _canonical(RISK_FREE_GROUP_HEADER):
        _message(
            messages,
            "Info",
            sheet,
            "Risk-free yields were detected from their header sequence (the group header is optional).",
        )
    if len(header_starts) > 1:
        _message(messages, "Warning", sheet, "Multiple risk-free-rate blocks were found; only the first block is used.")

    rows: list[dict] = []
    yield_columns = RISK_FREE_COLUMNS[2:]
    for row_idx in range(2, raw.shape[0]):
        values = [raw.iat[row_idx, start + offset] if start + offset < raw.shape[1] else np.nan for offset in range(8)]
        if all(pd.isna(value) or _clean_text(value) == "" for value in values):
            continue
        excel_row = row_idx + 1
        year_value = pd.to_numeric(values[0], errors="coerce")
        country = _clean_text(values[1])
        if pd.isna(year_value) or int(year_value) != float(year_value):
            _message(messages, "Error", sheet, "Risk-free-rate Year must be an integer.", [excel_row])
            continue
        if not country:
            _message(messages, "Warning", sheet, "Risk-free-rate rows should include a Country.", [excel_row])

        row = {"year": int(year_value), "country": country, "source_row": excel_row}
        valid_yields = 0
        for value, column, label in zip(values[2:], yield_columns, RISK_FREE_EXCEL_HEADERS[2:]):
            parsed, interpreted = _parse_percent(value)
            if pd.notna(parsed):
                valid_yields += 1
            elif not (pd.isna(value) or _clean_text(value) == ""):
                _message(messages, "Error", sheet, f"Risk-free {label} must be numeric.", [excel_row])
            if interpreted:
                _message(messages, "Info", sheet, f"Interpreted {label} in row {excel_row} as a percentage.")
            row[column] = parsed
        if valid_yields == 0:
            _message(messages, "Warning", sheet, "Risk-free-rate rows need at least one yield.", [excel_row])
            continue
        rows.append(row)

    result = pd.DataFrame(rows)
    if result.empty:
        _message(messages, "Warning", sheet, "No usable risk-free-rate rows were found. Risk-adjusted metrics use 0%.")
        return _empty_risk_free_rates()
    duplicates = result.duplicated(subset=["year", "country"], keep=False)
    _flag_rows(result, duplicates, messages, "Warning", sheet, "Duplicate risk-free rate rows were found; the last row is used.")
    result = result.drop_duplicates(subset=["year", "country"], keep="last")
    _message(messages, "Info", sheet, "Risk-free block parsed successfully.")
    return result[RISK_FREE_COLUMNS].sort_values(["year", "country"]).reset_index(drop=True)


def _parse_daily_performance(raw: pd.DataFrame, messages: list[ValidationMessage]) -> pd.DataFrame:
    sheet = SHEET_DAILY_PERFORMANCE
    if raw.empty or raw.shape[1] < len(DAILY_PERFORMANCE_COLUMNS):
        _message(messages, "Warning", sheet, "Daily Performance sheet was found, but columns A:J could not be read for reconciliation.")
        return _empty_daily_performance_reference()

    rows: list[dict] = []
    for row_idx in range(raw.shape[0]):
        values = [raw.iat[row_idx, col] if col < raw.shape[1] else np.nan for col in range(len(DAILY_PERFORMANCE_COLUMNS))]
        if all(pd.isna(value) or _clean_text(value) == "" for value in values):
            continue
        parsed_date = pd.to_datetime(values[0], errors="coerce")
        if pd.isna(parsed_date):
            continue
        row = {"date": pd.Timestamp(parsed_date).normalize(), "source_row": row_idx + 1}
        for value, column in zip(values[1:], DAILY_PERFORMANCE_COLUMNS[1:]):
            if column in {"hpr", "twr"}:
                parsed, _ = _parse_percent(value)
            else:
                parsed = _parse_number(value)
            row[column] = float(parsed) if pd.notna(parsed) else np.nan
        rows.append(row)

    result = pd.DataFrame(rows, columns=DAILY_PERFORMANCE_COLUMNS + ["source_row"])
    if result.empty:
        _message(messages, "Warning", sheet, "Daily Performance sheet was found, but no cached date rows were available for reconciliation.")
        return _empty_daily_performance_reference()

    latest = result.sort_values(["date", "source_row"]).tail(1).reset_index(drop=True)
    _message(messages, "Info", sheet, "Daily Performance reference row parsed for reconciliation.", latest["source_row"].astype(int).tolist())
    return latest[DAILY_PERFORMANCE_COLUMNS + ["source_row"]]


def _parse_composition(raw: pd.DataFrame, messages: list[ValidationMessage]) -> pd.DataFrame:
    sheet = SHEET_PORTFOLIO_COMPOSITION
    if raw.shape[0] < 2 or raw.shape[1] < 4:
        _message(messages, "Error", sheet, "Portfolio Composition sheet must contain row 1 title and row 2 dynamic headers.")
        return _empty_composition()

    title = _clean_text(raw.iat[0, 0])
    if title != SHEET_PORTFOLIO_COMPOSITION:
        _message(messages, "Warning", sheet, "Cell A1 should be 'Portfolio Composition'.")

    headers = [_clean_text(v) for v in raw.iloc[1].tolist()]
    if headers[0] != "Year":
        _message(messages, "Error", sheet, "Cell A2 must be 'Year'.")

    tolerance_candidates = [idx for idx, h in enumerate(headers) if h == COMPOSITION_TOLERANCE_HEADER]
    if not tolerance_candidates:
        _message(messages, "Error", sheet, "A final Weight Deviation Tolerance column is required.")
        return _empty_composition()
    tolerance_col = tolerance_candidates[-1]

    groups: list[tuple[int, int, int]] = []
    col = 1
    while col < tolerance_col:
        instrument_header = headers[col]
        isin_header = headers[col + 1] if col + 1 < tolerance_col else ""
        weight_header = headers[col + 2] if col + 2 < tolerance_col else ""
        group_rows = [2]
        if col + 2 >= tolerance_col:
            _message(messages, "Error", sheet, f"Detected instrument group starting at {get_column_letter(col + 1)} is incomplete; expected Instrument / ISIN / Target Weight in Portfolio.")
            break
        if not instrument_header.startswith("Instrument") and isin_header == "ISIN":
            _message(messages, "Error", sheet, f"Group near {get_column_letter(col + 1)} has ISIN but no Instrument column.", group_rows)
        if instrument_header.startswith("Instrument") and isin_header != "ISIN":
            _message(messages, "Error", sheet, f"Group near {get_column_letter(col + 1)} has Instrument but no ISIN column.", group_rows)
        if (instrument_header.startswith("Instrument") or isin_header == "ISIN") and weight_header != COMPOSITION_TARGET_HEADER:
            _message(messages, "Error", sheet, f"Group near {get_column_letter(col + 1)} has Instrument/ISIN but no Target Weight in Portfolio column.", group_rows)
        if (
            instrument_header.startswith("Instrument")
            and isin_header == "ISIN"
            and weight_header == COMPOSITION_TARGET_HEADER
        ):
            groups.append((col, col + 1, col + 2))
        else:
            _message(messages, "Warning", sheet, f"Unexpected composition headers near {get_column_letter(col + 1)}.")
        col += 3

    if not groups:
        _message(messages, "Error", sheet, "No Instrument / ISIN / Target Weight groups were detected.")
        return _empty_composition()

    rows: list[dict] = []
    for row_idx in range(2, raw.shape[0]):
        excel_row = row_idx + 1
        row_values = raw.iloc[row_idx].tolist()
        if all(pd.isna(v) or _clean_text(v) == "" for v in row_values):
            continue
        year_value = pd.to_numeric(raw.iat[row_idx, 0], errors="coerce")
        if pd.isna(year_value):
            _message(messages, "Error", sheet, "Year must be an integer.", [excel_row])
            continue
        year = int(year_value)
        tolerance, interpreted_tolerance = _parse_percent(raw.iat[row_idx, tolerance_col])
        if pd.isna(tolerance):
            tolerance = 0.0
        if interpreted_tolerance:
            _message(messages, "Info", sheet, f"Interpreted tolerance in row {excel_row} as a percentage.")

        year_weights: list[float] = []
        year_isins: list[str] = []
        year_products: list[str] = []
        for instrument_col, isin_col, weight_col in groups:
            product = _clean_text(raw.iat[row_idx, instrument_col]) if instrument_col < raw.shape[1] else ""
            isin = _normalize_isin(raw.iat[row_idx, isin_col]) if isin_col < raw.shape[1] else ""
            weight_raw = raw.iat[row_idx, weight_col] if weight_col < raw.shape[1] else np.nan
            weight, interpreted_weight = _parse_percent(weight_raw)
            if not product and not isin and pd.isna(weight):
                continue
            if pd.isna(weight):
                _message(messages, "Error", sheet, "Target weights must be numeric.", [excel_row])
                continue
            if not isin:
                _message(messages, "Warning", sheet, "ISIN is blank for a target allocation row; product-name fallback matching will be used for this target.", [excel_row])
            if not product and abs(float(weight)) > 1e-12:
                _message(messages, "Warning", sheet, "Product is blank for a nonzero target allocation.", [excel_row])
            if interpreted_weight:
                _message(messages, "Info", sheet, f"Interpreted target weight in row {excel_row} as a percentage.")
            year_weights.append(float(weight))
            if isin:
                year_isins.append(isin)
            if product:
                year_products.append(_canonical(product))
            rows.append(
                {
                    "year": year,
                    "product": product,
                    "isin": isin,
                    "asset_id": make_asset_id(product, isin),
                    "target_weight": float(weight),
                    "tolerance": float(tolerance),
                    "source_row": excel_row,
                    "target_column": get_column_letter(weight_col + 1),
                }
            )
        if year_weights and abs(sum(year_weights) - 1.0) > 0.005:
            _message(messages, "Warning", sheet, f"Target weights for {year} sum to {sum(year_weights):.2%}, not 100%.", [excel_row])
        duplicate_isins = sorted({isin for isin in year_isins if year_isins.count(isin) > 1})
        if duplicate_isins:
            _message(messages, "Warning", sheet, f"Same ISIN appears more than once in the {year} composition row: {_format_values(duplicate_isins)}.", [excel_row])
        duplicate_products = sorted({product for product in year_products if year_products.count(product) > 1})
        if duplicate_products:
            _message(messages, "Warning", sheet, f"Same product appears more than once in the {year} composition row: {_format_values(duplicate_products)}.", [excel_row])

    out = pd.DataFrame(rows, columns=_empty_composition().columns)
    if out.empty:
        _message(messages, "Warning", sheet, "Portfolio Composition contains no target allocation rows.")
    return out.sort_values(["year", "source_row", "target_column"]).reset_index(drop=True)


def _flag_rows(
    df: pd.DataFrame,
    mask: pd.Series,
    messages: list[ValidationMessage],
    severity: str,
    sheet: str,
    message: str,
) -> None:
    if mask.any():
        rows = df.loc[mask, "source_row"].dropna().astype(int).tolist() if "source_row" in df.columns else []
        _message(messages, severity, sheet, message, rows)


def _find_risk_free_start(raw: pd.DataFrame) -> int | None:
    if raw.shape[0] < 2:
        return None
    target = _canonical(RISK_FREE_GROUP_HEADER)
    for col, value in enumerate(raw.iloc[0].tolist()):
        header = _canonical(value)
        if header and target in header:
            return col
    headers = [_clean_text(value) for value in raw.iloc[1].tolist()]
    for col in range(max(0, len(headers) - len(RISK_FREE_EXCEL_HEADERS) + 1)):
        if headers[col : col + len(RISK_FREE_EXCEL_HEADERS)] == RISK_FREE_EXCEL_HEADERS:
            return col
    return None


def _column_is_in_risk_free_block(col: int, risk_free_start: int | None) -> bool:
    return risk_free_start is not None and risk_free_start <= col < risk_free_start + len(RISK_FREE_EXCEL_HEADERS)


def _first_block_product(raw: pd.DataFrame, start_col: int) -> str:
    for row_idx in range(2, raw.shape[0]):
        product = _clean_text(raw.iat[row_idx, start_col]) if start_col < raw.shape[1] else ""
        if product:
            return product
    return ""


def _non_empty_set(df: pd.DataFrame, column: str) -> set[str]:
    if df.empty or column not in df.columns:
        return set()
    return {value for value in df[column].map(_normalize_isin) if value}


def _cross_validate(
    transactions: pd.DataFrame,
    prices: pd.DataFrame,
    composition: pd.DataFrame,
    messages: list[ValidationMessage],
) -> None:
    if transactions.empty:
        _message(messages, "Error", SHEET_TRANSACTIONS, "No usable transactions were found.")
    if prices.empty:
        _message(messages, "Error", SHEET_HISTORICAL_PRICES, "No usable historical prices were found.")

    tx_assets = set(transactions["asset_id"].dropna()) if not transactions.empty else set()
    price_assets = set(prices["asset_id"].dropna()) if not prices.empty else set()
    composition_assets = set(composition["asset_id"].dropna()) if not composition.empty else set()
    tx_isins = _non_empty_set(transactions, "isin")
    price_isins = _non_empty_set(prices, "isin")
    composition_isins = _non_empty_set(composition, "isin")

    missing_prices = tx_assets - price_assets
    if missing_prices:
        for asset_id in sorted(missing_prices):
            if transactions.empty:
                continue
            group = transactions[transactions["asset_id"].eq(asset_id)]
            rows = group["source_row"].dropna().astype(int).tolist()
            products = _format_values(group["product"])
            isins = _format_values(group["isin"])
            _message(
                messages,
                "Warning",
                "Cross-sheet",
                f"Transactions for asset_id '{asset_id}' did not match any Historical Prices block. Product(s): {products}. ISIN(s): {isins}. The asset is kept in the normalized transactions, but position value cannot be calculated until matching historical prices are added or the transaction Product/ISIN is corrected.",
                rows,
            )
    price_without_tx = price_assets - tx_assets
    if price_without_tx:
        for asset_id in sorted(price_without_tx):
            group = prices[prices["asset_id"].eq(asset_id)]
            products = _format_values(group["product"])
            blocks = _format_values(group["block"])
            _message(
                messages,
                "Info",
                "Cross-sheet",
                f"Historical Prices asset_id '{asset_id}' has prices but no matched transactions. Product(s): {products}. Block(s): {blocks}. It will not contribute to portfolio value unless transactions are added or transaction Product/ISIN values are corrected.",
                group["source_row"].dropna().astype(int).tolist(),
            )

    if composition_isins:
        for isin in sorted(composition_isins - tx_isins):
            group = composition[composition["isin"].eq(isin)]
            _message(
                messages,
                "Warning",
                "Cross-sheet",
                f"Portfolio Composition ISIN {isin} does not appear in Transactions. Target product(s): {_format_values(group['product'])}. This target can affect allocation drift, but no holdings were found for it.",
                group["source_row"].dropna().astype(int).tolist(),
            )
        for isin in sorted(composition_isins - price_isins):
            group = composition[composition["isin"].eq(isin)]
            _message(
                messages,
                "Warning",
                "Cross-sheet",
                f"Portfolio Composition ISIN {isin} does not appear in Historical Prices. Target product(s): {_format_values(group['product'])}. Allocation can show the target, but market value cannot be priced from this ISIN.",
                group["source_row"].dropna().astype(int).tolist(),
            )
    for isin in sorted(tx_isins - composition_isins):
        group = transactions[transactions["isin"].eq(isin)]
        _message(
            messages,
            "Warning",
            "Cross-sheet",
            f"Transaction ISIN {isin} does not appear in Portfolio Composition. Product(s): {_format_values(group['product'])}. The asset has no target allocation and will use 0% target weight.",
            group["source_row"].dropna().astype(int).tolist(),
        )
    for isin in sorted(price_isins - composition_isins):
        group = prices[prices["isin"].eq(isin)]
        _message(
            messages,
            "Info",
            "Cross-sheet",
            f"Historical Prices ISIN {isin} does not appear in Portfolio Composition. Product(s): {_format_values(group['product'])}. This price series has no target allocation unless a matching composition row is added.",
            group["source_row"].dropna().astype(int).tolist(),
        )

    known_products = set()
    if not transactions.empty:
        known_products.update(transactions["product"].dropna().map(_clean_text))
    if not prices.empty:
        known_products.update(prices["product"].dropna().map(_clean_text))
    if not composition.empty:
        known_products.update(composition["product"].dropna().map(_clean_text))
    composition_products = set(composition["product"].dropna().map(_clean_text)) if not composition.empty else set()
    assigned_tx_assets: set[str] = set()
    if not transactions.empty:
        for asset_id, group in transactions.groupby("asset_id"):
            products = set(group["product"].dropna().map(_clean_text))
            if asset_id in composition_assets or products.intersection(composition_products):
                assigned_tx_assets.add(asset_id)

    missing_targets = tx_assets - assigned_tx_assets
    if missing_targets and composition.empty:
        _message(messages, "Warning", "Cross-sheet", "No target allocations are available for traded assets.")
    elif missing_targets:
        _message(messages, "Warning", "Cross-sheet", "Some traded assets may be outside target allocation: " + ", ".join(sorted(missing_targets)))

    if not composition.empty:
        unmatched = [p for p in sorted(composition["product"].dropna().unique()) if p not in known_products and p not in tx_assets and p not in price_assets]
        if unmatched:
            _message(messages, "Warning", "Cross-sheet", "Target allocation instruments not found in transactions/prices: " + ", ".join(unmatched))

    combined_names = pd.concat(
        [
            transactions[["isin", "product"]].assign(_sheet=SHEET_TRANSACTIONS) if not transactions.empty else pd.DataFrame(columns=["isin", "product", "_sheet"]),
            prices[["isin", "product"]].assign(_sheet=SHEET_HISTORICAL_PRICES) if not prices.empty else pd.DataFrame(columns=["isin", "product", "_sheet"]),
            composition[["isin", "product"]].assign(_sheet=SHEET_PORTFOLIO_COMPOSITION) if not composition.empty else pd.DataFrame(columns=["isin", "product", "_sheet"]),
        ],
        ignore_index=True,
    )
    combined_names = combined_names[(combined_names["isin"].astype(str).str.len() > 0) & (combined_names["product"].astype(str).str.len() > 0)]
    for isin, group in combined_names.groupby("isin"):
        products = sorted(set(group["product"].map(_clean_text)))
        if len(products) > 1:
            _message(messages, "Warning", "Cross-sheet", f"Product names differ for ISIN {isin}; using ISIN as the asset key. Product names found: {_format_values(products)}.")

    product_names = combined_names.copy()
    product_names["_product_key"] = product_names["product"].map(_canonical)
    product_names = product_names[product_names["_product_key"].astype(str).str.len() > 0]
    for product_key, group in product_names.groupby("_product_key"):
        isins = sorted({isin for isin in group["isin"].map(_normalize_isin) if isin})
        if len(isins) > 1:
            product = _first_non_empty(group["product"])
            _message(messages, "Warning", "Cross-sheet", f"Product '{product}' has inconsistent ISINs across sheets: {_format_values(isins)}.")

    if not transactions.empty and not prices.empty:
        first_tx = transactions["date"].min()
        latest_price = prices["date"].max()
        if pd.notna(first_tx) and pd.notna(latest_price) and latest_price < first_tx:
            _message(messages, "Error", "Cross-sheet", "Historical prices end before the first transaction date.")


def build_upload_template_bytes(include_examples: bool = False) -> bytes:
    wb = Workbook()
    ws_comp = wb.active
    ws_comp.title = SHEET_PORTFOLIO_COMPOSITION
    ws_prices = wb.create_sheet(SHEET_HISTORICAL_PRICES)
    ws_tx = wb.create_sheet(SHEET_TRANSACTIONS)

    _build_composition_sheet(ws_comp, include_examples)
    _build_prices_sheet(ws_prices, include_examples)
    _build_transactions_sheet(ws_tx, include_examples)

    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out.getvalue()


def _build_transactions_sheet(ws, include_examples: bool) -> None:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=10)
    ws.cell(1, 1, "All Transactions")
    for col, header in enumerate(TRANSACTION_EXCEL_HEADERS, start=1):
        ws.cell(2, col, header)
    ws.freeze_panes = "A3"
    ws.auto_filter.ref = "A2:J2"
    action_validation = DataValidation(type="list", formula1='"Buy,Sell,Transfer"', allow_blank=True)
    ws.add_data_validation(action_validation)
    action_validation.add("F3:F10000")

    if include_examples:
        sample_rows = [
            ["DEGIRO IRELAND", "iShares Core MSCI World UCITS (Acc)", "IE00B4L5Y983", pd.Timestamp("2019-03-01"), "EAM", "Buy", 42.0, 48.50, 2037.00, 0.0],
            ["DEGIRO IRELAND", "iShares Core MSCI EM IMI UCITS (Acc)", "IE00BKM4GZ66", pd.Timestamp("2019-03-08"), "EAM", "Buy", 25.0, 22.95, 573.75, 0.0],
            ["DKB", "iShares Core MSCI World Small Cap UCITS (Acc)", "IE00BF4RFH31", pd.Timestamp("2020-01-10"), "XETRA", "Buy", 140.0, 4.15, 581.00, 1.50],
        ]
        for row_num, values in enumerate(sample_rows, start=3):
            for col, value in enumerate(values, start=1):
                ws.cell(row_num, col, value)

    _style_sheet(ws, max_col=10, percent_cols=[], date_cols=[4], money_cols=[8, 9, 10])
    widths = [18, 42, 16, 13, 12, 12, 12, 14, 17, 12]
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws["A1"].comment = Comment("Only the All Transactions section is parsed. Cash-flow values should be entered as positive EUR amounts.", "Codex")


def _build_prices_sheet(ws, include_examples: bool) -> None:
    products = [
        ("iShares Core MSCI World UCITS (Acc)", "IE00B4L5Y983"),
        ("iShares Core MSCI EM IMI UCITS (Acc)", "IE00BKM4GZ66"),
        ("iShares Core MSCI World Small Cap UCITS (Acc)", "IE00BF4RFH31"),
    ]
    for block_idx, (product, isin) in enumerate(products):
        start = 1 + block_idx * 5
        ws.merge_cells(start_row=1, start_column=start, end_row=1, end_column=start + 3)
        ws.cell(1, start, product)
        for offset, header in enumerate(PRICE_HEADERS):
            ws.cell(2, start + offset, header)
        if include_examples:
            sample_prices = [
                (pd.Timestamp("2019-01-02"), [43.44, 21.92, 3.89][block_idx]),
                (pd.Timestamp("2019-03-01"), [48.50, 22.80, 4.02][block_idx]),
                (pd.Timestamp("2019-03-08"), [47.92, 22.95, 4.01][block_idx]),
                (pd.Timestamp("2020-01-10"), [58.20, 25.10, 4.15][block_idx]),
                (pd.Timestamp("2020-12-31"), [65.00, 28.50, 4.85][block_idx]),
            ]
            for row_num, (date, price) in enumerate(sample_prices, start=3):
                ws.cell(row_num, start, product)
                ws.cell(row_num, start + 1, isin)
                ws.cell(row_num, start + 2, date)
                ws.cell(row_num, start + 3, price)

    risk_free_start = 16
    ws.merge_cells(start_row=1, start_column=risk_free_start, end_row=1, end_column=risk_free_start + 7)
    ws.cell(1, risk_free_start, RISK_FREE_GROUP_HEADER)
    for offset, header in enumerate(RISK_FREE_EXCEL_HEADERS):
        ws.cell(2, risk_free_start + offset, header)
    if include_examples:
        risk_free_rows = [
            [2019, "Germany", -0.62, -0.60, -0.48, -0.19, 0.28, 0.37],
            [2020, "Germany", -0.73, -0.74, -0.72, -0.57, -0.18, -0.17],
            [2021, "Germany", -0.70, -0.62, -0.49, -0.18, 0.20, 0.34],
            [2022, "Germany", 2.83, 2.60, 2.30, 2.10, 2.18, 2.13],
            [2023, "Germany", 3.21, 2.57, 2.19, 2.02, 2.18, 2.10],
        ]
        for row_num, values in enumerate(risk_free_rows, start=3):
            for offset, value in enumerate(values):
                ws.cell(row_num, risk_free_start + offset, value / 100 if offset >= 2 else value)
    ws.freeze_panes = "A3"
    _style_sheet(
        ws,
        max_col=23,
        percent_cols=[18, 19, 20, 21, 22, 23],
        date_cols=[3, 8, 13],
        money_cols=[4, 9, 14],
    )
    for col in range(1, 16):
        ws.column_dimensions[get_column_letter(col)].width = 18 if col % 5 else 4
    ws.column_dimensions["P"].width = 10
    ws.column_dimensions["Q"].width = 16
    for col in range(18, 24):
        ws.column_dimensions[get_column_letter(col)].width = 13
    ws["A1"].comment = Comment("Add more assets by continuing the four-column Product/ISIN/Date/Price block plus one blank spacer column. The optional government-bond block supplies risk-free rates for risk-adjusted metrics.", "Codex")


def _build_composition_sheet(ws, include_examples: bool) -> None:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=11)
    ws.cell(1, 1, SHEET_PORTFOLIO_COMPOSITION)
    headers = [
        "Year",
        "Instrument",
        "ISIN",
        COMPOSITION_TARGET_HEADER,
        "Instrument 2",
        "ISIN",
        COMPOSITION_TARGET_HEADER,
        "Instrument 3",
        "ISIN",
        COMPOSITION_TARGET_HEADER,
        COMPOSITION_TOLERANCE_HEADER,
    ]
    for col, header in enumerate(headers, start=1):
        ws.cell(2, col, header)
    if include_examples:
        world = "iShares Core MSCI World UCITS (Acc)"
        world_isin = "IE00B4L5Y983"
        em = "iShares Core MSCI EM IMI UCITS (Acc)"
        em_isin = "IE00BKM4GZ66"
        small = "iShares Core MSCI World Small Cap UCITS (Acc)"
        small_isin = "IE00BF4RFH31"
        rows = [
            [2019, world, world_isin, 0.60, em, em_isin, 0.40, small, small_isin, 0.00, 0.05],
            [2020, world, world_isin, 0.60, em, em_isin, 0.40, small, small_isin, 0.00, 0.05],
            [2021, world, world_isin, 0.60, em, em_isin, 0.40, small, small_isin, 0.00, 0.05],
            [2022, world, world_isin, 0.60, em, em_isin, 0.40, small, small_isin, 0.00, 0.05],
            [2023, world, world_isin, 0.60, em, em_isin, 0.30, small, small_isin, 0.10, 0.05],
            [2024, world, world_isin, 0.60, em, em_isin, 0.30, small, small_isin, 0.10, 0.05],
            [2025, world, world_isin, 0.60, em, em_isin, 0.30, small, small_isin, 0.10, 0.05],
            [2026, world, world_isin, 0.60, em, em_isin, 0.30, small, small_isin, 0.10, 0.05],
        ]
        for row_num, values in enumerate(rows, start=3):
            for col, value in enumerate(values, start=1):
                ws.cell(row_num, col, value)
    ws.freeze_panes = "A3"
    _style_sheet(ws, max_col=11, percent_cols=[4, 7, 10, 11], date_cols=[], money_cols=[])
    widths = [10, 42, 16, 24, 42, 16, 24, 42, 16, 24, 26]
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws["A1"].comment = Comment("Add more Instrument / ISIN / Target Weight in Portfolio groups before the final tolerance column.", "Codex")


def _style_sheet(ws, max_col: int, percent_cols: list[int], date_cols: list[int], money_cols: list[int]) -> None:
    title_fill = PatternFill("solid", fgColor="0F172A")
    header_fill = PatternFill("solid", fgColor="DBEAFE")
    title_font = Font(color="FFFFFF", bold=True, size=13)
    header_font = Font(color="111827", bold=True)
    thin = Side(style="thin", color="CBD5E1")
    border = Border(bottom=thin)

    for col in range(1, max_col + 1):
        cell = ws.cell(1, col)
        cell.fill = title_fill
        cell.font = title_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        header = ws.cell(2, col)
        header.fill = header_fill
        header.font = header_font
        header.border = border
        header.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for col in percent_cols:
        for row in range(3, 500):
            ws.cell(row, col).number_format = "0.00%"
    for col in date_cols:
        for row in range(3, 500):
            ws.cell(row, col).number_format = "yyyy-mm-dd"
    for col in money_cols:
        for row in range(3, 500):
            ws.cell(row, col).number_format = '#,##0.00'
