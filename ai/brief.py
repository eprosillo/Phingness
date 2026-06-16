"""
AI interpretation layer — calls Claude to generate a daily training brief.
"""
from __future__ import annotations
import os
from typing import Optional
import anthropic


def _signal_from_rec(rec: str) -> str:
    """Map rule-based recommendation string to PUSH / MODERATE / REST."""
    if rec == "Train hard":
        return "PUSH"
    if rec == "Rest / active recovery":
        return "REST"
    return "MODERATE"


def generate_brief(
    today: dict,
    history: list[dict],
    profile: dict,
    goal_name: str,
    rec: str,
    note: Optional[str] = None,
) -> dict:
    """Call Claude to generate a narrative brief for today's metrics.

    Returns dict with keys:
        narrative  — 3-4 sentence coaching text
        signal     — PUSH | MODERATE | REST
    """
    signal = _signal_from_rec(rec)
    goal_label = profile.get("label", goal_name)

    history_lines = []
    for row in (history[-7:] if len(history) >= 7 else history):
        history_lines.append(
            f"  {row.get('date','?')}: readiness={row.get('readiness_score','—')}, "
            f"sleep={row.get('sleep_score','—')}, "
            f"HRV={row.get('hrv_balance','—')}, "
            f"RHR={row.get('resting_heart_rate','—')} bpm, "
            f"steps={row.get('steps','—')}"
        )
    history_text = "\n".join(history_lines) or "  No history available."

    note_section = f"\nUser note for today: \"{note}\"" if note else ""

    priorities = ", ".join(p.replace("_", " ") for p in profile.get("priorities", []))

    prompt = f"""You are a concise personal health coach analyzing Oura Ring data.

Active Goal: {goal_label}
Goal priorities: {priorities}
Training signal determined by biometric thresholds: {signal}

Today ({today.get('date', 'today')}):
  Readiness: {today.get('readiness_score', '—')}/100
  Sleep score: {today.get('sleep_score', '—')}/100
  Total sleep: {today.get('total_sleep_hours', '—')}h
  HRV balance: {today.get('hrv_balance', '—')}
  Resting HR: {today.get('resting_heart_rate', '—')} bpm
  Activity score: {today.get('activity_score', '—')}/100
  Steps: {today.get('steps', '—')}{note_section}

7-day history:
{history_text}

Write exactly 3-4 sentences of coaching insight. Reference specific numbers. \
Connect today's metrics to the {goal_label} goal. End on the implication of the \
{signal} signal — what that means for today's effort level."""

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    narrative = response.content[0].text.strip()
    return {"narrative": narrative, "signal": signal}
