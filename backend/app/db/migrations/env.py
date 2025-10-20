"""Alembic environment configuration with schema support."""
import asyncio
import os
from logging.config import fileConfig
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# Import settings and models
from app.core.config import settings
from app.db.base import Base
from app.db.models import (
    Campaign, Topic, Persona, Question, Run, RunItem, Response, Export, Delivery, File
)
from app.db.compat import Event, Result

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add model's MetaData for 'autogenerate' support
target_metadata = Base.metadata

# Get DB schema from environment or settings
DB_SCHEMA = os.getenv("DB_SCHEMA", settings.db_schema)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL generation).

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=DB_SCHEMA,
        include_schemas=True,
    )

    with context.begin_transaction():
        # Create schema if not exists (local mode only)
        if settings.db_apply_migrations:
            context.execute(text(f"CREATE SCHEMA IF NOT EXISTS {DB_SCHEMA}"))
        
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations in online mode."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=DB_SCHEMA,
        include_schemas=True,
    )

    with context.begin_transaction():
        # Create schema if not exists (local mode only)
        if settings.db_apply_migrations:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {DB_SCHEMA}"))
        
        # Set search path
        connection.execute(text(f"SET search_path TO {DB_SCHEMA}, public"))
        
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in online mode with async engine."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.database_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()


