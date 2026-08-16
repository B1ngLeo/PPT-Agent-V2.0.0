"""Programmatic Alembic entry point used by services, CI, and local development."""

from __future__ import annotations

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config

from instant_ppt_domain.config import DomainSettings


def alembic_config(database_url: str | None = None) -> Config:
    package_root = Path(__file__).resolve().parent
    config = Config(str(package_root / "alembic.ini"))
    config.set_main_option("script_location", str(package_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url or DomainSettings.from_env().database_url)
    return config


def upgrade(database_url: str | None = None, revision: str = "head") -> None:
    command.upgrade(alembic_config(database_url), revision)


def downgrade(database_url: str | None = None, revision: str = "base") -> None:
    command.downgrade(alembic_config(database_url), revision)


def current(database_url: str | None = None) -> None:
    command.current(alembic_config(database_url), verbose=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the Instant PPT PostgreSQL schema")
    parser.add_argument("action", choices=("upgrade", "downgrade", "current"))
    parser.add_argument("revision", nargs="?", default=None)
    parser.add_argument("--database-url", default=None)
    arguments = parser.parse_args()
    if arguments.action == "upgrade":
        upgrade(arguments.database_url, arguments.revision or "head")
    elif arguments.action == "downgrade":
        downgrade(arguments.database_url, arguments.revision or "base")
    else:
        current(arguments.database_url)


if __name__ == "__main__":
    main()
