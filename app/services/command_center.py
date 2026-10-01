"""AI Career Command Center — aggregate existing intelligence (no duplicate scoring)."""

from __future__ import annotations

from typing import Any

from app.models.profile import StudentProfile
from app.services.personalization import dashboard_intelligence


def build_daily_briefing(profile: StudentProfile, dash: dict[str, Any] | None = None) -> dict[str, Any]:
    """Cheap deterministic daily briefing — no AI provider call."""
    data = dash or dashboard_intelligence(profile)
    actions = list(data.get("actions") or [])
    matches = list(data.get("career_matches") or [])
    roadmap = data.get("roadmap") or {}
    snapshot = data.get("career_snapshot") or {}
    interview = data.get("interview") or {}

    top = matches[0] if matches else {}
    gaps = top.get("gaps") or top.get("missing_skills") or []
    skill = None
    if gaps:
        g0 = gaps[0]
        skill = g0.get("skill_name") if isinstance(g0, dict) else str(g0)
    elif snapshot.get("biggest_gaps"):
        skill = str(snapshot["biggest_gaps"][0])[:80]

    priority = actions[0]["title"] if actions else "Complete your profile and skills"
    interview_q = (
        f"Practice a {top.get('role_name') or 'role'}-focused technical question"
        if top
        else "Start a short technical mock interview"
    )
    if interview.get("average_score") is not None:
        interview_q += f" (recent avg {interview['average_score']})"

    roadmap_task = (
        f"Continue roadmap “{roadmap.get('title')}” ({roadmap.get('progress_pct')}%)"
        if roadmap.get("has_roadmap")
        else "Generate a personalized learning roadmap"
    )
    profile_tip = (
        "Upload/analyze resume for ATS-style feedback"
        if not (data.get("resume") or {}).get("has_resume")
        else "Add measurable outcomes to projects already on file"
    )

    return {
        "today_priority": priority,
        "skill_to_practice": skill or "Add target-role skills to unlock focus",
        "interview_question": interview_q,
        "roadmap_task": roadmap_task,
        "profile_improvement": profile_tip,
        "source": "deterministic",
        "disclaimer": "Briefing is derived from saved EduNova data — educational only.",
    }


def build_command_center(profile: StudentProfile) -> dict[str, Any]:
    """
    Career Command Center payload from existing services.

    Reuses dashboard_intelligence to avoid recomputing readiness/gaps twice.
    """
    dash = dashboard_intelligence(profile)
    readiness = dash.get("readiness") or {}
    components = readiness.get("components") or {}
    matches = list(dash.get("career_matches") or [])
    top = matches[0] if matches else {}
    roadmap = dash.get("roadmap") or {}
    interview = dash.get("interview") or {}
    resume = dash.get("resume") or {}
    conf = list(dash.get("skill_confidence") or [])
    actions = list(dash.get("actions") or [])[:3]
    snapshot = dash.get("career_snapshot") or {}

    strongest = [c for c in conf if float(c.get("confidence") or 0) >= 0.6][:3]
    weakest = sorted(
        conf,
        key=lambda c: float(c.get("confidence") or 0),
    )[:3]
    if not strongest and components:
        strongest = [
            {"skill_name": k, "confidence": float(v) / 100.0}
            for k, v in sorted(components.items(), key=lambda x: -float(x[1] or 0))[:3]
        ]
    if not weakest and components:
        weakest = [
            {"skill_name": k, "confidence": float(v) / 100.0}
            for k, v in sorted(components.items(), key=lambda x: float(x[1] or 0))[:3]
        ]

    gaps = top.get("gaps") or top.get("missing_skills") or []
    top_gap = None
    if gaps:
        g0 = gaps[0]
        top_gap = {
            "skill": g0.get("skill_name") if isinstance(g0, dict) else str(g0),
            "detail": g0 if isinstance(g0, dict) else {"skill_name": str(g0)},
            "why": (
                f"Highest-impact gap toward {top.get('role_name')} "
                f"({top.get('match_pct')}% catalog match)."
            ),
        }

    project_rec = snapshot.get("project_to_build") or (
        f"Build a portfolio project that demonstrates {top_gap['skill']}."
        if top_gap
        else "Add a project that showcases your strongest evidenced skill."
    )
    interview_rec = snapshot.get("interview_focus") or (
        f"Practice questions for {top.get('role_name')}."
        if top
        else "Start a short technical mock interview."
    )
    resume_rec = (
        "Upload and analyze a resume to unlock ATS-style feedback."
        if not resume.get("has_resume")
        else "Quantify outcomes on projects already listed — do not invent experience."
    )

    weekly: list[dict[str, str]] = []
    for i, action in enumerate(actions[:3]):
        weekly.append(
            {
                "day_band": f"Days {i * 2 + 1}–{i * 2 + 2}",
                "task": action.get("title") or "Next action",
                "reason": action.get("reason") or "",
            }
        )
    if roadmap.get("has_roadmap"):
        weekly.append(
            {
                "day_band": "Days 5–7",
                "task": f"Advance roadmap ({roadmap.get('progress_pct')}%)",
                "reason": roadmap.get("title") or "Learning roadmap",
            }
        )
    else:
        weekly.append(
            {
                "day_band": "Days 5–7",
                "task": "Generate and start a learning roadmap",
                "reason": "No roadmap on file yet.",
            }
        )

    briefing = build_daily_briefing(profile, dash)

    return {
        "current_state": {
            "readiness": readiness.get("overall"),
            "readiness_components": components,
            "intelligence_score": (dash.get("intelligence") or {}).get("overall"),
            "strongest_skills": strongest,
            "weakest_skills": weakest,
            "target_role": top.get("role_name"),
            "match_pct": top.get("match_pct"),
            "roadmap_progress": roadmap.get("progress_pct"),
            "roadmap_title": roadmap.get("title"),
            "interview_average": interview.get("average_score"),
            "interview_completed": interview.get("completed_count"),
        },
        "ai_priorities": actions,
        "career_gap": top_gap,
        "project_recommendation": project_rec,
        "interview_recommendation": interview_rec,
        "resume_recommendation": resume_rec,
        "weekly_action_plan": weekly[:5],
        "daily_briefing": briefing,
        "disclaimer": (
            "Command Center aggregates educational estimates from your saved profile — "
            "not hiring predictions."
        ),
        "source": "deterministic",
    }
