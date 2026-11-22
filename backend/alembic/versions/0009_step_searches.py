"""agent_run_steps.searches: búsquedas de literatura del paso (SPEC-034 / T22.7)

Revision ID: 0009_step_searches
Revises: 0008_library_search_logs
Create Date: 2026-11-22 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009_step_searches'
down_revision: Union[str, Sequence[str], None] = '0008_library_search_logs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # `server_default` para que las filas anteriores queden con «sin búsquedas» y no NULL.
    with op.batch_alter_table('agent_run_steps', schema=None) as batch_op:
        batch_op.add_column(sa.Column('searches', sa.JSON(), nullable=False, server_default='[]'))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('agent_run_steps', schema=None) as batch_op:
        batch_op.drop_column('searches')
