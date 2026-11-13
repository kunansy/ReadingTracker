import datetime

import pytest

from tests.unit.materials.helpers import NOW
from tracker.common import database


@pytest.fixture
def frozen_now(mocker) -> datetime.datetime:
    mocker.patch.object(database, "utcnow", return_value=NOW)
    return NOW
