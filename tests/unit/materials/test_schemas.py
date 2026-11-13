import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from tests.unit.materials.helpers import uid
from tracker.materials import schemas
from tracker.models import enums


def _create_payload(**overrides):
    return {
        "title": "Война и мир",
        "authors": "Толстой",
        "pages": 1300,
        "material_type": "book",
    } | overrides


def _item_payload(**overrides):
    return {
        "material_id": str(uid(1)),
        "title": "Title",
        "authors": "Author",
        "pages": 10,
        "material_type": "book",
        "added_at": "2024-03-10T12:00:00",
        "is_outlined": False,
    } | overrides


def _statistics_payload(**overrides):
    return {
        "material": _item_payload(),
        "started_at": "2024-03-01",
        "duration": 2,
        "lost_time": 0,
        "total": 5,
        "min_record": None,
        "max_record": None,
        "mean": 3,
        "notes_count": 0,
        "percent_completed": 50.0,
    } | overrides


def test_create_material_request_defaults():
    request = schemas.CreateMaterialRequest(**_create_payload())

    assert request.material_type is enums.MaterialTypesEnum.book
    assert request.tags is None
    assert request.link is None
    assert request.get_link() is None


def test_create_material_request_strips_strings():
    request = schemas.CreateMaterialRequest(
        **_create_payload(title="  Война и мир ", authors="\tТолстой\n", tags=" a, b "),
    )

    assert (request.title, request.authors, request.tags) == ("Война и мир", "Толстой", "a, b")


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        ("https://habr.com/ru/articles/1/", "https://habr.com/ru/articles/1/"),
        ("http://example.com", "http://example.com/"),
        ("https://example.com/путь?q=1#frag", "https://example.com/%D0%BF%D1%83%D1%82%D1%8C?q=1#frag"),
    ],
    ids=["https", "root-slash-added", "cyrillic-path"],
)
def test_get_link_returns_normalised_string(link, expected):
    request = schemas.CreateMaterialRequest(**_create_payload(link=link))

    assert request.get_link() == expected


@pytest.mark.parametrize("pages", [1, 2**31 - 1], ids=["minimum", "large"])
def test_create_material_request_accepts_positive_pages(pages):
    assert schemas.CreateMaterialRequest(**_create_payload(pages=pages)).pages == pages


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pages", 0),
        ("pages", -1),
        ("pages", 1.5),
        ("pages", "many"),
        ("pages", None),
        ("material_type", "podcast"),
        ("material_type", ""),
        ("material_type", None),
        ("title", None),
        ("authors", None),
        ("link", "not a url"),
        ("link", "ftp://example.com/file"),
        ("link", ""),
        ("unknown_field", 1),
    ],
    ids=lambda value: f"{value!r}",
)
def test_create_material_request_rejects_invalid_field(field, value):
    with pytest.raises(ValidationError) as exc_info:
        schemas.CreateMaterialRequest(**_create_payload(**{field: value}))

    assert exc_info.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize("field", ["title", "authors", "pages", "material_type"])
def test_create_material_request_requires_field(field):
    payload = _create_payload()
    del payload[field]

    with pytest.raises(ValidationError) as exc_info:
        schemas.CreateMaterialRequest(**payload)

    assert [(e["loc"], e["type"]) for e in exc_info.value.errors()] == [((field,), "missing")]


@pytest.mark.parametrize("field", ["title", "authors"])
def test_create_material_request_accepts_blank_text_current_behaviour(field):
    request = schemas.CreateMaterialRequest(**_create_payload(**{field: "   "}))

    assert getattr(request, field) == ""


@pytest.mark.parametrize(
    "model",
    [schemas.UpdateMaterialRequest, schemas.UpdateMaterialResponse],
)
def test_update_material_models_require_material_id(model):
    with pytest.raises(ValidationError) as exc_info:
        model(**_create_payload())

    assert exc_info.value.errors()[0]["loc"] == ("material_id",)

    with pytest.raises(ValidationError):
        model(**_create_payload(material_id="not-a-uuid"))

    assert model(**_create_payload(material_id=str(uid(3)))).material_id == uid(3)


def test_update_material_request_inherits_create_limits():
    with pytest.raises(ValidationError):
        schemas.UpdateMaterialRequest(**_create_payload(material_id=str(uid(3)), pages=0))


@pytest.mark.parametrize(
    ("tags_query", "expected"),
    [
        (None, set()),
        ("", set()),
        ("   ", set()),
        ("python", {"python"}),
        ("python sql", {"python", "sql"}),
        ("  python \t sql\npython ", {"python", "sql"}),
        ("Python python", {"Python", "python"}),
        ("ядро Linux", {"ядро", "Linux"}),
        ("a,b", {"a,b"}),
    ],
    ids=[
        "none",
        "empty",
        "blank",
        "single",
        "two",
        "any-whitespace-and-duplicates",
        "case-is-kept",
        "cyrillic",
        "comma-is-not-a-separator",
    ],
)
def test_requested_tags(tags_query, expected):
    assert schemas.SearchParams(tags_query=tags_query).requested_tags() == expected


@pytest.mark.parametrize(
    ("material_type", "expected"),
    [
        (enums.MaterialTypesEnum.lecture, enums.MaterialTypesEnum.lecture),
        ("audiobook", enums.MaterialTypesEnum.audiobook),
        ("", None),
        (None, None),
    ],
    ids=["enum", "enum-value", "empty-string", "none"],
)
def test_get_material_type(material_type, expected):
    params = schemas.SearchParams(material_type=material_type)

    assert params.get_material_type() is expected


def test_search_params_defaults():
    params = schemas.SearchParams()

    assert (params.material_type, params.is_outlined, params.tags_query) == (None, None, None)
    assert params.get_material_type() is None
    assert params.requested_tags() == set()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("material_type", "podcast"),
        ("material_type", " "),
        ("material_type", "BOOK"),
        ("is_outlined", "maybe"),
        ("tags_query", 5),
        ("extra", "x"),
    ],
    ids=lambda value: f"{value!r}",
)
def test_search_params_reject_invalid_field(field, value):
    with pytest.raises(ValidationError):
        schemas.SearchParams(**{field: value})


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("false", False), (True, True), (None, None)],
    ids=["true-string", "false-string", "bool", "none"],
)
def test_search_params_parse_is_outlined(value, expected):
    assert schemas.SearchParams(is_outlined=value).is_outlined is expected


@pytest.mark.parametrize(
    ("model", "field"),
    [
        (schemas.StartMaterialRequest, "started_at"),
        (schemas.CompleteMaterialRequest, "completed_at"),
    ],
    ids=["start", "complete"],
)
def test_start_and_complete_requests_take_optional_date(model, field):
    assert getattr(model(), field) is None
    assert getattr(model(**{field: "2024-02-29"}), field) == datetime.date(2024, 2, 29)

    for invalid in ("2023-02-29", "29.02.2024", "2024-02-29T10:00:00", ""):
        with pytest.raises(ValidationError):
            model(**{field: invalid})

    with pytest.raises(ValidationError):
        model(**{field: "2024-02-29", "extra": 1})


@pytest.mark.parametrize(
    "link",
    ["https://habr.com/ru/articles/1/", "https://youtu.be/Y-wNpXtU_vg"],
)
def test_parse_link_request_accepts_http_urls(link):
    assert str(schemas.ParseLinkRequest(link=link).link) == link


@pytest.mark.parametrize("link", [None, "", "habr.com/ru", "javascript:alert(1)", "file:///etc"])
def test_parse_link_request_rejects_non_http_urls(link):
    with pytest.raises(ValidationError):
        schemas.ParseLinkRequest(link=link)


def test_parse_link_request_requires_link():
    with pytest.raises(ValidationError):
        schemas.ParseLinkRequest()


def test_parsed_material_response_duration_is_optional():
    response = schemas.ParsedMaterialResponse(
        authors="a",
        title="t",
        type="article",
        link="https://habr.com/",
    )

    assert response.duration is None
    with pytest.raises(ValidationError):
        schemas.ParsedMaterialResponse(authors="a", title="t", type="article", link="x")


def test_get_material_item_optional_fields():
    item = schemas.GetMaterialItem(**_item_payload())

    assert item.material_id == uid(1)
    assert item.tags is None
    assert item.link is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pages", -1),
        ("material_id", "1"),
        ("material_type", "x"),
        ("link", "nope"),
        ("added_at", "yesterday"),
        ("is_outlined", None),
    ],
    ids=lambda value: f"{value!r}",
)
def test_get_material_item_rejects_invalid_field(field, value):
    with pytest.raises(ValidationError) as exc_info:
        schemas.GetMaterialItem(**_item_payload(**{field: value}))

    assert exc_info.value.errors()[0]["loc"] == (field,)


def test_get_material_item_accepts_zero_pages():
    assert schemas.GetMaterialItem(**_item_payload(pages=0)).pages == 0


@pytest.mark.parametrize("expected_duration", [0, -1])
def test_material_estimate_rejects_non_positive_duration(expected_duration):
    with pytest.raises(ValidationError):
        schemas.MaterialEstimate(
            material=_item_payload(),
            will_be_started="2024-03-10",
            will_be_completed="2024-03-10",
            expected_duration=expected_duration,
        )


def test_material_estimate_accepts_one_day():
    estimate = schemas.MaterialEstimate(
        material=_item_payload(),
        will_be_started="2024-03-10",
        will_be_completed="2024-03-10",
        expected_duration=1,
    )

    assert estimate.expected_duration == 1


def test_material_statistics_accepts_boundary_zeroes():
    stat = schemas.MaterialStatistics(
        **_statistics_payload(
            lost_time=0,
            mean=0,
            notes_count=0,
            remaining_pages=0,
            remaining_days=0,
        ),
    )

    assert (stat.remaining_pages, stat.remaining_days) == (0, 0)
    assert stat.completed_at is None
    assert stat.would_be_completed is None


@pytest.mark.parametrize(
    "field",
    ["lost_time", "mean", "notes_count", "remaining_pages", "remaining_days"],
)
def test_material_statistics_rejects_negative_counter(field):
    with pytest.raises(ValidationError) as exc_info:
        schemas.MaterialStatistics(**_statistics_payload(**{field: -1}))

    assert exc_info.value.errors()[0]["loc"] == (field,)


def test_material_statistics_requires_percent_completed():
    payload = _statistics_payload()
    del payload["percent_completed"]

    with pytest.raises(ValidationError):
        schemas.MaterialStatistics(**payload)


def _queue_item_payload(**overrides):
    return {
        "material_id": str(uid(1)),
        "title": "t",
        "pages": 1,
        "material_type": "book",
        "is_outlined": True,
        "notes_count": 0,
        "cards_count": 0,
        "repeats_count": 0,
        "completed_at": None,
        "last_repeated_at": None,
        "priority_days": -3,
        "priority_months": 1.5,
    } | overrides


def test_repeating_queue_item_accepts_zero_counters_and_negative_priority():
    item = schemas.RepeatingQueueItem(**_queue_item_payload())

    assert item.priority_days == -3
    assert item.priority_months == 1.5


@pytest.mark.parametrize("field", ["pages", "notes_count", "cards_count", "repeats_count"])
def test_repeating_queue_item_rejects_negative_counter(field):
    with pytest.raises(ValidationError):
        schemas.RepeatingQueueItem(**_queue_item_payload(**{field: -1}))


def test_list_queue_response_rejects_negative_mean():
    assert schemas.ListMaterialsQueueResponse(
        next_token=None,
        total_count=0,
        estimates=[],
        mean={"book": 0},
    ).mean == {enums.MaterialTypesEnum.book: 0}

    with pytest.raises(ValidationError):
        schemas.ListMaterialsQueueResponse(
            next_token=None,
            total_count=0,
            estimates=[],
            mean={"book": -0.1},
        )
    with pytest.raises(ValidationError):
        schemas.ListMaterialsQueueResponse(
            next_token=None,
            total_count=0,
            estimates=[],
            mean={"podcast": 1},
        )


@pytest.mark.parametrize(
    ("model", "field"),
    [
        (schemas.ListReadingMaterialsResponse, "statistics"),
        (schemas.ListCompletedMaterialsResponse, "statistics"),
        (schemas.ListRepeatingQueueResponse, "repeating_queue"),
    ],
)
def test_page_responses_require_pagination_fields(model, field):
    assert getattr(model(next_token="t", total_count=3, **{field: []}), field) == []

    with pytest.raises(ValidationError):
        model(**{field: []})


def test_single_item_responses_wrap_models():
    statistics = schemas.GetCompletedMaterialResponse(statistics=_statistics_payload())
    material = schemas.GetMaterialResponse(material=_item_payload())

    assert statistics.statistics.total == 5
    assert material.material.title == "Title"


def test_simple_responses():
    assert schemas.CreateMaterialResponse(material_id=str(uid(2))).material_id == uid(2)
    assert schemas.IsMaterialReadingResponse(is_reading=True).is_reading is True
    assert schemas.GetMaterialTagsResponse(tags=["a", "a", "b"]).tags == {"a", "b"}
    assert list(schemas.GetAuthorsResponse(authors=("x", "y")).authors) == ["x", "y"]
    assert schemas.ListMaterialTitlesResponse(items={str(uid(1)): "t"}).items == {
        UUID(int=1): "t",
    }

    with pytest.raises(ValidationError):
        schemas.CreateMaterialResponse(material_id="x")
    with pytest.raises(ValidationError):
        schemas.ListMaterialTitlesResponse(items={"not-uuid": "t"})


def test_completion_info_accepts_zeroes():
    info = schemas.GetMaterialCompletionInfoResponse(
        material_pages=0,
        material_type="course",
        pages_read=0,
        read_days=0,
    )

    assert info.material_type is enums.MaterialTypesEnum.course


@pytest.mark.parametrize("field", ["material_pages", "pages_read", "read_days"])
def test_completion_info_rejects_negative_counter(field):
    payload = {"material_pages": 1, "material_type": "book", "pages_read": 1, "read_days": 1}

    with pytest.raises(ValidationError) as exc_info:
        schemas.GetMaterialCompletionInfoResponse(**(payload | {field: -1}))

    assert exc_info.value.errors()[0]["loc"] == (field,)
