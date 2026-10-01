"""AI Project Architect — profile-grounded project blueprints with AI/local fallback."""

from __future__ import annotations

import logging
from typing import Any

from flask import current_app

from app.ai.provider import complete_with_fallback
from app.ai.response import (
    ensure_structured_markdown,
    markdown_to_safe_html,
    normalize_ai_text,
)
from app.models.experience import Project
from app.models.profile import StudentProfile
from app.models.skills import StudentSkill
from app.services.career import match_roles
from app.services.skill_gap import analyze_skill_gaps
from app.extensions import db
from app.models.skills import CareerRole

logger = logging.getLogger(__name__)


def _student_skills(profile: StudentProfile) -> list[str]:
    rows = (
        StudentSkill.query.filter_by(student_id=profile.id)
        .order_by(StudentSkill.level.desc())
        .all()
    )
    return [
        (r.skill.name if r.skill else f"skill#{r.skill_id}")
        for r in rows
        if r.skill or r.skill_id
    ]


def _existing_projects(profile: StudentProfile) -> list[str]:
    return [p.title for p in Project.query.filter_by(student_id=profile.id).all()]


def _deterministic_blueprint(
    profile: StudentProfile,
    *,
    role_name: str,
    skills: list[str],
    gaps: list[str],
    interests: str | None,
) -> dict[str, Any]:
    focus = gaps[:3] or skills[:3] or ["core fundamentals"]
    interest_bit = f" with interest in {interests.strip()}" if interests and interests.strip() else ""
    title = f"{role_name} Portfolio Lab: {focus[0]}"
    stack = skills[:5] or ["Python", "SQL", "Git"]
    if gaps:
        for g in gaps[:2]:
            if g not in stack:
                stack.append(g)

    milestones = [
        {"week": 1, "goal": f"Define problem + data/API contract for {focus[0]}"},
        {"week": 2, "goal": f"Implement core feature using {', '.join(stack[:3])}"},
        {"week": 3, "goal": "Add tests, README, and one measurable demo output"},
        {"week": 4, "goal": "Polish UI/CLI, deploy notes, prepare interview walkthrough"},
    ]

    resume_suggestions = [
        {
            "text": (
                f"Built an educational {role_name.lower()} demo covering "
                f"{', '.join(focus[:2])} (complete only after you finish the work)."
            ),
            "label": "suggestion",
        },
        {
            "text": (
                "Documented architecture, setup steps, and one measured result "
                "(complete only after real implementation)."
            ),
            "label": "suggestion",
        },
    ]

    return {
        "ok": True,
        "title": title,
        "problem_statement": (
            f"Students targeting {role_name} often lack a single portfolio artifact "
            f"that proves {', '.join(focus[:2])}{interest_bit}. "
            "This project closes that evidence gap using skills already on your profile "
            "plus focused practice on documented gaps."
        ),
        "why_it_matters": (
            f"Addresses catalog gaps toward {role_name} while reusing your evidenced skills "
            f"({', '.join(skills[:5]) or 'add skills on profile'})."
        ),
        "tech_stack": stack[:8],
        "architecture": [
            "Client or notebook layer for inputs/demo",
            "Service/API or script layer for core logic",
            "Persistence (SQLite/CSV/JSON) for sample data",
            "Simple evaluation/metrics module",
        ],
        "database_design": [
            "entities table (id, attributes relevant to the domain)",
            "events or interactions table (timestamp, entity_id, payload)",
            "optional metrics_snapshot table for demo KPIs",
        ],
        "api_plan": [
            "GET /health",
            "POST /analyze (or equivalent batch script)",
            "GET /results/:id",
        ],
        "ml_component": (
            "Optional: simple sklearn baseline or rule-based scorer — "
            "only if it fits the role; label clearly as educational demo."
            if any("data" in (role_name or "").lower() or "ml" in s.lower() or "python" in s.lower() for s in skills + [role_name])
            else "Optional — skip ML unless the target role expects it."
        ),
        "milestones": milestones,
        "testing_plan": [
            "Unit tests for core transforms",
            "One integration smoke test on sample data",
            "Manual checklist for README + demo path",
        ],
        "deployment_plan": [
            "Local run documented in README",
            "Optional free-tier host (Render/Railway) if web UI exists",
            "Screenshot or short GIF for portfolio",
        ],
        "resume_bullet_suggestions": resume_suggestions,
        "existing_projects_on_file": _existing_projects(profile),
        "source": "deterministic",
        "disclaimer": (
            "Blueprint is educational. Resume bullets are SUGGESTIONS — "
            "only claim work you actually complete."
        ),
    }


def architect_project(
    profile: StudentProfile,
    *,
    target_role: str | None = None,
    interests: str | None = None,
    use_ai: bool = True,
) -> dict[str, Any]:
    """Generate a project blueprint grounded in the student profile."""
    skills = _student_skills(profile)
    matches = match_roles(profile, limit=1)
    role_name = (target_role or "").strip()
    role_obj = None
    if not role_name and matches:
        role_name = matches[0].get("role_name") or "Target Role"
        role_obj = db.session.get(CareerRole, matches[0]["role_id"])
    elif role_name:
        role_obj = CareerRole.query.filter(
            CareerRole.name.ilike(f"%{role_name}%")
        ).first()
        if role_obj:
            role_name = role_obj.name
    if not role_name:
        role_name = "Software / Data career role"

    gaps: list[str] = []
    if role_obj is not None:
        analysis = analyze_skill_gaps(profile, role_obj)
        for g in (analysis.get("gaps") or [])[:6]:
            gaps.append(g.get("skill_name") if isinstance(g, dict) else str(g))

    blueprint = _deterministic_blueprint(
        profile,
        role_name=role_name,
        skills=skills,
        gaps=gaps,
        interests=interests,
    )

    if not use_ai:
        return blueprint

    provider = str(current_app.config.get("AI_PROVIDER", "local") or "local").lower()
    if provider in {"local", "demo", "local-demo"}:
        return blueprint

    try:
        prompt = (
            "Refine this educational project blueprint for a college student. "
            "Do NOT invent skills or experience they do not have. "
            f"Role: {role_name}. Skills on file: {', '.join(skills) or 'none'}. "
            f"Gaps: {', '.join(gaps) or 'none'}. Interests: {interests or 'none'}. "
            f"Current title: {blueprint['title']}. "
            "Respond in structured Markdown using ONLY sections that apply, with headings "
            "and short bullet lists (not one long paragraph). Prefer:\n"
            "## Architecture Overview\n"
            "## Frontend\n"
            "## Backend\n"
            "## Database\n"
            "## AI / ML\n"
            "## APIs / Integrations\n"
            "## Security\n"
            "## Deployment\n"
            "## Current Problems\n"
            "## Recommended Improvements\n"
            "Also include ## Title, ## Problem, ## Why this project, ## Suggested stack, "
            "and ## Milestones (3-5 bullets) when helpful. "
            "Label resume bullets as suggestions only."
        )
        result = complete_with_fallback(
            current_app.config,
            prompt,
            system=(
                "You are EDUNOVA Project Architect. Ground advice in provided skills/gaps only. "
                "Never invent achievements. Use clear Markdown headings and bullet lists. "
                "Keep under 450 words. Never return a single unstructured paragraph."
            ),
            context={
                "skills": skills,
                "preferred_roles": [role_name],
                "project_titles": blueprint.get("existing_projects_on_file"),
            },
            history=None,
        )
        reply = normalize_ai_text(
            result.get("reply") if isinstance(result, dict) else str(result)
        )
        if reply and len(reply) > 40:
            structured = ensure_structured_markdown(reply)
            blueprint["ai_narrative"] = structured
            blueprint["ai_narrative_html"] = markdown_to_safe_html(structured)
            blueprint["source"] = (
                result.get("provider") if isinstance(result, dict) else "ai"
            )
            blueprint["fallback_used"] = bool(
                result.get("fallback_used") if isinstance(result, dict) else False
            )
    except Exception:  # noqa: BLE001
        logger.exception("Project architect AI failed; using deterministic blueprint")
        blueprint["fallback_used"] = True
        blueprint["status_message"] = (
            "AI refinement unavailable — showing deterministic blueprint from your profile."
        )

    return blueprint
