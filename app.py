import streamlit as st
import pandas as pd
from data_loader import load_accounts
from scorer import score_accounts

# ── Page config & styles ──────────────────────────────────────────────────────
st.set_page_config(page_title="Account Intelligence", layout="wide")

st.markdown("""
<style>
div[data-testid="stHorizontalBlock"] div[data-testid="stVerticalBlockBorderWrapper"] {
    height: 100%;
}
[data-testid="stDataFrame"] [data-testid="glideDataEditor"] canvas {
    cursor: pointer;
}
</style>
""", unsafe_allow_html=True)


# ── Data ──────────────────────────────────────────────────────────────────────
@st.cache_data
def get_data() -> pd.DataFrame:
    return score_accounts(load_accounts())


def fmt_revenue(v: float) -> str:
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    return f"${v / 1_000:.0f}K"


# ── Sidebar ───────────────────────────────────────────────────────────────────
def render_sidebar(df: pd.DataFrame) -> tuple[list, list, str]:
    st.sidebar.title("Filters")

    all_segments = sorted(df["segment"].unique())
    selected_segments = st.sidebar.multiselect("Segment", all_segments, default=all_segments)

    all_regions = sorted(df["region"].unique())
    selected_regions = st.sidebar.multiselect("Region", all_regions, default=all_regions)

    st.sidebar.divider()

    sort_option = st.sidebar.selectbox(
        "Sort by",
        ["Attention Score", "Renewal Date", "Revenue", "Days Since Activity"],
    )

    return selected_segments or all_segments, selected_regions or all_regions, sort_option


# ── Filter & sort ─────────────────────────────────────────────────────────────
def apply_filters(df: pd.DataFrame, segments: list, regions: list, sort_option: str) -> pd.DataFrame:
    sort_map = {
        "Attention Score":     (["attention_score", "current_revenue"], [False, False]),
        "Renewal Date":        (["days_to_next_renewal"],               [True]),
        "Revenue":             (["current_revenue"],                    [False]),
        "Days Since Activity": (["days_since_last_sales_activity"],     [False]),
    }
    sort_cols, sort_asc = sort_map[sort_option]
    return (
        df[df["segment"].isin(segments) & df["region"].isin(regions)]
        .copy()
        .sort_values(sort_cols, ascending=sort_asc)
    )


# ── Account table ─────────────────────────────────────────────────────────────
def render_account_table(filtered: pd.DataFrame, total: int):
    st.title("Account Intelligence")
    st.caption(f"Showing {len(filtered):,} of {total:,} accounts — click any row to view details")

    table = pd.DataFrame({
        "Account":         filtered["account_name"].values,
        "Industry":        filtered["industry"].values,
        "Segment":         filtered["segment"].values,
        "Attention":       filtered["attention_score"].values,
        "Action":          filtered["primary_action"].values,
        "Days to Renewal": filtered["days_to_next_renewal"].astype(int).values,
        "Revenue ($)":     filtered["current_revenue"].values,
        "Last Activity":   filtered["days_since_last_sales_activity"].apply(lambda x: f"{x:.0f}d ago").values,
    })

    return st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Attention":       st.column_config.NumberColumn(format="%.1f"),
            "Days to Renewal": st.column_config.NumberColumn(),
            "Revenue ($)":     st.column_config.NumberColumn(format="%,.0f"),
        },
    )


# ── Account detail ────────────────────────────────────────────────────────────
def render_scores(account: pd.Series) -> None:
    col_arr, col_projected, col_attention, col_risk, col_opportunity = st.columns(5)

    col_arr.metric(
        "Current ARR",
        fmt_revenue(account["current_revenue"]),
        help="Annual recurring revenue as of today.",
    )

    uplift_delta = (
        f"+{(account['arr_uplift'] - 1):.0%}" if account["expansion_signal"]
        else (f"{(account['arr_uplift'] - 1):.0%}" if account["contraction_signal"] else "flat")
    )
    col_projected.metric(
        "Projected ARR",
        fmt_revenue(account["revenue_end_of_quarter"]),
        uplift_delta,
        delta_color="normal" if account["expansion_signal"] else ("inverse" if account["contraction_signal"] else "off"),
        help="End-of-quarter projected ARR. Green = expansion, red = contraction.",
    )

    col_attention.metric(
        "Attention Score",
        account["attention_score"],
        help="Composite priority score: 60% risk + 40% opportunity (0–100). Higher means the account needs attention sooner.",
    )
    risk_delta_color = "normal" if account["risk_label"] == "Healthy" else "inverse"
    col_risk.metric(
        "Risk Score",
        account["risk_score"],
        account["risk_label"],
        delta_color=risk_delta_color,
        help="0–100. Signals: renewal urgency (30%), sales inactivity (25%), support tickets (20%), low seat utilization (15%), ARR contraction (10%). At Risk ≥ 50 · Needs Check-in ≥ 30 · Healthy < 30.",
    )

    opportunity_delta_color = "off" if account["opportunity_label"] == "Stable" else "normal"
    col_opportunity.metric(
        "Opportunity Score",
        account["opportunity_score"],
        account["opportunity_label"],
        delta_color=opportunity_delta_color,
        help="0–100. Signals: AI adoption (35%), projected ARR growth (25%), seat saturation (25%), seat whitespace (15%). Expansion Ready ≥ 70 · Growth Signal ≥ 40 · Stable < 40.",
    )


def render_risk_signals(account: pd.Series) -> None:
    with st.container(border=True):
        st.markdown("**Risk Signals**")

        col_renewal, col_last_activity = st.columns(2)
        col_renewal.metric(
            "Renewal", f"{int(account['days_to_next_renewal'])}d",
            help="Days until the next renewal. Accounts renewing within 180 days contribute to the risk score.",
        )
        col_last_activity.metric(
            "Last Activity", f"{int(account['days_since_last_sales_activity'])}d ago",
            help="Days since the last recorded sales interaction. Longer gaps increase risk.",
        )

        col_tickets, col_utilization = st.columns(2)
        col_tickets.metric(
            "Open Tickets", int(account["nr_support_tickets"]),
            help="Number of open support tickets. Calibrated to the 99th percentile (~13 tickets).",
        )
        col_utilization.metric(
            "Utilization", f"{account['seat_utilization']:.0%}",
            f"{int(account['unused_seats'])} unused", delta_color="off",
            help="Active users ÷ licensed seats. Accounts below 50% utilization score higher risk — they're paying for capacity they don't use.",
        )


def render_opportunity_signals(account: pd.Series) -> None:
    with st.container(border=True):
        st.markdown("**Opportunity Signals**")

        col_ai, col_whitespace, col_saturation = st.columns(3)
        col_ai.metric(
            "AI Adoption", f"{account['ai_usage']:.0%}",
            help="Share of available AI features actively used. The strongest expansion signal (35% weight) — high adoption indicates value realization.",
        )
        col_whitespace.metric(
            "Seat Whitespace", f"{account['seat_penetration']:.0%}",
            help="Licensed seats ÷ total employees. Below 25%, most of the company isn't on the platform yet — this is the expansion whitespace. Contributes 15% to the opportunity score.",
        )
        col_saturation.metric(
            "Seat Saturation", f"{account['seat_utilization']:.0%}",
            f"{account['nr_active_users']}/{account['nr_licensed_seats']} seats", delta_color="off",
            help="Active users ÷ licensed seats. Above 75%, the account has nearly outgrown its current plan — a natural upsell trigger. Contributes 25% to the opportunity score.",
        )


def render_account_detail(account: pd.Series) -> None:
    st.divider()

    st.subheader(account["account_name"])
    st.caption(f"{account['industry']} · {account['segment']} · {account['region']}")

    render_scores(account)
    st.divider()

    col_risk_signals, col_opportunity_signals = st.columns(2)
    with col_risk_signals:
        render_risk_signals(account)
    with col_opportunity_signals:
        render_opportunity_signals(account)

    st.divider()

    st.markdown("**Last Call**")
    if account["has_transcript"]:
        days = int(account["days_since_last_sales_activity"])
        st.info(f"{account['call_transcript_summary']}\n\n*{days} days ago*")
    else:
        st.caption("No recent call on record.")

    st.divider()

    brief_key = f"brief_{account['account_id']}"
    if st.button("Generate Meeting Brief", type="primary", use_container_width=True):
        with st.spinner("Generating brief..."):
            st.session_state[brief_key] = "_LLM integration coming in Phase 2._"
    if st.session_state.get(brief_key):
        st.markdown(st.session_state[brief_key])


# ── Main ──────────────────────────────────────────────────────────────────────
df = get_data()

segments, regions, sort_option = render_sidebar(df)
filtered = apply_filters(df, segments, regions, sort_option)
event = render_account_table(filtered, total=len(df))

selected_rows = event.selection.rows
if selected_rows:
    render_account_detail(filtered.iloc[selected_rows[0]])
