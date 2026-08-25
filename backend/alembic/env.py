from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context

# -------------------------------------------------------------------
# Make the backend directory importable
# -------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# -------------------------------------------------------------------
# Application imports
# -------------------------------------------------------------------
from app.core.config import get_settings
from app.db.session import Base
from app.models import User, Merchant, Product, MerchantPolicy  # noqa: F401


# -------------------------------------------------------------------
# Alembic configuration
# -------------------------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()

# SQLAlchemy metadata used by Alembic autogenerate
target_metadata = Base.metadata


# -------------------------------------------------------------------
# Normalize PostgreSQL URL to use psycopg v3
# -------------------------------------------------------------------
def get_database_url() -> str:
    """
    Convert a generic PostgreSQL SQLAlchemy URL to explicitly use
    the psycopg v3 driver.

    Example:
        postgresql://...
    becomes:
        postgresql+psycopg://...
    """
    database_url = settings.DATABASE_URL

    if database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    return database_url


# -------------------------------------------------------------------
# Offline migrations
# -------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations in offline mode."""

    database_url = get_database_url()

    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# -------------------------------------------------------------------
# Online migrations
# -------------------------------------------------------------------
def run_migrations_online() -> None:
    """Run migrations against the live database."""

    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    database_url = get_database_url()

    connectable = create_engine(
        database_url,
        poolclass=NullPool,
        pool_pre_ping=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


# -------------------------------------------------------------------
# Entry point
# -------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()