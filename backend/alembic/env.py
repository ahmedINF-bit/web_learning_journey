from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.core.config import settings
from app.core.database import Base

# Import all models so SQLAlchemy registers them
# in Base.metadata.
from app.models.user import User
from app.models.chat import Chat, Message
from app.models.folder import Folder
from app.models.note import Note
from app.models.file import File
from app.models.file_chunk import FileChunk
from app.models.subscription import Subscription
from app.models.settings import UserSettings
from app.models.user_memory import UserMemory
from app.models.password_reset_token import PasswordResetToken
from app.models.billing_order import BillingOrder

# ============================================================
# Alembic Config
# ============================================================

config = context.config


# ============================================================
# Logging
# ============================================================

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# ============================================================
# SQLAlchemy Metadata
# ============================================================

target_metadata = Base.metadata


# ============================================================
# Database URL
# ============================================================

config.set_main_option(
    "sqlalchemy.url",
    settings.DATABASE_URL.replace("%", "%%"),
)


# ============================================================
# Offline migrations
# ============================================================

def run_migrations_offline() -> None:
    """
    Run migrations without creating a database connection.
    """

    url = config.get_main_option(
        "sqlalchemy.url"
    )

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named"
        },
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ============================================================
# Online migrations
# ============================================================

def do_run_migrations(
    connection: Connection,
) -> None:
    """
    Configure and run migrations using an active connection.
    """

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Create an async engine and run migrations.
    """

    configuration = config.get_section(
        config.config_ini_section,
        {}
    )

    configuration[
        "sqlalchemy.url"
    ] = settings.DATABASE_URL

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(
            do_run_migrations
        )

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Run migrations in online mode.
    """

    import asyncio

    asyncio.run(
        run_async_migrations()
    )


# ============================================================
# Entry Point
# ============================================================

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()