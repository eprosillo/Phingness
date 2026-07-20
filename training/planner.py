"""
AI training plan generator — calls Claude with race context + Oura data
to produce a week-by-week adaptive running plan.
"""
from __future__ import annotations
import json
from datetime import date, timedelta
from typing import Optional
import anthropic


def weeks_until(race_date_str: str) -> int:
    try:
        race_date = date.fromisoformat(race_date_str)
        return max(0, (race_date - date.today()).days // 7)
    except Exception:
        return 0


def generate_weekly_plan(
    race: dict,
    oura_rows: list[dict],
    workouts: list[dict],
    profile: dict,
    week_start: Optional[str] = None,
) -> dict:
    """Call Claude to generate a 7-day training plan.

    Returns a dict with keys:
        week_start (str)
        days (list of 7 dicts: {day, date, workout_type, description, distance_mi, effort})
        rationale (str)
    """
    if week_start is None:
        today = date.today()
        week_start = str(today - timedelta(days=today.weekday()))

    weeks_out = weeks_until(race["date"])
    recent_oura = oura_rows[-14:] if len(oura_rows) >= 14 else oura_rows
    recent_workouts = workouts[-14:] if len(workouts) >= 14 else workouts

    oura_lines = "\n".join(
        f"  {r['date']}: readiness={r.get('readiness_score','—')}, "
        f"HRV={r.get('hrv_balance','—')}, sleep={r.get('sleep_score','—')}/100"
        for r in recent_oura
    ) or "  No recent Oura data."

    workout_lines = "\n".join(
        f"  {w['date']}: {w['type']} {w.get('distance_mi','—')}mi "
        f"@ {w.get('pace_per_mile','—')}/mi, effort={w.get('effort','—')}/10"
        for w in recent_workouts
    ) or "  No recent workouts logged."

    prompt = f"""You are an elite running coach building a weekly training plan.

RACE: {race['name']}
Date: {race['date']} ({weeks_out} weeks away)
Distance: {race['distance_mi']} miles
Goal pace: {race.get('goal_pace') or 'as fast as possible'}
Notes: {race.get('notes') or 'none'}

ATHLETE OURA DATA (last 14 days):
{oura_lines}

RECENT WORKOUTS (last 14 days):
{workout_lines}

WEEK TO PLAN: Starting {week_start}

Generate a 7-day training plan for this week. Return ONLY valid JSON in this exact structure:
{{
  "week_start": "{week_start}",
  "rationale": "2-3 sentence explanation of this week's focus based on the athlete's data",
  "days": [
    {{
      "day": "Monday",
      "date": "YYYY-MM-DD",
      "workout_type": "easy run|tempo|intervals|long run|cross-train|rest|race",
      "description": "specific workout description",
      "distance_mi": 0.0,
      "effort": 5
    }}
  ]
}}

Rules:
- effort is 1-10 (1=very easy, 10=race effort)
- Adapt intensity to Oura readiness — if recent readiness is low, reduce hard sessions
- With {weeks_out} weeks to race, apply appropriate periodization
- For 2.5 mile race pace work: target workouts at goal pace or faster
- Include at least 1 rest or easy day per week
- distance_mi should be 0 for rest/cross-train days"""

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    plan = json.loads(text)
    return plan
