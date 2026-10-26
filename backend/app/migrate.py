"""Provision the application database role, apply migrations, and grant least-privilege access.

Runs once per deployment with the migration account; API replicas only use the application role.
"""

import asyncio
import logging
from pathlib import Path

import asyncpg
from alembic import command
from alembic.config import Config

from app.config import MigrationSettings
from app.observability import configure_logging

logger = logging.getLogger("app.migrate")

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"

ROLE_ATTRIBUTES = "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L"
GRANT_TEMPLATES = (
    "REVOKE ALL ON DATABASE %I FROM PUBLIC",
    "REVOKE CREATE ON SCHEMA public FROM PUBLIC",
    "GRANT CONNECT ON DATABASE %I TO %I",
    "GRANT USAGE ON SCHEMA public TO %I",
    "GRANT SELECT, INSERT, UPDATE ON TABLE public.users TO %I",
    "GRANT SELECT, INSERT ON TABLE public.products TO %I",
)


async def _connect(settings: MigrationSettings) -> asyncpg.Connection:
    return await asyncpg.connect(
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.migration_db_user,
        password=settings.migration_db_password.get_secret_value(),
    )


async def _quoted(connection: asyncpg.Connection, template: str, *args: str) -> str:
    """Let PostgreSQL quote identifiers and literals for statements that cannot take bind parameters."""
    placeholders = ", ".join(f"${index}::text" for index in range(1, len(args) + 1))
    return await connection.fetchval(f"SELECT format('{template}', {placeholders})", *args)


async def ensure_app_role(settings: MigrationSettings) -> None:
    connection = await _connect(settings)
    try:
        exists = await connection.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", settings.db_user)
        verb = "ALTER ROLE %I WITH" if exists else "CREATE ROLE %I"
        statement = await _quoted(
            connection,
            f"{verb} {ROLE_ATTRIBUTES}",
            settings.db_user,
            settings.db_password.get_secret_value(),
        )
        await connection.execute(statement)
    finally:
        await connection.close()


async def grant_app_privileges(settings: MigrationSettings) -> None:
    connection = await _connect(settings)
    try:
        async with connection.transaction():
            for template in GRANT_TEMPLATES:
                args: list[str] = []
                if "DATABASE %I" in template:
                    args.append(settings.db_name)
                if template.endswith("TO %I"):
                    args.append(settings.db_user)
                statement = await _quoted(connection, template, *args) if args else template
                await connection.execute(statement)
    finally:
        await connection.close()


def run_migrations() -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "migrations"))
    command.upgrade(config, "head")


def main() -> None:
    configure_logging("INFO")
    settings = MigrationSettings()
    asyncio.run(ensure_app_role(settings))
    logger.info("application role %s is provisioned", settings.db_user)
    run_migrations()
    logger.info("migrations applied")
    asyncio.run(grant_app_privileges(settings))
    logger.info("privileges granted to %s", settings.db_user)


if __name__ == "__main__":
    main()
