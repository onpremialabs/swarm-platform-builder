"""library_documents: declaración «aportado por el autor» (SPEC-034 / T22.13 / ADR-0013)

Revision ID: 0011_author_provided_sources
Revises: 0010_citation_links
Create Date: 2026-11-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011_author_provided_sources'
down_revision: Union[str, Sequence[str], None] = '0010_citation_links'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('library_documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'author_provided', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column('author_provided_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('author_provided_by', sa.UUID(), nullable=True))
        batch_op.create_foreign_key(
            'fk_library_documents_author_provided_by', 'users',
            ['author_provided_by'], ['id'], ondelete='SET NULL')
        batch_op.create_check_constraint(
            'ck_library_documents_author_provided_no_doi',
            'author_provided = false OR (doi IS NULL AND author_provided_at IS NOT NULL)')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('library_documents', schema=None) as batch_op:
        batch_op.drop_constraint('ck_library_documents_author_provided_no_doi', type_='check')
        batch_op.drop_constraint('fk_library_documents_author_provided_by', type_='foreignkey')
        batch_op.drop_column('author_provided_by')
        batch_op.drop_column('author_provided_at')
        batch_op.drop_column('author_provided')
