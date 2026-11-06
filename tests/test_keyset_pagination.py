import datetime
from collections.abc import Awaitable, Callable
from uuid import UUID

import pytest
import sqlalchemy.sql as sa

from tracker.cards import db as cards_db
from tracker.common import database, sort_keys
from tracker.common.pagination import Order, Page, PageParams, encode_token
from tracker.materials import db as materials_db
from tracker.models import models
from tracker.notes import db as notes_db
from tracker.reading_log import db as logs_db


PAGE_SIZES = (1, 3, 100)


async def _collect[T](
    fetch: Callable[[PageParams], Awaitable[Page[T]]],
    *,
    page_size: int,
    order: Order | None = None,
) -> list[T]:
    items: list[T] = []
    params = PageParams(page_size=page_size, order=order)
    total_counts = set()

    while True:
        page = await fetch(params)
        assert len(page.items) <= page_size
        items.extend(page.items)
        total_counts.add(page.total_count)

        if page.next_token is None:
            break
        assert len(page.items) == page_size
        params = PageParams(next_token=page.next_token, page_size=page_size, order=order)

    assert total_counts == {len(items)}
    return items


async def _ids(stmt: sa.Select) -> list[UUID]:
    async with database.session() as ses:
        return [UUID(str(row[0])) for row in (await ses.execute(stmt)).all()]


async def test_stored_sort_keys_match_generator():
    async with database.session() as ses:
        materials = (await ses.execute(sa.select(models.Materials))).all()
        logs = (await ses.execute(sa.select(models.ReadingLog))).all()
        cards = (await ses.execute(sa.select(models.Cards))).all()
        notes = (await ses.execute(sa.select(models.Notes))).all()

    assert materials and logs and cards and notes
    for m in materials:
        assert m.sort_key == sort_keys.material_sort_key(
            added_at=m.added_at,
            material_id=m.material_id,
        )
    for log in logs:
        assert log.sort_key == sort_keys.reading_log_sort_key(
            material_id=log.material_id,
            date=log.date,
            log_id=log.log_id,
        )
    for card in cards:
        assert card.sort_key == sort_keys.card_sort_key(
            added_at=card.added_at,
            card_id=card.card_id,
        )
    for note in notes:
        assert note.sort_key == sort_keys.note_sort_key(
            material_id=note.material_id,
            chapter=note.chapter,
            page=note.page,
            note_id=note.note_id,
        )


@pytest.mark.parametrize("page_size", PAGE_SIZES)
async def test_cards_pages(page_size):
    items = await _collect(
        lambda params: cards_db.get_cards_page(material_id=None, params=params),
        page_size=page_size,
    )
    stmt = (
        sa.select(models.Cards.c.card_id)
        .join(models.Notes, models.Notes.c.note_id == models.Cards.c.note_id)
        .join(
            models.Materials, models.Materials.c.material_id == models.Notes.c.material_id
        )
        .order_by(models.Cards.c.sort_key.desc())
    )

    assert [card.card_id for card in items] == await _ids(stmt)


@pytest.mark.parametrize("page_size", PAGE_SIZES)
async def test_reading_logs_pages(page_size):
    items = await _collect(
        lambda params: logs_db.list_log_records_page(material_id=None, params=params),
        page_size=page_size,
    )
    stmt = sa.select(models.ReadingLog.c.log_id).order_by(
        models.ReadingLog.c.date.desc(),
        models.ReadingLog.c.sort_key.desc(),
    )

    assert [log.log_id for log in items] == await _ids(stmt)


async def test_reading_logs_pages_filter_by_material():
    stmt = sa.select(models.ReadingLog.c.material_id).limit(1)
    [material_id] = await _ids(stmt)

    items = await _collect(
        lambda params: logs_db.list_log_records_page(
            material_id=material_id, params=params
        ),
        page_size=2,
    )

    assert items
    assert {log.material_id for log in items} == {material_id}
    assert [log.date for log in items] == sorted(
        (log.date for log in items), reverse=True
    )


@pytest.mark.parametrize("page_size", PAGE_SIZES)
async def test_notes_search_pages(page_size):
    items = await _collect(
        lambda params: notes_db.search_notes_page(
            material_id=None,
            tags=set(),
            note_ids=None,
            params=params,
        ),
        page_size=page_size,
    )
    stmt = (
        sa.select(models.Notes.c.note_id)
        .where(~models.Notes.c.is_deleted)
        .order_by(models.Notes.c.sort_key)
    )

    assert [note.note_id for note in items] == await _ids(stmt)


async def test_notes_search_pages_filter_by_tags_and_ids():
    notes = await notes_db.get_notes()
    tagged = [note for note in notes if note.tags]
    assert tagged
    tag = sorted(tagged[0].tags)[0]
    note_ids = [note.note_id for note in notes[::2]]

    items = await _collect(
        lambda params: notes_db.search_notes_page(
            material_id=None,
            tags={tag},
            note_ids=note_ids,
            params=params,
        ),
        page_size=2,
    )

    expected = {
        note.note_id for note in notes if tag in note.tags and note.note_id in note_ids
    }
    assert {note.note_id for note in items} == expected


async def test_notes_search_empty_ids():
    page = await notes_db.search_notes_page(
        material_id=None,
        tags=set(),
        note_ids=[],
        params=PageParams(),
    )

    assert page.items == []
    assert page.total_count == 0
    assert page.next_token is None


async def test_distinct_chapters_follow_listing_order():
    notes = await _collect(
        lambda params: notes_db.search_notes_page(
            material_id=None,
            tags=set(),
            note_ids=None,
            params=params,
        ),
        page_size=100,
    )

    chapters = await notes_db.get_distinct_chapters(
        material_id=None,
        tags=set(),
        note_ids=None,
    )

    expected: dict[UUID, list[str]] = {}
    for note in notes:
        if note.chapter not in expected.setdefault(note.material_id, []):
            expected[note.material_id].append(note.chapter)
    assert chapters == expected


async def test_token_past_the_end_gives_empty_page():
    page = await notes_db.search_notes_page(
        material_id=None,
        tags=set(),
        note_ids=None,
        params=PageParams(next_token=encode_token("~")),
    )

    assert page.items == []
    assert page.next_token is None


async def test_note_links_pages():
    stmt = (
        sa.select(models.Notes.c.link_id)
        .where(models.Notes.c.link_id != None)
        .where(~models.Notes.c.is_deleted)
        .group_by(models.Notes.c.link_id)
        .order_by(sa.func.count().desc())
        .limit(1)
    )
    [link_id] = await _ids(stmt)

    items = await _collect(
        lambda params: notes_db.get_links_from_page(note_id=link_id, params=params),
        page_size=1,
    )

    expected = await notes_db.get_links_from(note_id=link_id)
    assert [note.note_id for note in items] == [note.note_id for note in expected]


@pytest.mark.parametrize("page_size", PAGE_SIZES)
async def test_completed_materials_pages(page_size):
    items = await _collect(
        lambda params: materials_db.completed_statistics_page(params=params),
        page_size=page_size,
        order=Order.ASC,
    )
    stmt = (
        sa.select(models.Materials.c.material_id)
        .join(
            models.Statuses,
            models.Statuses.c.material_id == models.Materials.c.material_id,
        )
        .where(models.Statuses.c.completed_at != None)
        .order_by(models.Statuses.c.completed_at, models.Materials.c.sort_key)
    )

    assert [stat.material.material_id for stat in items] == await _ids(stmt)


async def test_completed_materials_pages_filter_by_tags():
    completed = await materials_db._get_completed_materials()
    tagged = [m for m in completed if m.material.tags]
    assert tagged
    tag = tagged[0].material.tags.split(", ")[0]

    items = await _collect(
        lambda params: materials_db.completed_statistics_page(tags={tag}, params=params),
        page_size=2,
    )

    expected = {
        m.material_id for m in completed if tag in (m.material.tags or "").split(", ")
    }
    assert {stat.material.material_id for stat in items} == expected


async def test_completed_material_statistics_match_listing():
    [first, *_] = (
        await materials_db.completed_statistics_page(params=PageParams())
    ).items

    result = await materials_db.get_completed_statistics(
        material_id=first.material.material_id,
    )

    assert result == first


async def test_completed_material_statistics_not_found():
    reading = (await materials_db.reading_statistics_page(params=PageParams())).items
    assert reading

    with pytest.raises(database.NotFoundException):
        await materials_db.get_completed_statistics(
            material_id=reading[0].material.material_id,
        )


@pytest.mark.parametrize("page_size", PAGE_SIZES)
async def test_reading_materials_pages(page_size):
    items = await _collect(
        lambda params: materials_db.reading_statistics_page(params=params),
        page_size=page_size,
    )
    full = await materials_db.reading_statistics()

    async with database.session() as ses:
        last_read = dict(
            (
                await ses.execute(
                    sa.select(
                        models.ReadingLog.c.material_id,
                        sa.func.max(models.ReadingLog.c.date),
                    ).group_by(models.ReadingLog.c.material_id),
                )
            ).all(),
        )
        material_sort_keys = dict(
            (
                await ses.execute(
                    sa.select(
                        models.Materials.c.material_id, models.Materials.c.sort_key
                    ),
                )
            ).all(),
        )

    def key(stat: materials_db.MaterialStatistics) -> tuple[datetime.date, str]:
        material_id = stat.material.material_id
        return (
            last_read.get(material_id) or stat.started_at,
            material_sort_keys[material_id],
        )

    expected = sorted(full, key=key, reverse=True)
    assert [s.material.material_id for s in items] == [
        s.material.material_id for s in expected
    ]
    assert items == expected


@pytest.mark.parametrize("page_size", PAGE_SIZES)
async def test_queue_pages_keep_estimates(page_size):
    today = database.utcnow().date()

    async def fetch(params: PageParams) -> Page[materials_db.MaterialEstimate]:
        nonlocal start_date
        page, start_date = await materials_db.estimate_page(
            start_date=start_date,
            params=params,
        )
        return page

    start_date = today
    items = await _collect(fetch, page_size=page_size, order=Order.ASC)

    free_materials = await materials_db._get_free_materials()
    mean = await materials_db.get_means()
    expected = []
    last_date = today
    for material in free_materials:
        duration = round(material.pages / mean.get(material.material_type, 1))
        end = last_date + datetime.timedelta(days=duration)
        expected.append((material.material_id, last_date, end, duration + 1))
        last_date = end + datetime.timedelta(days=1)

    assert [
        (
            e.material.material_id,
            e.will_be_started,
            e.will_be_completed,
            e.expected_duration,
        )
        for e in items
    ] == expected


@pytest.mark.parametrize("is_outlined", (False, True))
@pytest.mark.parametrize("page_size", PAGE_SIZES)
async def test_repeating_queue_pages(page_size, is_outlined):
    items = await _collect(
        lambda params: materials_db.get_repeating_queue_page(
            is_outlined=is_outlined,
            params=params,
        ),
        page_size=page_size,
    )

    analytics = await materials_db.get_repeats_analytics()
    notes_count = await notes_db.get_all_notes_count()
    cards_count = await cards_db.get_all_cards_count()
    completed = await materials_db._get_completed_materials()
    async with database.session() as ses:
        material_sort_keys = dict(
            (
                await ses.execute(
                    sa.select(
                        models.Materials.c.material_id, models.Materials.c.sort_key
                    ),
                )
            ).all(),
        )

    expected = [
        (
            -analytics[m.material_id].priority_months,
            material_sort_keys[m.material_id],
            m.material_id,
        )
        for m in completed
        if not (m.material.is_outlined and not notes_count.get(m.material_id))
        and (not is_outlined or m.material.is_outlined)
        and analytics[m.material_id].priority_months >= 1
    ]
    expected.sort()

    assert [item.material_id for item in items] == [row[2] for row in expected]
    for item in items:
        assert item.priority_months == analytics[item.material_id].priority_months
        assert item.repeats_count == analytics[item.material_id].repeats_count
        assert item.notes_count == notes_count.get(item.material_id, 0)
        assert item.cards_count == cards_count.get(item.material_id, 0)


async def _queue_page(params: PageParams) -> Page[UUID]:
    page, _ = await materials_db.estimate_page(
        start_date=database.utcnow().date(),
        params=params,
    )
    ids = [e.material.material_id for e in page.items]
    return Page(items=ids, next_token=page.next_token, total_count=page.total_count)


def _ids_page[T](
    fetch: Callable[[PageParams], Awaitable[Page[T]]],
    get_id: Callable[[T], UUID],
) -> Callable[[PageParams], Awaitable[Page[UUID]]]:
    async def wrapped(params: PageParams) -> Page[UUID]:
        page = await fetch(params)
        return Page(
            items=[get_id(item) for item in page.items],
            next_token=page.next_token,
            total_count=page.total_count,
        )

    return wrapped


async def _first_link_id() -> UUID:
    stmt = (
        sa.select(models.Notes.c.link_id)
        .where(models.Notes.c.link_id != None)
        .where(~models.Notes.c.is_deleted)
        .limit(1)
    )
    [link_id] = await _ids(stmt)
    return link_id


LISTINGS = {
    "cards": (
        lambda p: cards_db.get_cards_page(material_id=None, params=p),
        lambda card: card.card_id,
        Order.DESC,
    ),
    "reading_logs": (
        lambda p: logs_db.list_log_records_page(material_id=None, params=p),
        lambda log: log.log_id,
        Order.DESC,
    ),
    "notes_search": (
        lambda p: notes_db.search_notes_page(
            material_id=None, tags=set(), note_ids=None, params=p
        ),
        lambda note: note.note_id,
        Order.ASC,
    ),
    "completed": (
        lambda p: materials_db.completed_statistics_page(params=p),
        lambda stat: stat.material.material_id,
        Order.DESC,
    ),
    "reading": (
        lambda p: materials_db.reading_statistics_page(params=p),
        lambda stat: stat.material.material_id,
        Order.DESC,
    ),
    "repeat": (
        lambda p: materials_db.get_repeating_queue_page(is_outlined=False, params=p),
        lambda item: item.material_id,
        Order.ASC,
    ),
}


@pytest.mark.parametrize("name", LISTINGS)
async def test_listing_default_and_reverse_order(name):
    fetch, get_id, default_order = LISTINGS[name]
    fetch_ids = _ids_page(fetch, get_id)
    reverse_order = Order.ASC if default_order == Order.DESC else Order.DESC

    default = await _collect(fetch_ids, page_size=3)
    explicit = await _collect(fetch_ids, page_size=3, order=default_order)
    reverse = await _collect(fetch_ids, page_size=3, order=reverse_order)

    assert default
    assert default == explicit
    assert reverse == default[::-1]


async def test_queue_default_order_is_desc():
    asc = await _collect(_queue_page, page_size=3, order=Order.ASC)
    default = await _collect(_queue_page, page_size=3)

    assert asc
    assert default == asc[::-1]


async def test_note_links_reverse_order():
    link_id = await _first_link_id()

    def fetch(params: PageParams) -> Awaitable[Page[UUID]]:
        return _ids_page(
            lambda p: notes_db.get_links_from_page(note_id=link_id, params=p),
            lambda note: note.note_id,
        )(params)

    asc = await _collect(fetch, page_size=1)
    desc = await _collect(fetch, page_size=1, order=Order.DESC)

    assert asc
    assert desc == asc[::-1]
