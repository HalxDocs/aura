import os
import hmac
from fastapi import Request, HTTPException
import jwt
from db.crud import get_user_by_id
from db.database import async_session
from db.models import User
from utils.config import JWT_SECRET

WORKER_API_KEY = os.getenv("WORKER_API_KEY", "")


class _WorkerUser:
    """Sentinel object returned when the caller authenticates with WORKER_API_KEY."""
    id = "worker"
    role = "worker"


async def get_current_user(request: Request) -> User | _WorkerUser:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(401, "Not authenticated")

    token = auth_header.removeprefix("Bearer ").strip()

    # Constant-time comparison avoids leaking key length/content via timing.
    if WORKER_API_KEY and hmac.compare_digest(token, WORKER_API_KEY):
        return _WorkerUser()

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")

    # A forged token can legally decode yet lack 'sub' — reject it as
    # invalid instead of letting the KeyError surface as a 500.
    if not isinstance(payload.get("sub"), str):
        raise HTTPException(401, "Invalid token")

    async with async_session() as db:
        user = await get_user_by_id(db, payload["sub"])

    if not user:
        raise HTTPException(401, "User not found")
    return user


def require_admin(user) -> None:
    if getattr(user, "role", None) != "admin":
        raise HTTPException(403, "Admin access required")


def require_recruiter(user) -> None:
    """Recruiter gate.

    Roles are exclusive, so ``role`` is the whole story: a user is a
    recruiter, or an admin (admins keep recruiter access to operate the
    app). Lives next to ``require_admin`` so both the invites endpoints and
    the profiles router can share it without a circular import through
    ``api.main``.
    """
    if getattr(user, "role", None) in ("admin", "recruiter"):
        return
    raise HTTPException(403, "Recruiter access required")


def require_candidate(user) -> None:
    """Candidate gate, the mirror of require_recruiter.

    Recruiters are rejected now that roles are exclusive. An unpicked role
    ("") still passes: the candidate flow allows uploading a resume before
    the role picker ever runs, and forcing a pick first would break that
    flow. Admins pass to keep operating every surface as today.
    """
    if getattr(user, "role", None) in ("", "candidate", "admin"):
        return
    raise HTTPException(403, "Candidate access required")
