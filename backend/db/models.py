import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Index, UniqueConstraint, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    provider: Mapped[str] = mapped_column(String(20))  # "google" | "github" | "email"
    provider_id: Mapped[str] = mapped_column(String(255))
    # Exclusive role: "" until the user picks "candidate" or "recruiter" on
    # the role picker, then exactly one of the two (switching is blocked once
    # the chosen side has been used — see crud.set_user_role). "admin" is
    # granted only via ADMIN_EMAIL promotion on login and is never
    # picker-selectable.
    role: Mapped[str] = mapped_column(String(20), default="")
    # Email/password auth (None for OAuth-only accounts). OAuth emails are
    # provider-verified, so those accounts are trusted immediately.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # SHA-256 hash of the one-time token emailed to the user; the raw token
    # only ever lives in the email link, never in the database.
    verification_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reset_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reset_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    provider_id: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint("provider", "provider_id", name="uq_oauth_provider_identity"),
        UniqueConstraint("user_id", "provider", name="uq_oauth_user_provider"),
    )


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    candidate_name: Mapped[str] = mapped_column(String(255), default="Unknown")
    plan_json: Mapped[str] = mapped_column(Text)
    report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # "pending" | "in_progress" | "completed"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_sessions_status", "status"),)


class InterviewInvite(Base):
    __tablename__ = "interview_invites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    recruiter_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    questions_json: Mapped[str] = mapped_column(Text)
    # Opaque token used in the shareable invite URL (/invite/{token})
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    candidate_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    # The interview session created on redemption. A forward pointer, written
    # by redeem_invite's atomic claim before the session row exists — so the
    # FK is DEFERRABLE INITIALLY DEFERRED (migration d5e6f7a8b9c0): Postgres
    # checks it at commit, after the caller's session INSERT has landed in the
    # same transaction, instead of rejecting the claim UPDATE. Kept on this
    # table (rather than a column on interview_sessions) so existing
    # deployments need no ALTER.
    session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("interview_sessions.id", deferrable=True, initially="DEFERRED"),
        nullable=True,
        index=True,
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # When the link stops being redeemable. Null means no expiry. Redemption
    # enforces it inside redeem_invite's atomic claim, not at read time.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # "pending" | "completed" | "cancelled"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CandidateProfile(Base):
    """Job-board style profile for the candidate side of an account.

    One row per user (1:1, created lazily on first save). List-shaped fields
    (skills, experience, education) follow the codebase's Text-JSON column
    pattern and are parsed with Pydantic at the API edge.
    """

    __tablename__ = "candidate_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, index=True)
    headline: Mapped[str] = mapped_column(String(200), default="")
    location: Mapped[str] = mapped_column(String(120), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    skills_json: Mapped[str] = mapped_column(Text, default="[]")
    experience_json: Mapped[str] = mapped_column(Text, default="[]")
    education_json: Mapped[str] = mapped_column(Text, default="[]")
    linkedin_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    portfolio_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # The resume PDF lives in MinIO (resumes/{user_id}/resume.pdf); this row
    # only records that one is attached, for "start interview from profile".
    resume_stored: Mapped[bool] = mapped_column(Boolean, default=False)
    resume_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class RecruiterProfile(Base):
    """Recruiter-side profile: branding shown to candidates on invites."""

    __tablename__ = "recruiter_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, index=True)
    company_name: Mapped[str] = mapped_column(String(200), default="")
    job_title: Mapped[str] = mapped_column(String(120), default="")
    company_website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    company_location: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
