import asyncio
import time
from collections.abc import AsyncGenerator, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import aiomysql
import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy.sql as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.core.container import DockerContainer

from tracker.common import database, manticoresearch, settings
from tracker.models import models


REPO_ROOT = Path(__file__).resolve().parents[2]
INTEGRATION_DIR = Path(__file__).resolve().parent

POSTGRES_IMAGE = "postgres:18-alpine"
POSTGRES_PORT = 5432
POSTGRES_USER = "tracker"
POSTGRES_PASSWORD = "tracker"
POSTGRES_DB = "tracker_test"

MANTICORE_IMAGE = "kunansy/tracker_search:6.3.2"
MANTICORE_MYSQL_PORT = 9306

STARTUP_TIMEOUT_SECONDS = 60
STARTUP_POLL_SECONDS = 0.3


def pytest_collection_modifyitems(items):
    for item in items:
        if INTEGRATION_DIR in Path(item.path).parents:
            item.add_marker(pytest.mark.integration)


def _wait_until_ready(probe, *, what: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            # a worker thread: asyncio.run() here would reset the event loop pytest-asyncio owns
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(asyncio.run, probe()).result()
        except Exception as e:
            last_error = e
            time.sleep(STARTUP_POLL_SECONDS)
        else:
            return
    raise RuntimeError(f"{what} did not become ready: {last_error!r}")


@pytest.fixture(scope="session")
def postgres_uri() -> Iterator[str]:
    container = (
        DockerContainer(POSTGRES_IMAGE)
        .with_env("POSTGRES_USER", POSTGRES_USER)
        .with_env("POSTGRES_PASSWORD", POSTGRES_PASSWORD)
        .with_env("POSTGRES_DB", POSTGRES_DB)
        .with_exposed_ports(POSTGRES_PORT)
    )
    container.start()
    try:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(POSTGRES_PORT))

        async def probe() -> None:
            conn = await asyncpg.connect(
                host=host,
                port=port,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                database=POSTGRES_DB,
                timeout=2,
            )
            await conn.close()

        _wait_until_ready(probe, what="PostgreSQL container")
        yield settings.DSN_TEMPLATE.format(
            username=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=host,
            port=port,
            db_name=POSTGRES_DB,
        )
    finally:
        container.stop()


# package scope: the application is pointed back at the pinned settings before unit tests run
@pytest_asyncio.fixture(scope="package", loop_scope="session", autouse=True)
async def db_engine(postgres_uri: str) -> AsyncGenerator[AsyncEngine]:
    """Point the application at the throwaway database and migrate it to head."""
    engine = create_async_engine(
        postgres_uri,
        isolation_level=settings.DB_ISOLATION_LEVEL,
        connect_args={
            "timeout": settings.DB_TIMEOUT,
            "statement_cache_size": 50,
            "max_cached_statement_lifetime": 0,
        },
        json_deserializer=database.orjson.loads,
        json_serializer=database._json_serializer,
    )

    patcher = pytest.MonkeyPatch()
    patcher.chdir(REPO_ROOT)
    patcher.setattr(settings, "DB_URI", postgres_uri)
    patcher.setattr(database, "engine", engine)
    try:
        await database.create_db()
        yield engine
    finally:
        await engine.dispose()
        patcher.undo()


TABLES = ", ".join(table.name for table in models.metadata.sorted_tables)


async def truncate_all(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(sa.text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
async def clean_database(db_engine: AsyncEngine) -> AsyncGenerator[None]:
    """Every test starts on empty tables and reads back only what it wrote."""
    yield
    await truncate_all(db_engine)


@pytest.fixture(scope="session")
def manticore_address() -> Iterator[tuple[str, int]]:
    container = (
        DockerContainer(MANTICORE_IMAGE)
        # no MCL=1: it downloads the columnar library on every start, the notes table does not use it
        .with_env("TELEMETRY", "0")
        .with_exposed_ports(MANTICORE_MYSQL_PORT)
    )
    container.start()
    try:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(MANTICORE_MYSQL_PORT))

        async def probe() -> None:
            conn = await aiomysql.connect(host=host, port=port, connect_timeout=2)
            conn.close()

        _wait_until_ready(probe, what="Manticore container")
        yield host, port
    finally:
        container.stop()


@pytest.fixture
async def manticore(manticore_address: tuple[str, int], monkeypatch) -> AsyncGenerator[None]:
    """A real Manticore with an empty `notes` table."""
    host, port = manticore_address
    monkeypatch.setattr(settings, "MANTICORE_MYSQL_HOST", host)
    monkeypatch.setattr(settings, "MANTICORE_MYSQL_PORT", port)

    await manticoresearch._drop_table()
    await manticoresearch._create_table()
    yield
    await manticoresearch._drop_table()
