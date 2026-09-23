from datetime import datetime, timedelta, timezone
from sqlalchemy import select, desc, func, update, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import (
    User,
    OAuthIdentity,
    InterviewSession,
    InterviewInvite,
    CandidateProfile,
    RecruiterProfile,
)
from utils.time import as_utc


def _verify_via_oauth(user: User) -> None:
    """Mark a user verified after a provider login.

    OAuth proves mailbox ownership, but it does *not* prove any password that an
    unauthenticated ``/auth/register`` may have pre-set on an unverified row.
    Clear the password on the unverified → verified transition so a pre-set
    password can never be activated by a later provider login (account takeover).
    """
    if not user.email_verified:
        user.password_hash = None
        user.email_verified = True


async def upsert_oauth_user(
    db: AsyncSession,
    *,
    email: str,
    name: str,
    provider: str,
    provider_id: str,
    avatar_url: str | None = None,
) -> tuple[User, bool]:
    """Resolve a provider identity, linking verified providers by email.

    Returns ``(user, created)``; ``created`` is True only when a brand-new
    account is inserted, so the OAuth callback can send the welcome email once.
    Providers only hand back verified emails (enforced in the callback), so the
    account is marked ``email_verified`` immediately — this is what lets the
    user later set a password and sign in with it.

    OAuth callbacks can race (retries, concurrent tabs), so every
    ``IntegrityError`` is rolled back and resolved against the rows the
    winning transaction committed, instead of surfacing a 500.
    """
    email = email.strip().lower()

    async def _resolve_identity() -> OAuthIdentity | None:
        result = await db.execute(
            select(OAuthIdentity).where(
                OAuthIdentity.provider == provider,
                OAuthIdentity.provider_id == provider_id,
            )
        )
        return result.scalar_one_or_none()

    last_error: IntegrityError | None = None
    for _ in range(2):
        identity = await _resolve_identity()
        if identity:
            user = await get_user_by_id(db, identity.user_id)
            if user:
                user.name, user.avatar_url = name, avatar_url
                user.last_login_at = datetime.now(timezone.utc)
                _verify_via_oauth(user)
                identity.email = email
                await db.commit()
                await db.refresh(user)
                return user, False

        user_result = await db.execute(select(User).where(func.lower(User.email) == email))
        user = user_result.scalar_one_or_none()
        created = False
        if not user:
            user = User(
                email=email,
                name=name,
                provider=provider,
                provider_id=provider_id,
                avatar_url=avatar_url,
                email_verified=True,
            )
            db.add(user)
            created = True
            try:
                # Flush now so user.id exists for the identity row below.
                await db.flush()
            except IntegrityError as exc:
                # A concurrent callback created the same email first.
                last_error = exc
                await db.rollback()
                continue
        else:
            user.name, user.avatar_url = name, avatar_url
            user.last_login_at = datetime.now(timezone.utc)
            _verify_via_oauth(user)

        db.add(OAuthIdentity(user_id=user.id, provider=provider, provider_id=provider_id, email=email))
        try:
            await db.commit()
            await db.refresh(user)
            return user, created
        except IntegrityError as exc:
            # The identity (or user+identity pair) was committed concurrently.
            last_error = exc
            await db.rollback()

    # Both attempts raced with another callback; resolve read-only against
    # whatever survived, preferring the provider identity.
    identity = await _resolve_identity()
    if identity:
        existing_user = await get_user_by_id(db, identity.user_id)
        if existing_user:
            _verify_via_oauth(existing_user)
            await db.commit()
            return existing_user, False
    user_result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = user_result.scalar_one_or_none()
    if user:
        _verify_via_oauth(user)
        await db.commit()
        return user, False
    if last_error is None:
        raise RuntimeError("upsert_oauth_user failed to resolve a user")
    raise last_error


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Look up a user by email, case-insensitively.

    Matches ``upsert_oauth_user``'s linking behaviour so legacy rows stored
    with mixed-case emails are visible to the email/password routes too (and a
    lowercase registration can't insert a duplicate alongside them).
    """
    normalized = email.strip().lower()
    result = await db.execute(select(User).where(func.lower(User.email) == normalized))
    return result.scalar_one_or_none()


async def store_verification_token(
    db: AsyncSession, user: User, token_hash: str, expires_at: datetime
) -> None:
    user.verification_token_hash = token_hash
    user.verification_token_expires_at = expires_at
    await db.commit()


async def mark_email_verified(db: AsyncSession, user: User) -> None:
    user.email_verified = True
    user.verification_token_hash = None
    user.verification_token_expires_at = None
    await db.commit()


async def store_reset_token(
    db: AsyncSession, user: User, token_hash: str, expires_at: datetime
) -> None:
    user.reset_token_hash = token_hash
    user.reset_token_expires_at = expires_at
    await db.commit()


async def set_user_password(db: AsyncSession, user: User, password_hash: str) -> None:
    # Reset-link clicks prove mailbox ownership, so a previously unverified
    # account gets verified here as well.
    user.password_hash = password_hash
    user.email_verified = True
    user.reset_token_hash = None
    user.reset_token_expires_at = None
    await db.commit()


async def create_session(
    db: AsyncSession,
    *,
    user_id: str,
    candidate_name: str,
    plan_json: str,
    session_id: str | None = None,
) -> InterviewSession:
    session = InterviewSession(
        user_id=user_id,
        candidate_name=candidate_name,
        plan_json=plan_json,
        status="pending",
        **({"id": session_id} if session_id else {}),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def create_session_for_invite(
    db: AsyncSession,
    *,
    session_id: str,
    user_id: str,
    candidate_name: str,
    plan_json: str,
) -> InterviewSession:
    """Create the session a redeemed invite points at, and commit the pair.

    redeem_invite claims without committing (the FK on interview_invites
    .session_id is DEFERRABLE INITIALLY DEFERRED), so claim + session INSERT
    must land in one transaction: the deferred check runs at COMMIT, after
    the session row exists, and a crash can no longer strand a claimed invite
    pointing at a session that was never written. On failure the transaction
    rolls back and the claim with it — the link simply stays redeemable, so
    release_invite_claim is no longer needed on this path.
    """
    session = InterviewSession(
        id=session_id,
        user_id=user_id,
        candidate_name=candidate_name,
        plan_json=plan_json,
        status="pending",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_session(db: AsyncSession, session_id: str) -> InterviewSession | None:
    result = await db.execute(select(InterviewSession).where(InterviewSession.id == session_id))
    return result.scalar_one_or_none()


async def update_session_report(
    db: AsyncSession,
    session_id: str,
    report_json: str,
    status: str = "completed",
) -> None:
    session = await get_session(db, session_id)
    if session:
        session.report_json = report_json
        session.status = status
        session.completed_at = datetime.now(timezone.utc)
        await db.commit()


async def update_session_transcript(
    db: AsyncSession,
    session_id: str,
    transcript_json: str,
) -> None:
    session = await get_session(db, session_id)
    if session:
        session.transcript_json = transcript_json
        await db.commit()


async def list_user_sessions(
    db: AsyncSession,
    user_id: str,
    limit: int = 20,
    offset: int = 0,
) -> list[InterviewSession]:
    result = await db.execute(
        select(InterviewSession)
        .where(InterviewSession.user_id == user_id)
        .order_by(desc(InterviewSession.created_at))
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def list_all_sessions(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
) -> list[InterviewSession]:
    stmt = select(InterviewSession).order_by(desc(InterviewSession.created_at))
    if status:
        stmt = stmt.where(InterviewSession.status == status)
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_invites_for_recruiter(db: AsyncSession, recruiter_id: str) -> int:
    """All invites the user has ever created (any status) — the recruiter-side usage lock unit."""
    result = await db.execute(
        select(func.count()).select_from(InterviewInvite).where(InterviewInvite.recruiter_id == recruiter_id)
    )
    return int(result.scalar_one())


async def count_sessions_for_user(db: AsyncSession, user_id: str) -> int:
    """All interview sessions the user owns (any status) — the candidate-side
    usage lock unit, also applied to an unpicked role's recruiter pick."""
    result = await db.execute(
        select(func.count()).select_from(InterviewSession).where(InterviewSession.user_id == user_id)
    )
    return int(result.scalar_one())


async def set_user_role(db: AsyncSession, user_id: str, role: str) -> User | None | str:
    """Set the user's exclusive role (candidate/recruiter role picker). Admins are excluded upstream.

    Roles are mutually exclusive: this overwrites whatever string was there.
    Switching away from a role that has been *used* is refused — a recruiter
    with invites on record or a candidate with interview sessions keeps that
    role, so ownership history (invites, sessions, reports) always matches
    the role that created it. The candidate side of an *unpicked* role is
    locked against the recruiter pick too: the candidate flow allows taking
    practice interviews before the picker runs (``require_candidate`` passes
    ``""``), and those sessions must stay attached to a candidate-side
    account — picking ``candidate`` still works, since it matches the
    history. Picking the current role again is an idempotent no-op. Returns
    the updated user, the ``ROLE_LOCKED`` sentinel when the switch is
    refused, or None when the user does not exist.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return None
    if user.role == role:
        return user
    if user.role == "recruiter":
        used = await count_invites_for_recruiter(db, user.id)
    elif user.role == "candidate" or role == "recruiter":
        used = await count_sessions_for_user(db, user.id)
    else:
        # Unpicked role picking candidate: its sessions (if any) match the
        # role being picked, so nothing locks.
        used = 0
    if used:
        return ROLE_LOCKED
    user.role = role
    await db.commit()
    await db.refresh(user)
    return user


async def create_invite(
    db: AsyncSession,
    *,
    recruiter_id: str,
    title: str,
    context: str | None,
    questions: list[str],
    token: str,
    expires_in_hours: int | None = None,
) -> InterviewInvite:
    """Create a pending invite.

    ``expires_in_hours`` bounds how long the shareable link stays redeemable;
    the endpoint resolves the product default (24h) before calling, so None
    here means "no expiry" — which only invites created before the feature
    (and any caller omitting it) have.
    """
    import json

    expires_at = (
        datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)
        if expires_in_hours
        else None
    )
    invite = InterviewInvite(
        recruiter_id=recruiter_id,
        title=title,
        context=context,
        questions_json=json.dumps(questions),
        token=token,
        expires_at=expires_at,
        status="pending",
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite


async def get_invite_by_id(db: AsyncSession, invite_id: str) -> InterviewInvite | None:
    result = await db.execute(select(InterviewInvite).where(InterviewInvite.id == invite_id))
    return result.scalar_one_or_none()


async def get_invite_by_token(db: AsyncSession, token: str) -> InterviewInvite | None:
    result = await db.execute(select(InterviewInvite).where(InterviewInvite.token == token))
    return result.scalar_one_or_none()


async def get_invite_by_session(db: AsyncSession, session_id: str) -> InterviewInvite | None:
    result = await db.execute(select(InterviewInvite).where(InterviewInvite.session_id == session_id))
    return result.scalar_one_or_none()


async def list_invites_for_recruiter(
    db: AsyncSession,
    recruiter_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[InterviewInvite]:
    result = await db.execute(
        select(InterviewInvite)
        .where(InterviewInvite.recruiter_id == recruiter_id)
        .order_by(desc(InterviewInvite.created_at))
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def count_redeemed_invites_this_month(db: AsyncSession, recruiter_id: str) -> int:
    """Count invites redeemed in the current UTC calendar month (the quota unit)."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count())
        .select_from(InterviewInvite)
        .where(
            InterviewInvite.recruiter_id == recruiter_id,
            InterviewInvite.redeemed_at >= month_start,
        )
    )
    return int(result.scalar_one())


CLAIMED = "claimed"
ALREADY_CLAIMED = "already_claimed"
CANCELLED = "cancelled"
EXPIRED = "expired"
# set_user_role sentinel: the switch was refused because the current role has
# been used (invites or sessions on record). Same convention as the redeem
# statuses above — return a status, let the endpoint pick the HTTP response.
ROLE_LOCKED = "role_locked"
QUOTA_EXCEEDED = "quota_exceeded"


async def redeem_invite(
    db: AsyncSession,
    invite_id: str,
    *,
    candidate_user_id: str,
    session_id: str,
    recruiter_id: str | None = None,
    monthly_limit: int | None = None,
) -> str:
    """Atomically claim an invite for a candidate.

    The claim is a single conditional UPDATE, so two concurrent
    ``/invite/{token}/start`` requests cannot both create a session, both
    consume quota, or redeem a cancelled link — the loser sees zero rows
    affected and gets one of these failure reasons:

    - ``claimed`` — the UPDATE bound the invite; caller must create the
      session **and commit the same transaction** before the session ends
      (see ``create_session_for_invite``, which does both atomically).
    - ``already_claimed`` — another candidate (or an earlier request) holds it.
    - ``cancelled`` — the invite was cancelled (a cancel racing a redeem loses
      its own race here rather than leaving a cancelled link spendable).
    - ``expired`` — the link's ``expires_at`` passed before this start landed.
      Like cancellation, expiry is a guard *inside* the atomic claim, so a
      start racing the expiry moment loses rather than spending a dead link.
    - ``quota_exceeded`` — the recruiter's monthly limit was hit *inside* the
      atomic claim, so concurrent starts on different invites of one recruiter
      cannot overshoot the quota the way a pre-claim count check lets them.
    """
    now = datetime.now(timezone.utc)
    guards = [
        InterviewInvite.id == invite_id,
        InterviewInvite.candidate_user_id.is_(None),
        InterviewInvite.status == "pending",
        # Null expires_at (pre-feature and crud-level invites) never expires.
        or_(InterviewInvite.expires_at.is_(None), InterviewInvite.expires_at > now),
    ]
    if monthly_limit is not None:
        month_start = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        quota_count = (
            select(func.count())
            .select_from(InterviewInvite)
            .where(
                InterviewInvite.recruiter_id == recruiter_id,
                InterviewInvite.redeemed_at >= month_start,
            )
            .scalar_subquery()
        )
        guards.append(quota_count < monthly_limit)

    result = await db.execute(
        update(InterviewInvite)
        .where(*guards)
        .values(
            candidate_user_id=candidate_user_id,
            session_id=session_id,
            redeemed_at=now,
        )
    )
    # Committed by the caller together with the session INSERT
    # (create_session_for_invite) — splitting this into its own commit would
    # open a crash window with a claimed invite pointing at a session that
    # never lands, and the deferred FK would rightly reject it at commit.
    if result.rowcount == 1:
        return CLAIMED

    # Claim lost — re-read the committed row to tell the caller *why*, so the
    # endpoint can return an accurate error instead of a generic 403. No
    # rollback needed: this transaction's UPDATE matched zero rows, so it has
    # nothing of its own to discard (and a rollback here would wrongly discard
    # other uncommitted work on shared-connection setups).
    stored = await get_invite_by_id(db, invite_id)
    if stored is None or stored.candidate_user_id is not None:
        return ALREADY_CLAIMED
    if stored.status == "cancelled":
        return CANCELLED
    if stored.expires_at is not None and as_utc(stored.expires_at) <= now:
        return EXPIRED
    if monthly_limit is not None and recruiter_id is not None:
        used = await count_redeemed_invites_this_month(db, recruiter_id)
        if used >= monthly_limit:
            return QUOTA_EXCEEDED
    return ALREADY_CLAIMED


async def release_invite_claim(db: AsyncSession, invite_id: str) -> None:
    """Manually undo a claim, making the link redeemable again.

    The /invite/{token}/start path no longer calls this — a failed
    create_session_for_invite rolls the whole transaction back, claim
    included. Kept for tests and manual recovery.
    """
    await db.execute(
        update(InterviewInvite)
        .where(InterviewInvite.id == invite_id)
        .values(candidate_user_id=None, session_id=None, redeemed_at=None)
    )
    await db.commit()


async def complete_invite_by_session(db: AsyncSession, session_id: str) -> None:
    """Mark the invite linked to a session as completed (called when the report lands)."""
    invite = await get_invite_by_session(db, session_id)
    if invite:
        invite.status = "completed"
        invite.completed_at = datetime.now(timezone.utc)
        await db.commit()


# --- Profiles (one row per user, created lazily on first save) -----------------


async def get_candidate_profile(db: AsyncSession, user_id: str) -> CandidateProfile | None:
    result = await db.execute(
        select(CandidateProfile).where(CandidateProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _upsert_profile_row(db: AsyncSession, model_cls, user_id: str, **fields):
    """Create or update a 1:1 profile row, safe against concurrent creation.

    Two concurrent upserts (double-click Save, two tabs) can both see no row
    and both INSERT; the loser hits the unique ``user_id`` constraint and,
    like the OAuth callback race in ``get_or_create_user_by_oauth``, rolls
    back and re-selects the winning row instead of surfacing a 500.
    """
    result = await db.execute(select(model_cls).where(model_cls.user_id == user_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = model_cls(user_id=user_id, **fields)
        db.add(profile)
    else:
        for key, value in fields.items():
            setattr(profile, key, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        result = await db.execute(select(model_cls).where(model_cls.user_id == user_id))
        winner = result.scalar_one_or_none()
        if winner is None:
            # Not a creation race (e.g. a violated FK) — surface it.
            raise
        profile = winner
        for key, value in fields.items():
            setattr(profile, key, value)
        await db.commit()
    await db.refresh(profile)
    return profile


async def upsert_candidate_profile(
    db: AsyncSession, user_id: str, **fields
) -> CandidateProfile:
    """Create or update the candidate profile from validated schema fields.

    Callers pass already-serialized lists (skills_json=... etc.); this keeps
    the ORM layer ignorant of the JSON schema shape.
    """
    return await _upsert_profile_row(db, CandidateProfile, user_id, **fields)


async def get_recruiter_profile(db: AsyncSession, user_id: str) -> RecruiterProfile | None:
    result = await db.execute(
        select(RecruiterProfile).where(RecruiterProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def upsert_recruiter_profile(
    db: AsyncSession, user_id: str, **fields
) -> RecruiterProfile:
    return await _upsert_profile_row(db, RecruiterProfile, user_id, **fields)
