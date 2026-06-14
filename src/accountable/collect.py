"""Download and cache RBWM supplier payment CSVs."""

from pathlib import Path

import pandas as pd
import requests

RBWM_URLS = [
    # FY 2023-24 (annual)
    "https://www.rbwm.gov.uk/sites/default/files/2024-06/finance_supplier_data_202304-2024303.csv",
    # FY 2024-25 (annual)
    "https://www.rbwm.gov.uk/sites/default/files/2025-07/finance_supplier_data_2024-04_2025-03.csv",
    # FY 2025-26 (monthly)
    "https://www.rbwm.gov.uk/sites/default/files/2025-06/finance_supplier_data_2025-04.csv",
    "https://www.rbwm.gov.uk/sites/default/files/2025-06/finance_supplier_data_2025-05.csv",
    "https://www.rbwm.gov.uk/sites/default/files/2025-07/finance_supplier_data_2025-06.csv",
    "https://www.rbwm.gov.uk/sites/default/files/2025-09/finance_supplier_data_2025-07.csv",
    "https://www.rbwm.gov.uk/sites/default/files/2025-11/finance_supplier_data_2025-08.csv",
    "https://www.rbwm.gov.uk/sites/default/files/2025-11/finance_supplier_data_2025-09.csv",
    "https://www.rbwm.gov.uk/sites/default/files/2025-11/finance_supplier_data_2025-10.csv",
    "https://www.rbwm.gov.uk/sites/default/files/2026-01/finance_supplier_data_2025-11.csv",
    "https://www.rbwm.gov.uk/sites/default/files/2026-01/finance_supplier_data_2025-12.csv",
    "https://www.rbwm.gov.uk/sites/default/files/2026-02/finance_supplier_data_2026-01.csv",
    "https://www.rbwm.gov.uk/sites/default/files/2026-04/finance_supplier_data_2026-02.csv",
    "https://www.rbwm.gov.uk/sites/default/files/2026-04/finance_supplier_data_2026-03.csv",
    "https://www.rbwm.gov.uk/sites/default/files/2026-05/finance_supplier_data_2026-04.csv",
]

# Standard format (most files)
COLUMN_MAP = {
    "Organisation Name": "org_name",
    "Organisation code": "org_code",
    "Effective Date": "effective_date",
    "Directorate": "directorate",
    "Service Category Label": "service_category_code",
    "Service": "service",
    "Supplier (Beneficiary name)": "supplier",
    "Local Supplier(beneficiary) internal reference ": "supplier_ref",
    "Local Supplier(beneficiary) internal reference": "supplier_ref",
    "Payment Date": "payment_date",
    "Transaction number": "transaction_number",
    "Net Amount": "net_amount",
    "Invoice Date": "invoice_date",
    "Irrecoverable VAT": "irrecoverable_vat",
    "Purpose of spend": "purpose",
    "Procurement Classification": "procurement_class",
    # Sep 2025 alternate column names
    "Directorate(T)": "directorate",
    "Sercop": "service_category_code",
    "Sercop(T)": "service",
    "Supplier": "supplier",
    "Purpose of spend(T)": "purpose",
    "Proclass": "procurement_class",
}

REQUIRED_COLS = {
    "org_name", "effective_date", "directorate", "service",
    "supplier", "payment_date", "net_amount",
}


def _detect_header_row(path: Path) -> int:
    """Return number of rows to skip before the real header row."""
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, encoding=enc) as f:
                for i, line in enumerate(f):
                    if "Organisation Name" in line:
                        return i
            break
        except UnicodeDecodeError:
            continue
    return 0


def _cache_path(url: str, cache_dir: Path) -> Path:
    return cache_dir / url.split("/")[-1]


def download_all(cache_dir: Path = Path("data/raw"), force: bool = False) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    frames = []

    for url in RBWM_URLS:
        path = _cache_path(url, cache_dir)
        if not path.exists() or force:
            print(f"  Downloading {url.split('/')[-1]} ...", end=" ", flush=True)
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            path.write_bytes(resp.content)
            print("done")
        else:
            print(f"  Cached: {path.name}")

        df = _parse_csv(path)
        frames.append(df)

    return _deduplicate(pd.concat(frames, ignore_index=True))


def _parse_csv(path: Path) -> pd.DataFrame:
    skip = _detect_header_row(path)
    df = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            df = pd.read_csv(path, encoding=enc, dtype=str, skiprows=skip)
            break
        except UnicodeDecodeError:
            continue
    if df is None:
        raise ValueError(f"Could not decode {path}")

    df = df.rename(columns=COLUMN_MAP)

    # Drop unnamed/empty columns that appear in some files
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    df = df.loc[:, df.columns != ""]

    # net_amount: strip commas/spaces and cast
    df["net_amount"] = (
        df["net_amount"].str.replace(",", "", regex=False).str.strip().astype(float)
    )

    for col in ("payment_date", "invoice_date", "effective_date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")

    df["source_file"] = path.name
    df["supplier"] = df["supplier"].str.strip()

    # Normalise rogue acute-accent character (´ U+00B4) used as apostrophe in some files
    for col in ("directorate", "service", "supplier", "purpose"):
        if col in df.columns:
            df[col] = df[col].str.replace("´", "'", regex=False)

    # Consolidate known supplier name variants
    SUPPLIER_ALIASES = {
        "Optalis (Main Contract Only)": "Optalis Ltd",
    }
    if "supplier" in df.columns:
        df["supplier"] = df["supplier"].replace(SUPPLIER_ALIASES)

    # Drop rows with no supplier or no amount (trailing blank rows)
    df = df.dropna(subset=["supplier", "net_amount"])
    df = df[df["supplier"].str.strip() != ""]

    return df


def _deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove duplicate transactions that appear across multiple source files.
    Annual files overlap with monthly files for some periods. We keep the first
    occurrence (annual files sort before monthly alphabetically, so annual wins).
    Rows with no transaction number are kept as-is.
    """
    df["transaction_number"] = df["transaction_number"].astype(str).str.strip()
    has_txn = df["transaction_number"] != "nan"
    dupes_before = has_txn.sum() - df[has_txn].drop_duplicates("transaction_number").shape[0]
    df = pd.concat([
        df[has_txn].sort_values("source_file").drop_duplicates("transaction_number", keep="first"),
        df[~has_txn],
    ], ignore_index=True)
    if dupes_before > 0:
        print(f"  Removed {dupes_before:,} duplicate transactions across source files")
    return df


def load_payments(cache_dir: Path = Path("data/raw")) -> pd.DataFrame:
    """Load all cached CSVs without re-downloading."""
    frames = []
    for url in RBWM_URLS:
        path = _cache_path(url, cache_dir)
        if path.exists():
            frames.append(_parse_csv(path))
    if not frames:
        raise FileNotFoundError("No cached data found. Run download_all() first.")
    return _deduplicate(pd.concat(frames, ignore_index=True))
