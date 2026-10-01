"""Explainable skill prioritizer — wraps skill_gap with transparent WHY reasons."""

from __future__ import annotations

from typing import Any

from app.extensions import db
from app.models.profile import StudentProfile
from app.models.skills import CareerRole
from app.services.career import match_roles
from app.services.skill_gap import skill_gap_matrix


def _pick_role(profile: StudentProfile, role: CareerRole | None) -> CareerRole | None:
    if role is not None:
        return role
    matches = match_roles(profile, limit=1)
    if not matches:
        return None
    return db.session.get(CareerRole, matches[0]["role_id"])


def _why(row: dict[str, Any], *, role_name: str) -> str:
    """Human-readable explanation — no black-box score."""
    parts: list[str] = []
    priority = row.get("priority") or "Low"
    importance = float(row.get("importance") or 1.0)
    gap = int(row.get("gap_level") or 0)
    current = int(row.get("current_level") or 0)
    required = int(row.get("required_level") or 0)
    band = row.get("importance_band") or "supporting"

    parts.append(
        f"{priority} for {role_name}: catalog marks this skill as {band} "
        f"(importance {importance:.2f})."
    )
    if gap > 0:
        parts.append(
            f"Gap size is {gap} level(s) (current L{current} vs required L{required})."
        )
    else:
        parts.append(f"You already meet or exceed the required level (L{current}/{required}).")

    conf = row.get("confidence")
    if conf is not None:
        parts.append(f"Evidence confidence on profile: {float(conf):.0%}.")
    evidence = row.get("evidence") or []
    if evidence:
        parts.append("Evidence: " + "; ".join(str(e) for e in evidence[:2]))

    return " ".join(parts)


def prioritize_skills(
    profile: StudentProfile,
    role: CareerRole | None = None,
) -> dict[str, Any]:
    """
    Bucket skills into HIGH / MEDIUM / LOW with explainable reasons.

    Uses existing skill_gap matrix (role importance × gap × evidence).
    """
    target = _pick_role(profile, role)
    if target is None:
        return {
            "ok": False,
            "role_name": None,
            "high": [],
            "medium": [],
            "low": [],
            "disclaimer": "Choose a target career role to prioritize skills.",
        }

    matrix = skill_gap_matrix(profile, target)
    high: list[dict[str, Any]] = []
    medium: list[dict[str, Any]] = []
    low: list[dict[str, Any]] = []

    for row in matrix.get("matrix") or []:
        if int(row.get("gap_level") or 0) <= 0:
            # Met skills stay low priority for learning focus
            entry = {
                **row,
                "priority_band": "LOW",
                "why": _why({**row, "priority": "Low"}, role_name=target.name),
            }
            low.append(entry)
            continue
        label = (row.get("priority") or "Medium").title()
        if label in {"Critical", "High"}:
            band = "HIGH"
            bucket = high
        elif label == "Medium":
            band = "MEDIUM"
            bucket = medium
        else:
            band = "LOW"
            bucket = low
        bucket.append(
            {
                **row,
                "priority_band": band,
                "why": _why(row, role_name=target.name),
            }
        )

    return {
        "ok": True,
        "role_id": target.id,
        "role_name": target.name,
        "coverage_pct": matrix.get("coverage_pct"),
        "weighted_coverage_pct": matrix.get("weighted_coverage_pct"),
        "high": high,
        "medium": medium,
        "low": low,
        "disclaimer": (
            "Priorities combine role importance, gap size, and profile evidence — "
            "educational guidance, not hiring outcomes."
        ),
    }


def top_priorities(profile: StudentProfile, *, limit: int = 5) -> list[dict[str, Any]]:
    result = prioritize_skills(profile)
    if not result.get("ok"):
        return []
    combined = list(result.get("high") or []) + list(result.get("medium") or [])
    return combined[:limit]
