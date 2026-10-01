"""Targeted tests for auth/session, GitHub, roadmap, interview, AI formatting repairs."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.ai.response import (
    ensure_structured_markdown,
    markdown_to_safe_html,
    normalize_ai_text,
)
from app.extensions import db
from app.models import CareerRole, LearningRoadmap, StudentProfile, User
from app.models.experience import Project
from app.services import interview as interview_svc
from app.services import roadmap as roadmap_svc
from app.services.github_project import (
    GitHubAnalysisError,
    analyze_github_repository,
    apply_analysis_to_project_fields,
    parse_github_url,
)


def _login(client, email="student@test.com", password="Student@123"):
    return client.post(
        "/login",
        data={"email": email, "password": password, "remember": True, "submit": True},
        follow_redirects=False,
    )


def test_register_login_logout_invalid_and_protected(client, app):
    email = "reliability.student@example.com"
    r = client.post(
        "/register",
        data={
            "name": "Reliability Student",
            "email": email,
            "password": "SecurePass1!",
            "confirm": "SecurePass1!",
            "submit": True,
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    client.get("/logout", follow_redirects=True)

    bad = client.post(
        "/login",
        data={
            "email": email,
            "password": "WrongPassword!",
            "submit": True,
        },
        follow_redirects=False,
    )
    assert bad.status_code == 401

    ok = _login(client, email=email, password="SecurePass1!")
    assert ok.status_code in (302, 303)

    # New accounts are redirected to onboarding until profile is complete.
    protected = client.get("/student/dashboard", follow_redirects=False)
    assert protected.status_code in (200, 302)
    onboard = client.get("/student/onboarding", follow_redirects=True)
    assert onboard.status_code == 200

    client.get("/logout", follow_redirects=True)
    blocked = client.get("/student/dashboard", follow_redirects=False)
    assert blocked.status_code in (302, 401)


def test_session_cookie_secure_helpers(monkeypatch):
    from config import _default_session_cookie_secure

    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    assert _default_session_cookie_secure() is True
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    assert _default_session_cookie_secure() is False
    monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
    monkeypatch.setenv("RENDER", "true")
    assert _default_session_cookie_secure() is True
    monkeypatch.setenv("RENDER", "false")
    monkeypatch.setenv("FLASK_ENV", "development")
    assert _default_session_cookie_secure() is False


def test_proxy_fix_installed(app):
    # Werkzeug ProxyFix wraps wsgi_app so Render X-Forwarded-Proto is honored.
    assert type(app.wsgi_app).__name__ == "ProxyFix"


def test_github_url_normalization_variants():
    assert parse_github_url("https://github.com/pallets/flask") == ("pallets", "flask")
    assert parse_github_url("https://www.github.com/pallets/flask/") == ("pallets", "flask")
    assert parse_github_url("https://github.com/pallets/flask.git") == ("pallets", "flask")
    with pytest.raises(GitHubAnalysisError):
        parse_github_url("https://gitlab.com/pallets/flask")
    with pytest.raises(GitHubAnalysisError):
        parse_github_url("not-a-url")


def test_github_api_failure_friendly(app):
    with app.app_context():
        with patch(
            "app.services.github_project._http_json",
            side_effect=GitHubAnalysisError(
                "GitHub repository could not be accessed. Please check that the repository "
                "is public and the URL is correct."
            ),
        ):
            with pytest.raises(GitHubAnalysisError) as exc:
                analyze_github_repository("https://github.com/missing/repo-xyz")
            assert "public" in str(exc.value).lower()


def test_github_timeout_friendly(app):
    with app.app_context():
        with patch(
            "app.services.github_project.urllib.request.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            with pytest.raises(GitHubAnalysisError) as exc:
                analyze_github_repository("https://github.com/pallets/flask")
            assert "long" in str(exc.value).lower() or "try again" in str(exc.value).lower()


def test_github_analysis_persists(app):
    payload = {
        "ok": True,
        "source_url": "https://github.com/acme/demo",
        "owner": "acme",
        "repo": "demo",
        "found_in_repository": {
            "title": "Demo",
            "description": "A demo repo",
            "languages": ["Python"],
            "frameworks": ["Flask"],
            "technologies": ["Python", "Flask"],
            "libraries": [],
            "features": [],
            "architecture_clues": [],
            "files_reviewed": ["README.md"],
            "readme_excerpt": "Hello",
            "dependency_files": [],
            "topics": [],
        },
        "suggested_tech_stack": "Flask, Python",
        "suggested_description": "A demo repo",
        "summary_text": "Repository: acme/demo",
    }
    fields = apply_analysis_to_project_fields(payload)
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        project = Project(
            student_id=profile.id,
            title=fields["title"],
            description=fields["description"],
            tech_stack=fields["tech_stack"],
            url=fields["url"],
            analysis_json=fields["analysis_json"],
            analysis_status="analyzed",
        )
        db.session.add(project)
        db.session.commit()
        pid = project.id
        again = db.session.get(Project, pid)
        assert again is not None
        assert again.analysis_json
        assert "acme" in again.analysis_json


def test_roadmap_idempotent_and_progress(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        role = CareerRole.query.filter_by(name="Data Analyst").first()
        assert role is not None
        first = roadmap_svc.generate_roadmap(profile, role, replace_existing=True)
        summary = roadmap_svc.roadmap_summary(first)
        task_id = summary["tasks"][0]["id"]
        roadmap_svc.set_task_status(task_id, "completed", student_id=profile.id)
        progress = db.session.get(LearningRoadmap, first.id).progress_pct
        assert progress > 0

        # Idempotent generate must not wipe progress
        second = roadmap_svc.generate_roadmap(profile, role, replace_existing=False)
        assert second.id == first.id
        assert db.session.get(LearningRoadmap, first.id).progress_pct == progress

        # Explicit regenerate rebuilds
        third = roadmap_svc.generate_roadmap(profile, role, replace_existing=True)
        assert third.id != first.id or db.session.get(LearningRoadmap, third.id).progress_pct == 0


def test_interview_progression_and_idempotent_submit(app):
    with app.app_context():
        student = User.query.filter_by(email="student@test.com").first()
        profile = StudentProfile.query.filter_by(user_id=student.id).first()
        sess = interview_svc.start_session(profile, "technical", role_focus="Analyst")
        detail = interview_svc.session_detail(sess.id, student_id=profile.id)
        qid = detail["current_question_id"]
        later = [q for q in detail["questions"] if q["id"] != qid][0]["id"]

        with pytest.raises(ValueError):
            interview_svc.submit_answer(
                later,
                "Skipping ahead should fail because earlier questions are unanswered.",
                student_id=profile.id,
            )

        ans = interview_svc.submit_answer(
            qid,
            "I used Python and SQL on a campus analytics project with clear metrics and teamwork.",
            student_id=profile.id,
        )
        again = interview_svc.submit_answer(
            qid,
            "Different text that should be ignored on double submit.",
            student_id=profile.id,
        )
        assert again.id == ans.id
        assert again.answer_text == ans.answer_text


def test_ai_architecture_formatting_structured():
    wall = (
        "Architecture Overview: Flask monolith with SQLAlchemy. "
        "Frontend: Jinja templates and CSS. "
        "Backend: Route blueprints and services. "
        "Recommended Improvements: Add caching and clearer error messages."
    )
    structured = ensure_structured_markdown(wall)
    assert "## Architecture Overview" in structured
    assert "## Frontend" in structured
    html = markdown_to_safe_html(structured)
    assert "<h3" in html
    assert "<ul>" in html or "<p>" in html

    md = (
        "## Architecture Overview\n"
        "* Flask backend\n"
        "* SQLAlchemy persistence\n\n"
        "## Deployment\n"
        "1. Bind to PORT\n"
        "2. Use Gunicorn\n"
    )
    html2 = markdown_to_safe_html(md)
    assert "<h3" in html2
    assert "<li>" in html2
    assert "<ol>" in html2

    # Malformed JSON-like AI payload falls back to readable text
    weird = normalize_ai_text({"answer": "Use modular blueprints and keep Groq as primary."})
    assert "Groq" in weird or "blueprint" in weird.lower()
    assert "{'answer'" not in weird

    # Already-good markdown is not destroyed
    good = "## Backend\n* Flask\n* Routes"
    assert ensure_structured_markdown(good) == good
