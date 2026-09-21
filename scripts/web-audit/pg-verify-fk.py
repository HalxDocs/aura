"""Postgres verification for the invite FK fix (run inside the backend
container, against a scratch database so prod data is untouched):

1. create scratch DB, run `alembic upgrade head` on it
2. assert interview_invites_session_id_fkey exists and is DEFERRABLE
   INITIALLY DEFERRED (checked at COMMIT, so the claim UPDATE passes)
3. run the exact redeem ordering: claim (writes session_id) -> create
   session -> single commit
4. prove the deferred check bites: a dangling pointer is rejected at commit
5. downgrade -1 (FK drops), assert gone; upgrade again (FK returns deferred)

Usage:
  docker exec -i aura-backend sh -c 'cd /app && uv run python -' < pg-verify-fk.py
Environment: reads DATABASE_URL from the container env; DB name is rewritten
to a scratch `aura_fk_verify_<ts>` database (same server, same credentials).
"""
import asyncio
import os
import re
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine


def scratch_url() -> tuple[str, str, str]:
    raw = os.environ["DATABASE_URL"]
    m = re.match(r"postgresql\+asyncpg://([^:]+):([^@]+)@([^/]+)/([^?]+)", raw)
    if not m:
        raise SystemExit(f"cannot parse DATABASE_URL: {raw}")
    user, pw, host, db = m.groups()
    scratch = os.environ.get("SCRATCH_DB", "aura_fk_verify_1")
    sync_url = f"postgresql://{user}:{pw}@{host}/postgres"
    return f"postgresql+asyncpg://{user}:{pw}@{host}/{scratch}", scratch, sync_url


ASYNC_URL, SCRATCH_DB, PG_ADMIN_URL = scratch_url()
os.environ["DATABASE_URL"] = ASYNC_URL

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402


def run_alembic(target: str) -> None:
    cfg = Config("/app/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", ASYNC_URL.replace("+asyncpg", ""))
    command.upgrade(cfg, target)


def run_downgrade(target: str) -> None:
    cfg = Config("/app/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", ASYNC_URL.replace("+asyncpg", ""))
    command.downgrade(cfg, target)


async def fks_on_invites() -> list[dict]:
    eng = create_async_engine(ASYNC_URL)
    try:
        async with eng.connect() as conn:
            def _sync(c):
                return sa.inspect(c).get_foreign_keys("interview_invites")
            return await conn.run_sync(_sync)
    finally:
        await eng.dispose()


async def indexes_on_invites() -> set:
    eng = create_async_engine(ASYNC_URL)
    try:
        async with eng.connect() as conn:
            def _sync(c):
                return {ix["name"] for ix in sa.inspect(c).get_indexes("interview_invites")}
            return await conn.run_sync(_sync)
    finally:
        await eng.dispose()


def session_fks(fks: list[dict]) -> list[dict]:
    return [fk for fk in fks if "session_id" in fk["constrained_columns"]]


async def claim_then_create() -> None:
    from db.database import async_session
    from db.crud import create_invite, create_session_for_invite, redeem_invite, CLAIMED
    from db.models import User
    from models.schemas import InterviewPlan

    async with async_session() as db:
        user = User(email=f"verify-{uuid.uuid4().hex[:8]}@fk.test", name="Verify", provider="email", provider_id=uuid.uuid4().hex)
        db.add(user)
        await db.flush()
        invite = await create_invite(
            db, recruiter_id=user.id, title="verify", context=None,
            questions=["Q1?", "Q2?"], token=uuid.uuid4().hex, expires_in_hours=24,
        )
        sid = str(uuid.uuid4())
        reason = await redeem_invite(
            db, invite.id, candidate_user_id=user.id, session_id=sid,
            recruiter_id=user.id, monthly_limit=20,
        )
        assert reason == CLAIMED, reason
        s = await create_session_for_invite(
            db, session_id=sid, user_id=user.id, candidate_name="Verify",
            plan_json=InterviewPlan(
                candidate_name="Verify", extracted_skills=[],
                question_bank=["Q1?", "Q2?"], job_description=None,
            ).model_dump_json(),
        )
        print(f"  claim + session committed as ONE transaction: invite -> session {s.id}")


async def dangling_pointer_is_rejected() -> None:
    """The whole point of the deferrable FK: binding session_id to a row that
    never exists must fail at COMMIT (the claim rolls back), not pass."""
    from db.database import async_session
    from db.crud import create_invite, redeem_invite, CLAIMED
    from db.models import User

    async with async_session() as db:
        user = User(email=f"verify-{uuid.uuid4().hex[:8]}@fk.test", name="Verify", provider="email", provider_id=uuid.uuid4().hex)
        db.add(user)
        await db.flush()
        invite = await create_invite(
            db, recruiter_id=user.id, title="verify dangling", context=None,
            questions=["Q1?"], token=uuid.uuid4().hex, expires_in_hours=24,
        )
        reason = await redeem_invite(
            db, invite.id, candidate_user_id=user.id, session_id=str(uuid.uuid4()),
            recruiter_id=user.id, monthly_limit=20,
        )
        assert reason == CLAIMED, reason
        try:
            await db.commit()  # no session row was created — FK must reject
        except Exception as exc:
            await db.rollback()
            assert "interview_invites_session_id_fkey" in str(exc) or "foreign key" in str(exc).lower(), exc
            print(f"  dangling pointer rejected at commit: {type(exc).__name__}")
            return
        raise AssertionError("deferred FK did not reject a dangling session_id at commit")


async def main() -> None:
    # Scratch DB is created/owned externally (see README note in the audit
    # scripts): the app user lacks CREATEDB, so the caller runs
    #   CREATE DATABASE <scratch> OWNER <app-user>
    # via docker exec psql before invoking this script.
    print(f"scratch db: {SCRATCH_DB}")

    await asyncio.to_thread(run_alembic, "head")
    fks = session_fks(await fks_on_invites())
    print(f"after upgrade head: session_id FKs = {fks}")
    assert len(fks) == 1, "expected exactly one session_id FK after upgrade"
    opts = fks[0].get("options") or {}
    assert opts.get("deferrable") is True and (opts.get("initially") or "").upper() == "DEFERRED", (
        f"FK is not DEFERRABLE INITIALLY DEFERRED: {fks[0]}"
    )
    print("after upgrade head: FK is DEFERRABLE INITIALLY DEFERRED")

    indexes = await indexes_on_invites()
    assert "ix_interview_invites_session_id" in indexes, (
        f"lookup index missing after upgrade; indexes = {sorted(indexes)}"
    )
    print("after upgrade head: ix_interview_invites_session_id present")

    await claim_then_create()
    await dangling_pointer_is_rejected()

    await asyncio.to_thread(run_downgrade, "d5e6f7a8b9c0")
    fks = session_fks(await fks_on_invites())
    print(f"after downgrade -1: session_id FKs = {[fk['name'] for fk in fks]}")
    assert not fks, "downgrade did not drop the deferred FK"

    indexes = await indexes_on_invites()
    assert "ix_interview_invites_session_id" not in indexes, (
        f"downgrade did not drop the lookup index; indexes = {sorted(indexes)}"
    )
    print("after downgrade -1: lookup index dropped with the migration")

    await asyncio.to_thread(run_alembic, "head")
    fks = session_fks(await fks_on_invites())
    assert len(fks) == 1 and (fks[0].get("options") or {}).get("deferrable") is True
    print("re-upgrade: deferred FK restored — upgrade/downgrade cycle verified")
    print("ALL POSTGRES CHECKS PASSED")


asyncio.run(main())
