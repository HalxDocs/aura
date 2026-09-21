"""Re-add the interview_invites.session_id FK as DEFERRABLE INITIALLY DEFERRED

d5e6f7a8b9c0 dropped interview_invites_session_id_fkey entirely: the forward
pointer is written by redeem_invite's atomic claim before the
interview_sessions row exists, so an immediately-checked FK rejected every
claim UPDATE. Dropping the constraint fixed redemption but gave up the
invariant that session_id always points at a real session — a crash between
the claim commit and the session INSERT leaves a dangling pointer that
get_invite_by_session trips over.

Postgres can have both: DEFERRABLE INITIALLY DEFERRED defers the check to
COMMIT, after the caller's session INSERT has landed in the same transaction,
so claim-then-create keeps working while a genuinely dangling pointer is
rejected at commit time. SQLite never enforced FKs, so the batch rebuild here
just mirrors the model's constraint (un-enforced there, as always).

Because ADD CONSTRAINT validates every existing row, any dangling session_id
written while the constraint was down is pruned first (the invite reverts to
unclaimed, so the link stays redeemable) — otherwise the ALTER would abort.

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-09-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, Sequence[str], None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Same name the model's ForeignKey derives and d5e6f7a8b9c0's downgrade used,
# so every path (migrations, create_all) builds identically-named constraints.
_CONSTRAINT = 'interview_invites_session_id_fkey'


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # Constraint ops are SQLite no-ops by design: SQLite never enforces
        # FKs in this app (no PRAGMA foreign_keys=ON), a reflected drop would
        # fail on the unnamed FK b8e2802f0d1b declared, and a batch
        # create_foreign_key would stack a second FK next to the reflected
        # one. Dev databases that create_all builds get the deferred FK
        # straight from the model; migration-built ones live without it —
        # inert either way.
        return

    # ADD CONSTRAINT validates existing rows even when the constraint is
    # deferred (deferrability applies to later DML only), so dangling
    # pointers accumulated while the FK was down must go first. Reverting the
    # whole claim (candidate, timestamp) keeps the link redeemable instead of
    # stranding it in a half-redeemed state.
    orphaned = bind.execute(
        sa.text(
            "UPDATE interview_invites i "
            "SET candidate_user_id = NULL, session_id = NULL, redeemed_at = NULL "
            "WHERE session_id IS NOT NULL "
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM interview_sessions s WHERE s.id = i.session_id"
            "  ) "
            "RETURNING i.id"
        )
    ).fetchall()
    if orphaned:
        print(
            f"pruned {len(orphaned)} dangling interview_invites.session_id "
            f"pointer(s): {[row[0] for row in orphaned]}"
        )

    op.create_foreign_key(
        _CONSTRAINT,
        'interview_invites',
        'interview_sessions',
        ['session_id'],
        ['id'],
        deferrable=True,
        initially='DEFERRED',
    )


def downgrade() -> None:
    # Restores the state d5e6f7a8b9c0 left behind: no FK, index intact.
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint(_CONSTRAINT, 'interview_invites', type_='foreignkey')
