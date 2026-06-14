"""Write analysis results to Excel with one sheet per flag."""

from __future__ import annotations
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()


def print_summary(df: pd.DataFrame) -> None:
    total_spend = df["net_amount"].sum()
    n_suppliers = df["supplier"].nunique()
    n_payments = len(df)
    date_range = f"{df['payment_date'].min().date()} → {df['payment_date'].max().date()}"

    table = Table(title="RBWM Payment Data — Overview", show_header=False)
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value", style="white")
    table.add_row("Total spend", f"£{total_spend:,.0f}")
    table.add_row("Payments", f"{n_payments:,}")
    table.add_row("Unique suppliers", f"{n_suppliers:,}")
    table.add_row("Date range", date_range)
    console.print(table)


def print_top_suppliers(summary: pd.DataFrame, n: int = 20) -> None:
    table = Table(title=f"Top {n} Suppliers by Total Spend")
    table.add_column("Supplier", style="white", max_width=45)
    table.add_column("Total Spend", style="green", justify="right")
    table.add_column("Payments", justify="right")
    table.add_column("Avg", style="yellow", justify="right")
    table.add_column("Directorate(s)", style="dim", max_width=35)

    for _, row in summary.head(n).iterrows():
        table.add_row(
            row["supplier"],
            f"£{row['total_spend']:,.0f}",
            str(int(row["payment_count"])),
            f"£{row['avg_payment']:,.0f}",
            row["directorates"],
        )
    console.print(table)


def print_flags(flags: dict[str, pd.DataFrame]) -> None:
    for name, flagged in flags.items():
        count = len(flagged)
        colour = "red" if count > 0 else "green"
        console.print(f"  [{colour}]{name}:[/{colour}] {count} rows flagged")


def save_report(
    summary: pd.DataFrame,
    flags: dict[str, pd.DataFrame],
    concentration: pd.DataFrame,
    output_path: Path = Path("reports/rbwm_analysis.xlsx"),
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Supplier Summary", index=False)
        concentration.to_excel(writer, sheet_name="Concentration", index=False)
        for name, flagged in flags.items():
            sheet = name[:31]  # Excel sheet name limit
            if not flagged.empty:
                flagged.to_excel(writer, sheet_name=sheet, index=False)
    console.print(f"\n[bold green]Report saved:[/bold green] {output_path}")
