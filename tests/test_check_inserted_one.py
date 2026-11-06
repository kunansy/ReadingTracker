import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from tracker.cards import db as cards_db
from tracker.common import database


def test_one_inserted_row_passes():
    database.check_inserted_one(SimpleNamespace(rowcount=1), entity="Card")


@pytest.mark.parametrize("rowcount", [0, 2])
def test_other_row_counts_raise(rowcount):
    with pytest.raises(database.DatabaseException, match=f"affected {rowcount} rows"):
        database.check_inserted_one(SimpleNamespace(rowcount=rowcount), entity="Card")


async def test_insert_that_affects_no_rows_raises(mocker):
    class _Session:
        async def execute(self, _stmt):
            return SimpleNamespace(rowcount=0)

    @asynccontextmanager
    async def _session(**_kwargs):
        yield _Session()

    mocker.patch("tracker.common.database.session", _session)

    with pytest.raises(database.DatabaseException, match="Card insert affected 0 rows"):
        await cards_db.add_card(
            material_id=uuid.uuid4(),
            note_id=uuid.uuid4(),
            question="question",
        )
