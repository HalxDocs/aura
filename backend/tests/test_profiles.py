"""Tests for per-role profiles, the recruiter capability flag, and interviews from profile."""
import itertools
import json

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from api.main import app
from api.deps import get_current_user, _WorkerUser
from db.database import async_session
from db.crud import create_invite, get_candidate_profile, upsert_candidate_profile
from db.models import User, InterviewSession
from models.schemas import ParsedResumeProfile


class _StubUser:
    def __init__(self, id="test-user-id", email="test@example.com", name="Test User",
                 role="admin"):
        self.id = id
        self.email = email
        self.name = name
        self.role = role
        self.avatar_url = None


def override_user(user):
    async def _override(request=None):
        return user
    app.dependency_overrides[get_current_user] = _override


@pytest.fixture(autouse=True)
def _leave_default_auth_override():
    """Re-apply the conftest TEST_USER override after each test (see test_invites)."""
    yield
    import conftest as _conftest

    async def _default_override(request=None):
        return _conftest.TEST_USER

    app.dependency_overrides[get_current_user] = _default_override


_client_counter = itertools.count(1)
_user_counter = itertools.count(1)


def _client():
    ip = f"10.7.{next(_client_counter)}.1"
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                       headers={"X-Forwarded-For": ip})


async def _make_user(role="candidate"):
    n = next(_user_counter)
    stub = _StubUser(
        id=f"profile-user-{n}", email=f"profile-{n}@example.com",
        name="Profile Pat", role=role,
    )
    async with async_session() as db:
        existing = await db.get(User, stub.id)
        if existing is None:
            db.add(User(
                id=stub.id,
                email=stub.email,
                name=stub.name,
                provider="google",
                provider_id=f"{stub.id}-provider-id",
                role=role,
            ))
            await db.commit()
    override_user(stub)
    return stub


# ---------------------------------------------------------------- candidate profile


@pytest.mark.asyncio
async def test_get_candidate_profile_returns_empty_defaults():
    await _make_user()
    async with _client() as ac:
        resp = await ac.get("/profile/candidate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["headline"] == ""
    assert body["skills"] == []
    assert body["experience"] == []
    assert body["resume_stored"] is False


@pytest.mark.asyncio
async def test_put_and_get_candidate_profile_roundtrip():
    await _make_user()
    payload = {
        "headline": "Senior Backend Engineer",
        "location": "Berlin, DE",
        "summary": "Ships distributed systems.",
        "skills": ["Python", "Postgres", "Go"],
        "experience": [{"title": "Staff Engineer", "company": "Acme",
                        "start": "2022-01", "end": "", "description": "Built things."}],
        "education": [{"school": "TU Berlin", "degree": "MSc", "field": "CS",
                       "start": "2015", "end": "2017"}],
        "linkedin_url": "https://linkedin.com/in/pp",
        "github_url": "https://github.com/pp",
        "portfolio_url": None,
    }
    async with _client() as ac:
        put = await ac.put("/profile/candidate", json=payload)
        assert put.status_code == 200
        got = await ac.get("/profile/candidate")
    body = got.json()
    assert body["headline"] == "Senior Backend Engineer"
    assert body["skills"] == ["Python", "Postgres", "Go"]
    assert body["experience"][0]["company"] == "Acme"
    assert body["education"][0]["school"] == "TU Berlin"
    assert body["linkedin_url"] == "https://linkedin.com/in/pp"

    async with async_session() as db:
        row = await get_candidate_profile(db, "nobody")
    assert row is None  # sanity: no cross-user rows

    # JSON list columns round-trip through the DB, not just the response:
    async with async_session() as db:
        from db.models import CandidateProfile
        rows = (await db.execute(select(CandidateProfile))).scalars().all()
        assert len(rows) == 1
        assert json.loads(rows[0].skills_json) == ["Python", "Postgres", "Go"]


@pytest.mark.asyncio
async def test_candidate_profile_rejects_non_http_link():
    await _make_user()
    async with _client() as ac:
        resp = await ac.put("/profile/candidate", json={"github_url": "github.com/evil"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_candidate_profile_strips_html():
    await _make_user()
    async with _client() as ac:
        resp = await ac.put(
            "/profile/candidate",
            json={"headline": "<script>x</script>Engineer", "summary": "A" * 5000},
        )
    # Over-limit free text 422s (same convention as InviteCreate.context),
    # while the headline is tag-stripped and saved.
    assert resp.status_code == 422
    async with _client() as ac:
        resp = await ac.put("/profile/candidate", json={"headline": "<script>x</script>Engineer"})
    assert resp.status_code == 200
    assert resp.json()["headline"] == "Engineer"


@pytest.mark.asyncio
async def test_candidate_profile_sanitizes_entry_and_skill_fields():
    """Skills and nested entries pass through the sanitizer like plain fields."""
    await _make_user()
    async with _client() as ac:
        resp = await ac.put("/profile/candidate", json={
            "skills": ["<script>x</script>Python", "Go"],
            "experience": [{
                "title": "<img src=x onerror=alert(1)>Engineer",
                "company": "Acme",
                "description": "<style>p{}</style>Built things",
            }],
            "education": [{"school": "TU<script>y</script>", "degree": "MSc"}],
        })
    assert resp.status_code == 200
    body = resp.json()
    assert body["skills"] == ["Python", "Go"]
    assert body["experience"][0]["title"] == "Engineer"
    assert body["experience"][0]["description"] == "Built things"
    assert body["education"][0]["school"] == "TU"


@pytest.mark.asyncio
async def test_candidate_profile_preserves_summary_paragraphs():
    """Prose fields keep their line structure instead of flattening to one line."""
    await _make_user()
    async with _client() as ac:
        resp = await ac.put(
            "/profile/candidate",
            json={"summary": "Ships distributed systems.\n\nLoves on-call."},
        )
    assert resp.status_code == 200
    assert resp.json()["summary"] == "Ships distributed systems.\n\nLoves on-call."


# ---------------------------------------------------------------- resume parse


@pytest.mark.asyncio
async def test_resume_upload_stores_and_returns_parsed(monkeypatch):
    user = await _make_user()
    monkeypatch.setattr("api.profiles.archive_resume", lambda uid, data: True)

    async def _extract(data):
        return "Jane Doe — Backend Engineer"

    monkeypatch.setattr("api.profiles.extract_text_from_pdf", _extract)
    parsed_out = ParsedResumeProfile(
        headline="Backend Engineer",
        skills=["Python"],
    )

    class _Result:
        output = parsed_out

    async def _run(text):
        return _Result()

    monkeypatch.setattr("api.profiles.profile_parser_agent.run", _run)

    async with _client() as ac:
        resp = await ac.post(
            "/profile/candidate/resume",
            files={"file": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed"]["headline"] == "Backend Engineer"
    assert body["parsed"]["skills"] == ["Python"]
    assert body["resume_stored"] is True

    async with async_session() as db:
        row = await get_candidate_profile(db, user.id)
    assert row.resume_stored is True
    # Parsed fields must NOT be auto-saved into the editable profile:
    assert row.headline == ""


@pytest.mark.asyncio
async def test_resume_parse_truncates_instead_of_discarding(monkeypatch):
    """One over-long field from the parser must truncate, not void the whole
    parse: strings cut to the profile caps, skills capped at 30, and entries
    missing a required field drop out (matching the client's save rules)."""
    await _make_user()
    monkeypatch.setattr("api.profiles.archive_resume", lambda uid, data: True)

    async def _extract(data):
        return "text"

    monkeypatch.setattr("api.profiles.extract_text_from_pdf", _extract)

    parsed_out = ParsedResumeProfile(
        headline="H" * 500,
        location="L" * 300,
        summary="S" * 5000,
        skills=[f"skill-{i}" for i in range(40)],
        experience=[
            {"title": "T" * 300, "company": "C", "description": "D" * 5000},
            {"title": "", "company": "Acme"},  # no usable title — dropped
        ],
        education=[{"school": "", "degree": "MSc"}],  # no school — dropped
    )

    class _Result:
        output = parsed_out

    async def _run(text):
        return _Result()

    monkeypatch.setattr("api.profiles.profile_parser_agent.run", _run)

    async with _client() as ac:
        resp = await ac.post(
            "/profile/candidate/resume",
            files={"file": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    assert resp.status_code == 200
    parsed = resp.json()["parsed"]
    assert parsed["headline"] == "H" * 200
    assert parsed["location"] == "L" * 120
    assert parsed["summary"] == "S" * 4000
    assert len(parsed["skills"]) == 30
    assert len(parsed["experience"]) == 1
    assert parsed["experience"][0]["title"] == "T" * 120
    assert parsed["experience"][0]["description"] == "D" * 2000
    assert parsed["education"] == []


@pytest.mark.asyncio
async def test_resume_upload_survives_agent_failure(monkeypatch):
    user = await _make_user()
    monkeypatch.setattr("api.profiles.archive_resume", lambda uid, data: True)

    async def _extract(data):
        return "text"

    monkeypatch.setattr("api.profiles.extract_text_from_pdf", _extract)

    async def _boom(text):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("api.profiles.profile_parser_agent.run", _boom)

    async with _client() as ac:
        resp = await ac.post(
            "/profile/candidate/resume",
            files={"file": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    assert resp.status_code == 200
    assert resp.json()["parsed"] == {
        "headline": None, "location": None, "summary": None, "skills": [],
        "experience": [], "education": [], "linkedin_url": None,
        "github_url": None, "portfolio_url": None,
    }
    async with async_session() as db:
        row = await get_candidate_profile(db, user.id)
    assert row.resume_stored is True


@pytest.mark.asyncio
async def test_resume_upload_rejects_non_pdf():
    await _make_user()
    async with _client() as ac:
        resp = await ac.post(
            "/profile/candidate/resume",
            files={"file": ("resume.txt", b"hello", "text/plain")},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_resume_upload_rejects_oversized_file(monkeypatch):
    """The upload is read in chunks and 413s as soon as the cap is exceeded,
    before extraction or storage — nothing is written for the failed upload."""
    import api.profiles as profiles_mod
    import api.uploads as uploads_mod

    user = await _make_user()
    # Shrink the cap and the read chunk so a tiny body genuinely overflows
    # mid-stream instead of shipping megabytes through the test.
    monkeypatch.setattr(profiles_mod, "MAX_RESUME_SIZE", 10)
    monkeypatch.setattr(uploads_mod, "_CHUNK", 4)

    async with _client() as ac:
        resp = await ac.post(
            "/profile/candidate/resume",
            files={"file": ("resume.pdf", b"%PDF-1.4 " + b"x" * 20, "application/pdf")},
        )
    assert resp.status_code == 413

    async with async_session() as db:
        assert await get_candidate_profile(db, user.id) is None


# ---------------------------------------------------------------- interview from profile


@pytest.mark.asyncio
async def test_interview_from_profile_creates_session(monkeypatch):
    user = await _make_user()
    async with async_session() as db:
        await upsert_profile_row(db, user.id)

    monkeypatch.setattr("api.profiles.get_resume", lambda uid: b"%PDF-1.4 fake")

    async def _extract(data):
        return "Jane — Backend Engineer"

    monkeypatch.setattr("api.profiles.extract_text_from_pdf", _extract)

    from models.schemas import InterviewPlan

    class _Result:
        output = InterviewPlan(
            candidate_name="Jane",
            extracted_skills=["Python"],
            question_bank=["Tell me about a system you designed."],
        )

    async def _run(text):
        return _Result()

    monkeypatch.setattr("api.profiles.interview_parser_agent.run", _run)

    async with _client() as ac:
        resp = await ac.post("/profile/candidate/interview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"]
    assert body["plan_summary"]["candidate_name"] == "Jane"

    from db.models import InterviewSession
    async with async_session() as db:
        row = await db.get(InterviewSession, body["session_id"])
    assert row is not None
    assert row.user_id == user.id
    assert "question_bank" in row.plan_json


async def upsert_profile_row(db, user_id):
    """Give the user a stored resume so /profile/candidate/interview proceeds."""
    from db.crud import upsert_candidate_profile
    await upsert_candidate_profile(db, user_id, resume_stored=True)


@pytest.mark.asyncio
async def test_interview_from_profile_without_resume_404():
    await _make_user()
    async with _client() as ac:
        resp = await ac.post("/profile/candidate/interview")
    assert resp.status_code == 404


# ---------------------------------------------------------------- recruiter profile


@pytest.mark.asyncio
async def test_recruiter_profile_roundtrip():
    await _make_user(role="recruiter")
    async with _client() as ac:
        put = await ac.put("/profile/recruiter", json={
            "company_name": "Acme Robotics",
            "job_title": "Engineering Manager",
            "company_website": "https://acme.example",
            "company_location": "Remote",
        })
        assert put.status_code == 200
        got = await ac.get("/profile/recruiter")
    body = got.json()
    assert body["company_name"] == "Acme Robotics"
    assert body["company_website"] == "https://acme.example"


@pytest.mark.asyncio
async def test_recruiter_profile_forbidden_for_plain_candidate():
    await _make_user(role="candidate")
    async with _client() as ac:
        resp = await ac.get("/profile/recruiter")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_role_pick_is_idempotent():
    """Picking the current role again succeeds and does not change anything."""
    await _make_user(role="recruiter")
    async with _client() as ac:
        resp = await ac.post("/auth/role", json={"role": "recruiter"})
    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "recruiter"


@pytest.mark.asyncio
async def test_unused_recruiter_can_switch_to_candidate():
    user = await _make_user(role="recruiter")
    async with _client() as ac:
        resp = await ac.post("/auth/role", json={"role": "candidate"})
    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "candidate"
    async with async_session() as db:
        row = await db.get(User, user.id)
    assert row.role == "candidate"


@pytest.mark.asyncio
async def test_used_recruiter_cannot_switch_to_candidate():
    """Any invite on record (even cancelled) locks the recruiter role."""
    user = await _make_user(role="recruiter")
    async with async_session() as db:
        await create_invite(
            db, recruiter_id=user.id, title="T", context=None,
            questions=["Q1?"], token="lock-rec-token",
            expires_in_hours=1,
        )
    async with _client() as ac:
        resp = await ac.post("/auth/role", json={"role": "candidate"})
    assert resp.status_code == 409
    assert "recruiter" in resp.json()["detail"]
    async with async_session() as db:
        row = await db.get(User, user.id)
    assert row.role == "recruiter"


@pytest.mark.asyncio
async def test_used_candidate_cannot_switch_to_recruiter():
    """Any interview session on record locks the candidate role."""
    user = await _make_user(role="candidate")
    async with async_session() as db:
        db.add(InterviewSession(
            id=f"lock-session-{user.id}", user_id=user.id,
            candidate_name="P", plan_json='{"title":"t"}',
        ))
        await db.commit()
    async with _client() as ac:
        resp = await ac.post("/auth/role", json={"role": "recruiter"})
    assert resp.status_code == 409
    assert "candidate" in resp.json()["detail"]
    async with async_session() as db:
        row = await db.get(User, user.id)
    assert row.role == "candidate"


@pytest.mark.asyncio
async def test_pre_pick_sessions_block_recruiter_pick():
    """Sessions taken before the picker runs (unpicked role) lock the
    recruiter pick — those interviews must stay candidate-side."""
    user = await _make_user(role="")
    async with async_session() as db:
        db.add(InterviewSession(
            id=f"lock-session-{user.id}", user_id=user.id,
            candidate_name="P", plan_json='{"title":"t"}',
        ))
        await db.commit()
    async with _client() as ac:
        resp = await ac.post("/auth/role", json={"role": "recruiter"})
    assert resp.status_code == 409
    assert "can't pick the recruiter role" in resp.json()["detail"]
    async with async_session() as db:
        row = await db.get(User, user.id)
    assert row.role == ""


@pytest.mark.asyncio
async def test_pre_pick_sessions_still_allow_candidate_pick():
    """An unpicked role with sessions can still formally pick candidate."""
    user = await _make_user(role="")
    async with async_session() as db:
        db.add(InterviewSession(
            id=f"lock-session-{user.id}", user_id=user.id,
            candidate_name="P", plan_json='{"title":"t"}',
        ))
        await db.commit()
    async with _client() as ac:
        resp = await ac.post("/auth/role", json={"role": "candidate"})
    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "candidate"


# ---------------------------------------------------------------- invite branding


@pytest.mark.asyncio
async def test_invite_preview_shows_recruiter_company():
    recruiter = await _make_user(role="recruiter")
    async with async_session() as db:
        await create_invite(
            db, recruiter_id=recruiter.id, title="Backend role", context=None,
            questions=["Q1?", "Q2?"], token="brand-token",
        )
        from db.crud import upsert_recruiter_profile
        await upsert_recruiter_profile(db, recruiter.id, company_name="Acme Robotics")

    async with _client() as ac:
        resp = await ac.get("/invite/brand-token")
    assert resp.status_code == 200
    body = resp.json()
    assert body["recruiter_company"] == "Acme Robotics"
    assert body["recruiter_name"] == "Profile Pat"


# ---------------------------------------------------------------- storage failures


@pytest.mark.asyncio
async def test_resume_upload_storage_failure_keeps_existing_resume(monkeypatch):
    """A failed MinIO store must not clear a resume that is already on file."""
    user = await _make_user()
    async with async_session() as db:
        from db.crud import upsert_candidate_profile
        await upsert_candidate_profile(db, user.id, headline="Kept", resume_stored=True)

    monkeypatch.setattr("api.profiles.archive_resume", lambda uid, data: False)

    async def _extract(data):
        return "text"

    monkeypatch.setattr("api.profiles.extract_text_from_pdf", _extract)

    async with _client() as ac:
        resp = await ac.post(
            "/profile/candidate/resume",
            files={"file": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    assert resp.status_code == 200
    # The response reports the effective on-file state, not this attempt.
    assert resp.json()["resume_stored"] is True

    async with async_session() as db:
        row = await get_candidate_profile(db, user.id)
    assert row.resume_stored is True
    assert row.headline == "Kept"


@pytest.mark.asyncio
async def test_resume_upload_storage_failure_on_fresh_profile(monkeypatch):
    """No prior resume + failed store: nothing is marked on file."""
    user = await _make_user()
    monkeypatch.setattr("api.profiles.archive_resume", lambda uid, data: False)

    async def _extract(data):
        return "text"

    monkeypatch.setattr("api.profiles.extract_text_from_pdf", _extract)

    async with _client() as ac:
        resp = await ac.post(
            "/profile/candidate/resume",
            files={"file": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    assert resp.status_code == 200
    assert resp.json()["resume_stored"] is False

    # Nothing was stored, so the failed attempt creates no profile row —
    # one appears on the first actual save.
    async with async_session() as db:
        row = await get_candidate_profile(db, user.id)
    assert row is None


@pytest.mark.asyncio
async def test_resume_upload_rejects_unextractable_pdf(monkeypatch):
    """A scanned/image-only PDF is rejected before anything is stored."""
    user = await _make_user()

    def _fail_storage(uid, data):  # pragma: no cover - must never be reached
        raise AssertionError("archive_resume called for an unextractable PDF")

    monkeypatch.setattr("api.profiles.archive_resume", _fail_storage)

    async def _extract(data):
        raise ValueError("No text could be extracted from the PDF.")

    monkeypatch.setattr("api.profiles.extract_text_from_pdf", _extract)

    async with _client() as ac:
        resp = await ac.post(
            "/profile/candidate/resume",
            files={"file": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    assert resp.status_code == 400
    # Rejected up front: no resume on file and no profile row.
    async with async_session() as db:
        row = await get_candidate_profile(db, user.id)
    assert row is None


@pytest.mark.asyncio
async def test_interview_from_profile_failure_returns_generic_500(monkeypatch):
    """Agent failures surface the global generic 500 — no internals in the body."""
    user = await _make_user()
    async with async_session() as db:
        await upsert_profile_row(db, user.id)

    monkeypatch.setattr("api.profiles.get_resume", lambda uid: b"%PDF-1.4 fake")

    async def _extract(data):
        return "Jane — Backend Engineer"

    monkeypatch.setattr("api.profiles.extract_text_from_pdf", _extract)

    async def _boom(text):
        raise RuntimeError("secret internal model details")

    monkeypatch.setattr("api.profiles.interview_parser_agent.run", _boom)

    # raise_app_exceptions=False: the global Exception handler builds the
    # response on ServerErrorMiddleware, which then re-raises — a real ASGI
    # server delivers that response, so the transport must too.
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test",
        headers={"X-Forwarded-For": "10.7.98.1"},
    ) as ac:
        resp = await ac.post("/profile/candidate/interview")

    assert resp.status_code == 500
    assert resp.json()["detail"] == "An unexpected error occurred. Please try again later."
    assert "secret internal model details" not in resp.text


# ---------------------------------------------------------------- profile upsert race


@pytest.mark.asyncio
async def test_profile_upsert_survives_creation_race(monkeypatch):
    """Loser of a concurrent first-save retries as an update instead of 500ing."""
    from sqlalchemy.exc import IntegrityError

    from db.crud import upsert_candidate_profile
    from db.models import CandidateProfile

    user = await _make_user()
    # A concurrent first save committed its row between our select (which saw
    # nothing) and our commit. Emulate the loser: the winner's row exists, and
    # the loser's commit raises the unique-constraint error exactly once —
    # the upsert must roll back, re-select, and apply the update on top.
    async with async_session() as db:
        db.add(CandidateProfile(user_id=user.id, headline="winner"))
        await db.commit()

    async with async_session() as db:
        original_commit = db.commit
        raced = False

        async def raced_commit():
            nonlocal raced
            if not raced:
                raced = True
                raise IntegrityError(
                    "INSERT INTO candidate_profiles ...", {},
                    Exception("UNIQUE constraint failed: candidate_profiles.user_id"),
                )
            return await original_commit()

        monkeypatch.setattr(db, "commit", raced_commit)
        profile = await upsert_candidate_profile(db, user.id, headline="loser")
        assert profile.headline == "loser"

    async with async_session() as db:
        rows = (
            await db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].headline == "loser"


# ---------------------------------------------------------------- write/read schema alignment


@pytest.mark.asyncio
async def test_candidate_profile_rejects_markup_only_required_fields():
    """A required entry field made only of active-tag markup 422s instead of
    storing an empty string that would fail read-side validation forever."""
    await _make_user()
    async with _client() as ac:
        resp = await ac.put("/profile/candidate", json={
            "experience": [{"title": "<script>x</script>", "company": "Acme"}],
        })
        assert resp.status_code == 422
        assert "job title and a company" in resp.json()["detail"]

        edu = await ac.put("/profile/candidate", json={
            "education": [{"school": "<style>p{}</style>", "degree": "MSc"}],
        })
        assert edu.status_code == 422
        assert "school" in edu.json()["detail"]

        # Nothing was stored, so reads stay healthy.
        got = await ac.get("/profile/candidate")
    assert got.status_code == 200
    assert got.json()["experience"] == []
    assert got.json()["education"] == []


@pytest.mark.asyncio
async def test_candidate_profile_read_skips_invalid_stored_entries():
    """Defense in depth: a row that already fails read validation (e.g. from
    before the write-side fix) is skipped, not a 500 on every GET."""
    user = await _make_user()
    async with async_session() as db:
        await upsert_candidate_profile(db, user.id, experience_json=json.dumps([
            {"title": "", "company": "Acme", "start": "", "end": "", "description": ""},
            {"title": "SWE", "company": "Acme", "start": "", "end": "", "description": ""},
        ]))

    async with _client() as ac:
        resp = await ac.get("/profile/candidate")
    assert resp.status_code == 200
    body = resp.json()
    assert [e["title"] for e in body["experience"]] == ["SWE"]


@pytest.mark.asyncio
async def test_candidate_profile_read_survives_corrupt_skills_shape():
    """Defense in depth: skills_json that is not a JSON list of strings (a
    corrupt/externally-edited row) degrades instead of failing list
    validation and 500ing every future GET."""
    user = await _make_user()
    async with async_session() as db:
        await upsert_candidate_profile(db, user.id, skills_json='"abc"')

    async with _client() as ac:
        resp = await ac.get("/profile/candidate")
    assert resp.status_code == 200
    assert resp.json()["skills"] == []

    other = await _make_user()
    async with async_session() as db:
        await upsert_candidate_profile(db, other.id, skills_json='["React", 1, null, "Python"]')

    async with _client() as ac:
        resp = await ac.get("/profile/candidate")
    assert resp.status_code == 200
    assert resp.json()["skills"] == ["React", "Python"]


# ---------------------------------------------------------------- worker sentinel


@pytest.mark.asyncio
async def test_worker_cannot_use_profile_endpoints():
    """The worker sentinel owns no users row; profile endpoints must 403 it
    cleanly instead of letting its writes hit the users FK as a 500."""
    app.dependency_overrides[get_current_user] = lambda request=None: _WorkerUser()
    async with _client() as ac:
        get = await ac.get("/profile/candidate")
        put = await ac.put("/profile/candidate", json={"headline": "x"})
        resume = await ac.post(
            "/profile/candidate/resume",
            files={"file": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    assert get.status_code == 403
    assert put.status_code == 403
    assert resume.status_code == 403
