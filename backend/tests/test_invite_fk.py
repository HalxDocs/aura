"""Regression tests for the interview_invites.session_id FK lifecycle.

The invite-claim UPDATE (redeem_invite) writes session_id *before* the
interview_sessions row exists — the column is a forward pointer. Postgres
enforced the FK immediately on that UPDATE, so every /invite/{token}/start
returned 500 once production moved to Postgres (SQLite never enforced FKs,
which is how this shipped). Migration d5e6f7a8b9c0 dropped the constraint;
e7f8a9b0c1d2 re-adds it as DEFERRABLE INITIALLY DEFERRED, so the check moves
to COMMIT — claim and session INSERT now share one transaction and the
invariant "session_id points at a real session" holds again. These tests pin
the deferred schema and the single-transaction claim-then-create ordering.

On the default in-memory SQLite suite the deferrability is vacuous (SQLite
never enforces FKs); the meaningful run is `uv run pytest` with DATABASE_URL
pointed at a real Postgres database, where an immediate FK would fail the
claim UPDATE and a missing constraint would let dangling pointers commit.
"""
import uuid

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

from db.database import async_session, engine
from db.crud import (
    CLAIMED,
    create_invite,
    create_session_for_invite,
    get_invite_by_id,
    redeem_invite,
)
from db.models import User


@pytest.mark.asyncio
async def test_invites_session_id_fk_is_deferred():
    """session_id must carry exactly one FK to interview_sessions, and it must
    be DEFERRABLE INITIALLY DEFERRED — an immediate FK rejects the claim
    UPDATE (the original production outage), a missing FK lets dangling
    pointers commit (what the FK-drop accidentally allowed)."""

    def _get_fks(sync_conn):
        insp = sa_inspect(sync_conn)
        return insp.get_foreign_keys("interview_invites")

    async with engine.connect() as conn:
        fks = await conn.run_sync(_get_fks)
    session_fks = [fk for fk in fks if "session_id" in (fk.get("constrained_columns") or [])]
    assert len(session_fks) == 1, f"expected one session_id FK, found: {session_fks}"
    fk = session_fks[0]
    assert fk.get("referred_table") == "interview_sessions", fk
    assert fk.get("options", {}).get("deferrable") is True, fk
    assert (fk.get("options", {}).get("initially") or "").upper() == "DEFERRED", fk

    def _get_indexes(sync_conn):
        insp = sa_inspect(sync_conn)
        return {ix["name"] for ix in insp.get_indexes("interview_invites")}

    async with engine.connect() as conn:
        indexes = await conn.run_sync(_get_indexes)
    assert "ix_interview_invites_session_id" in indexes, (
        "session_id must carry the lookup index (get_invite_by_session runs on "
        "every recruiter access path); on Postgres only migration d5e6f7a8b9c0 "
        "creates it because create_all skips existing tables"
    )


@pytest.mark.asyncio
async def test_claim_and_session_commit_in_one_transaction():
    """The production ordering: claim (writes session_id) then create the
    session row, committed together in ONE transaction by
    create_session_for_invite. Under the deferred FK this commits on Postgres;
    with an immediate FK the claim UPDATE itself would fail."""
    async with async_session() as db:
        user = User(
            email=f"fk-test-{uuid.uuid4().hex[:8]}@example.com",
            name="FK Test",
            provider="email",
            provider_id=uuid.uuid4().hex,
        )
        db.add(user)
        await db.flush()

        invite = await create_invite(
            db,
            recruiter_id=user.id,
            title="FK ordering test",
            context=None,
            questions=["Q1?", "Q2?"],
            token=uuid.uuid4().hex,
            expires_in_hours=24,
        )

        session_id = str(uuid.uuid4())
        reason = await redeem_invite(
            db,
            invite.id,
            candidate_user_id=user.id,
            session_id=session_id,
            recruiter_id=user.id,
            monthly_limit=20,
        )
        assert reason == CLAIMED

        # Still uncommitted here — the invite row is only bound inside this
        # transaction until create_session_for_invite commits claim + session.
        session = await create_session_for_invite(
            db,
            session_id=session_id,
            user_id=user.id,
            candidate_name="FK Test",
            plan_json=(await _minimal_plan_json()),
        )

        await db.refresh(invite)
        assert invite.session_id == session.id
        assert invite.status == "pending"

        # A second session sees the committed pair — claim and session landed
        # atomically, so no crash window can leave a dangling pointer.
        async with async_session() as db2:
            stored = await get_invite_by_id(db2, invite.id)
            assert stored.session_id == session.id
            linked = await db2.execute(
                text("SELECT COUNT(*) FROM interview_sessions WHERE id = :sid"),
                {"sid": session.id},
            )
            assert linked.scalar_one() == 1


async def _minimal_plan_json() -> str:
    from models.schemas import InterviewPlan

    return InterviewPlan(
        candidate_name="FK Test",
        extracted_skills=[],
        question_bank=["Q1?", "Q2?"],
        job_description=None,
    ).model_dump_json()
