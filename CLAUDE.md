# Accountable — RBWM Transparency Dashboard

## Project Goal

Build a public-facing transparency dashboard that makes Royal Borough of Windsor and Maidenhead (RBWM) council spending data easy for ordinary residents to explore and understand. The end goal is to share this with local Facebook groups and community forums to drive civic engagement and demonstrate the power of AI-assisted public scrutiny.

## Core Principles

- **Audience is non-technical residents**, not analysts. Language must be plain English. No jargon.
- **Clarity over cleverness.** Big numbers, clear charts, simple filters. People should understand the data in 30 seconds.
- **Transparency first.** Show what the council spends, who it pays, and what for — without editorialising. Let the data speak.
- **Flags are engagement hooks.** Surface anomalies (e.g. "payments made before invoices were issued") as accessible, shareable callouts — not dry audit findings.
- **Always cite the source.** Link back to RBWM's published data so users can verify everything themselves.

## Technical Stack

- **Python** with `uv` for all tooling
- **Streamlit** for the dashboard (simple, shareable URL, deployable to Streamlit Cloud for free)
- **Plotly** for interactive charts
- **Pandas** for data processing
- **Data storage:** processed Parquet files committed to the repo for fast dashboard load

## Data Source

Royal Borough of Windsor and Maidenhead supplier payment CSVs, published monthly at:
`https://www.rbwm.gov.uk/council-and-democracy/budgets-and-spending`

Currently covers **April 2023 → April 2026** (15 files, ~64k payment records, £779M total spend).

The scraper should auto-discover new files from the RBWM page rather than relying on hardcoded URLs, so it stays current as new monthly files are published.

## Dashboard Phases

### Phase 1 — Visibility (current focus)
- Hero stats: total spend, number of suppliers, date range
- Spending breakdown by Directorate (treemap / bar chart)
- Top suppliers table (searchable, sortable)
- Monthly spend trend (line chart)
- Spending by category/purpose

### Phase 2 — Scrutiny
- "Red flags" tab: anomalies surfaced by automated checks
  - Payments made before invoices were issued
  - Payments clustering just below procurement thresholds
  - Suppliers appearing under multiple name variants
  - Round-number large payments
- Companies House cross-reference for top suppliers (status, incorporation date)

### Phase 3 — Automation
- Monthly scrape of RBWM website to detect and ingest new CSV files
- Automated rebuild of Parquet data and dashboard refresh

## Development Notes

- Use `uv` for all package management, never bare `pip`
- Data lives in `data/raw/` (downloaded CSVs) and `data/processed/` (clean Parquet)
- Dashboard entry point: `dashboard.py` (run with `uv run streamlit run dashboard.py`)
- Analysis utilities: `src/accountable/`
