"""Add tenant image-count and image-cost reservations.

Revision ID: 9c0e3f6a4b12
Revises: 8b9d2e5f3a01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c0e3f6a4b12"
down_revision: str | None = "8b9d2e5f3a01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "entitlements",
        sa.Column(
            "max_images_per_deck",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "entitlements",
        sa.Column(
            "monthly_image_limit",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
    )
    op.add_column(
        "entitlements",
        sa.Column(
            "monthly_image_cost_limit_microunits",
            sa.BigInteger(),
            nullable=False,
            server_default="3000000",
        ),
    )
    op.create_check_constraint(
        op.f("ck_entitlements_images_bounded"),
        "entitlements",
        "max_images_per_deck BETWEEN 0 AND 32",
    )
    op.create_check_constraint(
        op.f("ck_entitlements_monthly_images_nonnegative"),
        "entitlements",
        "monthly_image_limit >= 0",
    )
    op.create_check_constraint(
        op.f("ck_entitlements_monthly_image_cost_nonnegative"),
        "entitlements",
        "monthly_image_cost_limit_microunits >= 0",
    )

    for name, column_type in (
        ("reserved_images", sa.Integer()),
        ("settled_images", sa.Integer()),
        ("reserved_cost_microunits", sa.BigInteger()),
        ("settled_cost_microunits", sa.BigInteger()),
    ):
        op.add_column(
            "usage_reservations",
            sa.Column(name, column_type, nullable=False, server_default="0"),
        )
        op.create_check_constraint(
            op.f(f"ck_usage_reservations_{name}_nonnegative"),
            "usage_reservations",
            f"{name} >= 0",
        )


def downgrade() -> None:
    for name in (
        "settled_cost_microunits",
        "reserved_cost_microunits",
        "settled_images",
        "reserved_images",
    ):
        op.drop_constraint(
            op.f(f"ck_usage_reservations_{name}_nonnegative"),
            "usage_reservations",
            type_="check",
        )
        op.drop_column("usage_reservations", name)

    op.drop_constraint(
        op.f("ck_entitlements_monthly_image_cost_nonnegative"),
        "entitlements",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_entitlements_monthly_images_nonnegative"),
        "entitlements",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_entitlements_images_bounded"),
        "entitlements",
        type_="check",
    )
    op.drop_column("entitlements", "monthly_image_cost_limit_microunits")
    op.drop_column("entitlements", "monthly_image_limit")
    op.drop_column("entitlements", "max_images_per_deck")
