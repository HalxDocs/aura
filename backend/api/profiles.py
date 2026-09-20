"""Per-role profile endpoints (candidate job-board profile, recruiter company profile).

Rationale for the shapes:
- GET returns an empty-but-complete profile when no row exists yet, so the
  frontend form can always initialize from the response without a null check.
- POST /profile/candidate/resume stores the PDF and runs the profile parser
  agent but NEVER writes parsed fields to the profile — the client prefills
  its form for review and only PUT persists them.
- POST /interviews/from-profile re-parses the stored resume with the existing
  interview parser agent so returning candidates skip the file upload.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

import sentry_sdk
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from langfuse import propagate_attributes

from agent.parser import agent as interview_parser_agent
from agent.profile_parser import agent as profile_parser_agent
from api.deps import get_current_user, require_recruiter, _WorkerUser
from api.rate_limit import limiter
from api.uploads import read_upload_capped
from db.crud import (
    create_session,
    get_candidate_profile,
    get_recruiter_profile,
    upsert_candidate_profile,
    upsert_recruiter_profile,
)
from db.database import async_session
from models.schemas import (
    CandidateProfileIn,
    CandidateProfileOut,
    ParsedResumeProfile,
    RecruiterProfileIn,
    RecruiterProfileOut,
    ResumeParseResponse,
    UploadResponse,
)
from utils.pdf_parser import extract_text_from_pdf
from utils.storage import archive_resume, get_resume
from utils.text import sanitize_name, sanitize_rich_text

logger = logging.getLogger("profiles")

router = APIRouter(prefix="/profile", tags=["profiles"])

MAX_RESUME_SIZE = 10 * 1024 * 1024  # 10 MB — matches the /upload-pdf limit


def _reject_worker(user) -> None:
    """The worker sentinel owns no ``users`` row, so any profile write it
    attempts would violate the profile FK and surface as a 500; give it a
    clean 403 instead (same treatment /auth/role gives the sentinel)."""
    if isinstance(user, _WorkerUser):
        raise HTTPException(status_code=403, detail="Workers cannot use profile endpoints")


def _strip_html(text: str, *, preserve_newlines: bool = False) -> str:
    """Sanitize free-text profile fields (drops active-tag content too).

    No cap here — each caller applies its own field cap right after, so the
    sanitizer runs uncapped (``max_length=None``)."""
    return sanitize_rich_text(text, None, preserve_newlines=preserve_newlines)


def _experience_row(entry) -> dict:
    """Sanitized schema entry -> JSON-serializable dict for storage.

    The schema validated the *raw* strings, but a required field made up
    entirely of active-tag markup sanitizes to empty here — and a stored
    empty title/company would then fail read-side validation and 500 every
    future GET (see CandidateProfileOut.from_row). Reject instead, mirroring
    the client's completeness message.
    """
    row = {
        "title": _strip_html(entry.title)[:120],
        "company": _strip_html(entry.company)[:120],
        "start": _strip_html(entry.start)[:40],
        "end": _strip_html(entry.end)[:40],
        "description": _strip_html(entry.description, preserve_newlines=True)[:2000],
    }
    if not row["title"] or not row["company"]:
        raise HTTPException(
            status_code=422,
            detail="Each experience entry needs a job title and a company — fill them in or remove the row.",
        )
    return row


def _education_row(entry) -> dict:
    row = {
        "school": _strip_html(entry.school)[:160],
        "degree": _strip_html(entry.degree)[:160],
        "field": _strip_html(entry.field)[:160],
        "start": _strip_html(entry.start)[:40],
        "end": _strip_html(entry.end)[:40],
    }
    if not row["school"]:
        raise HTTPException(
            status_code=422,
            detail="Each education entry needs a school — fill it in or remove the row.",
        )
    return row


def _candidate_fields(payload: CandidateProfileIn) -> dict:
    """Validated schema -> ORM kwargs (lists serialized to JSON Text columns).

    Every stored string goes through the sanitizer — including the nested
    entry lists and skills, which the schema validators only trim.
    """
    return {
        "headline": _strip_html(payload.headline)[:200],
        "location": _strip_html(payload.location)[:120],
        "summary": _strip_html(payload.summary, preserve_newlines=True)[:4000],
        "skills_json": json.dumps([s for s in (_strip_html(skill)[:60] for skill in payload.skills) if s]),
        "experience_json": json.dumps([_experience_row(e) for e in payload.experience]),
        "education_json": json.dumps([_education_row(e) for e in payload.education]),
        "linkedin_url": payload.linkedin_url,
        "github_url": payload.github_url,
        "portfolio_url": payload.portfolio_url,
    }


@router.get("/candidate", response_model=CandidateProfileOut)
@limiter.limit("60/minute")
async def read_candidate_profile(request: Request, user=Depends(get_current_user)):
    """The caller's candidate profile; empty defaults when never saved."""
    _reject_worker(user)
    async with async_session() as db:
        profile = await get_candidate_profile(db, user.id)
    if profile is None:
        return CandidateProfileOut()
    return CandidateProfileOut.from_row(profile)


@router.put("/candidate", response_model=CandidateProfileOut)
@limiter.limit("60/minute")
async def save_candidate_profile(request: Request, payload: CandidateProfileIn, user=Depends(get_current_user)):
    """Create or update the caller's candidate profile."""
    _reject_worker(user)
    async with async_session() as db:
        profile = await upsert_candidate_profile(db, user.id, **_candidate_fields(payload))
    return CandidateProfileOut.from_row(profile)


@router.post("/candidate/resume", response_model=ResumeParseResponse)
@limiter.limit("10/hour")
async def upload_profile_resume(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Store the candidate's resume PDF and return parsed fields for review.

    Nothing is written to the profile's editable fields here — the client
    prefills empty form fields and the user saves explicitly. Unextractable
    PDFs are rejected up front (400) and never stored. If the parser agent
    fails, the resume is still stored (it is what powers "start interview
    from profile") and an empty `parsed` is returned. If MinIO storage
    itself fails, a resume already on file stays authoritative — the flag
    and timestamp are only written on a successful store, and no profile
    row is created by the failed attempt.
    """
    _reject_worker(user)
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    pdf_bytes = await read_upload_capped(file, MAX_RESUME_SIZE, "Resume exceeds 10 MB limit")
    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Extraction runs BEFORE the archive: an unextractable (e.g. scanned)
    # PDF must not be marked on file, because it could never power
    # "start interview from profile". Once extraction succeeds, an agent
    # failure below still leaves the stored resume in place.
    try:
        text = await extract_text_from_pdf(pdf_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # MinIO I/O is blocking — keep it off the event loop.
    resume_stored = await asyncio.to_thread(archive_resume, user.id, pdf_bytes)
    if not resume_stored:
        logger.error("Resume storage failed for user %s", user.id)

    parsed = ParsedResumeProfile()
    try:
        with propagate_attributes(user_id=user.id):
            result = await profile_parser_agent.run(text)
        parsed = result.output
    except Exception as exc:
        logger.error("Profile parse failed for user %s: %s", user.id, exc)
        sentry_sdk.capture_exception(exc)

    # Only a successful store may flip the flag on; a failed one must never
    # clear it (an older resume may still be in the bucket and usable). A
    # failed store also creates no profile row — one appears on first save.
    profile_fields: dict = {}
    if resume_stored:
        profile_fields = {
            "resume_stored": True,
            "resume_uploaded_at": datetime.now(timezone.utc),
        }

    async with async_session() as db:
        if profile_fields:
            profile = await upsert_candidate_profile(db, user.id, **profile_fields)
        else:
            # Report the effective on-file state: a prior resume may still
            # be in the bucket even though this store failed.
            profile = await get_candidate_profile(db, user.id)
    return ResumeParseResponse(parsed=parsed, resume_stored=bool(profile and profile.resume_stored))


@router.get("/recruiter", response_model=RecruiterProfileOut)
@limiter.limit("60/minute")
async def read_recruiter_profile(request: Request, user=Depends(get_current_user)):
    """The caller's recruiter profile; empty defaults when never saved."""
    require_recruiter(user)
    async with async_session() as db:
        profile = await get_recruiter_profile(db, user.id)
    if profile is None:
        return RecruiterProfileOut()
    return RecruiterProfileOut(
        company_name=profile.company_name,
        job_title=profile.job_title,
        company_website=profile.company_website,
        company_location=profile.company_location,
    )


@router.put("/recruiter", response_model=RecruiterProfileOut)
@limiter.limit("60/minute")
async def save_recruiter_profile(request: Request, payload: RecruiterProfileIn, user=Depends(get_current_user)):
    """Create or update the caller's recruiter profile. Requires recruiter access."""
    require_recruiter(user)
    async with async_session() as db:
        profile = await upsert_recruiter_profile(
            db,
            user.id,
            company_name=_strip_html(payload.company_name)[:200],
            job_title=_strip_html(payload.job_title)[:120],
            company_website=payload.company_website,
            company_location=_strip_html(payload.company_location)[:120],
        )
    return RecruiterProfileOut(
        company_name=profile.company_name,
        job_title=profile.job_title,
        company_website=profile.company_website,
        company_location=profile.company_location,
    )


@router.post("/candidate/interview", response_model=UploadResponse)
@limiter.limit("10/hour")
async def start_interview_from_profile(request: Request, user=Depends(get_current_user)):
    """Start a practice interview from the stored resume — no re-upload.

    Fetches the resume PDF archived by POST /profile/candidate/resume,
    re-extracts its text, and runs the same interview parser agent as
    POST /upload, so the created session is identical in shape and the
    standard /plan → /token voice flow works unchanged.
    """
    _reject_worker(user)
    # MinIO I/O is blocking — keep it off the event loop.
    pdf_bytes = await asyncio.to_thread(get_resume, user.id)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="No resume on file. Upload one on your profile first.")

    try:
        text = await extract_text_from_pdf(pdf_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    session_id = str(uuid.uuid4())
    try:
        with propagate_attributes(session_id=session_id, user_id=user.id):
            result = await interview_parser_agent.run(text)
        plan = result.output
        plan.candidate_name = sanitize_name(plan.candidate_name) if plan.candidate_name else "Unknown"

        async with async_session() as db:
            await create_session(
                db,
                user_id=user.id,
                candidate_name=plan.candidate_name,
                plan_json=plan.model_dump_json(),
                session_id=session_id,
            )
        return UploadResponse(session_id=session_id, plan_summary=plan)
    except HTTPException:
        raise
    except Exception:
        # Full traceback goes to the error log (and Sentry via the global
        # handler); the client only sees the generic message — same contract
        # as POST /upload.
        logger.exception("Interview-from-profile failed for user %s", user.id)
        raise
