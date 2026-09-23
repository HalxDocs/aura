# CLAUDE.md

Global rules for working in this repository.

## Project Overview

**Aura** — a real-time voice AI that conducts job interviews. A candidate shares a resume
(or accepts a recruiter's invite), talks to an AI interviewer over WebRTC, and receives a
structured hiring report. Recruiters create invite links with their own questions and get
back the report, transcript, and audio recording.

[README.md](README.md) documents the product, every environment variable, and the full API
surface — read it there rather than duplicating it here.

## Commands

```bash
# Backend (from backend/)
uv sync
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload   # API
uv run python agent/worker.py dev                                  # LiveKit worker
uv run pytest                                                      # 252 tests, all passing

# Frontend (from frontend/)
npm install
npm run dev                                                        # dev server on :3000
npm test                                                           # vitest, 57 tests passing
npm run build                                                      # tsc -b && vite build
```

**Linting is noisy on purpose — do not "fix" it as a side task.** `uv run ruff check .`
reports 19 `E402` errors and `npm run lint` reports 41 problems; both are pre-existing and
concentrated in files that are correct as written:

- The backend `E402`s are all in `agent/worker.py` and `scripts/migrate_sqlite_to_postgres.py`
  — the deliberate "manipulate `sys.path` / call `load_dotenv()` before importing app modules"
  pattern required to run them as scripts. Other agent modules silence this with a trailing
  `# noqa: E402` on the import; these two carry many imports and were left unsuppressed.
- The frontend errors are in unused vendored scaffolding (`components/agents-ui/`,
  `hooks/agents-ui/`, `use-toast.ts`) and `test.ts`, a scratch file that exists to hold
  type errors.

Check that you haven't *added* to these counts; don't drive them to zero unasked.

## Architecture

The design is a **hybrid loop**: LiveKit's `AgentSession` owns the low-latency voice
conversation; Pydantic AI owns the slower reasoning that must not block audio.

```
Frontend (React) ──API──▶ Backend (FastAPI) ──▶ SQLite/Postgres + MinIO
       │                        ▲
       │ WebRTC audio           │ report + transcript, authenticated by WORKER_API_KEY
       ▼                        │
LiveKit Cloud ◀──── Worker (LiveKit Agent + Pydantic AI)
```

**Reasoning agents** — each is a Pydantic AI `Agent` with a typed `output_type`, selectable
via env (`<AGENT>_MODEL` → `REASONING_MODEL` → built-in default):

| Agent | File | Input → Output |
|---|---|---|
| Parser | `agent/parser.py` | resume text → `InterviewPlan` |
| Evaluator | `agent/evaluator.py` | one answer → `EvaluationResult` (score + follow-up) |
| Reporter | `agent/reporter.py` | transcript → `FinalReport` |
| Profile parser | `agent/profile_parser.py` | resume text → `ParsedResumeProfile` |

**Worker lifecycle** (`agent/worker.py`) — the most important file to understand:

1. `entrypoint` connects to the room and fetches the plan from the backend.
2. Builds `AgentSession` (Silero VAD; STT/LLM/TTS from env) and an `InterviewWorkflow`.
3. `_run_interview` collects the transcript from `user_input_transcribed` (final only) and
   `conversation_item_added` events, and exposes two LLM function tools: `evaluate_answer`
   and `end_interview`.
4. A **10-minute cap** timer: a wrap-up line at 8 minutes, hard disconnect at 10.
5. The report is saved **before** the room is deleted — the candidate's browser starts
   polling `/report/{id}` the moment its room disconnects, so ordering here is load-bearing.
6. `end_interview` deletes the LiveKit room (that is what actually ends the interview) and
   has a delayed-shutdown fallback if the close fails.

**Two interview paths share one frontend component.** Practice mode (`/interview`) is
resume-driven and does not record audio. Recruiter mode (`/invite/:token`) uses the
recruiter's 2–5 questions, records audio in-browser, and is the only path with
`recordAudio` enabled.

## Structure

```
backend/
  api/          FastAPI routers + main.py (app, migrations, CORS, session middleware)
  agent/        LiveKit worker + the four Pydantic AI agents
  db/           SQLAlchemy models, crud, engine/session setup
  models/       Pydantic schemas + InterviewContext dataclass
  migrations/   Alembic (env.py, versions/)
  utils/        config, storage (MinIO), text sanitizers, email, PDF, tracing, time
  tests/        pytest suite (conftest.py supplies fixtures + auth overrides)
frontend/
  src/api/      client.ts — the single axios instance and every endpoint wrapper
  src/pages/    route components
  src/components/  ui/ (shadcn), auth/, interview/, layout/, voice/, vendored agents-ui
  src/hooks/    interview, recorder, guard, page meta
  src/styles/   aura-*.css, hand-written page-scoped stylesheets
  src/contexts/ AuthContext.tsx
scripts/web-audit/   squirrelscan/axe audit toolkit
```

## Backend Patterns

**Configuration lives in `utils/config.py`, and is resolved eagerly at import.** A weak or
missing secret, or a malformed model name, must crash the process at boot rather than fail
mid-interview. Import `JWT_SECRET`, `ENVIRONMENT`, `PARSER_MODEL`, etc. from there — never
read those variables from `os.getenv` in a new module.

**Authorization goes through `api/deps.py`.** `get_current_user` resolves the caller (and
returns a `_WorkerUser` sentinel for `WORKER_API_KEY`, compared with `hmac.compare_digest`).
Gate with `require_admin` / `require_recruiter`, or call `can_access_session` for the
owner-or-admin-or-inviting-recruiter rule. The JWT carries a `role` claim but the backend
**re-reads role from the DB on every request** — never trust the claim.

**Every error response is shaped by `api/error_handlers.py`.** Unhandled exceptions return a
generic message plus an `error_id` that maps to exactly one Sentry event; validation errors
become a compact 422; query strings are omitted from request logs because they carry tokens.
Raise `HTTPException` and let the handler normalize it — don't hand-build error responses.

**Sanitize all free text with `utils/text.py`** before storing or re-rendering it:
`sanitize_name` for names, `sanitize_text` for single-line fields, `sanitize_rich_text` for
prose that must keep its paragraph structure. Note that `sanitize_rich_text` drops the
*content* of active tags, not just the tags — profile fields are stored verbatim and
re-rendered in dashboards.

**Rate-limit new endpoints** with `@limiter.limit("N/unit")` from `api/rate_limit.py`. The
key function deliberately uses the *last* `X-Forwarded-For` hop (the one our nginx vouched
for); using the first would let a client spoof a fresh value per request.

**CRUD lives in `db/crud.py`** and follows a consistent shape: keyword-only arguments, and
race-prone operations return a **sentinel status string** (`CLAIMED`, `ALREADY_CLAIMED`,
`CANCELLED`, `EXPIRED`) rather than raising, so the endpoint can translate it into the right
HTTP status. Concurrency paths catch `IntegrityError`, roll back, and resolve against the
winner's committed rows. Example worth reading: `redeem_invite`.

**`utils/storage.py` (MinIO) logs and never raises.** Archival is best-effort — a MinIO
outage must not fail a user's request. Artifacts are keyed `{name_slug}_{session_id}/`.

**Long-running work goes in `BackgroundTasks`**, not inline (archival, email sends).

## Frontend Patterns

**Two styling systems coexist deliberately.** Tailwind + shadcn/ui (`src/components/ui/`)
covers auth, password, and toast surfaces. Everything else uses the hand-written, page-scoped
stylesheets in `src/styles/aura-*.css`, each rooting under one class
(`.aura-landing-page`, `.aura-dashboard-page`, `.aura-pre-page`, `.aura-arena-page`,
`.aura-report-page`). Match the surrounding page; don't migrate one to the other.

**All HTTP goes through `src/api/client.ts`** — a single axios instance that injects
`Authorization: Bearer <localStorage.aura_token>` and exports one typed wrapper per endpoint.
Add a wrapper there rather than calling `api.get` from a page. Normalize error messages for
display with `apiErrorMessage(error, fallback)`, which already handles string `detail`, the
422 `{message, errors[]}` shape, and slowapi's 429 body.

**Roles are exclusive and live on the account** (`user.role`: `''` unpicked, `candidate`,
`recruiter`, `admin`). There is no client-side mode state — links and guards derive from
`user.role`; the "Switch role" link opens `/choose-role?switch=1` and the **server** enforces
the usage lock (a recruiter with invites or a candidate with sessions cannot switch). Route
guards in `components/auth/ProtectedRoute.tsx` are cosmetic — the backend re-checks every
request.

**Transcript capture is client-side only** (`InterviewAgent` via `useTranscriptions`); nothing
is POSTed from the browser. The worker persists the authoritative transcript.

**The report is fetched by polling** (`getReport` every 3s, up to 120s) after the room
disconnects, because the SSE transport could not carry the JWT. 404 means "still generating".

## Database & Migrations

Alembic owns the schema for **both** SQLite and Postgres; `api/main.py:_run_migrations` runs
it at startup. For SQLite there is an additional auto-heal path for databases created by the
pre-Alembic `create_all` era: such a database is validated against the current models and then
stamped at head — but a genuinely drifted schema is **refused**, so startup fails loudly
rather than 500ing later with an opaque "no such column".

When adding a migration:

- Write a real `downgrade()` — existing migrations have them.
- Give `upgrade()` a docstring explaining *why* the change is shaped that way, especially for
  nullable/default choices. See `c3d4e5f6a7b8_add_invite_expires_at.py`.
- A column added to `users` must also be appended to `_USER_COLUMNS_ADDED` in `db/database.py`,
  which is what heals legacy SQLite databases.
- Watch out for **FK enforcement differences**: SQLite does not enforce foreign keys by
  default, Postgres does. A constraint that works in dev can 500 every request in production —
  this exact bug shipped once on `interview_invites.session_id`. If a column is a forward
  pointer written before its target row exists, the FK must be `DEFERRABLE INITIALLY DEFERRED`
  or absent.

List-shaped data uses **Text-JSON columns** parsed with Pydantic at the API edge. Read-side
parsers (`CandidateProfileOut.from_row`) skip corrupt entries rather than raising, so one bad
row can't 500 every future read.

## Testing

**Backend** (`backend/tests/`) — pytest + pytest-asyncio in strict mode, against an in-memory
SQLite DB. `conftest.py` seeds a `TEST_USER` and installs a `get_current_user` dependency
override before every test. To exercise a different role, override it with a stub and restore
it afterwards (see `test_invites.py`); to test the real auth path including the worker
sentinel, pop the override entirely (`use_real_auth()`). Patch `reporter_agent` / `httpx` to
avoid real network and LLM calls (`test_worker.py` shows the pattern). Every module must
still import cleanly with no API keys set.

**Frontend** (`frontend/src/**/__tests__/`) — vitest + Testing Library, jsdom, `globals: true`
with an empty `setupFiles`. Files needing jest-dom matchers must import
`'@testing-library/jest-dom/vitest'` explicitly. Fakes for browser APIs are hand-written
(`vi.stubGlobal` in `use-recorder.test.tsx`) rather than library mocks.

**Known coverage gap:** nothing exercises the LiveKit room logic, transcript assembly, the
report-polling loop, `AuthContext`, `ReportView`, or `ProtectedRoute`. There is no `vi.mock`
of `@livekit/components-react` anywhere. Treat `InterviewAgent.tsx` as unverified by tests.

**Any change to a schema, an auth path, or the invite/quota flow needs a test.** Those are the
areas where this codebase has historically shipped bugs.

## Conventions

**Never add a co-author trailer to a commit. No exceptions.**

Commits use conventional prefixes (`feat:`, `fix:`, `chore:`, `docs:`) with a descriptive
subject; squash-merged PRs append the number, e.g.
`fix: agent-initiated interview ending, complete transcript capture (#24)`.

**Comments explain *why*, not *what*, and this codebase takes that seriously.** The dominant
style is a docstring or comment that records the specific bug or constraint that made the
current shape necessary — e.g. why the transcript check uses `text_content` (the previous
`hasattr(part, "text")` never matched a `str`, silently dropping every interviewer line), why
`pool_pre_ping` is enabled for Postgres but not SQLite, why the rate-limit key is the last
XFF hop. Match this. Do not add comments that restate the next line, and do not annotate your
own change as correct — that's noise once merged.

**Prefer failing loudly at startup over failing obscurely at request time.** This shows up in
the eager config resolution, the production schema-drift check, and the weak-secret rejection.

**Don't run destructive or outward-facing commands** (deploys, migrations against a live
database, sending email, deleting rooms) without being asked.

## Key Files

| File | Why it matters |
|---|---|
| `backend/agent/worker.py` | The interviewer: session setup, transcript, tools, time cap, report-on-exit |
| `backend/api/main.py` | App wiring, startup migrations, upload/plan/token/report/invite endpoints |
| `backend/api/deps.py` | Auth resolution and the authorization gates |
| `backend/utils/config.py` | Single source of truth for secrets and model selection |
| `backend/db/models.py` | The six tables; read the comments on `InterviewInvite` and `User.role` |
| `backend/db/crud.py` | Concurrency-safe claim/redeem logic |
| `backend/models/schemas.py` | Every request/response contract |
| `frontend/src/api/client.ts` | All HTTP + the types shared with the backend |
| `frontend/src/components/voice/InterviewAgent.tsx` | The live interview arena (large, untested) |
| `frontend/src/contexts/AuthContext.tsx` | Token storage, role mode resolution |
| `frontend/nginx.conf` + `nginx-headers.conf` | CSP and the rest of the security headers |
