#!/usr/bin/env python3
"""
CLI daily report.
Usage:
    python report.py                          # sync then print AI brief
    python report.py --no-sync               # skip sync
    python report.py --note "Felt tired"     # pass context to Claude
    python report.py --manual                # enter metrics by hand (no Oura sync)
    python report.py --goal performance      # override active goal
"""
from __future__ import annotations
import argparse
import sys
from datetime import date
from typing import Optional

from oura.ingest import sync
from oura.db import fetch_metrics, DEFAULT_USER
from goals.loader import get_active_profile, set_active_goal, load_profiles
from analysis.trends import (
    hrv_trend,
    rhr_alert,
    sleep_debt,
    training_recommendation,
    step_recommendation,
    weekly_summary,
)
from ai.brief import generate_brief

SEP = "─" * 52

SIGNAL_BADGE = {
    "PUSH":     "🟢 PUSH",
    "MODERATE": "🟡 MODERATE",
    "REST":     "🔴 REST",
}


def _ask(prompt: str, cast=float, default=None) -> Optional[float]:
    raw = input(prompt).strip()
    if not raw and default is not None:
        return default
    try:
        return cast(raw)
    except (ValueError, TypeError):
        return default


def build_manual_row() -> dict:
    """Prompt user to enter today's metrics from keyboard."""
    print("\n  MANUAL METRIC ENTRY — press Enter to leave blank")
    today_str = str(date.today())
    return {
        "date": today_str,
        "readiness_score":   _ask("  Readiness score (0-100): ", int),
        "sleep_score":       _ask("  Sleep score (0-100): ",     int),
        "hrv_balance":       _ask("  HRV balance: ",             float),
        "resting_heart_rate":_ask("  Resting heart rate (bpm): ",int),
        "total_sleep_hours": _ask("  Total sleep hours: ",       float),
        "sleep_efficiency":  _ask("  Sleep efficiency (%): ",    float),
        "activity_score":    _ask("  Activity score (0-100): ",  int),
        "steps":             _ask("  Steps: ",                   int),
        "calories_active":   _ask("  Active calories: ",         int),
    }


def print_report(
    goal_override: Optional[str] = None,
    user_id: str = DEFAULT_USER,
    note: Optional[str] = None,
    manual_row: Optional[dict] = None,
):
    if goal_override:
        all_profiles = load_profiles()
        if goal_override not in all_profiles:
            print(f"Unknown goal '{goal_override}'. Available: {list(all_profiles)}")
            sys.exit(1)
        goal_name = goal_override
        profile = all_profiles[goal_override]
    else:
        goal_name, profile = get_active_profile()

    if manual_row:
        rows = [manual_row]
        today = manual_row
    else:
        rows = fetch_metrics(days=60, user_id=user_id)
        if not rows:
            print("No data in database. Run without --no-sync to pull from Oura.")
            return
        today = rows[-1]

    trend = hrv_trend(rows, profile["hrv_trend_window_days"])
    rhr_up = rhr_alert(rows, profile["rhr_alert_increase"])
    debt = sleep_debt(rows, profile["sleep_target_hours"])
    rec = training_recommendation(today.get("readiness_score"), trend, debt, profile)
    step_rec = step_recommendation(today.get("readiness_score"), trend, debt, profile)
    summary = weekly_summary(rows, profile)

    print()
    print(f"  OURA DAILY REPORT — {today['date']}")
    print(f"  Goal: {profile.get('label', goal_name)}")
    print(SEP)

    # Metrics summary line
    r = today.get("readiness_score", "—")
    s = today.get("sleep_score", "—")
    hrv = today.get("hrv_balance", "—")
    rhr_val = today.get("resting_heart_rate", "—")
    rhr_flag = "  ⚠ elevated" if rhr_up else ""
    print(f"  Readiness {r}/100  ·  Sleep {s}/100  ·  HRV {hrv}  ·  RHR {rhr_val} bpm{rhr_flag}")
    print()

    # Claude AI brief
    print("  Generating AI brief…", end="", flush=True)
    try:
        brief = generate_brief(
            today=today,
            history=rows,
            profile=profile,
            goal_name=goal_name,
            rec=rec,
            note=note,
        )
        signal_badge = SIGNAL_BADGE.get(brief["signal"], brief["signal"])
        print(f"\r  {signal_badge}")
        print()
        # Word-wrap narrative at ~72 chars
        words = brief["narrative"].split()
        line, out_lines = "", []
        for w in words:
            if len(line) + len(w) + 1 > 72:
                out_lines.append(line)
                line = w
            else:
                line = (line + " " + w).lstrip()
        if line:
            out_lines.append(line)
        for l in out_lines:
            print(f"  {l}")
        print()
    except Exception as exc:
        print(f"\r  ⚠ AI brief unavailable: {exc}")
        print(f"  → {rec}")
        print()

    # Step target
    step_color = {"high": "🟢", "moderate": "🟡", "low": "🔴"}.get(step_rec["level"], "⚪")
    print(f"  {step_color} {step_rec['feedback']}")
    print()

    # 7-day trend summary
    print("  7-DAY TREND")
    debt_str = f"{debt:+.1f}h vs {profile['sleep_target_hours']}h target"
    print(f"  HRV trend: {trend or '—'}  ·  Sleep avg: {summary['avg_sleep_hours']:.1f}h ({debt_str})" if summary['avg_sleep_hours'] else f"  Insufficient trend data.")
    print(f"  Avg readiness: {summary['avg_readiness']:.0f}/100" if summary['avg_readiness'] else "")
    print()
    print(SEP)
    print()


def main():
    parser = argparse.ArgumentParser(description="Oura daily report")
    parser.add_argument("--no-sync", action="store_true", help="Skip Oura API sync")
    parser.add_argument("--manual", action="store_true", help="Enter metrics manually")
    parser.add_argument("--note", metavar="TEXT", help="Daily context note passed to Claude")
    parser.add_argument("--goal", help="Override active goal for this run")
    parser.add_argument("--set-goal", help="Persist a new active goal and exit")
    parser.add_argument("--user", default=DEFAULT_USER, help="User ID")
    args = parser.parse_args()

    if args.set_goal:
        set_active_goal(args.set_goal)
        print(f"Active goal set to: {args.set_goal}")
        return

    manual_row = None
    if args.manual:
        manual_row = build_manual_row()
    elif not args.no_sync:
        print("Syncing from Oura API…")
        n = sync(days=60, user_id=args.user)
        print(f"Synced {n} days.\n")

    print_report(
        goal_override=args.goal,
        user_id=args.user,
        note=args.note,
        manual_row=manual_row,
    )


if __name__ == "__main__":
    main()
