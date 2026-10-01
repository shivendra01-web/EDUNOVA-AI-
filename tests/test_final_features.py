"""Regression tests for Command Center, Study Planner, Architect, Prioritizer."""

from __future__ import annotations

from app.models.profile import StudentProfile
from app.models.user import User
from app.services import coach, command_center, learning_planner, project_architect, skill_prioritizer


def _login(client):
    return client.post(
        "/login",
        data={"email": "student@test.com", "password": "Student@123", "submit": True},
        follow_redirects=True,
    )


def _profile(app):
    student = User.query.filter_by(email="student@test.com").first()
    return StudentProfile.query.filter_by(user_id=student.id).first()


def test_command_center_builds(app):
    with app.app_context():
        profile = _profile(app)
        center = command_center.build_command_center(profile)
        assert "current_state" in center
        assert "ai_priorities" in center
        assert center["daily_briefing"]["today_priority"]
        assert "disclaimer" in center


def test_command_center_page(client):
    _login(client)
    page = client.get("/student/command-center", follow_redirects=True)
    assert page.status_code == 200
    body = page.data.decode("utf-8", errors="replace")
    assert "Command Center" in body


def test_skill_prioritizer_buckets(app):
    with app.app_context():
        profile = _profile(app)
        result = skill_prioritizer.prioritize_skills(profile)
        assert result.get("ok") is True
        assert "high" in result and "medium" in result and "low" in result
        named = {
            r["skill_name"]
            for band in ("high", "medium", "low")
            for r in result[band]
        }
        assert "SQL" in named or "Python" in named
        for band in ("high", "medium", "low"):
            for row in result[band]:
                assert "why" in row
                assert row.get("priority_band") in {"HIGH", "MEDIUM", "LOW"}


def test_skill_prioritizer_page(client):
    _login(client)
    page = client.get("/student/skill-prioritizer", follow_redirects=True)
    assert page.status_code == 200
    assert b"Skill Prioritizer" in page.data or b"HIGH PRIORITY" in page.data


def test_study_planner_day_schedule(app):
    with app.app_context():
        profile = _profile(app)
        plan = learning_planner.build_learning_plan(
            profile, hours_per_day=2, days_per_week=5
        )
        assert plan.get("ok") is True
        assert len(plan["days"]) == 5
        assert plan["days"][0]["sessions"]
        assert plan["hours_per_day"] == 2


def test_study_planner_page(client):
    _login(client)
    page = client.post(
        "/student/study-planner",
        data={
            "hours_per_day": "2",
            "days_per_week": "5",
            "generate": "1",
        },
        follow_redirects=True,
    )
    assert page.status_code == 200
    assert b"Monday" in page.data or b"Study" in page.data


def test_project_architect_deterministic(app):
    with app.app_context():
        profile = _profile(app)
        bp = project_architect.architect_project(profile, use_ai=False)
        assert bp["ok"] is True
        assert bp["title"]
        assert bp["milestones"]
        assert bp["source"] == "deterministic"
        for bullet in bp["resume_bullet_suggestions"]:
            assert bullet.get("label") == "suggestion"


def test_project_architect_page(client):
    _login(client)
    page = client.post(
        "/student/project-architect",
        data={"target_role": "Data Analyst", "interests": "campus analytics"},
        follow_redirects=True,
    )
    assert page.status_code == 200
    assert b"Problem" in page.data or b"blueprint" in page.data.lower() or b"Milestone" in page.data


def test_coach_structured_intents(app):
    with app.app_context():
        profile = _profile(app)
        for q in (
            "What should I learn next?",
            "Why is my readiness low?",
            "What should I do this week?",
            "How can I improve my resume?",
        ):
            out = coach.ask_coach(profile, q, persist=False)
            assert out["reply"]
            assert len(out["reply"]) > 20
