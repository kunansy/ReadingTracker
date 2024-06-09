import pytest
import sqlalchemy.sql as sa

from tracker.common import database
from tracker.models import models


async def test_session():
    stmt = sa.text("SELECT 1 + 1")

    async with database.session() as ses:
        assert await ses.scalar(stmt) == 2


async def test_session_error():
    stmt = sa.text("SELECT 1 / 0")

    with pytest.raises(database.DatabaseException) as e:
        async with database.session() as ses:
            await ses.scalar(stmt)

    assert "division by zero" in str(e.value)


async def test_transaction():
    select_stmt = sa.select(models.Materials.c.authors).where(
        models.Materials.c.authors.ilike("%Гёте%")
    )

    update_stmt = models.Materials.update().where(
        models.Materials.c.authors.ilike("%Гёте%")
    )

    async with database.transaction() as trans:
        materials = (await trans.scalars(select_stmt)).all()
        assert materials

        replace_value = materials[0].replace("ё", "е")
        update_stmt = update_stmt.values(authors=replace_value)

        await trans.execute(update_stmt)

        updated_materials = (await trans.scalars(select_stmt)).all()
        assert len(updated_materials) == 0

        await trans.rollback()

    async with database.transaction() as trans:
        new_materials = (await trans.scalars(select_stmt)).all()

        assert new_materials == materials


async def test_readiness():
    assert await database.readiness()
