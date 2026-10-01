"""Personalized learning planner built on skill gaps + optional AI narrative."""

from __future__ import annotations

from typing import Any

from app.models.profile import StudentProfile
from app.models.skills import CareerRole
from app.services.career import match_roles
from app.services.skill_gap import analyze_skill_gaps


def _pick_role(profile: StudentProfile, role: CareerRole | None) -> CareerRole | None:
    if role is not None:
        return role
    matches = match_roles(profile, limit=1)
    if not matches:
        return None
    from app.extensions import db

    return db.session.get(CareerRole, matches[0]["role_id"])


def build_learning_plan(
    profile: StudentProfile,
    role: CareerRole | None = None,
    *,
    weeks: int = 4,
    hours_per_day: int = 2,
    days_per_week: int = 5,
) -> dict[str, Any]:
    """
    Deterministic weekly plan from skill gaps.

    Does not invent student achievements. Optional AI narrative is added by the route.
    """
    weeks = max(2, min(8, int(weeks)))
    hours_per_day = max(1, min(8, int(hours_per_day or 2)))
    days_per_week = max(3, min(7, int(days_per_week or 5)))
    target = _pick_role(profile, role)
    if target is None:
        return {
            "ok": False,
            "goal": "Choose a target career role to generate a learning plan.",
            "weeks": [],
            "days": [],
            "gaps": [],
            "disclaimer": "Educational plan only — not a placement guarantee.",
        }

    analysis = analyze_skill_gaps(profile, target)
    gaps = list(analysis.get("gaps") or analysis.get("missing") or [])[:12]
    gap_names: list[str] = []
    for g in gaps:
        if isinstance(g, dict):
            gap_names.append(str(g.get("skill_name") or g.get("name") or g))
        else:
            gap_names.append(str(g))

    known = [
        s.skill.name
        for s in (profile.skills or [])
        if getattr(s, "skill", None) and s.skill.name
    ]
    # Fallback if relationship not loaded
    if not known:
        from app.models.skills import StudentSkill

        known = [
            link.skill.name
            for link in StudentSkill.query.filter_by(student_id=profile.id).all()
            if link.skill and link.skill.name
        ]

    weekly: list[dict[str, Any]] = []
    focus_skills = gap_names or ["core fundamentals for your target role"]
    week_hours = hours_per_day * days_per_week
    for w in range(1, weeks + 1):
        skill = focus_skills[(w - 1) % len(focus_skills)]
        phase = (
            "Foundation"
            if w == 1
            else ("Practice" if w < weeks else "Interview & portfolio")
        )
        study_mins = min(90, max(30, hours_per_day * 30))
        practice_mins = min(60, max(20, hours_per_day * 20))
        weekly.append(
            {
                "week": w,
                "theme": phase,
                "focus_skill": skill,
                "estimated_hours": week_hours if w < weeks else week_hours + 2,
                "daily_tasks": [
                    f"Study {skill} concepts for {study_mins} minutes",
                    f"Complete one hands-on exercise related to {skill} ({practice_mins} min)",
                    "Log what you practiced in EduNova projects or notes",
                ],
                "practice": f"Build a small exercise that demonstrates {skill}",
                "checkpoint": f"Explain {skill} out loud in 3 minutes without notes",
                "interview_questions": [
                    f"What is {skill} and when would you use it?",
                    f"Describe a small task where {skill} improved a result.",
                ],
            }
        )

    # Day-of-week schedule for Study Planner UI
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_schedule: list[dict[str, Any]] = []
    for i in range(days_per_week):
        skill = focus_skills[i % len(focus_skills)]
        practice_skill = focus_skills[(i + 1) % len(focus_skills)]
        sessions = [
            {
                "skill": skill,
                "minutes": min(90, max(30, int(hours_per_day * 30))),
                "kind": "study",
            },
            {
                "skill": practice_skill if days_per_week > 1 else skill,
                "minutes": min(60, max(20, int(hours_per_day * 20))),
                "kind": "practice",
            },
        ]
        if hours_per_day >= 2:
            sessions.append(
                {
                    "skill": "Interview / roadmap",
                    "minutes": min(45, max(15, int(hours_per_day * 15))),
                    "kind": "interview",
                }
            )
        day_schedule.append(
            {
                "day": day_names[i],
                "sessions": sessions,
                "total_minutes": sum(s["minutes"] for s in sessions),
            }
        )

    mini_project = (
        f"Build a small portfolio piece for {target.name} that uses "
        f"{', '.join(focus_skills[:3])}."
        if focus_skills
        else f"Build a small portfolio piece aligned to {target.name}."
    )

    return {
        "ok": True,
        "goal": f"Prepare for {target.name} over {weeks} weeks",
        "role_id": target.id,
        "role_name": target.name,
        "hours_per_day": hours_per_day,
        "days_per_week": days_per_week,
        "current_skills": known[:20],
        "gaps": gap_names,
        "prerequisites": known[:6] or ["Complete onboarding and add your current skills"],
        "weeks": weekly,
        "days": day_schedule,
        "mini_project": mini_project,
        "revision_checkpoints": [
            f"End of week {i}: review notes and redo one exercise"
            for i in range(1, weeks + 1)
        ],
        "disclaimer": (
            "Educational learning plan derived from catalog skill gaps — "
            "not a hiring or placement guarantee."
        ),
    }
