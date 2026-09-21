"""Drop the FK on interview_invites.session_id + add its lookup index

`session_id` is a forward pointer written by redeem_invite's atomic claim
*before* the interview_sessions row exists. Postgres enforced the FK on that
UPDATE (interview_invites_session_id_fkey), making every /invite/{token}/start
a 500; SQLite never enforced FKs, which is why the feature shipped green.
The column stays exactly as it is — only the constraint goes.

The migration also builds the index the model now declares
(``index=True`` on session_id): ``get_invite_by_session`` looks invites up
by that column on every recruiter access path, and ``create_all`` skips
existing tables, so on Postgres this migration is the only thing that can
create the index.

Revision ID: d5e6f7a8b9c0
Revises: 6f34e3e1eca3
Create Date: 2026-09-20

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = '6f34e3e1eca3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Same name SQLAlchemy derives from the model's index=True, so a fresh
# database built by this migration and one built by create_all (SQLite dev)
# carry identical index names.
_INDEX = 'ix_interview_invites_session_id'


def upgrade() -> None:
    # Postgres: the constraint exists in the live catalog — drop it by name.
    # SQLite: batch mode rebuilds the table from the *current models metadata*,
    # which no longer declares the FK (models.py), so there is nothing to
    # drop and a named drop_constraint would fail with "No such constraint".
    if op.get_bind().dialect.name != "sqlite":
        with op.batch_alter_table('interview_invites') as batch:
            batch.drop_constraint('interview_invites_session_id_fkey', type_='foreignkey')
    # Runs on both dialects: on SQLite create_all may have built it already,
    # but Alembic-built databases (and :memory: test DBs) have not.
    op.create_index(_INDEX, 'interview_invites', ['session_id'])


def downgrade() -> None:
    # ADD CONSTRAINT validates existing rows: any dangling session_id written
    # while the FK was down (e.g. a crash between the claim commit and the
    # session INSERT — exactly the window this migration opened) would abort
    # the ALTER. Revert those whole claims so the link stays redeemable.
    if op.get_bind().dialect.name != "sqlite":
        import sqlalchemy as sa

        orphaned = op.get_bind().execute(
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
    op.drop_index(_INDEX, table_name='interview_invites')
    if op.get_bind().dialect.name != "sqlite":
        with op.batch_alter_table('interview_invites') as batch:
            batch.create_foreign_key(
                'interview_invites_session_id_fkey',
                'interview_sessions',
                ['session_id'],
                ['id'],
            )
