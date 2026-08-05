"""Alembic migration environment — wired to EduSense models & settings."""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# ── Make sure `backend/` is on the path so imports work ─────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import get_settings  # noqa: E402
from app.db.session import Base           # noqa: E402
import app.models.models                  # noqa: E402, F401  ← registers all tables

# ── Alembic config object ────────────────────────────────────────────────────
config = context.config

# Use Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from EduSense settings so there's one source of truth
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

# Supply the metadata for autogenerate (reads all mapped tables)
target_metadata = Base.metadata


# ── Offline mode (no live DB connection) ─────────────────────────────────────
def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to the database."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode (live connection) ─────────────────────────────────────────────
def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
