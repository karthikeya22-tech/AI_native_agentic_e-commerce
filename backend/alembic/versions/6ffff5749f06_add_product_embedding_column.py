"""add product embedding column

Revision ID: 6ffff5749f06
Revises: 8e1605c350c2
Create Date: 2026-08-25 22:41:27.435696

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = '6ffff5749f06'
down_revision: Union[str, None] = '8e1605c350c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("embedding", Vector(384), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "embedding")
