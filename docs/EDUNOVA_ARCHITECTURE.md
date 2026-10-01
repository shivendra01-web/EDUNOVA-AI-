# EDUNOVA AI — Architecture

**EDUNOVA AI** is a single Flask service for academic career intelligence demos.

## Stack

- Flask + Flask-Login + Flask-WTF (CSRF)
- SQLAlchemy (SQLite local / PostgreSQL on Render)
- Optional sklearn placement model + coefficient fallback
- AI providers: **Groq** (primary when configured), OpenAI, Gemini, **local deterministic**

## Layout

```
app/
  routes/     # main, auth, student, intelligence, api, admin
  services/   # readiness, skill_gap, roadmap, coach, interview, …
  ai/         # provider + response normalization
  models/     # users, profile, skills, resume, interview, analytics
  templates/  # Jinja2 UI
ml/           # dataset + placement training
scripts/      # seed_demo_data
tests/
```

## Request flow

UI form/API → blueprint route (auth + student scope) → service → DB / AI provider → JSON or template.

AI path: configured provider → timeout/error → local deterministic fallback → user-safe message.

## Key services

| Service | Role |
|---------|------|
| personalization | Dashboard intelligence (cached per request) |
| command_center | Aggregates personalization into Command Center + daily briefing |
| coach | Profile-grounded Q&A via Groq/local |
| roadmap / learning_planner | Personalized roadmap + study schedule |
| skill_gap / skill_prioritizer | Gaps + explainable HIGH/MED/LOW |
| interview | Hybrid local + optional AI evaluation |
| resume_intel / jd_intel | Resume & JD analysis |
| project_architect | Profile-grounded project blueprints |
| company_intel / what_if | Company fit & simulations |

## Data rules

- Never invent student achievements.
- Scores are educational estimates, not hiring predictions.
- Student-scoped queries must always filter by authenticated `student_id` / `user_id`.

## Deploy

One Gunicorn process (`run:app`). See `render.yaml`, `Procfile`, `runtime.txt`.
