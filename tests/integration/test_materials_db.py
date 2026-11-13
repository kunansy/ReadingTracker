import datetime
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy.sql as sa

from tests.integration import factories, helpers_materials as h
from tracker.common import database, sort_keys
from tracker.common.pagination import Order, PageParams
from tracker.materials import db
from tracker.models import enums, models
from tracker.reading_log import db as logs_db


BOOK = enums.MaterialTypesEnum.book
ARTICLE = enums.MaterialTypesEnum.article
LECTURE = enums.MaterialTypesEnum.lecture
FIXED_ID = "018e4a6c-0000-7000-8000-00000000abcd"


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> h.Clock:
    return h.freeze_clock(monkeypatch)


@pytest.fixture
def sql_today(clock: h.Clock) -> datetime.date:
    """The date the repeat queue SQL compares with: the frozen UTC date of the app."""
    return clock.utc_today()


def seconds_after_now(seconds: int) -> datetime.datetime:
    return h.NOW + datetime.timedelta(seconds=seconds)


def expected_material(material_id: UUID, *, added_at: datetime.datetime, **values: Any):
    return db.Material(
        **{
            "material_id": material_id,
            "title": f"Material at {added_at.isoformat()}",
            "authors": "Author",
            "pages": 100,
            "material_type": BOOK,
            "tags": None,
            "link": None,
            "added_at": added_at,
            "is_outlined": False,
            "started_at": None,
            "completed_at": None,
        }
        | values,
    )


# insert_material


async def test_insert_material_stores_every_column(mocker):
    mocker.patch.object(models, "generate_id", return_value=FIXED_ID)

    material_id = await db.insert_material(
        title="Clean Code",
        authors="Robert Martin",
        pages=464,
        material_type=BOOK,
        tags="programming, craft",
        link="https://example.com/clean-code",
    )

    assert material_id == UUID(FIXED_ID)
    assert await factories.fetch_row(models.Materials, material_id) == {
        "material_id": UUID(FIXED_ID),
        "title": "Clean Code",
        "authors": "Robert Martin",
        "pages": 464,
        "material_type": "book",
        "tags": "programming, craft",
        "link": "https://example.com/clean-code",
        "added_at": h.NOW,
        "is_outlined": False,
        "started_at": None,
        "completed_at": None,
        "sort_key": f"2024-03-15T12:30:45.123456$${FIXED_ID}",
    }


async def test_insert_material_sort_key_matches_the_generator(clock):
    material_id = await h.queued(clock)

    row = await factories.fetch_row(models.Materials, material_id)

    assert row["sort_key"] == sort_keys.material_sort_key(
        added_at=row["added_at"],
        material_id=material_id,
    )


async def test_insert_material_stores_none_tags_and_link(clock):
    material_id = await h.queued(clock, tags=None, link=None)

    row = await factories.fetch_row(models.Materials, material_id)

    assert row["tags"] is None
    assert row["link"] is None


@pytest.mark.parametrize("material_type", list(enums.MaterialTypesEnum))
async def test_insert_material_stores_every_material_type(clock, material_type):
    material_id = await h.queued(clock, material_type=material_type)

    material = await db.get_material_api(material_id=material_id)

    assert material.material_type is material_type


async def test_insert_material_rejects_duplicate_title_and_type(clock):
    await h.queued(clock, title="Same title", material_type=BOOK)

    with pytest.raises(database.AlreadyExistsException):
        await h.queued(clock, title="Same title", material_type=BOOK)

    assert await factories.count_rows(models.Materials) == 1


async def test_insert_material_allows_same_title_with_another_type(clock):
    book_id = await h.queued(clock, title="Same title", material_type=BOOK)
    article_id = await h.queued(clock, title="Same title", material_type=ARTICLE)

    assert await db.get_titles() == {book_id: "Same title", article_id: "Same title"}


async def test_insert_material_stores_cyrillic_values_at_max_length(clock):
    title = "Ж" * 256
    authors = "Ё" * 256
    tags = "я" * 256
    link = "https://пример.рф/" + "ы" * (2048 - 18)

    material_id = await h.queued(
        clock,
        title=title,
        authors=authors,
        tags=tags,
        link=link,
        pages=2**31 - 1,
    )

    row = await factories.fetch_row(models.Materials, material_id)
    assert (row["title"], row["authors"], row["tags"], row["link"], row["pages"]) == (
        title,
        authors,
        tags,
        link,
        2**31 - 1,
    )


@pytest.mark.parametrize(
    "values",
    [
        {"title": "t" * 257},
        {"authors": "a" * 257},
        {"tags": "g" * 257},
        {"link": "l" * 2049},
        {"pages": 2**31},
    ],
    ids=["title", "authors", "tags", "link", "pages"],
)
async def test_insert_material_rejects_a_value_one_past_the_limit(clock, values):
    with pytest.raises(database.DatabaseException):
        await h.queued(clock, **values)

    assert await factories.count_rows(models.Materials) == 0


# get_material, get_material_api, get_materials


async def test_get_material_returns_the_inserted_material(clock):
    material_id = await h.queued(
        clock,
        title="Чистый код",
        authors="Роберт Мартин",
        pages=464,
        material_type=LECTURE,
        tags="код, практика",
        link="https://example.com",
    )
    expected = expected_material(
        material_id,
        added_at=seconds_after_now(1),
        title="Чистый код",
        authors="Роберт Мартин",
        pages=464,
        material_type=LECTURE,
        tags="код, практика",
        link="https://example.com",
    )

    assert await db.get_material(material_id=material_id) == expected
    assert await db.get_material_api(material_id=material_id) == expected


async def test_get_material_strips_whitespace_stored_around_strings(clock):
    material_id = await h.queued(clock, title="  Padded  ", authors=" A ", tags=" t ")

    material = await db.get_material_api(material_id=material_id)
    row = await factories.fetch_row(models.Materials, material_id)

    assert (material.title, material.authors, material.tags) == ("Padded", "A", "t")
    assert row["title"] == "  Padded  "


async def test_get_material_returns_none_when_missing(clock):
    await h.queued(clock)

    assert await db.get_material(material_id=h.MISSING_ID) is None


async def test_get_material_api_raises_not_found_when_missing(clock):
    await h.queued(clock)

    with pytest.raises(database.NotFoundException, match=str(h.MISSING_ID)):
        await db.get_material_api(material_id=h.MISSING_ID)


async def test_get_materials_returns_materials_in_every_state(clock):
    queued_id = await h.queued(clock)
    reading_id = await h.reading(clock, started=h.day(5))
    completed_id = await h.completed(clock, started=h.day(5), finished=h.day(2))

    materials = await db.get_materials()

    assert sorted(materials, key=lambda m: m.added_at) == [
        expected_material(queued_id, added_at=seconds_after_now(1)),
        expected_material(
            reading_id,
            added_at=seconds_after_now(2),
            started_at=h.midnight(h.day(5)),
        ),
        expected_material(
            completed_id,
            added_at=seconds_after_now(3),
            started_at=h.midnight(h.day(5)),
            completed_at=h.midnight(h.day(2)),
        ),
    ]


async def test_listings_are_empty_on_an_empty_database():
    assert await db.get_materials() == []
    assert await db._get_free_materials() == []
    assert await db.get_reading_materials() == []
    assert await db._get_completed_materials() == []
    assert await db.get_last_material_started() is None
    assert await db.get_material_tags() == set()
    assert await db.get_authors() == ()
    assert await db.get_titles() == {}
    assert await db.get_read_material_titles() == {}
    assert await db.get_reading_material_titles() == {}
    assert await db.list_material_titles_with_cards() == {}
    assert await db.is_reading(material_id=h.MISSING_ID) is False


async def test_aggregates_are_empty_on_an_empty_database():
    assert await db.get_means() == {}
    assert await db.get_repeats_analytics() == {}
    assert await db.reading_statistics() == []
    assert await db._get_materials_statistics([]) == []
    assert await db._end_of_reading() == h.TODAY


# _get_free_materials, get_reading_materials, _get_completed_materials


async def test_free_materials_are_only_queued_ones_in_insertion_order(clock):
    first = await h.queued(clock)
    await h.reading(clock, started=h.day(5))
    await h.completed(clock, started=h.day(5), finished=h.day(2))
    second = await h.queued(clock)

    materials = await db._get_free_materials()

    assert materials == [
        expected_material(first, added_at=seconds_after_now(1)),
        expected_material(second, added_at=seconds_after_now(4)),
    ]


async def test_started_material_leaves_the_queue(clock):
    material_id = await h.queued(clock)

    await db.start_material(material_id=material_id)

    assert await db._get_free_materials() == []


async def test_reading_materials_are_only_started_and_not_completed(clock):
    await h.queued(clock)
    reading_id = await h.reading(clock, started=h.day(5))
    await h.completed(clock, started=h.day(5), finished=h.day(2))

    assert await db.get_reading_materials() == [
        expected_material(
            reading_id,
            added_at=seconds_after_now(2),
            started_at=h.midnight(h.day(5)),
        ),
    ]


async def test_reading_materials_go_from_the_most_recently_read(clock):
    read_long_ago = await h.reading(clock, started=h.day(9))
    read_yesterday = await h.reading(clock, started=h.day(9))
    never_read = await h.reading(clock, started=h.day(9))
    await logs_db.insert_log_record(material_id=read_long_ago, count=1, date=h.day(5))
    await logs_db.insert_log_record(material_id=read_long_ago, count=1, date=h.day(8))
    await logs_db.insert_log_record(material_id=read_yesterday, count=1, date=h.day(1))

    materials = await db.get_reading_materials()

    # DESC puts NULLs first in PostgreSQL: a material without logs leads the list
    assert [m.material_id for m in materials] == [
        never_read,
        read_yesterday,
        read_long_ago,
    ]


async def test_completed_materials_go_from_the_earliest_completion(clock):
    late = await h.completed(clock, started=h.day(9), finished=h.day(1))
    early = await h.completed(clock, started=h.day(9), finished=h.day(7))
    await h.reading(clock, started=h.day(9))
    await h.queued(clock)

    materials = await db._get_completed_materials()

    assert materials == [
        expected_material(
            early,
            added_at=seconds_after_now(2),
            started_at=h.midnight(h.day(9)),
            completed_at=h.midnight(h.day(7)),
        ),
        expected_material(
            late,
            added_at=seconds_after_now(1),
            started_at=h.midnight(h.day(9)),
            completed_at=h.midnight(h.day(1)),
        ),
    ]


@pytest.fixture
async def completed_set(clock: h.Clock) -> dict[str, UUID]:
    """Completed materials differing in type, outline flag and tags; completed in dict order."""
    ids = {
        "book_plain": await h.completed(
            clock,
            started=h.day(20),
            finished=h.day(9),
            tags="history, science",
        ),
        "book_outlined": await h.completed(
            clock,
            started=h.day(20),
            finished=h.day(8),
            tags="history",
        ),
        "article_plain": await h.completed(
            clock,
            started=h.day(20),
            finished=h.day(7),
            material_type=ARTICLE,
            tags="science",
        ),
        "article_outlined": await h.completed(
            clock,
            started=h.day(20),
            finished=h.day(6),
            material_type=ARTICLE,
            tags=None,
        ),
    }
    await db.outline_material(material_id=ids["book_outlined"])
    await db.outline_material(material_id=ids["article_outlined"])
    await h.reading(clock, started=h.day(20), tags="history, science")
    return ids


COMPLETED_FILTERS = [
    pytest.param(
        {},
        ["book_plain", "book_outlined", "article_plain", "article_outlined"],
        id="no filters",
    ),
    pytest.param(
        {"material_type": BOOK}, ["book_plain", "book_outlined"], id="type book"
    ),
    pytest.param(
        {"material_type": ARTICLE},
        ["article_plain", "article_outlined"],
        id="type article",
    ),
    pytest.param({"material_type": LECTURE}, [], id="type without materials"),
    pytest.param(
        {"is_outlined": True},
        ["book_outlined", "article_outlined"],
        id="outlined",
    ),
    pytest.param(
        {"is_outlined": False}, ["book_plain", "article_plain"], id="not outlined"
    ),
    pytest.param(
        {"is_outlined": None},
        ["book_plain", "book_outlined", "article_plain", "article_outlined"],
        id="outlined not set",
    ),
    pytest.param({"tags": {"history"}}, ["book_plain", "book_outlined"], id="one tag"),
    pytest.param(
        {"tags": {"science"}}, ["book_plain", "article_plain"], id="another tag"
    ),
    pytest.param(
        {"tags": {"science", "history"}}, ["book_plain"], id="all tags required"
    ),
    pytest.param({"tags": {"missing"}}, [], id="unknown tag"),
    pytest.param({"tags": {"hist"}}, [], id="tag prefix does not match"),
    pytest.param(
        {"tags": set()},
        ["book_plain", "book_outlined", "article_plain", "article_outlined"],
        id="empty tags",
    ),
    pytest.param(
        {"material_type": BOOK, "is_outlined": True, "tags": {"history"}},
        ["book_outlined"],
        id="all filters",
    ),
    pytest.param(
        {"material_type": ARTICLE, "is_outlined": True, "tags": {"science"}},
        [],
        id="all filters without a match",
    ),
]


@pytest.mark.parametrize(("filters", "expected"), COMPLETED_FILTERS)
async def test_completed_materials_filters(completed_set, filters, expected):
    materials = await db._get_completed_materials(**filters)

    assert [m.material_id for m in materials] == [
        completed_set[name] for name in expected
    ]


@pytest.mark.parametrize(("filters", "expected"), COMPLETED_FILTERS)
async def test_completed_statistics_page_filters(completed_set, filters, expected):
    page = await db.completed_statistics_page(
        **filters,
        params=PageParams(order=Order.ASC),
    )

    assert [stat.material.material_id for stat in page.items] == [
        completed_set[name] for name in expected
    ]
    assert page.total_count == len(expected)
    assert page.next_token is None


@pytest.mark.parametrize(
    "stored_tags",
    ["History,Science", "history,science", "History, Science"],
    ids=["no space and capitals", "no space", "capitals"],
)
async def test_every_listed_material_tag_finds_its_material(clock, stored_tags):
    material_id = await h.completed(
        clock,
        started=h.day(5),
        finished=h.day(1),
        tags=stored_tags,
    )

    listed_tags = await db.get_material_tags()
    found = {
        tag: [m.material_id for m in await db._get_completed_materials(tags={tag})]
        for tag in listed_tags
    }

    assert found == {"history": [material_id], "science": [material_id]}


# update_material


async def test_update_material_changes_only_the_given_columns(clock):
    material_id = await h.reading(clock, started=h.day(3), tags="old", link="https://old")
    before = await factories.fetch_row(models.Materials, material_id)

    await db.update_material(
        material_id=material_id,
        title="Новое название",
        authors="Новый автор",
        pages=7,
        material_type=ARTICLE,
        tags=None,
        link=None,
    )

    assert await factories.fetch_row(models.Materials, material_id) == before | {
        "title": "Новое название",
        "authors": "Новый автор",
        "pages": 7,
        "material_type": "article",
        "tags": None,
        "link": None,
    }


async def test_update_material_does_not_touch_other_materials(clock):
    material_id = await h.queued(clock, title="Target")
    other_id = await h.queued(clock, title="Other")
    other_before = await factories.fetch_row(models.Materials, other_id)

    await db.update_material(
        material_id=material_id,
        title="Target updated",
        authors="A",
        pages=1,
        material_type=BOOK,
        tags="t",
        link="l",
    )

    assert await factories.fetch_row(models.Materials, other_id) == other_before


async def test_update_material_raises_not_found_for_a_missing_id(clock):
    material_id = await h.queued(clock, title="Untouched")

    with pytest.raises(database.NotFoundException, match=str(h.MISSING_ID)):
        await db.update_material(
            material_id=h.MISSING_ID,
            title="New",
            authors="A",
            pages=1,
            material_type=BOOK,
            tags=None,
            link=None,
        )

    assert (await db.get_material_api(material_id=material_id)).title == "Untouched"


async def test_update_material_rejects_a_title_taken_by_the_same_type(clock):
    await h.queued(clock, title="Taken")
    material_id = await h.queued(clock, title="Free")

    with pytest.raises(database.AlreadyExistsException):
        await db.update_material(
            material_id=material_id,
            title="Taken",
            authors="A",
            pages=1,
            material_type=BOOK,
            tags=None,
            link=None,
        )

    assert (await db.get_material_api(material_id=material_id)).title == "Free"


# start_material, complete_material, outline_material, repeat_material


async def test_start_material_stores_the_given_date_at_midnight(clock):
    material_id = await h.queued(clock)

    await db.start_material(material_id=material_id, started_at=h.day(3))

    row = await factories.fetch_row(models.Materials, material_id)
    assert row["started_at"] == datetime.datetime(2024, 3, 12, 0, 0)
    assert row["completed_at"] is None


async def test_start_material_defaults_to_the_current_date(clock):
    material_id = await h.queued(clock)

    await db.start_material(material_id=material_id)

    row = await factories.fetch_row(models.Materials, material_id)
    assert row["started_at"] == datetime.datetime(2024, 3, 15, 0, 0)


async def test_start_material_twice_raises_conflict_and_keeps_the_first_date(clock):
    material_id = await h.reading(clock, started=h.day(3))

    with pytest.raises(database.ConflictException, match="is not in the queue"):
        await db.start_material(material_id=material_id, started_at=h.day(1))

    row = await factories.fetch_row(models.Materials, material_id)
    assert row["started_at"] == h.midnight(h.day(3))


async def test_start_completed_material_raises_conflict(clock):
    material_id = await h.completed(clock, started=h.day(3), finished=h.day(2))

    with pytest.raises(database.ConflictException, match="is not in the queue"):
        await db.start_material(material_id=material_id, started_at=h.day(1))

    row = await factories.fetch_row(models.Materials, material_id)
    assert row["started_at"] == h.midnight(h.day(3))


async def test_start_missing_material_raises_conflict(clock):
    await h.queued(clock)

    with pytest.raises(database.ConflictException, match="is not in the queue"):
        await db.start_material(material_id=h.MISSING_ID)


async def test_start_material_starts_only_the_given_material(clock):
    material_id = await h.queued(clock)
    other_id = await h.queued(clock)

    await db.start_material(material_id=material_id)

    assert (await factories.fetch_row(models.Materials, other_id))["started_at"] is None


async def test_complete_material_stores_the_given_date_at_midnight(clock):
    material_id = await h.reading(clock, started=h.day(3))

    await db.complete_material(material_id=material_id, completed_at=h.day(1))

    row = await factories.fetch_row(models.Materials, material_id)
    assert row["completed_at"] == datetime.datetime(2024, 3, 14, 0, 0)
    assert row["started_at"] == h.midnight(h.day(3))


async def test_complete_material_defaults_to_the_current_date(clock):
    material_id = await h.reading(clock, started=h.day(3))

    await db.complete_material(material_id=material_id)

    row = await factories.fetch_row(models.Materials, material_id)
    assert row["completed_at"] == datetime.datetime(2024, 3, 15, 0, 0)


async def test_complete_queued_material_raises_conflict(clock):
    material_id = await h.queued(clock)

    with pytest.raises(database.ConflictException, match="is not being read"):
        await db.complete_material(material_id=material_id)

    row = await factories.fetch_row(models.Materials, material_id)
    assert row["completed_at"] is None


async def test_complete_material_twice_raises_conflict_and_keeps_the_first_date(clock):
    material_id = await h.completed(clock, started=h.day(3), finished=h.day(2))

    with pytest.raises(database.ConflictException, match="is not being read"):
        await db.complete_material(material_id=material_id, completed_at=h.day(1))

    row = await factories.fetch_row(models.Materials, material_id)
    assert row["completed_at"] == h.midnight(h.day(2))


async def test_complete_missing_material_raises_conflict(clock):
    await h.reading(clock, started=h.day(3))

    with pytest.raises(database.ConflictException, match="is not being read"):
        await db.complete_material(material_id=h.MISSING_ID)


async def test_complete_material_accepts_a_date_before_the_start_current_behaviour(clock):
    material_id = await h.reading(clock, started=h.day(3))

    await db.complete_material(material_id=material_id, completed_at=h.day(9))

    row = await factories.fetch_row(models.Materials, material_id)
    assert row["completed_at"] == h.midnight(h.day(9))


@pytest.mark.parametrize("state", ["queued", "reading", "completed"])
async def test_outline_material_sets_the_flag_in_any_state(clock, state):
    material_id = await h.queued(clock)
    if state != "queued":
        await db.start_material(material_id=material_id, started_at=h.day(3))
    if state == "completed":
        await db.complete_material(material_id=material_id, completed_at=h.day(1))
    before = await factories.fetch_row(models.Materials, material_id)

    await db.outline_material(material_id=material_id)

    assert before["is_outlined"] is False
    assert await factories.fetch_row(models.Materials, material_id) == before | {
        "is_outlined": True,
    }


async def test_outline_material_twice_keeps_the_flag(clock):
    material_id = await h.queued(clock)

    await db.outline_material(material_id=material_id)
    await db.outline_material(material_id=material_id)

    assert (await db.get_material_api(material_id=material_id)).is_outlined is True


async def test_outline_missing_material_raises_not_found(clock):
    material_id = await h.queued(clock)

    with pytest.raises(database.NotFoundException, match=str(h.MISSING_ID)):
        await db.outline_material(material_id=h.MISSING_ID)

    assert (await db.get_material_api(material_id=material_id)).is_outlined is False


async def test_repeat_material_inserts_a_repeat_at_the_current_time(clock):
    material_id = await h.completed(clock, started=h.day(3), finished=h.day(2))

    await db.repeat_material(material_id=material_id)

    [repeat] = await h.fetch_all(models.Repeats)
    assert repeat["material_id"] == material_id
    assert repeat["repeated_at"] == clock.now
    assert isinstance(repeat["repeat_id"], UUID)


async def test_repeat_material_twice_inserts_two_repeats(clock):
    material_id = await h.completed(clock, started=h.day(3), finished=h.day(2))

    await db.repeat_material(material_id=material_id)
    clock.tick(60)
    await db.repeat_material(material_id=material_id)

    repeats = await h.fetch_all(models.Repeats, models.Repeats.c.repeated_at)
    assert [(r["material_id"], r["repeated_at"]) for r in repeats] == [
        (material_id, clock.now - datetime.timedelta(seconds=60)),
        (material_id, clock.now),
    ]


async def test_repeat_material_accepts_an_unknown_material_current_behaviour():
    await db.repeat_material(material_id=h.MISSING_ID)

    [repeat] = await h.fetch_all(models.Repeats)
    assert repeat["material_id"] == h.MISSING_ID


# get_last_material_started


async def test_last_material_started_ignores_queued_and_completed(clock):
    await h.queued(clock)
    await h.completed(clock, started=h.day(1), finished=h.day(0))

    assert await db.get_last_material_started() is None


async def test_last_material_started_is_the_latest_start_among_unread_materials(clock):
    await h.reading(clock, started=h.day(5))
    latest = await h.reading(clock, started=h.day(2))
    await h.reading(clock, started=h.day(8))

    assert await db.get_last_material_started() == latest


async def test_last_material_started_does_not_prefer_a_material_without_logs(clock):
    logged = await h.reading(clock, started=h.day(2))
    await h.reading(clock, started=h.day(8))
    await logs_db.insert_log_record(material_id=logged, count=1, date=h.day(1))

    assert await db.get_last_material_started() == logged


async def test_last_material_started_is_the_latest_start_whatever_the_logs_are(clock):
    started_long_ago = await h.reading(clock, started=h.day(10))
    started_recently = await h.reading(clock, started=h.day(5))
    await logs_db.insert_log_record(material_id=started_long_ago, count=1, date=h.day(1))
    await logs_db.insert_log_record(material_id=started_recently, count=1, date=h.day(3))

    assert await db.get_last_material_started() == started_recently


# tags, authors, titles, is_reading


async def test_material_tags_are_split_stripped_lowered_and_merged(clock):
    await h.queued(clock, tags="History, Science")
    await h.queued(clock, tags="history,  ФИЗИКА ,math")
    await h.queued(clock, tags=None)
    await h.reading(clock, started=h.day(1), tags="single")

    assert await db.get_material_tags() == {
        "history",
        "science",
        "физика",
        "math",
        "single",
    }


async def test_material_tags_skip_an_empty_tag(clock):
    await h.queued(clock, tags="trailing,")
    await h.queued(clock, tags="")

    assert await db.get_material_tags() == {"trailing"}


async def test_authors_are_distinct_and_not_split(clock):
    await h.queued(clock, authors="Knuth")
    await h.queued(clock, authors="Knuth")
    await h.queued(clock, authors="Кнут, Грэхем")

    authors = await db.get_authors()

    assert isinstance(authors, tuple)
    assert sorted(authors) == ["Knuth", "Кнут, Грэхем"]


async def test_titles_by_material_state(clock):
    queued_id = await h.queued(clock, title="Queued")
    reading_id = await h.reading(clock, started=h.day(3), title="Reading")
    completed_id = await h.completed(
        clock,
        started=h.day(3),
        finished=h.day(1),
        title="Completed",
    )

    assert await db.get_titles() == {
        queued_id: "Queued",
        reading_id: "Reading",
        completed_id: "Completed",
    }
    assert await db.get_read_material_titles() == {
        reading_id: "Reading",
        completed_id: "Completed",
    }
    assert await db.get_reading_material_titles() == {reading_id: "Reading"}


async def test_material_titles_with_cards_lists_each_material_once(clock):
    with_cards = await h.queued(clock, title="With cards")
    await h.queued(clock, title="Without cards")
    note_id = await factories.insert_note(material_id=with_cards)
    await factories.insert_card(material_id=with_cards, note_id=note_id)
    await factories.insert_card(material_id=with_cards, note_id=note_id)
    await factories.insert_card(material_id=h.MISSING_ID, note_id=note_id)

    assert await db.list_material_titles_with_cards() == {with_cards: "With cards"}


async def test_is_reading_by_material_state(clock):
    queued_id = await h.queued(clock)
    reading_id = await h.reading(clock, started=h.day(3))
    completed_id = await h.completed(clock, started=h.day(3), finished=h.day(1))

    assert await db.is_reading(material_id=queued_id) is False
    assert await db.is_reading(material_id=reading_id) is True
    assert await db.is_reading(material_id=completed_id) is False
    assert await db.is_reading(material_id=h.MISSING_ID) is False


# is_completion_request_valid


async def read_material(clock: h.Clock, *, pages: int = 100, read: int = 100) -> UUID:
    material_id = await h.reading(clock, started=h.day(5), pages=pages)
    if read:
        await logs_db.insert_log_record(
            material_id=material_id, count=read, date=h.day(4)
        )
    return material_id


@pytest.mark.parametrize(
    "completed_at",
    [None, h.TODAY, h.day(4), h.day(5)],
    ids=["default date", "today", "past", "the start date"],
)
async def test_completion_request_is_valid_for_a_fully_read_material(clock, completed_at):
    material_id = await read_material(clock)

    result = await db.is_completion_request_valid(
        material_id=material_id,
        completed_at=completed_at,
    )

    assert result is None


async def test_completion_request_is_valid_when_pages_are_read_over_several_days(clock):
    material_id = await read_material(clock, pages=100, read=60)
    await logs_db.insert_log_record(material_id=material_id, count=40, date=h.day(3))

    assert await db.is_completion_request_valid(material_id=material_id) is None


async def test_completion_request_for_a_missing_material_raises_not_found(clock):
    await read_material(clock)

    with pytest.raises(database.NotFoundException, match=str(h.MISSING_ID)):
        await db.is_completion_request_valid(material_id=h.MISSING_ID)


async def test_completion_request_rejects_a_queued_material(clock):
    material_id = await h.queued(clock)

    with pytest.raises(ValueError, match=r"^Material is not started$"):
        await db.is_completion_request_valid(material_id=material_id)


async def test_completion_request_rejects_a_completed_material(clock):
    material_id = await read_material(clock)
    await db.complete_material(material_id=material_id, completed_at=h.day(1))

    with pytest.raises(ValueError, match=r"^Material is already completed$"):
        await db.is_completion_request_valid(material_id=material_id)


async def test_completion_request_rejects_a_future_date(clock):
    material_id = await read_material(clock)

    with pytest.raises(ValueError, match=r"^Completion date must not be in the future$"):
        await db.is_completion_request_valid(
            material_id=material_id, completed_at=h.day(-1)
        )


async def test_completion_request_rejects_a_date_before_the_start(clock):
    material_id = await read_material(clock)

    with pytest.raises(
        ValueError,
        match=r"^Completion date must not be before the start date$",
    ):
        await db.is_completion_request_valid(
            material_id=material_id, completed_at=h.day(6)
        )


async def test_completion_request_rejects_a_material_without_logs(clock):
    material_id = await read_material(clock, read=0)

    with pytest.raises(ValueError, match=r"^Reading logs not found$"):
        await db.is_completion_request_valid(material_id=material_id)


@pytest.mark.parametrize("read", [99, 101], ids=["one page unread", "one page too many"])
async def test_completion_request_rejects_a_wrong_pages_sum(clock, read):
    material_id = await read_material(clock, pages=100, read=read)

    with pytest.raises(ValueError, match=r"^Invalid pages count, something is unread$"):
        await db.is_completion_request_valid(material_id=material_id)


async def test_completion_request_counts_only_logs_of_the_material(clock):
    material_id = await read_material(clock, pages=100, read=60)
    other_id = await h.reading(clock, started=h.day(5))
    await logs_db.insert_log_record(material_id=other_id, count=40, date=h.day(3))

    with pytest.raises(ValueError, match=r"^Invalid pages count, something is unread$"):
        await db.is_completion_request_valid(material_id=material_id)


# statistics of materials


def book_material(history: h.ReadingHistory) -> db.Material:
    return expected_material(
        history.book,
        added_at=seconds_after_now(1),
        title="Book",
        pages=h.BOOK_PAGES,
        started_at=h.midnight(h.day(10)),
        completed_at=h.midnight(h.day(7)),
    )


def article_material(history: h.ReadingHistory) -> db.Material:
    return expected_material(
        history.article,
        added_at=seconds_after_now(2),
        title="Article",
        pages=h.ARTICLE_PAGES,
        material_type=ARTICLE,
        started_at=h.midnight(h.day(9)),
    )


def book_statistics(history: h.ReadingHistory, *, notes_count: int = 0):
    return db.MaterialStatistics(
        material=book_material(history),
        started_at=h.day(10),
        completed_at=h.day(7),
        total_reading_duration="4 days",
        duration=3,
        lost_time=0,
        total=102,
        min_record=database.MinMax(
            log_id=history.book_last,
            material_id=history.book,
            date=h.day(7),
            count=22,
        ),
        max_record=database.MinMax(
            log_id=history.book_max,
            material_id=history.book,
            date=h.day(9),
            count=50,
        ),
        mean=34,
        notes_count=notes_count,
        remaining_pages=None,
        remaining_days=None,
        would_be_completed=None,
    )


def article_statistics(history: h.ReadingHistory, *, notes_count: int = 0):
    return db.MaterialStatistics(
        material=article_material(history),
        started_at=h.day(9),
        completed_at=None,
        # 9.5 days since the start plus the inclusive day
        total_reading_duration="10 days",
        duration=2,
        # day(8) and the six days after the last log
        lost_time=7,
        total=15,
        min_record=database.MinMax(
            log_id=history.article_min,
            material_id=history.article,
            date=h.day(6),
            count=5,
        ),
        max_record=database.MinMax(
            log_id=history.article_max,
            material_id=history.article,
            date=h.day(9),
            count=10,
        ),
        # round(15 / 2) with banker's rounding
        mean=8,
        notes_count=notes_count,
        remaining_pages=25,
        # round(25 / 8)
        remaining_days=3,
        would_be_completed=h.day(-3),
    )


async def test_get_means_delegates_to_the_reading_log_statistics(clock):
    await h.reading_history(clock)

    assert await db.get_means() == {BOOK: Decimal("34.00"), ARTICLE: Decimal("7.50")}


async def test_completed_statistics_of_a_material_with_logs(clock):
    history = await h.reading_history(clock)
    note_id = await factories.insert_note(material_id=history.book)
    await factories.insert_note(material_id=history.book, page=2)
    await factories.set_columns(models.Notes, note_id, is_deleted=True)

    statistics = await db.get_completed_statistics(material_id=history.book)

    assert statistics == book_statistics(history, notes_count=1)
    assert statistics.percent_completed == 100.0


async def test_completed_statistics_page_matches_the_single_material_read(clock):
    history = await h.reading_history(clock)

    page = await db.completed_statistics_page(params=PageParams())

    assert page.items == [book_statistics(history)]
    assert page.total_count == 1
    assert page.next_token is None


async def test_completed_statistics_of_a_material_without_logs(clock):
    await h.reading(clock, started=h.day(9))
    material_id = await h.completed(clock, started=h.day(4), finished=h.day(4))

    statistics = await db.get_completed_statistics(material_id=material_id)

    assert statistics == db.MaterialStatistics(
        material=expected_material(
            material_id,
            added_at=seconds_after_now(2),
            started_at=h.midnight(h.day(4)),
            completed_at=h.midnight(h.day(4)),
        ),
        started_at=h.day(4),
        completed_at=h.day(4),
        total_reading_duration="1 days",
        duration=0,
        lost_time=0,
        total=0,
        min_record=None,
        max_record=None,
        # no logs at all: the default mean
        mean=1,
        notes_count=0,
    )
    assert statistics.percent_completed == 0.0


async def test_statistics_of_a_material_without_pages_is_zero_percent_completed(clock):
    material_id = await h.completed(clock, started=h.day(0), finished=h.day(0), pages=0)

    statistics = await db.get_completed_statistics(material_id=material_id)

    assert (statistics.total, statistics.material.pages) == (0, 0)
    assert statistics.percent_completed == 0.0


@pytest.mark.parametrize("state", ["missing", "queued", "reading"])
async def test_completed_statistics_raises_not_found_unless_completed(clock, state):
    material_id = h.MISSING_ID
    if state != "missing":
        material_id = await h.queued(clock)
    if state == "reading":
        await db.start_material(material_id=material_id)

    with pytest.raises(database.NotFoundException, match="Completed material"):
        await db.get_completed_statistics(material_id=material_id)


async def test_reading_statistics_of_a_material_with_logs(clock):
    history = await h.reading_history(clock)
    await factories.insert_note(material_id=history.article)
    await factories.insert_note(material_id=history.article, page=2)

    statistics = await db.reading_statistics()

    assert statistics == [article_statistics(history, notes_count=2)]
    assert statistics[0].percent_completed == 37.5


async def test_reading_statistics_page_matches_the_full_listing(clock):
    history = await h.reading_history(clock)

    page = await db.reading_statistics_page(params=PageParams())

    assert page.items == [article_statistics(history)]
    assert page.total_count == 1
    assert page.next_token is None


async def test_reading_statistics_of_unread_materials_use_the_mean_of_their_type(clock):
    await h.reading_history(clock)
    book_id = await h.reading(clock, started=h.day(2), title="Unread book", pages=100)
    lecture_id = await h.reading(
        clock,
        started=h.day(1),
        title="Unread lecture",
        pages=7,
        material_type=LECTURE,
    )

    statistics = {
        stat.material.material_id: stat for stat in await db.reading_statistics()
    }

    book = statistics[book_id]
    # the mean of books is 34.00
    assert (book.mean, book.total, book.duration, book.lost_time) == (34, 0, 0, 0)
    assert (book.min_record, book.max_record) == (None, None)
    assert (book.remaining_pages, book.remaining_days) == (100, 3)
    assert book.would_be_completed == h.day(-3)
    assert book.total_reading_duration == "3 days"
    lecture = statistics[lecture_id]
    # no lecture was ever logged: the default mean of 1
    assert (lecture.mean, lecture.remaining_pages, lecture.remaining_days) == (1, 7, 7)
    assert lecture.would_be_completed == h.day(-7)


async def test_materials_statistics_keep_the_order_of_the_given_materials(clock):
    history = await h.reading_history(clock)
    materials = [article_material(history), book_material(history)]

    statistics = await db._get_materials_statistics(materials)

    assert statistics == [article_statistics(history), book_statistics(history)]


async def test_end_of_reading_adds_remaining_days_of_every_reading_material(clock):
    await h.reading_history(clock)
    await h.reading(clock, started=h.day(2), title="Unread book", pages=100)

    # 3 days for the article and 3 for the unread book
    assert await db._end_of_reading() == h.day(-6)


async def test_end_of_reading_is_today_when_only_completed_materials_exist(clock):
    await h.completed(clock, started=h.day(4), finished=h.day(0))

    assert await db._end_of_reading() == h.TODAY


async def test_reading_statistics_fail_on_a_zero_count_log_current_behaviour(clock):
    material_id = await h.reading(clock, started=h.day(0))
    await logs_db.insert_log_record(material_id=material_id, count=0, date=h.day(0))

    # materials/db.py:347 divides the remaining pages by the mean of 0
    with pytest.raises(ZeroDivisionError):
        await db.reading_statistics()


async def test_estimate_fails_when_the_mean_is_zero_current_behaviour(clock):
    material_id = await h.reading(clock, started=h.day(0))
    await logs_db.insert_log_record(material_id=material_id, count=0, date=h.day(0))
    await h.queued(clock)

    # materials/db.py:752 divides the pages by the mean of 0.00
    with pytest.raises(ZeroDivisionError):
        await db.estimate_page(start_date=h.TODAY, params=PageParams())


async def test_completed_statistics_survive_days_after_the_last_completion(clock):
    material_id = await h.completed(clock, started=h.day(3), finished=h.day(2))
    await logs_db.insert_log_record(material_id=material_id, count=100, date=h.day(2))

    statistics = await db.get_completed_statistics(material_id=material_id)

    assert (statistics.total, statistics.duration, statistics.lost_time) == (100, 1, 0)


# estimate_page


async def test_estimate_page_forecasts_the_queue_from_the_start_date(clock):
    await h.reading_history(clock)
    book_id = await h.queued(clock, title="Queued book", pages=100)
    article_id = await h.queued(
        clock, title="Queued article", pages=30, material_type=ARTICLE
    )
    lecture_id = await h.queued(
        clock, title="Queued lecture", pages=7, material_type=LECTURE
    )
    start = datetime.date(2024, 4, 1)

    page = await db.estimate_page(start_date=start, params=PageParams(order=Order.ASC))

    assert [
        (
            e.material.material_id,
            e.will_be_started,
            e.will_be_completed,
            e.expected_duration,
        )
        for e in page.items
    ] == [
        # round(100 / 34.00) = 3 days, both ends included
        (book_id, datetime.date(2024, 4, 1), datetime.date(2024, 4, 4), 4),
        # round(30 / 7.50) = 4 days
        (article_id, datetime.date(2024, 4, 5), datetime.date(2024, 4, 9), 5),
        # no mean for lectures: one page a day
        (lecture_id, datetime.date(2024, 4, 10), datetime.date(2024, 4, 17), 8),
    ]
    assert page.items[0].material == expected_material(
        book_id,
        added_at=seconds_after_now(3),
        title="Queued book",
    )
    assert page.total_count == 3
    assert page.next_token is None


async def test_estimate_page_goes_from_the_newest_material_by_default(clock):
    oldest = await h.queued(clock, pages=2)
    newest = await h.queued(clock, pages=5)
    start = datetime.date(2024, 4, 1)

    page = await db.estimate_page(start_date=start, params=PageParams())

    assert [
        (
            e.material.material_id,
            e.will_be_started,
            e.will_be_completed,
            e.expected_duration,
        )
        for e in page.items
    ] == [
        (newest, datetime.date(2024, 4, 1), datetime.date(2024, 4, 6), 6),
        (oldest, datetime.date(2024, 4, 7), datetime.date(2024, 4, 9), 3),
    ]


async def test_estimate_page_is_empty_without_queued_materials(clock):
    await h.reading(clock, started=h.day(1))

    page = await db.estimate_page(start_date=h.TODAY, params=PageParams())

    assert (page.items, page.total_count, page.next_token) == ([], 0, None)


async def test_estimate_page_of_a_material_without_pages(clock):
    material_id = await h.queued(clock, pages=0)

    page = await db.estimate_page(start_date=h.TODAY, params=PageParams())

    [estimate] = page.items
    assert (estimate.material.material_id, estimate.expected_duration) == (material_id, 1)
    assert (estimate.will_be_started, estimate.will_be_completed) == (h.TODAY, h.TODAY)


# get_repeats_analytics, get_repeating_queue_page


def days_before(today: datetime.date, days: int) -> datetime.date:
    return today - datetime.timedelta(days=days)


async def test_repeats_analytics_skip_queued_materials(clock, sql_today):
    await h.queued(clock)

    assert await db.get_repeats_analytics() == {}


async def test_repeats_analytics_of_a_reading_material_without_repeats(clock, sql_today):
    material_id = await h.reading(clock, started=days_before(sql_today, 5))

    analytics = await db.get_repeats_analytics()

    assert analytics == {
        material_id: db.RepeatAnalytics(
            repeats_count=0,
            last_repeated_at=None,
            priority_days=0,
        ),
    }
    assert analytics[material_id].priority_months == 0


async def test_repeats_analytics_of_a_completed_material_without_repeats(
    clock, sql_today
):
    material_id = await h.completed(
        clock,
        started=days_before(sql_today, 50),
        finished=days_before(sql_today, 40),
    )

    analytics = await db.get_repeats_analytics()

    assert analytics == {
        material_id: db.RepeatAnalytics(
            repeats_count=0,
            last_repeated_at=None,
            priority_days=40,
        ),
    }
    assert analytics[material_id].priority_months == pytest.approx(40 / 30)


async def test_repeats_analytics_of_a_material_repeated_once(clock, sql_today):
    material_id = await h.completed(
        clock,
        started=days_before(sql_today, 90),
        finished=days_before(sql_today, 80),
    )
    repeated_at = datetime.datetime.combine(
        days_before(sql_today, 35), datetime.time(23, 59)
    )
    await h.repeat(clock, material_id, at=repeated_at)

    analytics = await db.get_repeats_analytics()

    assert analytics == {
        material_id: db.RepeatAnalytics(
            repeats_count=1,
            last_repeated_at=repeated_at,
            priority_days=35,
        ),
    }
    # one repeat postpones the next one by 30 days
    assert analytics[material_id].priority_months == pytest.approx(5 / 30)


async def test_repeats_analytics_of_a_material_repeated_several_times(clock, sql_today):
    material_id = await h.completed(
        clock,
        started=days_before(sql_today, 300),
        finished=days_before(sql_today, 200),
    )
    other_id = await h.completed(
        clock,
        started=days_before(sql_today, 300),
        finished=days_before(sql_today, 10),
    )
    last_repeated_at = datetime.datetime.combine(
        days_before(sql_today, 20), datetime.time(1)
    )
    for days in (150, 20, 100):
        at = datetime.datetime.combine(days_before(sql_today, days), datetime.time(1))
        await h.repeat(clock, material_id, at=at)

    analytics = await db.get_repeats_analytics()

    assert analytics == {
        material_id: db.RepeatAnalytics(
            repeats_count=3,
            last_repeated_at=last_repeated_at,
            priority_days=20,
        ),
        other_id: db.RepeatAnalytics(
            repeats_count=0,
            last_repeated_at=None,
            priority_days=10,
        ),
    }
    # 20 days is less than three repeat periods
    assert analytics[material_id].priority_months == 0
    assert analytics[other_id].priority_months == pytest.approx(10 / 30)


async def repeating_queue(*, is_outlined: bool = False) -> list[db.RepeatingQueue]:
    page = await db.get_repeating_queue_page(is_outlined=is_outlined, params=PageParams())
    assert page.next_token is None
    assert page.total_count == len(page.items)
    return page.items


@pytest.fixture
def session_time_zone(monkeypatch: pytest.MonkeyPatch):
    """Run every database session of the code under test in the given time zone."""
    original = database.session

    def install(time_zone: str) -> None:
        @asynccontextmanager
        async def session(**kwargs):
            async with original(**kwargs) as ses:
                # LOCAL: the setting ends with the transaction, the pooled
                # connection goes back in UTC
                await ses.execute(sa.text(f"SET LOCAL TIME ZONE '{time_zone}'"))
                yield ses

        monkeypatch.setattr(database, "session", session)

    return install


TIME_ZONES = pytest.mark.parametrize(
    "time_zone",
    ["Pacific/Kiritimati", "Etc/GMT+12"],
    ids=["utc+14", "utc-12"],
)


@TIME_ZONES
async def test_repeats_analytics_do_not_depend_on_the_session_time_zone(
    clock, sql_today, session_time_zone, time_zone
):
    material_id = await h.completed(
        clock,
        started=days_before(sql_today, 50),
        finished=days_before(sql_today, 40),
    )
    session_time_zone(time_zone)

    analytics = await db.get_repeats_analytics()

    assert analytics[material_id].priority_days == 40


@TIME_ZONES
async def test_repeating_queue_does_not_depend_on_the_session_time_zone(
    clock, sql_today, session_time_zone, time_zone
):
    material_id = await h.completed(
        clock,
        started=days_before(sql_today, 60),
        finished=days_before(sql_today, 45),
    )
    session_time_zone(time_zone)

    [item] = await repeating_queue()

    assert (item.material_id, item.priority_days) == (material_id, 45)


async def test_repeating_queue_is_empty_on_an_empty_database():
    assert await repeating_queue() == []


async def test_repeating_queue_item_of_a_never_repeated_material(clock, sql_today):
    material_id = await h.completed(
        clock,
        started=days_before(sql_today, 60),
        finished=days_before(sql_today, 45),
        title="To repeat",
        pages=321,
        material_type=ARTICLE,
    )
    note_id = await factories.insert_note(material_id=material_id)
    deleted_note_id = await factories.insert_note(material_id=material_id, page=2)
    await factories.set_columns(models.Notes, deleted_note_id, is_deleted=True)
    for _ in range(3):
        await factories.insert_card(material_id=material_id, note_id=note_id)

    assert await repeating_queue() == [
        db.RepeatingQueue(
            material_id=material_id,
            title="To repeat",
            pages=321,
            material_type=ARTICLE,
            is_outlined=False,
            notes_count=1,
            cards_count=3,
            repeats_count=0,
            completed_at=h.midnight(days_before(sql_today, 45)),
            last_repeated_at=None,
            priority_days=45,
            priority_months=1.5,
        ),
    ]


async def test_repeating_queue_item_of_a_repeated_material(clock, sql_today):
    material_id = await h.completed(
        clock,
        started=days_before(sql_today, 300),
        finished=days_before(sql_today, 200),
    )
    last_repeated_at = datetime.datetime.combine(
        days_before(sql_today, 90), datetime.time(7)
    )
    await h.repeat(clock, material_id, at=last_repeated_at - datetime.timedelta(days=30))
    await h.repeat(clock, material_id, at=last_repeated_at)

    [item] = await repeating_queue()

    assert (item.material_id, item.repeats_count) == (material_id, 2)
    assert item.last_repeated_at == last_repeated_at
    assert item.completed_at == h.midnight(days_before(sql_today, 200))
    assert (item.priority_days, item.priority_months) == (90, 1.0)
    assert (item.notes_count, item.cards_count) == (0, 0)


@pytest.mark.parametrize(
    ("completed_days_ago", "repeated_days_ago", "is_listed"),
    [
        (30, [], True),
        (29, [], False),
        (0, [], False),
        (200, [60], True),
        (200, [59], False),
        (200, [120, 90], True),
        (200, [120, 89], False),
    ],
    ids=[
        "a month after completion",
        "a day short of a month",
        "completed today",
        "two months after the only repeat",
        "a day short after the only repeat",
        "three months after the second repeat",
        "a day short after the second repeat",
    ],
)
async def test_repeating_queue_lists_a_material_a_month_per_repeat_after_it_was_seen(
    clock,
    sql_today,
    completed_days_ago,
    repeated_days_ago,
    is_listed,
):
    material_id = await h.completed(
        clock,
        started=days_before(sql_today, 300),
        finished=days_before(sql_today, completed_days_ago),
    )
    for days in repeated_days_ago:
        at = datetime.datetime.combine(days_before(sql_today, days), datetime.time(12))
        await h.repeat(clock, material_id, at=at)

    items = await repeating_queue()

    assert [item.material_id for item in items] == ([material_id] if is_listed else [])


async def test_repeating_queue_skips_queued_and_reading_materials(clock, sql_today):
    await h.queued(clock)
    await h.reading(clock, started=days_before(sql_today, 100))

    assert await repeating_queue() == []


async def test_repeating_queue_skips_outlined_materials_without_live_notes(
    clock, sql_today
):
    dates = {
        "started": days_before(sql_today, 90),
        "finished": days_before(sql_today, 60),
    }
    without_notes = await h.completed(clock, **dates)
    with_deleted_note = await h.completed(clock, **dates)
    with_note = await h.completed(clock, **dates)
    not_outlined = await h.completed(clock, **dates)
    for material_id in (without_notes, with_deleted_note, with_note):
        await db.outline_material(material_id=material_id)
    deleted_note_id = await factories.insert_note(material_id=with_deleted_note)
    await factories.set_columns(models.Notes, deleted_note_id, is_deleted=True)
    await factories.insert_note(material_id=with_note)

    everything = await repeating_queue(is_outlined=False)
    outlined_only = await repeating_queue(is_outlined=True)

    assert [item.material_id for item in everything] == [with_note, not_outlined]
    assert [item.material_id for item in outlined_only] == [with_note]
    assert [item.notes_count for item in everything] == [1, 0]


async def test_repeating_queue_goes_from_the_most_overdue_material(clock, sql_today):
    completed_long_ago = await h.completed(
        clock,
        started=days_before(sql_today, 300),
        finished=days_before(sql_today, 90),
    )
    repeated_once = await h.completed(
        clock,
        started=days_before(sql_today, 300),
        finished=days_before(sql_today, 100),
    )
    completed_recently = await h.completed(
        clock,
        started=days_before(sql_today, 300),
        finished=days_before(sql_today, 40),
    )
    repeated_at = datetime.datetime.combine(days_before(sql_today, 65), datetime.time(12))
    await h.repeat(clock, repeated_once, at=repeated_at)

    items = await repeating_queue()

    assert [(item.material_id, item.priority_months) for item in items] == [
        (completed_long_ago, 3.0),
        (completed_recently, pytest.approx(40 / 30)),
        (repeated_once, pytest.approx(35 / 30)),
    ]
