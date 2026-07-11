from __future__ import annotations

import math

import pandas as pd


def fmt_eur(value) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"EUR {float(value):,.2f}"


def fmt_pct(value) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.2%}"


def fmt_num(value) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    number = float(value)
    if math.isinf(number):
        return "n/a"
    return f"{number:,.2f}"


def ordered_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    selected = [col for col in columns if col in df.columns]
    extras = [col for col in df.columns if col not in selected]
    return df[selected + extras]

