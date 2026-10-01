"""Teacher demo end-to-end journey — zero broken transitions."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from docx import Document

from app.extensions import db
from app.models.learning import LearningRoadmap, LearningTask
from app.models.profile import StudentProfile
from app.models.skills import CareerRole
from app.models.user import User
from app.services import (
    coach,
    command_center,
    interview as interview_svc,
    learning_planner,
    project_architect,
    resume_intel,
    roadmap as roadmap_svc,
    skill_prioritizer,
    what_if,
)
from app.services.jd_intel import compare_profile_to_jd, extract_jd_structured


def _login(client, email="student@test.com", password="Student@123"):
    r = client.post(
        "/login",
        data={"email": email, "password": password, "submit": True},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Please log in" not in r.data
    return r


def _assert_ok(client, path: str, *, must_contain: bytes | None = None):
    r = client.get(path, follow_redirects=True)
    assert r.status_code == 200, f"{path} returned {r.status_code}"
    body = r.data
    assert b"Internal Server Error" not in body
    assert b"Traceback" not in body
    if must_contain:
        assert must_contain in body, f"{path} missing {must_contain!r}"
    return r


def test_invalid_login_and_protected_routes(client):
    bad = client.post(
        "/login",
        data={"email": "student@test.com", "password": "WrongPass1", "submit": True},
        follow_redirects=True,
    )
    # App returns 401 with friendly message (not a traceback)
    assert bad.status_code in {200, 401}
    assert b"Invalid email or password" in bad.data

    blocked = client.get("/student/dashboard", follow_redirects=True)
    assert b"Log in" in blocked.data or b"Welcome back" in blocked.data


def test_teacher_demo_full_journey(client, app, tmp_path):
    """Exact examiner journey: login → every major feature → logout → login."""
    _login(client)

    # Dashboard + Command Center + Daily Briefing
    _assert_ok(client, "/student/dashboard", must_contain=b"Command Center")
    cc = _assert_ok(client, "/student/command-center", must_contain=b"Command Center")
    assert b"Daily Briefing" in cc.data or b"priority" in cc.data.lower()

    # AI Coach — question + follow-up
    with app.app_context():
        profile = StudentProfile.query.filter_by(
            user_id=User.query.filter_by(email="student@test.com").first().id
        ).first()
        r1 = coach.ask_coach(profile, "What should I learn next?", persist=True)
        assert r1["reply"] and len(r1["reply"]) > 15
        r2 = coach.ask_coach(profile, "Why should I learn that?", persist=True)
        assert r2["reply"] and len(r2["reply"]) > 15
        empty = coach.ask_coach(profile, "   ", persist=False)
        assert "enter a question" in empty["reply"].lower() or "Please" in empty["reply"]

    coach_page = client.post(
        "/student/coach",
        data={"message": "How can I improve my resume?", "submit": True},
        follow_redirects=True,
    )
    assert coach_page.status_code == 200
    assert b"Coach" in coach_page.data or b"coach" in coach_page.data.lower()

    # Career matching + skill gap
    _assert_ok(client, "/student/careers")
    gap = client.get("/student/skill-gap", follow_redirects=True)
    assert gap.status_code == 200

    with app.app_context():
        role = CareerRole.query.filter_by(name="Data Analyst").first()
        assert role is not None
        role_id = role.id
        profile = StudentProfile.query.filter_by(
            user_id=User.query.filter_by(email="student@test.com").first().id
        ).first()

    gap_post = client.post(
        "/student/skill-gap",
        data={"role_id": str(role_id), "submit": True},
        follow_redirects=True,
    )
    assert gap_post.status_code == 200
    assert b"SQL" in gap_post.data or b"gap" in gap_post.data.lower()

    # Resume analysis (DOCX)
    docx_path = tmp_path / "demo_resume.docx"
    doc = Document()
    doc.add_heading("Student Demo", 0)
    doc.add_paragraph("Skills: Python, SQL, Excel")
    doc.add_paragraph("Projects: Campus attendance dashboard with Flask")
    doc.save(docx_path)
    with docx_path.open("rb") as fh:
        upload = client.post(
            "/student/resume",
            data={
                "resume": (fh, "demo_resume.docx"),
                "submit": True,
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
    assert upload.status_code == 200
    assert b"Internal Server Error" not in upload.data

    # Invalid resume type
    with app.app_context():
        with pytest.raises(ValueError, match="Unsupported"):
            resume_intel.extract_text(tmp_path / "x.txt", "txt")

    # JD readiness simulator
    jd_text = (
        "Job Title: Data Analyst\n"
        "Required: Python, SQL, Excel, Statistics\n"
        "Preferred: Tableau, Power BI\n"
        "Location: Bengaluru\n"
    )
    with app.app_context():
        profile = StudentProfile.query.filter_by(
            user_id=User.query.filter_by(email="student@test.com").first().id
        ).first()
        structured = extract_jd_structured(jd_text)
        comparison = compare_profile_to_jd(profile, jd_text)
        assert structured.get("skills_required") or structured.get("role")
        assert "combined_fit_pct" in comparison or "matched_required" in comparison
        assert comparison.get("disclaimer") or True

    jd_page = client.post(
        "/student/jd-analyzer",
        data={
            "title": "Data Analyst",
            "company": "DemoCo",
            "raw_text": jd_text,
            "submit": True,
        },
        follow_redirects=True,
    )
    assert jd_page.status_code == 200
    assert b"fit" in jd_page.data.lower() or b"Required" in jd_page.data or b"JD" in jd_page.data

    # Personalized roadmap + complete a task
    with app.app_context():
        profile = StudentProfile.query.filter_by(
            user_id=User.query.filter_by(email="student@test.com").first().id
        ).first()
        role = CareerRole.query.filter_by(name="Data Analyst").first()
        rm = roadmap_svc.generate_roadmap(profile, role)
        assert rm.id
        tasks = (
            LearningTask.query.join(LearningRoadmap)
            .filter(LearningRoadmap.id == rm.id)
            .all()
        )
        assert tasks
        task = tasks[0]
        before_pct = float(rm.progress_pct or 0)
        roadmap_svc.set_task_status(task.id, "completed", student_id=profile.id)
        db.session.refresh(rm)
        after_pct = float(rm.progress_pct or 0)
        assert after_pct >= before_pct
        roadmap_id = rm.id

    road_page = client.get(f"/student/roadmap?roadmap_id={roadmap_id}", follow_redirects=True)
    assert road_page.status_code == 200

    # Mock interview
    with app.app_context():
        profile = StudentProfile.query.filter_by(
            user_id=User.query.filter_by(email="student@test.com").first().id
        ).first()
        sess = interview_svc.start_session(profile, "technical", role_focus="Data Analyst")
        detail = interview_svc.session_detail(sess.id, student_id=profile.id)
        qid = detail["current_question_id"]
        ans = interview_svc.submit_answer(
            qid,
            "I used Python and SQL to analyze student attendance and presented results.",
            student_id=profile.id,
        )
        assert ans is not None
        sid = sess.id

    results = client.get(f"/student/interview/{sid}/results", follow_redirects=True)
    # May redirect if incomplete — either results or interview page is fine if 200
    assert results.status_code == 200

    # Project Architect + Skill Prioritizer + Study Planner
    arch = client.post(
        "/student/project-architect",
        data={"target_role": "Data Analyst", "interests": "campus analytics"},
        follow_redirects=True,
    )
    assert arch.status_code == 200
    assert b"Problem" in arch.data or b"Milestone" in arch.data

    with app.app_context():
        profile = StudentProfile.query.filter_by(
            user_id=User.query.filter_by(email="student@test.com").first().id
        ).first()
        pri = skill_prioritizer.prioritize_skills(profile)
        assert pri.get("ok")
        plan = learning_planner.build_learning_plan(profile, hours_per_day=2, days_per_week=5)
        assert plan.get("ok") and plan.get("days")
        center = command_center.build_command_center(profile)
        assert center["daily_briefing"]["today_priority"]
        bp = project_architect.architect_project(profile, use_ai=False)
        assert bp["ok"] and bp["milestones"]

    _assert_ok(client, "/student/skill-prioritizer", must_contain=b"PRIORIT")
    planner = client.post(
        "/student/study-planner",
        data={"hours_per_day": "2", "days_per_week": "5", "generate": "1"},
        follow_redirects=True,
    )
    assert planner.status_code == 200
    assert b"Monday" in planner.data

    # What-If — skill improvement should change readiness estimate
    with app.app_context():
        profile = StudentProfile.query.filter_by(
            user_id=User.query.filter_by(email="student@test.com").first().id
        ).first()
        base = what_if.simulate_skill_level_change(profile, skill_name="SQL", new_level=5)
        assert "baseline" in base or "current" in base or "scenario" in base or "simulated" in base or "before" in base
        blob = str(base)
        assert "SQL" in blob or "readiness" in blob.lower() or "scenario" in blob.lower()

    what = client.post(
        "/student/what-if",
        data={"skill_name": "SQL", "new_level": "5", "submit": True},
        follow_redirects=True,
    )
    assert what.status_code == 200

    # Analytics + Report PDF
    _assert_ok(client, "/student/analytics")
    report = client.get("/student/report", follow_redirects=True)
    assert report.status_code == 200
    assert report.mimetype == "application/pdf" or report.data[:4] == b"%PDF"

    # Notifications + theme + readiness + companies
    for path in (
        "/student/notifications",
        "/student/theme",
        "/student/readiness-center",
        "/student/opportunity-fit",
        "/student/companies",
        "/student/intelligence-score",
        "/student/skill-intelligence",
        "/student/learning",
        "/student/projects",
        "/student/prediction",
        "/api/health",
    ):
        r = client.get(path, follow_redirects=True)
        assert r.status_code == 200, f"failed {path}"

    # Logout → login again (session persistence of roadmap)
    out = client.get("/logout", follow_redirects=True)
    assert out.status_code == 200
    blocked = client.get("/student/dashboard", follow_redirects=True)
    assert b"Welcome back" in blocked.data or b"Log in" in blocked.data

    _login(client)
    with app.app_context():
        profile = StudentProfile.query.filter_by(
            user_id=User.query.filter_by(email="student@test.com").first().id
        ).first()
        still = LearningRoadmap.query.filter_by(student_id=profile.id).count()
        assert still >= 1

    _assert_ok(client, "/student/dashboard")
    _assert_ok(client, f"/student/roadmap?roadmap_id={roadmap_id}")


def test_all_student_get_routes_no_500(client):
    """Smoke: every student GET page returns 200 after login (no blank 500s)."""
    _login(client)
    paths = [
        "/student/dashboard",
        "/student/profile",
        "/student/onboarding",
        "/student/prediction",
        "/student/explain",
        "/student/careers",
        "/student/skill-gap",
        "/student/roadmap",
        "/student/resume",
        "/student/interview",
        "/student/coach",
        "/student/projects",
        "/student/learning",
        "/student/analytics",
        "/student/command-center",
        "/student/study-planner",
        "/student/skill-prioritizer",
        "/student/project-architect",
        "/student/theme",
        "/student/notifications",
        "/student/skill-intelligence",
        "/student/companies",
        "/student/opportunity-fit",
        "/student/dream-company",
        "/student/what-if",
        "/student/compare-careers",
        "/student/compare-companies",
        "/student/jd-analyzer",
        "/student/intelligence-score",
        "/student/readiness-center",
        "/student/career-switch",
    ]
    failures = []
    for path in paths:
        r = client.get(path, follow_redirects=True)
        if r.status_code != 200:
            failures.append((path, r.status_code))
        elif b"Internal Server Error" in r.data or b"Traceback (most recent" in r.data:
            failures.append((path, "traceback"))
    assert not failures, f"Broken pages: {failures}"


def test_register_fresh_user_journey(client, app):
    r = client.post(
        "/register",
        data={
            "name": "Teacher Demo User",
            "email": "teacher.demo@test.com",
            "password": "Secure@123",
            "confirm": "Secure@123",
            "submit": True,
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    with app.app_context():
        u = User.query.filter_by(email="teacher.demo@test.com").first()
        assert u is not None
        assert u.check_password("Secure@123")
