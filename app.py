"""Read-only evaluator dashboard over the submitted CSV artifacts."""

from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"

REQUIRED_COLUMNS = {
    "overall.csv": {"tickets", "breaches", "breach_rate", "sla_credits_inr"},
    "weekly_summary.csv": {"week", "tickets", "breaches", "breach_rate", "credits_inr"},
    "weekly_agent_shift_breaches.csv": {
        "week", "agent_name", "shift", "ticket_count", "breach_count",
        "breach_rate", "sla_credits",
    },
    "overnight_summary.csv": {"overnight_created", "tickets", "breaches"},
    "ai_reason_sample_v2.csv": {"ticket_id", "ai_reason", "ai_confidence", "ai_evidence"},
    "ai_human_eval_30_v2.csv": {"ai_reason", "human_reason", "agreement", "review_notes"},
}


@st.cache_data
def load_artifacts(output_dir):
    """Load required final CSVs and fail with an actionable file/schema message."""
    artifacts = {}
    for filename, columns in REQUIRED_COLUMNS.items():
        path = Path(output_dir) / filename
        if not path.is_file():
            raise FileNotFoundError(f"Required dashboard file is missing: {path}")
        frame = pd.read_csv(path)
        missing = columns - set(frame.columns)
        if missing:
            raise ValueError(f"{filename} is missing columns: {', '.join(sorted(missing))}")
        artifacts[filename] = frame
    return artifacts


st.set_page_config(page_title="Vireo Audio — Support SLA Breach Monitor", layout="wide")
st.title("Vireo Audio — Support SLA Breach Monitor")
st.caption("Weekly first-response SLA analysis and AI-assisted breach-reason review")

try:
    data = load_artifacts(OUT)
except (OSError, ValueError, pd.errors.ParserError) as exc:
    st.error(f"Dashboard data could not be loaded: {exc}")
    st.stop()

overall = data["overall.csv"].iloc[0]
weekly = data["weekly_summary.csv"]
weekly_agent = data["weekly_agent_shift_breaches.csv"]
overnight = data["overnight_summary.csv"]
ai_sample = data["ai_reason_sample_v2.csv"]
ai_review = data["ai_human_eval_30_v2.csv"]

st.header("Executive KPIs")
kpis = st.columns(4)
kpis[0].metric("Unique tickets", f"{int(overall.tickets):,}")
kpis[1].metric("SLA breaches", f"{int(overall.breaches):,}")
kpis[2].metric("Breach rate", f"{overall.breach_rate:.2%}")
kpis[3].metric("Estimated SLA credits", f"₹{overall.sla_credits_inr:,.0f}")

st.header("Weekly trend and agent/shift report")
fcols = st.columns(3)
week_options = sorted(weekly_agent.week.dropna().unique())
shift_options = sorted(weekly_agent["shift"].dropna().unique())
agent_options = sorted(weekly_agent.agent_name.dropna().unique())
selected_weeks = fcols[0].multiselect("Week", week_options, default=week_options)
selected_shifts = fcols[1].multiselect("Shift", shift_options, default=shift_options)
selected_agents = fcols[2].multiselect("Agent", agent_options, default=agent_options)

filtered = weekly_agent.loc[
    weekly_agent.week.isin(selected_weeks)
    & weekly_agent["shift"].isin(selected_shifts)
    & weekly_agent.agent_name.isin(selected_agents)
].copy()

if not selected_weeks or not selected_shifts or not selected_agents:
    st.info("Select at least one value in each filter to view the report.")
    trend = pd.DataFrame(columns=["week", "tickets", "breaches", "breach_rate"])
elif len(selected_shifts) == len(shift_options) and len(selected_agents) == len(agent_options):
    trend = weekly.loc[weekly.week.isin(selected_weeks), [
        "week", "tickets", "breaches", "breach_rate"
    ]].copy()
elif filtered.empty:
    st.info("No report rows match these filters.")
    trend = pd.DataFrame(columns=["week", "tickets", "breaches", "breach_rate"])
else:
    trend = filtered.groupby("week", as_index=False).agg(
        tickets=("ticket_count", "sum"), breaches=("breach_count", "sum")
    )
    trend["breach_rate"] = trend.breaches / trend.tickets

chart_left, chart_right = st.columns(2)
with chart_left:
    st.subheader("Tickets and breaches by week")
    if not trend.empty:
        st.bar_chart(trend.set_index("week")[["tickets", "breaches"]])
with chart_right:
    st.subheader("Weekly breach rate")
    if not trend.empty:
        st.line_chart(trend.set_index("week")[["breach_rate"]])

st.subheader("Weekly agent/shift report")
report = filtered.rename(columns={
    "agent_name": "agent", "ticket_count": "tickets", "breach_count": "breaches",
    "sla_credits": "sla_credits_inr",
})[["week", "agent", "shift", "tickets", "breaches", "breach_rate", "sla_credits_inr"]]
st.dataframe(report.sort_values(["week", "agent", "shift"]), width="stretch", hide_index=True)
st.caption(
    "Agent-level metrics should be interpreted alongside ticket volume, roster assignment period, "
    "shift, and inherited overnight queue demand."
)

st.header("Overnight-created tickets")
night = overnight.loc[overnight.overnight_created.astype(str).str.lower().isin(["true", "1"])].iloc[0]
overnight_share = night.breaches / overall.breaches if overall.breaches else 0
ncols = st.columns(3)
ncols[0].metric("Overnight-created tickets", f"{int(night.tickets):,}")
ncols[1].metric("Overnight-created breaches", f"{int(night.breaches):,}")
ncols[2].metric("Share of all breaches", f"{overnight_share:.2%}")
st.info("66.84% of observed breaches were associated with tickets created overnight.")
st.caption(
    "Overnight-created tickets are strongly associated with breaches in this dataset; "
    "exact handoff timing is not directly observed."
)

st.header("AI-assisted breach reasons")
st.caption("AI-assisted qualitative classification — not used for SLA calculation.")
reason_counts = ai_sample.ai_reason.value_counts().rename_axis("reason").to_frame("tickets")
st.bar_chart(reason_counts)

if not ai_sample.empty:
    ticket_ids = ai_sample.ticket_id.astype(str).tolist()
    chosen_id = st.selectbox("Sample ticket", ticket_ids)
    chosen = ai_sample.loc[ai_sample.ticket_id.astype(str).eq(chosen_id)].iloc[0]
    st.write(f"**AI reason:** {chosen.ai_reason}")
    st.write(f"**Confidence:** {float(chosen.ai_confidence):.2f}")
    st.write(f"**Evidence:** {chosen.ai_evidence}")

reviewed = ai_review.loc[
    ai_review.human_reason.notna() & ai_review.ai_reason.notna()
    & ai_review.human_reason.astype(str).str.strip().ne("")
]
same_count = int(reviewed.human_reason.astype(str).eq(reviewed.ai_reason.astype(str)).sum())
if len(reviewed) == 30 and same_count == 30 and ai_review.review_notes.astype(str).str.startswith("Assistant-reviewed:").all():
    st.info(
        "30/30 agreement with assistant-generated review labels; "
        "this is not an independent model-accuracy estimate."
    )
else:
    st.info(
        f"Stored review labels: {same_count}/{len(reviewed)} agree. "
        "This review is not an independent model-accuracy estimate."
    )
