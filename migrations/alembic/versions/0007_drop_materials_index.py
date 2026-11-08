"""Drop materials.index: the queue is ordered by sort_key.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql.type_api import UserDefinedType


revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMN_NAME = "index"
CONSTRAINT_NAME = "uix_materials_index"


class _Serial(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw) -> str:  # noqa: ARG002
        return "serial"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "materials", type_="unique")
    # The owned materials_index_seq is dropped with the column.
    op.drop_column("materials", COLUMN_NAME)


def downgrade() -> None:
    op.add_column("materials", sa.Column(COLUMN_NAME, _Serial, nullable=False))
    op.execute(
        'UPDATE materials m SET "index" = ordered.position '
        "FROM (SELECT material_id, row_number() OVER (ORDER BY sort_key) AS position "
        "FROM materials) ordered "
        "WHERE ordered.material_id = m.material_id",
    )
    op.execute(
        "SELECT setval('materials_index_seq', coalesce(max(\"index\"), 1), "
        'max("index") IS NOT NULL) FROM materials',
    )
    op.create_unique_constraint(
        CONSTRAINT_NAME,
        "materials",
        [COLUMN_NAME],
        deferrable=True,
    )
