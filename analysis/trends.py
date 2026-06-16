"""
Rolling trend calculations — all inputs are lists of daily_metrics dicts
sorted oldest-first.
"""
from __future__ import annotations
from typing import Literal, Optional


def rolling_avg(values: list, window: int) -> Optional[float]:
    clean = [v for v in values[-window:] if v is not None]
    return sum(clean) / len(clean) if clean else None


def hrv_trend(
    rows: list, window: int
) -> Optional[Literal["improving", "stable", "declining"]]:
    vals = [r["hrv_balance"] for r in rows]
    if len(vals) < window * 2:
        return None
    recent = rolling_avg(vals, window)
    prior = rolling_avg(vals[:-window], window)
    if recent is None or prior is None:
        return None
    delta = recent - prior
    if delta > 1:
        return "improving"
    if delta < -1:
        return "declining"
    return "stable"


def rhr_alert(rows: list[dict], rhr_increase_threshold: int) -> bool:
    """Return True if today's RHR is >= threshold above 7-day rolling avg."""
    if not rows:
        return False
    today_rhr = rows[-1].get("resting_heart_rate")
    if today_rhr is None:
        return False
    avg = rolling_avg([r["resting_heart_rate"] for r in rows[:-1]], 7)
    if avg is None:
        return False
    return today_rhr >= avg + rhr_increase_threshold


def sleep_debt(rows: list[dict], target_hours: float, window: int = 7) -> float:
    """Negative means deficit; positive means surplus."""
    avg = rolling_avg([r["total_sleep_hours"] for r in rows], window)
    if avg is None:
        return 0.0
    return round(avg - target_hours, 2)


def training_recommendation(
    readiness: int | None,
    hrv: str | None,
    debt: float,
    profile: dict,
) -> str:
    if readiness is None:
        return "No readiness data — check Oura sync."

    high = profile["readiness_thresholds"]["high"]
    moderate = profile["readiness_thresholds"]["moderate"]
    significant_debt = debt < -0.5  # more than 30 min short on rolling avg

    # Downgrade conditions
    downgrade = hrv == "declining" or significant_debt

    if readiness >= high and not downgrade:
        return "Train hard"
    if readiness >= high and downgrade:
        return "Moderate training"
    if readiness >= moderate:
        return "Moderate training" if not downgrade else "Rest / active recovery"
    return "Rest / active recovery"


def step_recommendation(
    readiness: Optional[int],
    hrv: Optional[str],
    debt: float,
    profile: dict,
) -> dict:
    """Return target steps and feedback string for today."""
    targets = profile.get("step_targets", {"high": 8000, "moderate": 6000, "low": 4000})
    high = profile["readiness_thresholds"]["high"]
    moderate = profile["readiness_thresholds"]["moderate"]
    significant_debt = debt < -0.5
    downgrade = hrv == "declining" or significant_debt

    if readiness is None:
        level = "moderate"
    elif readiness >= high and not downgrade:
        level = "high"
    elif readiness >= moderate and not downgrade:
        level = "moderate"
    else:
        level = "low"

    target = targets[level]

    messages = {
        "high":     f"Aim for {target:,} steps — your body is ready to move.",
        "moderate": f"Target {target:,} steps — steady activity suits today's readiness.",
        "low":      f"Keep it to {target:,} steps — prioritise rest and light movement.",
    }

    return {"target": target, "level": level, "feedback": messages[level]}


def weekly_summary(rows: list[dict], profile: dict) -> dict:
    last7 = rows[-7:] if len(rows) >= 7 else rows
    avg_readiness = rolling_avg([r["readiness_score"] for r in last7], 7)
    avg_sleep = rolling_avg([r["total_sleep_hours"] for r in last7], 7)
    trend = hrv_trend(rows, profile["hrv_trend_window_days"])
    target = profile["sleep_target_hours"]
    debt = sleep_debt(rows, target)

    # Sleep consistency: std-dev of sleep hours
    sleep_vals = [r["total_sleep_hours"] for r in last7 if r["total_sleep_hours"]]
    if len(sleep_vals) >= 2:
        mean = sum(sleep_vals) / len(sleep_vals)
        variance = sum((v - mean) ** 2 for v in sleep_vals) / len(sleep_vals)
        consistency = round(variance ** 0.5, 2)
    else:
        consistency = None

    # Short narrative
    parts = []
    if avg_readiness is not None:
        parts.append(f"avg readiness {avg_readiness:.0f}")
    if trend:
        parts.append(f"HRV {trend}")
    if avg_sleep is not None:
        parts.append(f"avg sleep {avg_sleep:.1f}h (target {target}h)")
    if debt < -0.5:
        parts.append("sleep deficit — prioritise rest")
    elif debt > 0.5:
        parts.append("good sleep surplus")

    narrative = "; ".join(parts).capitalize() + "." if parts else "Insufficient data."

    return {
        "avg_readiness": avg_readiness,
        "hrv_trend": trend,
        "avg_sleep_hours": avg_sleep,
        "sleep_debt_hours": debt,
        "sleep_consistency_stddev": consistency,
        "narrative": narrative,
    }
