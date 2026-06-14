"""Flag suspicious patterns in RBWM payment data."""

from __future__ import annotations

import pandas as pd

# UK council procurement thresholds (approx) — payments clustering just below
# these are a classic sign of threshold splitting to avoid scrutiny
PROCUREMENT_THRESHOLDS = [500, 2_500, 10_000, 25_000, 50_000, 100_000, 200_000]
THRESHOLD_MARGIN = 0.05  # 5% below threshold counts as clustering


def supplier_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Total spend and payment count by supplier, descending."""
    return (
        df.groupby("supplier")
        .agg(
            total_spend=("net_amount", "sum"),
            payment_count=("net_amount", "count"),
            avg_payment=("net_amount", "mean"),
            directorates=("directorate", lambda x: ", ".join(sorted(x.dropna().unique()))),
            purposes=("purpose", lambda x: " | ".join(sorted(x.dropna().unique())[:3])),
        )
        .reset_index()
        .sort_values("total_spend", ascending=False)
    )


def flag_threshold_splitting(df: pd.DataFrame) -> pd.DataFrame:
    """
    Payments that land in the band [threshold * (1-margin), threshold).
    e.g. £9,500–£9,999 when the threshold is £10,000.
    """
    rows = []
    for threshold in PROCUREMENT_THRESHOLDS:
        low = threshold * (1 - THRESHOLD_MARGIN)
        mask = (df["net_amount"] >= low) & (df["net_amount"] < threshold)
        chunk = df[mask].copy()
        chunk["threshold_flagged"] = threshold
        chunk["pct_below_threshold"] = ((threshold - chunk["net_amount"]) / threshold * 100).round(2)
        rows.append(chunk)
    result = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return result.sort_values("net_amount", ascending=False)


def flag_duplicates(df: pd.DataFrame, window_days: int = 30) -> pd.DataFrame:
    """
    Same supplier + same net_amount paid more than once within window_days.
    """
    df = df.sort_values(["supplier", "net_amount", "payment_date"]).copy()
    df["payment_date"] = pd.to_datetime(df["payment_date"])

    flagged = []
    grouped = df.groupby(["supplier", "net_amount"])
    for (supplier, amount), group in grouped:
        if len(group) < 2:
            continue
        dates = group["payment_date"].sort_values().reset_index(drop=True)
        for i in range(1, len(dates)):
            if pd.isna(dates[i]) or pd.isna(dates[i - 1]):
                continue
            gap = (dates[i] - dates[i - 1]).days
            if gap <= window_days:
                flagged.append(group)
                break

    if not flagged:
        return pd.DataFrame()
    return (
        pd.concat(flagged, ignore_index=True)
        .sort_values(["supplier", "payment_date"])
    )


def flag_round_numbers(df: pd.DataFrame, min_amount: float = 5_000) -> pd.DataFrame:
    """Payments that are exact round thousands above min_amount."""
    mask = (
        (df["net_amount"] >= min_amount)
        & (df["net_amount"] % 1000 == 0)
    )
    return df[mask].sort_values("net_amount", ascending=False).copy()


def flag_stale_invoices(df: pd.DataFrame, days_threshold: int = 180) -> pd.DataFrame:
    """Invoices paid more than days_threshold days after invoice date."""
    gap = (df["payment_date"] - df["invoice_date"]).dt.days
    mask = gap > days_threshold
    result = df[mask].copy()
    result["days_to_pay"] = gap[mask]
    return result.sort_values("days_to_pay", ascending=False)


def flag_future_invoices(df: pd.DataFrame) -> pd.DataFrame:
    """Invoice date is after payment date — data error or fraud indicator."""
    mask = df["invoice_date"] > df["payment_date"]
    result = df[mask].copy()
    result["days_future"] = (df["invoice_date"] - df["payment_date"]).dt.days
    return result.sort_values("days_future", ascending=False)


def concentration_by_directorate(df: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """For each directorate, what % of spend goes to the top N suppliers?"""
    rows = []
    for directorate, group in df.groupby("directorate"):
        total = group["net_amount"].sum()
        top = group.groupby("supplier")["net_amount"].sum().nlargest(top_n)
        top_total = top.sum()
        rows.append({
            "directorate": directorate,
            "total_spend": total,
            "top_suppliers": ", ".join(top.index.tolist()),
            "top_supplier_spend": top_total,
            "concentration_pct": round(top_total / total * 100, 1) if total else 0,
        })
    return pd.DataFrame(rows).sort_values("concentration_pct", ascending=False)


def run_all_flags(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Run every flag check and return a dict of {flag_name: dataframe}."""
    return {
        "threshold_splitting": flag_threshold_splitting(df),
        "duplicate_payments": flag_duplicates(df),
        "round_numbers": flag_round_numbers(df),
        "stale_invoices": flag_stale_invoices(df),
        "future_invoices": flag_future_invoices(df),
    }
