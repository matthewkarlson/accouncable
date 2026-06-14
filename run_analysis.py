#!/usr/bin/env python3
"""Main entry point: download data, run flags, save report."""

from pathlib import Path

from src.accountable import collect, analyze, report

DATA_DIR = Path("data/raw")


def main():
    report.console.rule("[bold]RBWM Spending Analysis")

    # 1. Download / load data
    report.console.print("\n[bold cyan]1. Fetching data...[/bold cyan]")
    payments = collect.download_all(DATA_DIR)
    report.console.print(f"   Loaded {len(payments):,} payment records")

    # 2. Overview
    report.console.print("\n[bold cyan]2. Overview[/bold cyan]")
    report.print_summary(payments)

    # 3. Supplier summary
    report.console.print("\n[bold cyan]3. Top suppliers[/bold cyan]")
    summary = analyze.supplier_summary(payments)
    report.print_top_suppliers(summary, n=25)

    # 4. Concentration by directorate
    report.console.print("\n[bold cyan]4. Spend concentration by directorate[/bold cyan]")
    concentration = analyze.concentration_by_directorate(payments)
    report.console.print(concentration.to_string(index=False))

    # 5. Flags
    report.console.print("\n[bold cyan]5. Anomaly flags[/bold cyan]")
    flags = analyze.run_all_flags(payments)
    report.print_flags(flags)

    # Detail on threshold splitting (most interesting)
    ts = flags["threshold_splitting"]
    if not ts.empty:
        report.console.print("\n  [yellow]Threshold-splitting top hits:[/yellow]")
        cols = ["supplier", "net_amount", "threshold_flagged", "pct_below_threshold", "payment_date", "purpose"]
        report.console.print(ts[cols].head(20).to_string(index=False))

    # 6. Save Excel report
    report.console.print("\n[bold cyan]6. Saving report...[/bold cyan]")
    report.save_report(summary, flags, concentration)


if __name__ == "__main__":
    main()
