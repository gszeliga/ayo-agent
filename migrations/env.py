from alembic import context
from sqlalchemy import create_engine, pool

from ayo_copilot.config import DatabaseSettings


def _database_url() -> str:
    # Tests pass the URL through `Config.attributes`; otherwise use DATABASE_URL.
    url = context.config.attributes.get("database_url")
    if url is None:
        url = DatabaseSettings().database_url.get_secret_value()
    # Alembic runs on SQLAlchemy; point it at psycopg 3 rather than psycopg2.
    scheme, _, rest = url.partition("://")
    if scheme in ("postgres", "postgresql"):
        url = f"postgresql+psycopg://{rest}"
    return url


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline (--sql) migrations are not supported.")
run_migrations_online()
