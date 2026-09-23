"""Exclusive roles: fold is_recruiter into role

Dual roles let one account be candidate and recruiter at once (the one-way
``is_recruiter`` grant plus a ``role`` string that was only the last-picked
mode). Roles are now mutually exclusive: ``users.role`` is the single source
of truth, and the flag column goes away — keeping it would leave two
answers to "is this user a recruiter?".

The flag's one-way grant was presented to users as permanent, so anyone
holding it keeps the recruiter side: ``role = 'recruiter'`` wins over
whatever mode string was last picked (an admin's ``role`` is never touched —
admin promotion is orthogonal and must survive). Re-running the whole
6f34e3e1eca3 backfill in reverse is impossible from the flag alone; this
row-level winner-takes-all is the resolution the product chose.

Flag-holding admins (``role = 'admin' AND is_recruiter = TRUE``) deliberately
resolve to plain ``admin``: they keep recruiter *access* through the admin
role (require_recruiter admits admins), but the fact they once picked the
recruiter role is not recorded anywhere and cannot be recovered after the
column drops. If admins are ever allowed to switch roles or are demoted,
that preference will already be gone.

Revision ID: b2c3d4e5f6a7
Revises: e7f8a9b0c1d2
Create Date: 2026-09-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Resolve dual-role rows to a single role, then drop the flag column."""
    # The fixup must run while the column still exists. TRUE literal (not 1):
    # Postgres has no integer -> boolean assignment cast; SQLite accepts TRUE
    # since 3.23 (same reasoning as 6f34e3e1eca3's backfill).
    op.execute(
        "UPDATE users SET role = 'recruiter' "
        "WHERE is_recruiter = TRUE AND role NOT IN ('admin', 'recruiter')"
    )
    # batch_alter_table rebuilds the table on SQLite (which cannot DROP
    # COLUMN in old versions) and issues a plain ALTER TABLE DROP COLUMN on
    # Postgres.
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('is_recruiter')


def downgrade() -> None:
    """Restore the flag from role, mirroring 6f34e3e1eca3's forward step."""
    op.add_column(
        'users',
        sa.Column('is_recruiter', sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute("UPDATE users SET is_recruiter = TRUE WHERE role = 'recruiter'")
