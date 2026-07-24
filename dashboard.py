"""
Streamlit dashboard.
Run: streamlit run dashboard.py
"""
import json
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, timedelta

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
from training.db import (
    init_training_db,
    get_races, upsert_race, delete_race,
    get_workouts, log_workout, delete_workout, update_workout,
    get_strava_workouts, get_setting, set_setting,
    get_training_plan, save_training_plan,
    get_race_results, log_race_result, delete_race_result,
)
from training.planner import generate_weekly_plan, weeks_until
from strava.auth import get_auth_url, exchange_code, get_valid_token
from strava.sync import fetch_and_sync

st.set_page_config(page_title="Phingness", page_icon="⚡", layout="wide")

st.markdown("""
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#1D4ED8">
    <link rel="apple-touch-icon" href="/static/icon.svg">
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
init_db()
init_training_db()
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
    st.markdown("**Strava**")

    # Handle OAuth callback code in URL params
    params = st.query_params
    if "code" in params and "strava_tokens" not in st.session_state and "strava_code_used" not in st.session_state:
        code = params["code"]
        st.session_state["strava_code_used"] = True
        st.query_params.clear()
        with st.spinner("Connecting Strava…"):
            try:
                tokens = exchange_code(code)
                st.session_state["strava_tokens"] = tokens
                st.rerun()
            except Exception as e:
                st.error(f"Strava auth failed: {e}")

    strava_tokens = st.session_state.get("strava_tokens")

    if strava_tokens:
        st.success("Strava connected")
        if st.button("🏃 Sync Strava Workouts", use_container_width=True):
            with st.spinner("Fetching activities…"):
                try:
                    access_token, new_tokens = get_valid_token(
                        strava_tokens["access_token"],
                        strava_tokens["expires_at"],
                        strava_tokens["refresh_token"],
                    )
                    if new_tokens:
                        st.session_state["strava_tokens"] = {**strava_tokens, **new_tokens}
                    n = fetch_and_sync(access_token, days=60)
                    st.success(f"Synced {n} new workouts from Strava!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Sync failed: {e}")
        if st.button("Disconnect Strava", use_container_width=True):
            del st.session_state["strava_tokens"]
            st.rerun()
    else:
        app_url = "https://eprosillo-phingness.streamlit.app"
        auth_url = get_auth_url(redirect_uri="https://eprosillo-phingness.streamlit.app")
        st.markdown(f'<a href="{auth_url}" target="_blank"><button style="width:100%;padding:8px;background:#fc4c02;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px">🔗 Connect Strava</button></a>', unsafe_allow_html=True)
        st.caption("Opens Strava in a new tab. After authorizing, copy the code from the URL and paste it below.")
        strava_code = st.text_input("Paste Strava code here", placeholder="code from URL after ?code=")
        if strava_code:
            with st.spinner("Connecting…"):
                try:
                    tokens = exchange_code(strava_code)
                    st.session_state["strava_tokens"] = tokens
                    st.rerun()
                except Exception as e:
                    st.error(f"Auth failed: {e}")

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
st.title("💪 Phingness")
st.caption(f"Goal: **{profile.get('label', goal_name)}** · {today['date']}")

main_tab, training_tab = st.tabs(["📊 Daily Overview", "🏃 Race Trainer"])

SIGNAL_COLOR = {"PUSH": "#10b981", "MODERATE": "#f59e0b", "REST": "#ef4444"}
SIGNAL_EMOJI = {"PUSH": "🟢", "MODERATE": "🟡", "REST": "🔴"}

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Daily Overview
# ══════════════════════════════════════════════════════════════════════════════
with main_tab:
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

    st.markdown("---")
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
            rec_color_map = {"Train hard": "🟢", "Moderate training": "🟡", "Rest / active recovery": "🔴"}
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

    st.markdown("---")
    st.subheader("📈 Trends (last 60 days)")
    df60 = df.tail(60)
    scores_tab, sleep_tab, heart_tab = st.tabs(["Scores", "Sleep", "Heart"])

    with scores_tab:
        fig = go.Figure()
        for col, color, name in [
            ("readiness_score", "#7c3aed", "Readiness"),
            ("sleep_score", "#0ea5e9", "Sleep"),
            ("activity_score", "#10b981", "Activity"),
        ]:
            fig.add_trace(go.Scatter(x=df60["date"], y=df60[col], name=name,
                line=dict(color=color, width=2), connectgaps=True))
        fig.update_layout(yaxis=dict(range=[0, 100]), height=340, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

    with sleep_tab:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=df60["date"], y=df60["total_sleep_hours"],
            name="Total sleep (h)", marker_color="#0ea5e9"), secondary_y=False)
        fig.add_hline(y=profile["sleep_target_hours"], line_dash="dash",
            line_color="#f59e0b", annotation_text=f"Target {profile['sleep_target_hours']}h")
        fig.add_trace(go.Scatter(x=df60["date"], y=df60["sleep_efficiency"],
            name="Efficiency (%)", line=dict(color="#a78bfa", width=2), connectgaps=True), secondary_y=True)
        fig.update_yaxes(title_text="Hours", secondary_y=False)
        fig.update_yaxes(title_text="Efficiency %", secondary_y=True, range=[60, 100])
        fig.update_layout(height=340, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

    with heart_tab:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=df60["date"], y=df60["hrv_balance"], name="HRV Balance",
            line=dict(color="#7c3aed", width=2), connectgaps=True), secondary_y=False)
        fig.add_trace(go.Scatter(x=df60["date"], y=df60["resting_heart_rate"], name="Resting HR (bpm)",
            line=dict(color="#ef4444", width=2), connectgaps=True), secondary_y=True)
        fig.update_yaxes(title_text="HRV", secondary_y=False)
        fig.update_yaxes(title_text="RHR (bpm)", secondary_y=True)
        fig.update_layout(height=340, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("📋 Weekly Summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avg Readiness", f"{summary['avg_readiness']:.0f}/100" if summary["avg_readiness"] else "—")
    c2.metric("HRV Trend", summary["hrv_trend"] or "—")
    c3.metric("Avg Sleep", f"{summary['avg_sleep_hours']:.1f}h" if summary["avg_sleep_hours"] else "—")
    debt_val = summary["sleep_debt_hours"]
    c4.metric("Sleep vs Target", f"{debt_val:+.1f}h",
        delta_color="normal" if debt_val >= 0 else "inverse")
    st.info(summary["narrative"])

    with st.expander("Raw data"):
        st.dataframe(df.sort_values("date", ascending=False), use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Race Trainer
# ══════════════════════════════════════════════════════════════════════════════
with training_tab:
    races = get_races()
    workouts = get_workouts(days=60)

    trainer_tab1, trainer_tab2, trainer_tab3, trainer_tab4 = st.tabs([
        "🗓 Weekly Plan", "📝 Log Workout", "🏆 Race Results", "⚙️ Manage Races"
    ])

    # ── Weekly Plan ────────────────────────────────────────────────────────────
    with trainer_tab1:
        if not races:
            st.info("No races set up yet. Go to **⚙️ Manage Races** to add your first race.")
        else:
            race_options = {r["name"]: r for r in races}
            selected_race_name = st.selectbox("Select race", list(race_options.keys()))
            selected_race = race_options[selected_race_name]
            weeks_out = weeks_until(selected_race["date"])

            rc1, rc2, rc3 = st.columns(3)
            rc1.metric("Race Date", selected_race["date"])
            rc2.metric("Distance", f"{selected_race['distance_mi']} mi")
            rc3.metric("Weeks Out", str(weeks_out) if weeks_out > 0 else "Race week!")

            today_d = date.today()
            week_start = str(today_d - timedelta(days=today_d.weekday()))

            existing_plan = get_training_plan(week_start)
            plan_data = None
            if existing_plan:
                try:
                    plan_data = json.loads(existing_plan["plan_json"])
                except Exception:
                    pass

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                generate_btn = st.button(
                    "✨ Generate This Week's Plan" if not plan_data else "🔄 Regenerate Plan",
                    use_container_width=True
                )
            with col_btn2:
                if plan_data and st.button("🗑 Clear Plan", use_container_width=True):
                    save_training_plan(week_start, json.dumps({}), selected_race["id"])
                    st.rerun()

            if generate_btn:
                with st.spinner("Building your training plan…"):
                    try:
                        plan_data = generate_weekly_plan(
                            race=selected_race,
                            oura_rows=rows_all,
                            workouts=workouts,
                            profile=profile,
                            week_start=week_start,
                        )
                        save_training_plan(week_start, json.dumps(plan_data), selected_race["id"])
                        st.success("Plan generated!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to generate plan: {e}")

            if plan_data and plan_data.get("days"):
                st.markdown(f"**Week of {week_start}**")
                if plan_data.get("rationale"):
                    st.info(plan_data["rationale"])

                effort_color = lambda e: (
                    "#10b981" if e <= 4 else "#f59e0b" if e <= 6 else "#ef4444"
                )

                # Build lookup: date -> logged workout
                logged_by_date = {w["date"]: w for w in workouts}
                # Build lookup: date -> strava activities (multiple per day possible)
                strava_by_date: dict[str, list[dict]] = {}
                for a in get_strava_workouts(days=60):
                    strava_by_date.setdefault(a["date"], []).append(a)

                WORKOUT_TYPES = ["easy run", "tempo", "intervals", "long run", "cross-train", "rest", "race"]

                for day in plan_data["days"]:
                    effort = day.get("effort", 5)
                    color = effort_color(effort)
                    dist = f"{day['distance_mi']} mi" if day.get("distance_mi") else ""
                    wtype = day.get("workout_type", "").replace("_", " ").title()
                    desc = day.get("description", "")
                    day_date = day.get("date", "")
                    logged = logged_by_date.get(day_date)

                    with st.container():
                        col_a, col_b = st.columns([5, 1])
                        with col_a:
                            done_badge = " ✅" if logged else ""
                            st.markdown(
                                f"**{day['day']}{done_badge}** &nbsp; "
                                f"<span style='color:#888;font-size:12px'>{day_date}</span> &nbsp; "
                                f"<span style='color:#aaa'>{wtype}</span>"
                                + (f" &nbsp; · &nbsp; <span style='color:#aaa'>{dist}</span>" if dist else ""),
                                unsafe_allow_html=True,
                            )
                        with col_b:
                            st.markdown(f"<div style='color:{color};font-weight:700;text-align:right'>Effort {effort}/10</div>", unsafe_allow_html=True)
                        st.caption(desc)

                        if logged:
                            lc1, lc2 = st.columns([6, 1])
                            with lc1:
                                ldist = f"{logged['distance_mi']} mi" if logged.get('distance_mi') else ""
                                lpace = f"@ {logged['pace_per_mile']}/mi" if logged.get('pace_per_mile') else ""
                                st.caption(f"Logged: {logged['type']} {ldist} {lpace} · effort {logged.get('effort','—')}/10")
                            with lc2:
                                if st.button("✏️", key=f"edit_logged_{day_date}", help="Edit logged workout"):
                                    st.session_state[f"edit_open_{day_date}"] = True

                        expander_label = "Edit actual workout" if logged else "Log actual workout"
                        if logged and not st.session_state.get(f"edit_open_{day_date}"):
                            pass
                        else:
                            with st.expander(expander_label, expanded=not logged):
                                entry_mode = st.radio(
                                    "Source",
                                    ["✏️ Manual", "🔗 Link from Strava"],
                                    horizontal=True,
                                    key=f"mode_{day_date}",
                                    label_visibility="collapsed",
                                )

                                if entry_mode == "🔗 Link from Strava":
                                    day_strava = strava_by_date.get(day_date, [])
                                    if not day_strava:
                                        st.info(f"No Strava activity found on {day_date}. Sync Strava or use manual entry.")
                                    else:
                                        def _act_label(a):
                                            d = f"{a['distance_mi']} mi" if a.get('distance_mi') else ""
                                            p = f"@ {a['pace_per_mile']}/mi" if a.get('pace_per_mile') else ""
                                            n = (a.get('notes') or '')[:40]
                                            return " ".join(x for x in [a['type'], d, p, n] if x)

                                        act_options = {_act_label(a): a for a in day_strava}
                                        sel_label = st.selectbox("Activity", list(act_options.keys()), key=f"strava_sel_{day_date}")
                                        sel_act = act_options[sel_label]

                                        with st.form(f"link_strava_{day_date}"):
                                            sc1, sc2 = st.columns(2)
                                            with sc1:
                                                s_type = st.selectbox("Type", WORKOUT_TYPES,
                                                    index=WORKOUT_TYPES.index(sel_act["type"]) if sel_act["type"] in WORKOUT_TYPES else 0,
                                                    key=f"s_type_{day_date}")
                                                s_dist = st.number_input("Distance (mi)", min_value=0.0, step=0.1, format="%.1f",
                                                    value=float(sel_act.get("distance_mi") or 0.0), key=f"s_dist_{day_date}")
                                            with sc2:
                                                s_dur = st.number_input("Duration (min)", min_value=0, step=1,
                                                    value=int(sel_act.get("duration_min") or 0), key=f"s_dur_{day_date}")
                                                s_pace = st.text_input("Pace/mi", value=sel_act.get("pace_per_mile") or "", key=f"s_pace_{day_date}")
                                                s_effort = st.slider("Effort (1-10)", 1, 10,
                                                    value=int(sel_act.get("effort") or 5), key=f"s_eff_{day_date}")
                                            s_notes = st.text_area("Notes", value=sel_act.get("notes") or "", key=f"s_notes_{day_date}")
                                            if st.form_submit_button("💾 Save", use_container_width=True):
                                                update_workout(sel_act["id"], s_type, s_dist or None, s_dur or None, s_pace or None, s_effort, s_notes or None)
                                                st.session_state.pop(f"edit_open_{day_date}", None)
                                                st.success("Saved!")
                                                st.rerun()

                                else:
                                    with st.form(f"manual_log_{day_date}"):
                                        mc1, mc2 = st.columns(2)
                                        planned_type = day.get("workout_type", "easy run")
                                        default_type = planned_type if planned_type in WORKOUT_TYPES else "easy run"
                                        with mc1:
                                            m_type = st.selectbox("Type", WORKOUT_TYPES,
                                                index=WORKOUT_TYPES.index(logged["type"] if logged and logged["type"] in WORKOUT_TYPES else default_type),
                                                key=f"m_type_{day_date}")
                                            m_dist = st.number_input("Distance (mi)", min_value=0.0, step=0.1, format="%.1f",
                                                value=float(logged["distance_mi"] if logged and logged.get("distance_mi") else day.get("distance_mi") or 0.0),
                                                key=f"m_dist_{day_date}")
                                        with mc2:
                                            m_dur = st.number_input("Duration (min)", min_value=0, step=1,
                                                value=int(logged["duration_min"] if logged and logged.get("duration_min") else 0),
                                                key=f"m_dur_{day_date}")
                                            m_pace = st.text_input("Pace/mi",
                                                value=logged.get("pace_per_mile", "") if logged else "",
                                                key=f"m_pace_{day_date}")
                                            m_effort = st.slider("Effort (1-10)", 1, 10,
                                                value=int(logged["effort"] if logged and logged.get("effort") else effort),
                                                key=f"m_eff_{day_date}")
                                        m_notes = st.text_area("Notes",
                                            value=logged.get("notes", "") if logged else "",
                                            placeholder="How did it feel?",
                                            key=f"m_notes_{day_date}")
                                        if st.form_submit_button("💾 Save", use_container_width=True):
                                            if logged:
                                                update_workout(logged["id"], m_type, m_dist or None, m_dur or None, m_pace or None, m_effort, m_notes or None)
                                            else:
                                                log_workout(day_date, m_type, m_dist or None, m_dur or None, m_pace or None, m_effort, m_notes or None)
                                            st.session_state.pop(f"edit_open_{day_date}", None)
                                            st.success("Saved!")
                                            st.rerun()

                        st.divider()

    # ── Log Workout ────────────────────────────────────────────────────────────
    with trainer_tab2:
        st.subheader("Log a Workout")

        log_mode = st.radio(
            "Entry mode",
            ["✏️ Manual entry", "🔗 Link from Strava"],
            horizontal=True,
            label_visibility="collapsed",
        )

        if log_mode == "🔗 Link from Strava":
            strava_activities = get_strava_workouts(days=60)
            if not strava_activities:
                st.info("No Strava workouts synced yet. Use the Strava sync in the sidebar to import your activities.")
            else:
                def _activity_label(a):
                    dist = f"{a['distance_mi']} mi" if a.get('distance_mi') else ""
                    pace = f"@ {a['pace_per_mile']}/mi" if a.get('pace_per_mile') else ""
                    note = (a.get('notes') or '')[:40]
                    parts = [p for p in [a['date'], "—", a['type'], dist, pace, f"({note})" if note else ""] if p]
                    return " ".join(parts)

                activity_labels = {_activity_label(a): a for a in strava_activities}
                selected_label = st.selectbox("Pick a Strava activity", list(activity_labels.keys()))
                selected_activity = activity_labels[selected_label]

                st.markdown("**Edit before saving** *(fields pre-filled from Strava)*")
                with st.form("link_strava_form"):
                    ls_col1, ls_col2 = st.columns(2)
                    with ls_col1:
                        ls_type = st.selectbox(
                            "Type",
                            ["easy run", "tempo", "intervals", "long run", "cross-train", "rest", "race"],
                            index=["easy run", "tempo", "intervals", "long run", "cross-train", "rest", "race"].index(
                                selected_activity["type"] if selected_activity["type"] in
                                ["easy run", "tempo", "intervals", "long run", "cross-train", "rest", "race"]
                                else "easy run"
                            ),
                        )
                        ls_distance = st.number_input(
                            "Distance (miles)",
                            min_value=0.0, step=0.1, format="%.1f",
                            value=float(selected_activity.get("distance_mi") or 0.0),
                        )
                    with ls_col2:
                        ls_duration = st.number_input(
                            "Duration (minutes)",
                            min_value=0, step=1,
                            value=int(selected_activity.get("duration_min") or 0),
                        )
                        ls_pace = st.text_input(
                            "Pace per mile",
                            value=selected_activity.get("pace_per_mile") or "",
                        )
                        ls_effort = st.slider(
                            "Effort (1-10)", 1, 10,
                            value=int(selected_activity.get("effort") or 5),
                        )
                    ls_notes = st.text_area("Notes", value=selected_activity.get("notes") or "")
                    ls_submitted = st.form_submit_button("💾 Save Linked Workout", use_container_width=True)
                    if ls_submitted:
                        update_workout(
                            workout_id=selected_activity["id"],
                            workout_type=ls_type,
                            distance_mi=ls_distance or None,
                            duration_min=ls_duration or None,
                            pace_per_mile=ls_pace or None,
                            effort=ls_effort,
                            notes=ls_notes or None,
                        )
                        st.success("Strava workout updated and saved!")
                        st.rerun()

        else:
            with st.form("log_workout_form"):
                lw_col1, lw_col2 = st.columns(2)
                with lw_col1:
                    lw_date = st.date_input("Date", value=date.today())
                    lw_type = st.selectbox("Type", ["easy run", "tempo", "intervals", "long run", "cross-train", "rest", "race"])
                    lw_distance = st.number_input("Distance (miles)", min_value=0.0, step=0.1, format="%.1f")
                with lw_col2:
                    lw_duration = st.number_input("Duration (minutes)", min_value=0, step=1)
                    lw_pace = st.text_input("Pace per mile (e.g. 8:30)")
                    lw_effort = st.slider("Effort (1-10)", 1, 10, 5)
                lw_notes = st.text_area("Notes", placeholder="How did it feel?")
                submitted = st.form_submit_button("💾 Save Workout", use_container_width=True)
                if submitted:
                    log_workout(
                        date=str(lw_date),
                        workout_type=lw_type,
                        distance_mi=lw_distance or None,
                        duration_min=lw_duration or None,
                        pace_per_mile=lw_pace or None,
                        effort=lw_effort,
                        notes=lw_notes or None,
                    )
                    st.success("Workout logged!")
                    st.rerun()

        if workouts:
            st.markdown("---")
            st.subheader("Recent Workouts")
            for w in reversed(workouts[-14:]):
                effort = w.get("effort", 5)
                c = "#10b981" if effort <= 4 else "#f59e0b" if effort <= 6 else "#ef4444"
                dist = f"{w['distance_mi']} mi" if w.get("distance_mi") else ""
                pace = f"@ {w['pace_per_mile']}/mi" if w.get("pace_per_mile") else ""
                st.markdown(
                    f"""
                    <div style="background:#1e1e2e;border-radius:10px;padding:12px 16px;margin:4px 0;border-left:3px solid {c}">
                        <b style="color:#fff">{w['date']}</b>
                        <span style="color:#aaa;margin-left:10px">{w['type']}</span>
                        <span style="color:#ccc;margin-left:10px">{dist} {pace}</span>
                        <span style="color:{c};float:right">effort {effort}/10</span>
                        {f'<div style="color:#888;font-size:12px;margin-top:4px">{w["notes"]}</div>' if w.get("notes") else ''}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(f"Delete", key=f"del_w_{w['id']}"):
                    delete_workout(w["id"])
                    st.rerun()

    # ── Race Results ───────────────────────────────────────────────────────────
    with trainer_tab3:
        st.subheader("Log a Race Result")
        with st.form("log_result_form"):
            rr_col1, rr_col2 = st.columns(2)
            with rr_col1:
                rr_name = st.text_input("Race name", placeholder="e.g. Zilker Relays 2025")
                rr_date = st.date_input("Race date", value=date.today())
                rr_dist = st.number_input("Distance (miles)", min_value=0.1, value=2.5, step=0.1, format="%.1f")
            with rr_col2:
                rr_time = st.text_input("Finish time (MM:SS or H:MM:SS)", placeholder="18:45")
                rr_pace = st.text_input("Pace per mile (optional)", placeholder="7:30")
                rr_place = st.text_input("Place / division (optional)", placeholder="3rd in age group")
            rr_notes = st.text_area("Notes", placeholder="Race conditions, how you felt…")
            rr_submitted = st.form_submit_button("🏆 Save Result", use_container_width=True)
            if rr_submitted and rr_name and rr_time:
                log_race_result(
                    race_name=rr_name,
                    date=str(rr_date),
                    distance_mi=rr_dist,
                    finish_time=rr_time,
                    pace_per_mile=rr_pace or None,
                    place=rr_place or None,
                    notes=rr_notes or None,
                )
                st.success("Result saved!")
                st.rerun()

        results = get_race_results()
        if results:
            st.markdown("---")
            st.subheader("Race History")
            for r in results:
                st.markdown(
                    f"""
                    <div style="background:#1e1e2e;border-radius:10px;padding:14px 18px;margin:6px 0;border-left:4px solid #7c3aed">
                        <b style="color:#fff;font-size:15px">{r['race_name']}</b>
                        <span style="color:#888;font-size:12px;margin-left:10px">{r['date']}</span>
                        <div style="margin-top:6px">
                            <span style="color:#10b981;font-size:18px;font-weight:700">{r['finish_time']}</span>
                            <span style="color:#aaa;margin-left:10px">{r['distance_mi']} mi</span>
                            {f'<span style="color:#aaa;margin-left:10px">· {r["pace_per_mile"]}/mi</span>' if r.get("pace_per_mile") else ''}
                            {f'<span style="color:#f59e0b;margin-left:10px">· {r["place"]}</span>' if r.get("place") else ''}
                        </div>
                        {f'<div style="color:#888;font-size:12px;margin-top:4px">{r["notes"]}</div>' if r.get("notes") else ''}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button("Delete", key=f"del_r_{r['id']}"):
                    delete_race_result(r["id"])
                    st.rerun()

    # ── Manage Races ───────────────────────────────────────────────────────────
    with trainer_tab4:
        st.subheader("Add a Race")
        with st.form("add_race_form"):
            ar_col1, ar_col2 = st.columns(2)
            with ar_col1:
                ar_name = st.text_input("Race name", value="Zilker Relays")
                ar_date = st.date_input("Race date", value=date(2025, 9, 1))
            with ar_col2:
                ar_dist = st.number_input("Your distance (miles)", min_value=0.1, value=2.5, step=0.1, format="%.1f")
                ar_pace = st.text_input("Goal pace per mile (optional)", placeholder="7:00")
            ar_notes = st.text_area("Notes", placeholder="Relay team, course info…")
            ar_submitted = st.form_submit_button("➕ Add Race", use_container_width=True)
            if ar_submitted and ar_name:
                upsert_race(
                    name=ar_name,
                    date=str(ar_date),
                    distance_mi=ar_dist,
                    goal_pace=ar_pace or None,
                    notes=ar_notes or None,
                )
                st.success(f"Race '{ar_name}' saved!")
                st.rerun()

        if races:
            st.markdown("---")
            st.subheader("Your Races")
            for r in races:
                weeks = weeks_until(r["date"])
                st.markdown(
                    f"""
                    <div style="background:#1e1e2e;border-radius:10px;padding:14px 18px;margin:6px 0">
                        <b style="color:#fff">{r['name']}</b>
                        <span style="color:#888;margin-left:10px">{r['date']}</span>
                        <span style="color:#7c3aed;margin-left:10px">{r['distance_mi']} mi</span>
                        <span style="color:#aaa;margin-left:10px">· {weeks} weeks out</span>
                        {f'<div style="color:#888;font-size:12px;margin-top:4px">Goal: {r["goal_pace"]}/mi</div>' if r.get("goal_pace") else ''}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button("Delete race", key=f"del_race_{r['id']}"):
                    delete_race(r["id"])
                    st.rerun()
