import streamlit as st
import pandas as pd
from data_loader import load_accounts
from scorer import score_accounts

st.set_page_config(page_title="Account Intelligence", layout="wide")

st.markdown("""
<style>
div[data-testid="stHorizontalBlock"] div[data-testid="stVerticalBlockBorderWrapper"] {
    height: 100%;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
/* Hide the row selector checkbox column in st.dataframe */
[data-testid="stDataFrame"] [data-testid="glideDataEditor"] canvas {
    cursor: pointer;
}
div[class*="dvn-scroller"] > div:first-child > div:first-child {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)


@st.cache_data
def get_data() -> pd.DataFrame:
    return score_accounts(load_accounts())


def fmt_revenue(v: float) -> str:
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    return f"${v / 1_000:.0f}K"


df = get_data()

# ── Sidebar ──────────────────────────────────────────────────────────────────
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

# ── Filter & Sort ─────────────────────────────────────────────────────────────
active_segments = selected_segments or all_segments
active_regions = selected_regions or all_regions

filtered = df[
    df["segment"].isin(active_segments) & df["region"].isin(active_regions)
].copy()

sort_map = {
    "Attention Score":      (["attention_score", "current_revenue"], [False, False]),
    "Renewal Date":         (["days_to_next_renewal"],               [True]),
    "Revenue":              (["current_revenue"],                    [False]),
    "Days Since Activity":  (["days_since_last_sales_activity"],     [False]),
}
sort_cols, sort_asc = sort_map[sort_option]
filtered = filtered.sort_values(sort_cols, ascending=sort_asc)

# ── Account Table ─────────────────────────────────────────────────────────────
st.title("Account Intelligence")
st.caption(f"Showing {len(filtered):,} of {len(df):,} accounts — click any row to view details")

table = pd.DataFrame({
    "Account":         filtered["account_name"].values,
    "Industry":        filtered["industry"].values,
    "Segment":         filtered["segment"].values,
    "Attention":       filtered["attention_score"].values,
    "Risk":            filtered["risk_label"].values,
    "Opportunity":     filtered["opportunity_label"].values,
    "Days to Renewal": filtered["days_to_next_renewal"].astype(int).values,
    "Revenue":         filtered["current_revenue"].apply(fmt_revenue).values,
    "Last Activity":   filtered["days_since_last_sales_activity"].apply(lambda x: f"{x:.0f}d ago").values,
})

event = st.dataframe(
    table,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "Attention": st.column_config.NumberColumn(format="%.1f"),
        "Days to Renewal": st.column_config.NumberColumn(),
    },
)

# ── Account Detail ────────────────────────────────────────────────────────────
selected_rows = event.selection.rows
if not selected_rows:
    st.stop()

account = filtered.iloc[selected_rows[0]]
account_id = account["account_id"]

st.divider()

# ── Header ────────────────────────────────────────────────────────────────────
col_name, col_arr = st.columns([5, 1])
with col_name:
    st.subheader(account["account_name"])
    st.caption(f"{account['industry']} · {account['segment']} · {account['region']}")
with col_arr:
    st.metric("ARR", fmt_revenue(account["current_revenue"]))

# ── Scores ────────────────────────────────────────────────────────────────────
col_attention, col_risk, col_opportunity = st.columns(3)
col_attention.metric("Attention Score", account["attention_score"])
col_risk.metric("Risk Score", account["risk_score"], account["risk_label"], delta_color="off")
col_opportunity.metric("Opportunity Score", account["opportunity_score"], account["opportunity_label"], delta_color="off")

st.divider()

# ── Signals ───────────────────────────────────────────────────────────────────
st.markdown("""<style>
[data-testid="stHorizontalBlock"] [data-testid="stVerticalBlockBorderWrapper"] {
    height: 100%;
}
</style>""", unsafe_allow_html=True)

col_risk_signals, col_opportunity_signals = st.columns(2)

with col_risk_signals:
    with st.container(border=True):
        st.markdown("**Risk Signals**")
        col_renewal, col_last_activity = st.columns(2)
        col_renewal.metric("Renewal", f"{int(account['days_to_next_renewal'])}d")
        col_last_activity.metric("Last Activity", f"{int(account['days_since_last_sales_activity'])}d ago")
        col_tickets, col_utilization = st.columns(2)
        col_tickets.metric("Open Tickets", int(account["nr_support_tickets"]))
        col_utilization.metric("Utilization", f"{account['seat_utilization']:.0%}",
                               f"{int(account['unused_seats'])} unused", delta_color="off")

with col_opportunity_signals:
    with st.container(border=True):
        st.markdown("**Opportunity Signals**")
        col_ai, col_arr_projection = st.columns(2)
        col_ai.metric("AI Adoption", f"{account['ai_usage']:.0%}")
        uplift_delta = f"+{(account['arr_uplift'] - 1):.0%}" if account["expansion_signal"] \
            else (f"{(account['arr_uplift'] - 1):.0%}" if account["contraction_signal"] else "flat")
        col_arr_projection.metric("ARR Projection", fmt_revenue(account["revenue_end_of_quarter"]), uplift_delta,
                                  delta_color="normal" if account["expansion_signal"] else
                                  ("inverse" if account["contraction_signal"] else "off"))
        col_penetration, col_saturation = st.columns(2)
        col_penetration.metric("Penetration", f"{account['seat_penetration']:.0%}")
        col_saturation.metric("Saturation", f"{account['seat_utilization']:.0%}",
                              f"{account['nr_active_users']}/{account['nr_licensed_seats']} seats", delta_color="off")

st.divider()

# ── Last Call ─────────────────────────────────────────────────────────────────
st.markdown("**Last Call**")
if account["has_transcript"]:
    days = int(account["days_since_last_sales_activity"])
    st.info(f"{account['call_transcript_summary']}\n\n*{days} days ago*")
else:
    st.caption("No recent call on record.")

# ── Meeting Brief ─────────────────────────────────────────────────────────────
st.divider()
brief_key = f"brief_{account_id}"

if st.button("Generate Meeting Brief", type="primary", use_container_width=True):
    with st.spinner("Generating brief..."):
        st.session_state[brief_key] = "_LLM integration coming in Phase 2._"

if st.session_state.get(brief_key):
    st.markdown(st.session_state[brief_key])
