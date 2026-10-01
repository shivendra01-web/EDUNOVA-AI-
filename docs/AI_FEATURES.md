# EDUNOVA AI — AI Features

## Provider configuration

| Variable | Purpose |
|----------|---------|
| `AI_PROVIDER` | `groq` \| `openai` \| `gemini` \| `local` |
| `AI_API_KEY` | Generic key (OpenAI/Gemini/Groq fallback) |
| `AI_MODEL` | Model override |
| `GROQ_API_KEY` | Preferred Groq secret |
| `GROQ_MODEL` | Groq model (default `openai/gpt-oss-120b`) |

`DEMO_MODE` does **not** force local AI. Groq remains available when configured.

## Fallback architecture

```
PRIMARY AI (Groq / OpenAI / Gemini)
        ↓ timeout / HTTP / SDK error
LOCAL DETERMINISTIC FALLBACK
        ↓
USER-FRIENDLY RESPONSE (no stack traces)
```

## Feature matrix

| Feature | Primary | Fallback | Notes |
|---------|---------|----------|-------|
| AI Coach | Groq/configured | Local structured intents | Compact profile context; history persisted |
| Mock Interview | Local scoring + optional AI eval | Local only | Not an objective hiring score |
| Project Architect | Deterministic blueprint + optional AI refine | Deterministic | Resume bullets labeled suggestions |
| Learning / Study Planner | Deterministic from gaps | N/A | Hours/day × days/week schedule |
| Career Command Center | Aggregates existing services | Soft empty states | No duplicate expensive scoring |
| Skill Prioritizer | skill_gap matrix + WHY text | Empty role message | Explainable, not black-box |
| What-If / JD / Resume | Deterministic (+ optional narrative) | Numbers/heuristic only | Educational estimates |
| Daily Briefing | Deterministic from dashboard intel | Static tips | No AI call |

## Context builders

- `coach.build_student_context` — compact facts (skills, projects, readiness, gaps)
- `ai.provider._format_context` — single-line context for API calls
- Avoid re-sending full profile history; conversation window limited

## Quality rules

- Lower temperature for analytical tasks (provider defaults)
- Reasonable timeouts on HTTP/SDK calls
- Never hallucinate CGPA, projects, or certifications
- Structured coach answers: SUMMARY / WHY / ACTION PLAN / NEXT STEP where applicable
