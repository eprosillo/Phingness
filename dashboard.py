"""
Streamlit dashboard.
Run: streamlit run dashboard.py
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from oura.db import fetch_all_metrics, init_db
from goals.loader import (
    load_profiles,
    get_active_goal_name,
    set_active_goal,
    get_active_profile,
)
from analysis.trends import (
    hrv_trend,
    rhr_alert,
    sleep_debt,
    training_recommendation,
    step_recommendation,
    weekly_summary,
)
from ai.brief import generate_brief

st.set_page_config(page_title="Oura Tracker", page_icon="💍", layout="wide")

# ── Sidebar ───────────────────────────────────────────────────────────────────
init_db()
profiles = load_profiles()
active_name = get_active_goal_name()

with st.sidebar:
    st.title("⚙️ Goal Profile")
    chosen = st.selectbox(
        "Active goal",
        options=list(profiles.keys()),
        index=list(profiles.keys()).index(active_name),
        format_func=lambda x: profiles[x]["label"],
    )
    if chosen != active_name:
        set_active_goal(chosen)
        st.rerun()

    goal_name, profile = get_active_profile()
    st.markdown("**Priorities**")
    for p in profile["priorities"]:
        st.markdown(f"- {p.replace('_', ' ').title()}")

    st.markdown("---")
    st.markdown("**Oura Sync**")
    if st.button("🔄 Sync from Oura", use_container_width=True):
        with st.spinner("Syncing…"):
            try:
                from oura.ingest import sync
                n = sync(days=60)
                st.success(f"Synced {n} days.")
                st.rerun()
            except Exception as e:
                st.error(f"Sync failed: {e}")

    st.markdown("---")
    st.markdown("**Daily Note**")
    daily_note = st.text_area(
        "Add context for Claude (optional)",
        placeholder="e.g. Felt tired, big workout yesterday…",
        height=100,
        label_visibility="collapsed",
    )

# ── Load data ─────────────────────────────────────────────────────────────────
rows = fetch_all_metrics()

if not rows:
    st.info("No data yet — click **🔄 Sync from Oura** in the sidebar to load your data.")
    st.stop()

df = pd.DataFrame(rows)
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date")

rows_all = rows
today = rows_all[-1]
trend = hrv_trend(rows_all, profile["hrv_trend_window_days"])
rhr_up = rhr_alert(rows_all, profile["rhr_alert_increase"])
debt = sleep_debt(rows_all, profile["sleep_target_hours"])
rec = training_recommendation(today.get("readiness_score"), trend, debt, profile)
step_rec = step_recommendation(today.get("readiness_score"), trend, debt, profile)
summary = weekly_summary(rows_all, profile)

# ── Header & metric cards ─────────────────────────────────────────────────────
st.title("💍 Oura Data & Goals Tracker")
st.caption(f"Goal: **{profile.get('label', goal_name)}** · {today['date']}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Readiness", f"{today.get('readiness_score', '—')}/100")
col2.metric("Sleep Score", f"{today.get('sleep_score', '—')}/100")
col3.metric(
    "Resting HR",
    f"{today.get('resting_heart_rate', '—')} bpm",
    delta="elevated" if rhr_up else None,
    delta_color="inverse",
)
col4.metric("HRV Trend", trend or "—")

# ── AI Brief card ─────────────────────────────────────────────────────────────
st.markdown("---")

SIGNAL_COLOR = {"PUSH": "#10b981", "MODERATE": "#f59e0b", "REST": "#ef4444"}
SIGNAL_EMOJI = {"PUSH": "🟢", "MODERATE": "🟡", "REST": "🔴"}

brief_state = st.session_state.get("brief")

brief_col, step_col = st.columns([3, 2])

with brief_col:
    if st.button("✨ Generate AI Brief", use_container_width=True):
        with st.spinner("Asking Claude…"):
            try:
                brief_state = generate_brief(
                    today=today,
                    history=rows_all,
                    profile=profile,
                    goal_name=goal_name,
                    rec=rec,
                    note=daily_note or None,
                )
                st.session_state["brief"] = brief_state
            except Exception as exc:
                st.error(f"Claude unavailable: {exc}")
                brief_state = None

    if brief_state:
        signal = brief_state["signal"]
        color = SIGNAL_COLOR.get(signal, "#888")
        emoji = SIGNAL_EMOJI.get(signal, "⚪")
        st.markdown(
            f"""
            <div style="background:#1e1e2e;border-radius:12px;padding:20px 24px;margin:8px 0">
                <div style="font-size:12px;color:#aaa;margin-bottom:6px;letter-spacing:.08em">TODAY'S TRAINING SIGNAL</div>
                <div style="font-size:24px;font-weight:700;color:{color};margin-bottom:10px">{emoji} {signal}</div>
                <div style="font-size:14px;color:#ccc;line-height:1.6">{brief_state['narrative']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        # Fallback rule-based card until AI brief is generated
        rec_color_map = {
            "Train hard": "🟢",
            "Moderate training": "🟡",
            "Rest / active recovery": "🔴",
        }
        rec_color = rec_color_map.get(rec, "⚪")
        st.markdown(
            f"""
            <div style="background:#1e1e2e;border-radius:12px;padding:20px 24px;margin:8px 0">
                <div style="font-size:12px;color:#aaa;margin-bottom:6px;letter-spacing:.08em">TODAY'S TRAINING (rule-based)</div>
                <div style="font-size:22px;font-weight:700;margin-bottom:8px">{rec_color} {rec}</div>
                <div style="font-size:13px;color:#888">Press "Generate AI Brief" for a personalized narrative from Claude.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

with step_col:
    step_color = {"high": "🟢", "moderate": "🟡", "low": "🔴"}.get(step_rec["level"], "⚪")
    today_steps = today.get("steps")
    step_progress = min(today_steps / step_rec["target"], 1.0) if today_steps else 0.0
    step_pct = int(step_progress * 100)
    step_actual_str = f"{today_steps:,}" if today_steps else "—"
    st.markdown(
        f"""
        <div style="background:#1e1e2e;border-radius:12px;padding:20px 24px;margin:8px 0">
            <div style="font-size:12px;color:#aaa;margin-bottom:6px;letter-spacing:.08em">STEP TARGET</div>
            <div style="font-size:24px;font-weight:700;margin-bottom:8px">{step_color} {step_rec['target']:,} steps</div>
            <div style="font-size:13px;color:#888">{step_actual_str} today · {step_pct}% of target</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.progress(step_progress)
    st.caption(step_rec["feedback"])

# ── Charts ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("📈 Trends (last 60 days)")

df60 = df.tail(60)

tab1, tab2, tab3 = st.tabs(["Scores", "Sleep", "Heart"])

with tab1:
    fig = go.Figure()
    for col, color, name in [
        ("readiness_score", "#7c3aed", "Readiness"),
        ("sleep_score", "#0ea5e9", "Sleep"),
        ("activity_score", "#10b981", "Activity"),
    ]:
        fig.add_trace(go.Scatter(
            x=df60["date"], y=df60[col], name=name,
            line=dict(color=color, width=2), connectgaps=True,
        ))
    fig.update_layout(yaxis=dict(range=[0, 100]), height=340, margin=dict(t=20))
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=df60["date"], y=df60["total_sleep_hours"],
        name="Total sleep (h)", marker_color="#0ea5e9",
    ), secondary_y=False)
    fig.add_hline(
        y=profile["sleep_target_hours"], line_dash="dash",
        line_color="#f59e0b",
        annotation_text=f"Target {profile['sleep_target_hours']}h",
    )
    fig.add_trace(go.Scatter(
        x=df60["date"], y=df60["sleep_efficiency"],
        name="Efficiency (%)", line=dict(color="#a78bfa", width=2), connectgaps=True,
    ), secondary_y=True)
    fig.update_yaxes(title_text="Hours", secondary_y=False)
    fig.update_yaxes(title_text="Efficiency %", secondary_y=True, range=[60, 100])
    fig.update_layout(height=340, margin=dict(t=20))
    st.plotly_chart(fig, use_container_width=True)

with tab3:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=df60["date"], y=df60["hrv_balance"], name="HRV Balance",
        line=dict(color="#7c3aed", width=2), connectgaps=True,
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=df60["date"], y=df60["resting_heart_rate"], name="Resting HR (bpm)",
        line=dict(color="#ef4444", width=2), connectgaps=True,
    ), secondary_y=True)
    fig.update_yaxes(title_text="HRV", secondary_y=False)
    fig.update_yaxes(title_text="RHR (bpm)", secondary_y=True)
    fig.update_layout(height=340, margin=dict(t=20))
    st.plotly_chart(fig, use_container_width=True)

# ── Weekly summary ────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("📋 Weekly Summary")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Avg Readiness", f"{summary['avg_readiness']:.0f}/100" if summary["avg_readiness"] else "—")
c2.metric("HRV Trend", summary["hrv_trend"] or "—")
c3.metric("Avg Sleep", f"{summary['avg_sleep_hours']:.1f}h" if summary["avg_sleep_hours"] else "—")
debt_val = summary["sleep_debt_hours"]
c4.metric(
    "Sleep vs Target",
    f"{debt_val:+.1f}h",
    delta_color="normal" if debt_val >= 0 else "inverse",
)
st.info(summary["narrative"])

# ── Raw data ──────────────────────────────────────────────────────────────────
with st.expander("Raw data"):
    st.dataframe(df.sort_values("date", ascending=False), use_container_width=True)
