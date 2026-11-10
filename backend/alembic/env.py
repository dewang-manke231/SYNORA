import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool, create_engine

from alembic import context

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.core.database import Base, engine as app_engine, normalize_db_url
import app.models  # Import all models to register with Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url():
    """
    Get database URL. If a specific valid URL was passed to config via test, use it.
    Otherwise, default to settings.DATABASE_URL (which has sqlite:///./synora.db default).
    Normalizes postgres:// to postgresql+psycopg2://
    """
    ini_url = config.get_main_option("sqlalchemy.url")
    if ini_url and ini_url != "driver://user:pass@localhost/dbname":
        return normalize_db_url(ini_url)
    return normalize_db_url(settings.DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True if url.startswith("sqlite") else False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    url = get_url()
    is_sqlite = url.startswith("sqlite")

    if url == normalize_db_url(settings.DATABASE_URL):
        connectable = app_engine
    else:
        connect_args = {"check_same_thread": False} if is_sqlite else {"sslmode": "require", "connect_timeout": 15}
        connectable = create_engine(url, connect_args=connect_args)

    with connectable.connect() as connection:
        if not is_sqlite:
            # Enable pgvector extension before running migrations on Supabase PostgreSQL
            try:
                from sqlalchemy import text
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                connection.commit()
            except Exception:
                pass

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=is_sqlite,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
