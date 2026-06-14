"""RBWM Transparency Dashboard — uv run streamlit run dashboard.py"""

import pandas as pd
import plotly.express as px
import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="Where does RBWM spend your money?",
    page_icon="💷",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Data ──────────────────────────────────────────────────────────────────────

@st.cache_data
def load_data() -> pd.DataFrame:
    directorate_labels = {
        "Adults Social Care and Health": "Adult Social Care & Health",
        "Adult Social Care and Health":  "Adult Social Care & Health",
        "Adult Social Care":             "Adult Social Care & Health",
        "Children's Services":           "Children's Services",
        "Children's Directorate":        "Children's Services",
        "Place":                         "Place (roads, waste, housing, parks)",
        "Place Directorate":             "Place (roads, waste, housing, parks)",
        "Resources Directorate":         "Resources",
        "Governance, Law, Strategy and Public Health": "Governance & Law",
        "Governance, Law & Strategy Directorate":      "Governance & Law",
        "Contingency & Corporate":       "Corporate & Contingency",
        "Chief Executive":               "Corporate & Contingency",
        "Technical Accounting":          "Technical Accounting",
    }
    df = pd.read_parquet("data/processed/payments.parquet")
    df["payment_date"] = pd.to_datetime(df["payment_date"], errors="coerce")
    df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce")
    df["year_month"] = df["payment_date"].dt.to_period("M").astype(str)
    df["directorate"] = df["directorate"].replace(directorate_labels)
    return df


@st.cache_data
def load_flag(name: str) -> pd.DataFrame:
    p = Path(f"data/processed/flag_{name}.parquet")
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


@st.cache_data
def load_enriched() -> pd.DataFrame:
    p = Path("data/processed/companies_enriched.parquet")
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    df["incorporated"] = pd.to_datetime(df["incorporated"], errors="coerce")
    return df


df = load_data()
enriched = load_enriched()

TOTAL = df["net_amount"].sum()
DATE_FROM = df["payment_date"].min().strftime("%b %Y")
DATE_TO = df["payment_date"].max().strftime("%b %Y")

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("## Where does RBWM spend your money?")

st.markdown(
    f"Every month, Royal Borough of Windsor & Maidenhead publishes a list of every payment "
    f"it makes to external suppliers over £100. This dashboard pulls together all of those "
    f"records from **{DATE_FROM} to {DATE_TO}** — {len(df):,} payments totalling "
    f"**£{TOTAL / 1e6:.0f} million** — and makes them easy to explore. "
    f"Staff salaries and internal transfers are not included; these figures cover money "
    f"paid out to outside organisations."
)
st.caption(
    f"[Source: RBWM published supplier payments ↗](https://www.rbwm.gov.uk/council-and-democracy/budgets-and-spending) · "
    "Figures are net of VAT"
)

st.divider()

# ── Hero metrics ──────────────────────────────────────────────────────────────

weeks = (df["payment_date"].max() - df["payment_date"].min()).days / 7
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total paid to suppliers", f"£{TOTAL / 1e6:.0f}M")
c2.metric("Avg per week", f"£{TOTAL / weeks / 1e6:.1f}M")
c3.metric("Unique suppliers", f"{df['supplier'].nunique():,}")
c4.metric("Payment records", f"{len(df):,}")

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_overview, tab_suppliers, tab_trend, tab_search, tab_flags = st.tabs(
    ["Overview", "Suppliers", "Trend", "Search", "Red flags"]
)

# ─────────────────────────────────────────────────────────────────────────────
# OVERVIEW
# ─────────────────────────────────────────────────────────────────────────────
with tab_overview:
    st.markdown("### Where the money goes")
    st.markdown(
        "The council is divided into directorates — essentially departments. "
        "Each bar shows everything paid to outside suppliers within that department "
        f"over the full {DATE_FROM}–{DATE_TO} period. "
        "Adult social care and children's services dominate because councils are legally "
        "required to fund care for elderly people, disabled adults, and vulnerable children "
        "— they can't cut these services the way they can cut libraries or parks."
    )

    dir_spend = (
        df.groupby("directorate")["net_amount"]
        .sum()
        .reset_index()
        .sort_values("net_amount", ascending=True)
    )
    dir_spend["label"] = dir_spend["net_amount"].apply(lambda x: f"£{x / 1e6:.0f}M")

    fig = px.bar(
        dir_spend,
        x="net_amount",
        y="directorate",
        orientation="h",
        text="label",
        color_discrete_sequence=["#3B82F6"],
        labels={"net_amount": "", "directorate": ""},
    )
    fig.update_layout(
        margin=dict(l=0, r=90, t=10, b=0),
        height=380,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False, range=[0, dir_spend["net_amount"].max() * 1.25]),
        yaxis=dict(gridcolor="rgba(128,128,128,0.15)"),
    )
    fig.update_traces(
        textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>£%{x:,.0f}<extra></extra>",
    )
    st.plotly_chart(fig, use_container_width=True)

    social_care = df[
        df["directorate"].isin(["Adult Social Care & Health", "Children's Services"])
    ]["net_amount"].sum()
    optalis = df[df["supplier"].str.contains("Optalis", case=False, na=False)]["net_amount"].sum()
    afc = df[df["supplier"].str.contains("Achieving for Children", case=False, na=False)]["net_amount"].sum()

    st.info(
        f"**Social care accounts for {social_care / TOTAL * 100:.0f}% of all spending** "
        f"(£{social_care / 1e6:.0f}M). This is a legal duty — councils must fund care for "
        "elderly residents, disabled adults, and vulnerable children regardless of budget pressure."
    )

    st.warning(
        f"**More than £1 in every £3 goes to two companies most residents have never heard of.** "
        f"Optalis (£{optalis / 1e6:.0f}M) and Achieving for Children (£{afc / 1e6:.0f}M) "
        f"together account for **£{(optalis + afc) / 1e6:.0f}M — "
        f"{(optalis + afc) / TOTAL * 100:.0f}% of total spend**. "
        "Both are arm's-length companies the council itself created."
    )

# ─────────────────────────────────────────────────────────────────────────────
# SUPPLIERS
# ─────────────────────────────────────────────────────────────────────────────
with tab_suppliers:
    st.markdown("### Biggest suppliers")
    st.markdown(
        "These are the companies and organisations that received the most money from RBWM "
        f"over the full {DATE_FROM}–{DATE_TO} period. The top two — "
        "**Achieving for Children** and **Optalis** — are both companies the council itself "
        "set up to deliver social care services at arm's length. Most residents have never "
        "heard of either, yet together they account for more than a third of all supplier spending."
    )

    st.info(
        "**Note on two entries you may see:** "
        "The 'Department for Communities & Local Government' (ranked #3, £81M) is not a commercial supplier — "
        "these are statutory Business Rates Tariff payments that councils are legally required to remit to "
        "central government under the business rates retention scheme. "
        "Entries labelled 'REDACTED PERSONAL DATA' are grants and payments to individuals (e.g. foster carers) "
        "where personal details are withheld; they are excluded from this chart."
    )

    n = st.select_slider("Show top", options=[10, 20, 30, 50], value=20)

    top = (
        df[~df["supplier"].str.contains("REDACTED", case=False, na=False)]
        .groupby("supplier")["net_amount"]
        .sum()
        .reset_index()
        .sort_values("net_amount", ascending=False)
        .head(n)
    )
    top["label"] = top["net_amount"].apply(lambda x: f"£{x / 1e6:.1f}M")

    fig2 = px.bar(
        top.sort_values("net_amount"),
        x="net_amount",
        y="supplier",
        orientation="h",
        text="label",
        color_discrete_sequence=["#3B82F6"],
        labels={"net_amount": "", "supplier": ""},
    )
    fig2.update_layout(
        margin=dict(l=0, r=90, t=10, b=0),
        height=max(320, n * 22),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False, range=[0, top["net_amount"].max() * 1.25]),
        yaxis=dict(gridcolor="rgba(128,128,128,0.15)"),
    )
    fig2.update_traces(
        textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>£%{x:,.0f}<extra></extra>",
    )
    st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(
        top.drop(columns="label")
        .rename(columns={"supplier": "Supplier", "net_amount": "Total spend (£)"})
        .reset_index(drop=True)
        .style.format({"Total spend (£)": "£{:,.0f}"}),
        use_container_width=True,
        hide_index=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# TREND
# ─────────────────────────────────────────────────────────────────────────────
with tab_trend:
    st.markdown("### Spending over time")
    st.markdown(
        "Total payments to external suppliers by month. Spikes often reflect large quarterly "
        "or annual contract instalments rather than a sudden increase in activity. "
        "The overall upward trend may partly reflect rising social care demand and inflation in contract costs."
    )

    monthly = (
        df.groupby("year_month")["net_amount"]
        .sum()
        .reset_index()
        .sort_values("year_month")
    )

    fig3 = px.line(
        monthly,
        x="year_month",
        y="net_amount",
        markers=True,
        labels={"net_amount": "", "year_month": ""},
    )
    fig3.update_traces(
        line_color="#60A5FA",
        marker_color="#60A5FA",
        hovertemplate="<b>%{x}</b><br>£%{y:,.0f}<extra></extra>",
    )
    fig3.update_layout(
        margin=dict(l=0, r=0, t=10, b=0),
        height=350,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(tickprefix="£", gridcolor="rgba(128,128,128,0.15)", zeroline=False),
        xaxis=dict(showgrid=False),
    )
    st.plotly_chart(fig3, use_container_width=True)

    # Complete-year totals
    df_year = df.copy()
    df_year["year"] = df_year["payment_date"].dt.year
    by_year = (
        df_year[df_year["year"].between(2023, 2025)]
        .groupby("year")["net_amount"]
        .sum()
        .reset_index()
    )
    cols = st.columns(len(by_year))
    for col, (_, row) in zip(cols, by_year.iterrows()):
        year = int(row["year"])
        label = f"{year} (Apr–Dec only)" if year == 2023 else str(year)
        col.metric(label, f"£{row['net_amount'] / 1e6:.0f}M")

    st.caption("2023 data runs from April only (9 months). 2026 figures are partial (data through April 2026).")

# ─────────────────────────────────────────────────────────────────────────────
# SEARCH
# ─────────────────────────────────────────────────────────────────────────────
with tab_search:
    st.markdown("### Search all payments")
    st.markdown(
        f"Look up any supplier, service, or keyword across all {len(df):,} payment records. "
        "Try a company name, a type of service, or a place — results show every individual "
        "payment that matches, with the date, amount, and what it was for."
    )
    query = st.text_input(
        "", placeholder="Type a supplier name, service, or keyword…", label_visibility="collapsed"
    )

    if query:
        mask = (
            df["supplier"].str.contains(query, case=False, na=False)
            | df["purpose"].str.contains(query, case=False, na=False)
            | df["service"].str.contains(query, case=False, na=False)
        )
        results = df[mask].sort_values("net_amount", ascending=False)
        st.caption(
            f"{len(results):,} payments · total £{results['net_amount'].sum():,.0f}"
        )
        st.dataframe(
            results[["payment_date", "supplier", "net_amount", "directorate", "purpose"]]
            .rename(columns={
                "payment_date": "Date",
                "supplier": "Supplier",
                "net_amount": "Amount (£)",
                "directorate": "Directorate",
                "purpose": "Purpose",
            })
            .style.format({"Amount (£)": "£{:,.2f}"}),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption(f"Search {len(df):,} payment records from {DATE_FROM} onwards.")

# ─────────────────────────────────────────────────────────────────────────────
# RED FLAGS
# ─────────────────────────────────────────────────────────────────────────────
with tab_flags:
    st.markdown("### Anomalies worth scrutinising")
    st.markdown(
        "These patterns were detected automatically by analysing the payment data. "
        "They are not evidence of wrongdoing — there are often innocent explanations. "
        "But they are the kinds of questions a well-functioning audit committee should be "
        "able to answer, and that residents have every right to ask."
    )

    # Pre-invoice payments
    pre = df[df["invoice_date"] > df["payment_date"]].copy()
    pre["days_early"] = (pre["invoice_date"] - pre["payment_date"]).dt.days

    with st.expander(
        f"💸 Paid before the invoice arrived — {len(pre):,} payments, £{pre['net_amount'].sum() / 1e6:.1f}M",
        expanded=True,
    ):
        st.markdown(
            "The council paid before the invoice was formally issued. "
            "Some may be legitimate prepayments — but at £37M it warrants explanation."
        )
        if not pre.empty:
            st.dataframe(
                pre[["payment_date", "invoice_date", "days_early", "supplier", "net_amount", "directorate"]]
                .sort_values("days_early", ascending=False)
                .head(50)
                .rename(columns={
                    "payment_date": "Paid",
                    "invoice_date": "Invoice Date",
                    "days_early": "Days Early",
                    "supplier": "Supplier",
                    "net_amount": "Amount (£)",
                    "directorate": "Directorate",
                })
                .style.format({"Amount (£)": "£{:,.2f}"}),
                use_container_width=True,
                hide_index=True,
            )

    # Threshold clustering
    # £10,000 and £213,477 are defensible: £10k is the commonly cited minor procurement
    # threshold across UK councils; £213,477 is the statutory UK tender threshold for
    # sub-central authorities under the Procurement Act 2023 (in force Feb 2025).
    # RBWM's specific internal Contract Procedure Rules were not publicly accessible
    # at time of analysis — an FOI request would be needed to confirm their exact tiers.
    thresholds = [10_000, 213_477]
    ts_rows = [
        df[(df["net_amount"] >= t * 0.95) & (df["net_amount"] < t)].assign(threshold=t)
        for t in thresholds
    ]
    ts = pd.concat(ts_rows, ignore_index=True) if ts_rows else pd.DataFrame()

    with st.expander(f"⚠️ Payments just below key procurement thresholds — {len(ts):,} cases"):
        st.markdown(
            "Payments clustering just *below* significant procurement thresholds can sometimes "
            "indicate amounts being kept deliberately low to avoid additional scrutiny or process. "
            "The two thresholds used here are: **£10,000** (a commonly cited minor procurement "
            "threshold at UK councils) and **£213,477** (the statutory UK public tender threshold "
            "for councils under the Procurement Act 2023, above which contracts must be openly "
            "advertised). RBWM's own internal approval tiers are not publicly available online — "
            "their Contract Procedure Rules would need to be requested via FOI to confirm the "
            "exact levels."
        )
        if not ts.empty:
            st.dataframe(
                ts[["payment_date", "supplier", "net_amount", "threshold", "directorate"]]
                .sort_values("net_amount", ascending=False)
                .head(50)
                .rename(columns={
                    "payment_date": "Date",
                    "supplier": "Supplier",
                    "net_amount": "Amount (£)",
                    "threshold": "Threshold (£)",
                    "directorate": "Directorate",
                })
                .style.format({"Amount (£)": "£{:,.2f}", "Threshold (£)": "£{:,.0f}"}),
                use_container_width=True,
                hide_index=True,
            )

    # Dissolved companies
    dissolved = load_flag("dissolved_companies")
    if not dissolved.empty:
        verified = dissolved[
            dissolved.get("cessation_verified", pd.Series(False, index=dissolved.index)) == True
        ]
        with st.expander(f"🔴 Payments to dissolved companies — {len(verified)} confirmed"):
            st.markdown(
                "These suppliers received payments *after* their registered dissolution date on Companies House."
            )
            if not verified.empty:
                show_v = verified[["supplier", "ch_status", "date_of_cessation", "post_dissolution_spend"]].copy()
                show_v["date_of_cessation"] = pd.to_datetime(show_v["date_of_cessation"]).dt.strftime("%d/%m/%Y")
                st.dataframe(
                    show_v.rename(columns={
                        "supplier": "Supplier",
                        "ch_status": "Status",
                        "date_of_cessation": "Dissolved On",
                        "post_dissolution_spend": "Paid After (£)",
                    }).style.format({"Paid After (£)": "£{:,.0f}"}),
                    use_container_width=True,
                    hide_index=True,
                )
                st.caption(
                    "📋 We have submitted formal information requests to RBWM about "
                    "Vivid Resourcing Ltd and Barkland Tree Specialists and are awaiting their response."
                )

    # Director crossover
    crossover = load_flag("director_crossover")
    if not crossover.empty:
        with st.expander(f"🔗 Directors at multiple RBWM suppliers — {len(crossover)} directors"):
            st.markdown(
                "These individuals are registered directors at two or more companies that all receive "
                "RBWM payments. Not automatically suspicious — but worth knowing."
            )
            st.dataframe(
                crossover.rename(columns={
                    "director": "Director",
                    "supplier_count": "# Suppliers",
                    "suppliers": "Suppliers",
                    "combined_spend": "Combined Spend (£)",
                }).style.format({"Combined Spend (£)": "£{:,.0f}"}),
                use_container_width=True,
                hide_index=True,
            )

    # New companies
    new_co = load_flag("new_companies")
    if not new_co.empty:
        with st.expander(f"🆕 New companies receiving large contracts — {len(new_co)} found"):
            st.markdown(
                "These companies received more than £50,000 from RBWM within 2 years of being incorporated."
            )
            show = new_co[["supplier", "incorporated", "months_old_at_first_payment", "total_spend"]].copy()
            show["incorporated"] = pd.to_datetime(show["incorporated"], errors="coerce").dt.strftime("%d/%m/%Y")
            show["months_old_at_first_payment"] = show["months_old_at_first_payment"].apply(
                lambda x: f"{x:.0f} months" if pd.notna(x) and x >= 0 else "⚠️ Before incorporation"
            )
            st.dataframe(
                show.rename(columns={
                    "supplier": "Supplier",
                    "incorporated": "Incorporated",
                    "months_old_at_first_payment": "Age at first payment",
                    "total_spend": "Total Paid (£)",
                }).style.format({"Total Paid (£)": "£{:,.0f}"}),
                use_container_width=True,
                hide_index=True,
            )

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Built from RBWM published supplier payments · Not affiliated with RBWM · "
    "[Source data ↗](https://www.rbwm.gov.uk/council-and-democracy/budgets-and-spending)"
)
