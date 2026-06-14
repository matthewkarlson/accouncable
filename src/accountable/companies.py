"""
Companies House enrichment for RBWM suppliers.

Key design decisions:
- Strip "t/a <trading name>" before searching — the legal entity name is before "t/a"
- Fetch date_of_cessation so we can tell if payments preceded or followed dissolution
- Score match confidence: exact > prefix > fuzzy
- Fetch PSC data to detect council-controlled arm's-length bodies
"""

from __future__ import annotations

import json
import os
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

import requests

BASE_URL = "https://api.company-information.service.gov.uk"
CACHE_DIR = Path("data/companies_house")

SUSPICIOUS_STATUSES = {
    "dissolved",
    "liquidation",
    "receivership",
    "converted-closed",
    "insolvency-proceedings",
    "administration",
}

# PSC keywords that indicate a company is council/public-body controlled
COUNCIL_PSC_KEYWORDS = {
    "council", "borough", "district", "county", "authority",
    "government", "nhs", "trust", "foundation",
}


def _key() -> str:
    k = os.environ.get("COMPANIES_HOUSE_API_KEY", "")
    if not k:
        raise EnvironmentError("COMPANIES_HOUSE_API_KEY not set")
    return k


def _get(path: str, params: dict | None = None) -> dict:
    r = requests.get(f"{BASE_URL}{path}", params=params, auth=(_key(), ""), timeout=10)
    r.raise_for_status()
    return r.json()


# ── Name cleaning ─────────────────────────────────────────────────────────────

def _legal_name(supplier: str) -> str:
    """
    Extract the legal entity name, stripping trading-as suffixes.
    'Healthcare Homes (LSC) Ltd t/a Sandown Park' → 'Healthcare Homes (LSC) Ltd'
    'Serco Limited'                                → 'Serco Limited'
    """
    for marker in (" t/a ", " T/A ", " ta ", " trading as ", " Trading As "):
        if marker in supplier:
            supplier = supplier.split(marker)[0].strip()
            break
    return supplier


def _match_confidence(query: str, ch_title: str) -> str:
    """Rate how well our query matches the Companies House result title."""
    q = query.lower().strip()
    t = ch_title.lower().strip()
    if q == t:
        return "exact"
    if t.startswith(q) or q.startswith(t):
        return "prefix"
    ratio = SequenceMatcher(None, q, t).ratio()
    if ratio > 0.85:
        return "high"
    if ratio > 0.65:
        return "medium"
    return "low"


# ── Cache ─────────────────────────────────────────────────────────────────────

def _cache_path(supplier_name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in supplier_name)
    return CACHE_DIR / f"{safe[:80]}.json"


def _load_cache(supplier_name: str) -> dict | None:
    p = _cache_path(supplier_name)
    if p.exists():
        data = json.loads(p.read_text())
        # Invalidate old cache entries that are missing new fields
        if "date_of_cessation" not in data and data.get("ch_found"):
            return None
        return data
    return None


def _save_cache(supplier_name: str, data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(supplier_name).write_text(json.dumps(data, indent=2))


# ── Core lookup ───────────────────────────────────────────────────────────────

def lookup_supplier(name: str, delay: float = 0.3) -> dict:
    """
    Find the best Companies House match for a supplier name.
    Uses the legal entity name (strips t/a). Returns enriched dict. Caches.
    """
    cached = _load_cache(name)
    if cached is not None:
        return cached

    legal = _legal_name(name)

    try:
        results = _get("/search/companies", {"q": legal, "items_per_page": 5})
        items = results.get("items", [])

        if not items:
            data = {"supplier": name, "ch_found": False, "ch_status": "not_found",
                    "date_of_cessation": None, "match_confidence": "none"}
            _save_cache(name, data)
            return data

        best = items[0]
        confidence = _match_confidence(legal, best.get("title", ""))
        cn = best.get("company_number", "")

        profile = _get(f"/company/{cn}") if cn else {}
        officers_resp = _get(f"/company/{cn}/officers", {"items_per_page": 50}) if cn else {}
        psc_resp = _get(f"/company/{cn}/persons-with-significant-control", {"items_per_page": 25}) if cn else {}

        officers = officers_resp.get("items", [])
        pscs = psc_resp.get("items", [])

        active_directors = [
            o for o in officers
            if o.get("officer_role") in ("director", "secretary")
            and not o.get("resigned_on")
        ]

        # Is this company controlled by a council/public body?
        psc_names = [p.get("name", "").lower() for p in pscs]
        is_council_controlled = any(
            kw in psc_name
            for psc_name in psc_names
            for kw in COUNCIL_PSC_KEYWORDS
        )

        status = profile.get("company_status", best.get("company_status", "unknown"))
        sic_codes = profile.get("sic_codes", [])
        accounts = profile.get("accounts", {})
        accounts_overdue = accounts.get("overdue", False)

        data = {
            "supplier": name,
            "legal_name_searched": legal,
            "ch_found": True,
            "ch_name": best.get("title", ""),
            "company_number": cn,
            "match_confidence": confidence,
            "ch_status": status,
            "is_suspicious_status": status in SUSPICIOUS_STATUSES,
            "date_of_cessation": profile.get("date_of_cessation"),
            "incorporated": profile.get("date_of_creation", ""),
            "company_type": profile.get("type", ""),
            "registered_address": _fmt_address(profile.get("registered_office_address", {})),
            "sic_codes": sic_codes,
            "sic_description": ", ".join(sic_codes),
            "accounts_overdue": accounts_overdue,
            "is_council_controlled": is_council_controlled,
            "psc_names": [p.get("name", "") for p in pscs],
            "director_names": [o.get("name", "") for o in active_directors],
            "director_count": len(active_directors),
        }

    except Exception as e:
        data = {"supplier": name, "ch_found": False, "ch_status": f"error: {e}",
                "date_of_cessation": None, "match_confidence": "error"}

    _save_cache(name, data)
    time.sleep(delay)
    return data


def _fmt_address(addr: dict) -> str:
    parts = [
        addr.get("address_line_1", ""),
        addr.get("address_line_2", ""),
        addr.get("locality", ""),
        addr.get("postal_code", ""),
        addr.get("country", ""),
    ]
    return ", ".join(p for p in parts if p)


# ── Batch enrichment ──────────────────────────────────────────────────────────

def enrich_top_suppliers(
    payments_df,
    top_n: int = 200,
    delay: float = 0.3,
) -> "pd.DataFrame":
    import pandas as pd

    top_suppliers = (
        payments_df.groupby("supplier")["net_amount"]
        .sum()
        .nlargest(top_n)
        .index.tolist()
    )

    uncached = [s for s in top_suppliers if _load_cache(s) is None]
    print(f"  {len(top_suppliers)} suppliers · {len(uncached)} need API lookup")

    results = []
    for i, name in enumerate(top_suppliers):
        if i > 0 and i % 20 == 0:
            print(f"  ... {i}/{len(top_suppliers)}")
        results.append(lookup_supplier(name, delay=delay))

    return pd.DataFrame(results)


# ── Flag generation ───────────────────────────────────────────────────────────

def build_flags(enriched_df, payments_df) -> dict[str, "pd.DataFrame"]:
    import pandas as pd

    spend = (
        payments_df.groupby("supplier")
        .agg(total_spend=("net_amount", "sum"), payment_count=("net_amount", "count"))
        .reset_index()
    )
    df = enriched_df.merge(spend, on="supplier", how="left")

    # Only use high-confidence matches for flags (exact, prefix, high)
    confident = df[df["match_confidence"].isin(["exact", "prefix", "high"])]

    flags = {}

    # 1. Dissolved companies — with actual post-dissolution payments
    #    Join back to payments to find transactions AFTER date_of_cessation
    suspicious = confident[confident["is_suspicious_status"] & confident["ch_found"]].copy()
    suspicious["date_of_cessation"] = pd.to_datetime(
        suspicious["date_of_cessation"], errors="coerce"
    )

    post_dissolution_rows = []
    for _, row in suspicious.iterrows():
        cessation = row["date_of_cessation"]
        supplier_payments = payments_df[payments_df["supplier"] == row["supplier"]].copy()

        if pd.isna(cessation):
            # No cessation date from API — include all payments but mark as unverified
            total = supplier_payments["net_amount"].sum()
            post_dissolution_rows.append({
                **row.to_dict(),
                "post_dissolution_spend": None,
                "post_dissolution_payments": None,
                "last_payment_date": supplier_payments["payment_date"].max(),
                "cessation_verified": False,
            })
        else:
            after = supplier_payments[supplier_payments["payment_date"] > cessation]
            if len(after) > 0:
                post_dissolution_rows.append({
                    **row.to_dict(),
                    "post_dissolution_spend": after["net_amount"].sum(),
                    "post_dissolution_payments": len(after),
                    "last_payment_date": after["payment_date"].max(),
                    "cessation_verified": True,
                })
            # If zero payments after dissolution: company closed before payments ended — not a flag

    flags["dissolved_companies"] = (
        pd.DataFrame(post_dissolution_rows).sort_values(
            "post_dissolution_spend", ascending=False, na_position="last"
        )
        if post_dissolution_rows else pd.DataFrame()
    )

    # 2. New companies — only high-confidence matches, exclude council-controlled
    first_payments = payments_df.groupby("supplier")["payment_date"].min().reset_index()
    first_payments.columns = ["supplier", "first_payment_date"]
    df2 = confident.merge(first_payments, on="supplier", how="left")
    df2["incorporated"] = pd.to_datetime(df2["incorporated"], errors="coerce")
    df2["months_old_at_first_payment"] = (
        (df2["first_payment_date"] - df2["incorporated"]).dt.days / 30.44
    ).round(1)
    flags["new_companies"] = df2[
        df2["ch_found"]
        & ~df2.get("is_council_controlled", pd.Series(False, index=df2.index))
        & (df2["months_old_at_first_payment"] >= 0)   # exclude negative (bad name match)
        & (df2["months_old_at_first_payment"] < 24)
        & (df2["total_spend"] > 50_000)
    ].sort_values("months_old_at_first_payment")[
        ["supplier", "ch_name", "match_confidence", "incorporated",
         "months_old_at_first_payment", "total_spend", "ch_status"]
    ]

    # 3. Accounts overdue — exclude council-controlled entities
    flags["accounts_overdue"] = confident[
        confident["ch_found"]
        & confident["accounts_overdue"]
        & ~confident.get("is_council_controlled", pd.Series(False, index=confident.index))
    ].sort_values("total_spend", ascending=False)

    # 4. Director crossover — exclude council-controlled entities
    director_rows = []
    for _, row in confident[confident["ch_found"]].iterrows():
        if row.get("is_council_controlled"):
            continue
        names = row.get("director_names")
        if names is None:
            names = []
        elif not isinstance(names, list):
            names = list(names) if hasattr(names, "__iter__") else []
        for d in names:
            if d:
                director_rows.append({
                    "director": d,
                    "supplier": row["supplier"],
                    "total_spend": row.get("total_spend", 0),
                })

    if director_rows:
        dir_df = pd.DataFrame(director_rows)
        counts = dir_df.groupby("director")["supplier"].nunique()
        shared = counts[counts > 1].index
        crossover = dir_df[dir_df["director"].isin(shared)].copy()
        crossover_summary = (
            crossover.groupby("director")
            .agg(
                supplier_count=("supplier", "nunique"),
                suppliers=("supplier", lambda x: " | ".join(sorted(set(x)))),
                combined_spend=("total_spend", "sum"),
            )
            .reset_index()
            .sort_values("combined_spend", ascending=False)
        )
        flags["director_crossover"] = crossover_summary
    else:
        flags["director_crossover"] = pd.DataFrame()

    return flags
