# EDUNOVA AI — QA Checklist

**Date:** 2026-09-30 (zero-broken-demo verification)  
**Suite:** `pytest -q` → **89 passed, 1 skipped, 0 failed**  
**Environment:** local SQLite + `AI_PROVIDER=local` (TestConfig); Groq provider unit-tested with mocks

## Teacher demo journey (automated)

`tests/test_teacher_demo.py::test_teacher_demo_full_journey` — **PASS**

| Step | Result |
|------|--------|
| Login | PASS |
| Dashboard + Command Center + Daily Briefing | PASS |
| AI Coach question + follow-up + empty input | PASS |
| Career matching + Skill Gap | PASS |
| Resume DOCX upload + unsupported type rejection | PASS |
| JD → Readiness (fit + missing/matched + prep plan) | PASS |
| Roadmap generate + task complete + persist after logout | PASS |
| Mock Interview answer submit | PASS |
| Project Architect + Skill Prioritizer + Study Planner | PASS |
| What-If skill change | PASS |
| Analytics + PDF report | PASS |
| Notifications / theme / readiness / companies / health | PASS |
| Logout → protected block → Login again | PASS |

Also: `test_all_student_get_routes_no_500` — **31 student GET routes return 200, no traceback**.

## Features verified

Authentication, dashboard, readiness, skill intel/gap/prioritizer, careers, company intel, opportunity fit, resume, JD readiness simulator, coach (+ local fallback), roadmap progress, interview, What-If, analytics, PDF, Command Center, Study Planner, Project Architect, daily briefing, theme, notifications, `/api/health`.

## AI / Groq

| Check | Status |
|-------|--------|
| Provider abstraction (`get_ai_provider` / `complete_with_fallback`) | PASS |
| Groq selected when `AI_PROVIDER=groq` | PASS (unit) |
| Groq accepts `AI_API_KEY` alias | PASS (unit) |
| Groq failure → local fallback, no key leakage | PASS (unit) |
| Local coach / interview / architect offline | PASS |
| No committed secrets | PASS |

## Render readiness

`Procfile`, `render.yaml`, `runtime.txt` (3.11.9), Gunicorn `$PORT`, `/api/health`, env-based `SECRET_KEY` / Groq keys (`sync: false`), `FLASK_DEBUG=false`.

## Bugs found & fixed this pass

1. **JD analyzer template** — duplicate/corrupt comparison block → cleaned; clarified “JD → Readiness” + preparation plan CTAs.
2. **Resume page** — missing visible Resume → Roadmap bridge → added CTA panel.
3. **Teacher demo coverage** — added examiner journey tests as a hard gate.
4. **learning_planner** — `Query.get` → `db.session.get`.

## Remaining issues before a live demo (must-know, not blockers)

1. **Live Groq** requires a real `GROQ_API_KEY` / `AI_API_KEY` on Render or `.env` — without a key the app uses local fallback (does not crash).
2. **sklearn joblib version warning** (1.9.0 model vs 1.9.1 runtime) — retrain on deploy to silence; model still loads.
3. **Study Planner** day checkmarks are not separately persisted (Roadmap tasks remain durable progress).
4. **Lightweight automation** is inline service refresh in routes (no event bus) — by design; no duplicate-loop issues found.

## Examiner manual click-path

Use `demo@edunova.ai` / `Demo@123` after seed, or register fresh. Follow the table above in order. Expect educational disclaimers, not hiring guarantees.
