import asyncio
import datetime
import re
from collections import Counter, defaultdict
from collections.abc import Collection, Iterable
from typing import Any
from uuid import UUID

import networkx as nx
import orjson
import sqlalchemy.sql as sa
from fastapi.encoders import jsonable_encoder
from pydantic import field_serializer, field_validator
from pyvis.network import Network
from sqlalchemy.engine import Row

from tracker.common import database, pagination, settings, sort_keys
from tracker.common.logger import logger
from tracker.common.schemas import CustomBaseModel
from tracker.models import enums, models
from tracker.notes import schemas


_TAG_PATTERN = r"(\B)#({tag})(\b)"
_NOTES_PATH = "/notes/"


class Note(CustomBaseModel):
    note_id: UUID
    link_id: UUID | None = None
    material_id: UUID
    title: str | None = None
    content: str
    added_at: datetime.datetime
    chapter: str
    page: int
    tags: set[str]
    is_deleted: bool
    note_number: int
    # only for listing/one-page view
    links_count: int | None = None

    @field_validator("tags", mode="before")
    def load_tags(cls, tags: set[str] | list[str] | str | None) -> Any:
        # the column is nullable: SQL NULL arrives as None, a JSON null as "null"
        if isinstance(tags, str):
            tags = orjson.loads(tags)
        return tags or set()

    @field_serializer("added_at")
    def serialize_added_at(self, added_at: datetime.datetime) -> str:
        return added_at.strftime(settings.DATETIME_FORMAT)

    @property
    def content_md(self) -> str:
        return str(self)

    @property
    def short_content(self) -> str:
        return f"{self.content_md[:50]}..."

    @property
    def info(self) -> str:
        return (
            f"ID: {self.note_id}\n"
            f"Number: {self.note_number}\n"
            f"Material ID: {self.material_id}\n\n"
            f"{self}"
        )

    @property
    def chapter_int(self) -> int:
        return sort_keys.chapter_int(self.chapter)

    def highlight(self, from_: str, to: str) -> None:
        self.content = self.content.replace(from_, to)

    def __str__(self) -> str:
        return schemas.demark_note(self.content)

    @classmethod
    def _mark_tags_with_ref(cls, text: str, tags: set[str]) -> str:
        link_text_template = (
            f"<a href={settings.TRACKER_URL}{_NOTES_PATH}?"
            'tags_query={tag} target="_blank">#{tag}</a>'
        )

        for tag in sorted(tags, key=len, reverse=True):
            link_text = link_text_template.format(tag=tag)

            text = re.sub(_TAG_PATTERN.format(tag=tag), rf"\1{link_text}\3", text)

        return text

    @property
    def link_html(self) -> str:
        if not self.link_id:
            return ""

        link_text = f"[[{self.link_id}]]"

        return f'<a class="link-ref" href={settings.TRACKER_URL}{_NOTES_PATH}{self.link_id} target="_blank">{link_text}</a>'  # noqa: E501

    @property
    def content_html(self) -> str:
        return self.content

    @property
    def tags_str(self) -> str:
        return " ".join(f"#{tag}" for tag in sorted(self.tags))

    @property
    def tags_html(self) -> str:
        return self._mark_tags_with_ref(self.tags_str, self.tags)


def _to_note(row: Row) -> Note:
    return Note.model_validate(row, from_attributes=True)


def _search_notes_stmt(
    *,
    material_id: UUID | str | None,
    tags: set[str],
    note_ids: Collection[UUID] | None,
) -> sa.Select:
    stmt = _get_note_stmt(material_id=material_id)
    notes_model = stmt.selected_columns

    if tags:
        stmt = stmt.where(notes_model.tags.contains(sorted(tags)))
    if note_ids is not None:
        stmt = stmt.where(notes_model.note_id.in_([str(note_id) for note_id in note_ids]))
    return stmt


async def search_notes_page(
    *,
    material_id: UUID | str | None,
    query: str | None,
    tags: set[str],
    note_ids: Collection[UUID] | None,
    params: pagination.PageParams,
) -> pagination.Page[Note]:
    """`note_ids=None` applies no full-text filter, an empty one matches nothing."""
    logger.debug("Searching notes page material_id=%s", material_id)
    request = pagination.page_request(
        params,
        default_order=pagination.Order.ASC,
        material_id=material_id,
        query=query,
        tags=tags,
    )

    stmt = _search_notes_stmt(material_id=material_id, tags=tags, note_ids=note_ids)
    page = await pagination.fetch_page(
        stmt,
        cursor_expr=pagination.cursor(stmt.selected_columns.sort_key),
        request=request,
        to_item=_to_note,
    )

    logger.debug("%s notes got", len(page.items))
    return page


async def get_distinct_chapters(
    *,
    material_id: UUID | str | None,
    tags: set[str],
    note_ids: Collection[UUID] | None,
) -> defaultdict[UUID, list[str]]:
    """Chapters of all found notes in listing order, to build the menu."""
    logger.debug("Getting distinct chapters")

    notes = _search_notes_stmt(
        material_id=material_id,
        tags=tags,
        note_ids=note_ids,
    ).subquery()
    stmt = (
        sa.select(notes.c.material_id, notes.c.chapter)
        .group_by(notes.c.material_id, notes.c.chapter)
        .order_by(sa.func.min(notes.c.sort_key))
    )

    chapters: defaultdict[UUID, list[str]] = defaultdict(list)
    async with database.session() as ses:
        for material_id_, chapter in (await ses.execute(stmt)).all():
            chapters[material_id_].append(chapter)

    logger.debug("Distinct chapters got")
    return chapters


async def get_material_types() -> dict[UUID, enums.MaterialTypesEnum]:
    logger.debug("Getting material types")

    stmt = sa.select(models.Materials.c.material_id, models.Materials.c.material_type)

    async with database.session() as ses:
        types = {
            row.material_id: row.material_type
            for row in (await ses.execute(stmt)).mappings().all()
        }

    logger.debug("Material types got")
    return types


async def get_material_titles() -> dict[UUID, str]:
    logger.debug("Getting material titles")

    stmt = sa.select(models.Materials.c.material_id, models.Materials.c.title)

    async with database.session() as ses:
        titles = {
            row.material_id: row.title
            for row in (await ses.execute(stmt)).mappings().all()
        }

    logger.debug("Titles got")
    return titles


async def get_material_with_notes_titles() -> dict[UUID, str]:
    """Get materials that have a note."""
    logger.debug("Getting material with note titles")

    stmt = (
        sa.select(
            sa.text("distinct on (materials.material_id) materials.material_id"),
            models.Materials.c.title,
        )
        .join(models.Notes, models.Notes.c.material_id == models.Materials.c.material_id)
        .where(~models.Notes.c.is_deleted)
    )

    async with database.session() as ses:
        titles = {
            row.material_id: row.title
            for row in (await ses.execute(stmt)).mappings().all()
        }

    logger.debug("Material with note titles got")
    return titles


def _get_note_stmt(
    *,
    note_id: UUID | str | None = None,
    material_id: UUID | str | None = None,
    link_id: UUID | str | None = None,
) -> sa.Select:
    links_count_query = "(select count(1) as links_count from notes where link_id = n.note_id and not is_deleted)"  # noqa: E501

    notes_model = models.Notes.alias("n")
    stmt = (
        sa.select(notes_model, sa.text(links_count_query))
        .where(~notes_model.c.is_deleted)
        .order_by(notes_model.c.note_number)
    )

    if note_id:
        stmt = stmt.where(notes_model.c.note_id == str(note_id))
    if material_id:
        stmt = stmt.where(notes_model.c.material_id == str(material_id))
    if link_id:
        stmt = stmt.where(notes_model.c.link_id == str(link_id))

    return stmt


async def get_notes(*, material_id: UUID | str | None = None) -> list[Note]:
    logger.debug("Getting notes material_id=%s", material_id)

    stmt = _get_note_stmt(material_id=material_id)

    async with database.session() as ses:
        notes = [
            Note.model_validate(row, from_attributes=True)
            for row in (await ses.execute(stmt)).all()
        ]
    logger.debug("%s notes got", len(notes))
    return notes


async def get_note(*, note_id: UUID) -> Note:
    logger.debug("Getting note_id='%s'", note_id)

    stmt = _get_note_stmt(note_id=note_id)

    async with database.session() as ses:
        if note := (await ses.execute(stmt)).one_or_none():
            logger.debug("Note got")
            return Note.model_validate(note, from_attributes=True)

    raise database.NotFoundException(f"Note_id='{note_id}' not found")


async def get_all_notes_count() -> dict[UUID, int]:
    """Get notes count for the materials."""
    logger.debug("Getting notes count for all materials")

    stmt = (
        sa.select(
            models.Notes.c.material_id.label("material_id"),
            sa.func.count(1).label("count"),  # type: ignore[arg-type]
        )
        .select_from(models.Notes)
        .where(~models.Notes.c.is_deleted)
        .group_by(models.Notes.c.material_id)
    )

    async with database.session() as ses:
        return dict((await ses.execute(stmt)).all())  # type: ignore[arg-type]


async def insert_note(
    *,
    material_id: UUID,
    link_id: UUID | None,
    title: str | None,
    content: str,
    chapter: str,
    page: int,
    tags: list[str],
) -> UUID:
    logger.debug("Inserting note for material_id='%s'", material_id)

    note_id = models.generate_id()
    values = {
        "note_id": note_id,
        "sort_key": sort_keys.note_sort_key(
            material_id=material_id,
            chapter=chapter,
            page=page,
            note_id=note_id,
        ),
        "material_id": str(material_id),
        "title": title,
        "content": content,
        "chapter": chapter,
        "page": page,
        "tags": tags,
        "link_id": str(link_id) if link_id else None,
    }

    stmt = models.Notes.insert().values(values)

    async with database.session() as ses:
        result = await ses.execute(stmt)

    database.check_inserted_one(result, entity="Note")

    logger.debug("Note_id='%s' inserted", note_id)
    return UUID(note_id)


async def update_note(
    *,
    note_id: UUID,
    material_id: UUID,
    link_id: UUID | None,
    title: str | None,
    content: str,
    page: int,
    chapter: str,
    tags: list[str],
) -> None:
    logger.debug("Updating note_id='%s'", note_id)

    values = {
        "sort_key": sort_keys.note_sort_key(
            material_id=material_id,
            chapter=chapter,
            page=page,
            note_id=note_id,
        ),
        "material_id": str(material_id),
        "title": title,
        "content": content,
        "page": page,
        "chapter": chapter,
        "tags": tags,
        "link_id": str(link_id) if link_id else None,
    }

    stmt = models.Notes.update().values(values).where(models.Notes.c.note_id == note_id)

    async with database.session() as ses:
        result = await ses.execute(stmt)

    database.check_updated_one(result, entity="Note", entity_id=note_id)

    logger.debug("Note updated")


async def _del_or_restore(*, note_id: UUID, is_deleted: bool) -> None:
    values = {"is_deleted": is_deleted}
    stmt = models.Notes.update().values(values).where(models.Notes.c.note_id == note_id)

    async with database.session() as ses:
        result = await ses.execute(stmt)

    database.check_updated_one(result, entity="Note", entity_id=note_id)


async def is_link_cyclic(*, note_id: UUID, link_id: UUID) -> bool:
    """Whether linking `note_id` to `link_id` closes a cycle of links.

    Deleted notes are followed too: restoring one must not bring a cycle back.
    """
    logger.debug(
        "Checking link note_id='%s' -> link_id='%s' for a cycle",
        note_id,
        link_id,
    )

    stmt = sa.select(models.Notes.c.link_id).where(
        models.Notes.c.note_id == sa.bindparam("id"),
    )
    visited: set[UUID] = set()
    current: UUID | None = link_id

    async with database.session() as ses:
        while current is not None and current not in visited:
            if current == note_id:
                return True
            visited.add(current)
            current = await ses.scalar(stmt, {"id": current})

    return False


async def count_links_to(*, note_id: UUID) -> int:
    logger.debug("Counting notes linked to note_id='%s'", note_id)

    stmt = (
        sa.select(sa.func.count(1))  # type: ignore[arg-type]
        .select_from(models.Notes)
        .where(models.Notes.c.link_id == note_id)
        .where(~models.Notes.c.is_deleted)
    )

    async with database.session() as ses:
        return await ses.scalar(stmt) or 0


async def delete_note(*, note_id: UUID) -> None:
    logger.debug("Deleting note_id='%s'", note_id)
    await _del_or_restore(note_id=note_id, is_deleted=True)
    logger.debug("Note deleted")


async def restore_note(*, note_id: UUID) -> None:
    logger.debug("Restoring note_id='%s'", note_id)
    await _del_or_restore(note_id=note_id, is_deleted=False)
    logger.debug("Note restored")


def _flatten_tags(rows: Iterable[list[str] | None]) -> list[str]:
    # a JSON null passes `tags != []`
    return [tag for tags in rows if tags for tag in tags]


async def _get_tags() -> set[str]:
    logger.debug("Getting tags")

    stmt = sa.select(models.Notes.c.tags).where(models.Notes.c.tags != [])

    async with database.session() as ses:
        tags = _flatten_tags((await ses.scalars(stmt)).all())

    tags_set = set(tags)
    logger.debug("Total %s unique tags got", len(tags_set))

    return tags_set


async def _get_material_tags(material_id: str | UUID) -> list[str]:
    logger.debug("Getting tags for material_id=%s", material_id)

    stmt = (
        sa.select(models.Notes.c.tags)
        .where(models.Notes.c.material_id == str(material_id))
        .where(models.Notes.c.tags != [])
    )

    async with database.session() as ses:
        tags = _flatten_tags((await ses.scalars(stmt)).all())

    tags_counter = Counter(tags)
    logger.debug("Total %s unique tags got", len(tags_counter))

    # sort by frequency
    return [tag for tag, _ in tags_counter.most_common()]


async def get_possible_links(note_id: UUID, note_tags: set[str]) -> list[Note]:
    """Get notes with which the given one might be linked.

    So possibility coeff = size of tags set intersection.
    """
    logger.debug("Getting possible links for note=%s, tags=%s", note_id, note_tags)

    stmt = (
        sa.select(models.Notes)
        .where(~models.Notes.c.is_deleted)
        .where(models.Notes.c.note_id != note_id)
        .where(
            sa.text(
                f"tags ?| array(SELECT jsonb_array_elements_text(tags) FROM notes WHERE note_id = '{note_id}')",  # noqa: S608, E501
            ),
        )
    )

    async with database.session() as ses:
        links = [
            Note.model_validate(link, from_attributes=True)
            for link in (await ses.execute(stmt)).all()
        ]

    # most possible first
    links.sort(key=lambda link: len(link.tags & note_tags), reverse=True)

    logger.debug("%s possible links got", len(links))
    return links


def _get_links_from(*, note_id: UUID, notes: Iterable[Note]) -> list[Note]:
    """Get all notes linked with the given one."""
    return [note for note in notes if note.link_id == note_id]


def _get_note_link(note: Note, **attrs: str) -> tuple[str, dict[str, Any]]:
    return (
        str(note.note_id),
        jsonable_encoder(
            {
                **attrs,
                "title": note.content_md,
                "material_id": note.material_id,
                "note_number": note.note_number,
                "label": note.short_content,
            },
        ),
    )


def _add_links_to(
    graph: nx.DiGraph,
    notes: dict[UUID, Note],
    note_id: UUID,
    even_added_notes: set[UUID],
) -> None:
    link_id = notes[note_id].link_id
    if not link_id or link_id in even_added_notes or link_id not in notes:
        return

    # to resolve circular recursion
    even_added_notes.add(link_id)

    graph.add_nodes_from([_get_note_link(notes[link_id])])
    graph.add_edge(str(note_id), str(link_id))

    _add_links_to(graph, notes, link_id, even_added_notes)


def _link_cohesive_notes(
    graph: nx.DiGraph,
    notes: dict[UUID, Note],
    note_id: UUID,
    *,
    visited: set[UUID],
) -> None:
    """Iterate over graph and find all note links."""
    if note_id in visited:
        return
    # before following the link, so a cycle already in the data terminates
    visited.add(note_id)

    link_id = notes[note_id].link_id
    links_from = _get_links_from(note_id=note_id, notes=notes.values())

    # a deleted note is missing from `notes`
    if link_id and link_id in notes:
        graph.add_nodes_from([_get_note_link(notes[link_id])])
        graph.add_edge(str(note_id), str(link_id))

        _link_cohesive_notes(graph, notes, link_id, visited=visited)

    for link in links_from:
        graph.add_nodes_from([_get_note_link(notes[link.note_id])])
        graph.add_edge(str(link.note_id), str(note_id))

        _link_cohesive_notes(graph, notes, link.note_id, visited=visited)


def link_notes(
    *,
    note_id: UUID,
    notes: dict[UUID, Note],
    color: str | None = "black",
) -> nx.DiGraph:
    logger.debug("Linking %s notes from the %s", len(notes), note_id)

    graph = nx.DiGraph()
    graph.add_nodes_from(
        [_get_note_link(notes[note_id])],
        color=color,
    )

    # link together all cohesive notes, which bounds with the given one
    _link_cohesive_notes(graph, notes, note_id, visited=set())

    logger.debug("Notes linked, %s nodes, %s edges", len(graph.nodes), len(graph.edges))

    return graph


def link_all_notes(notes: list[Note]) -> nx.DiGraph:
    if not notes:
        return nx.DiGraph()

    logger.debug("Linking all %s notes started", len(notes))

    note_ids = {note.note_id for note in notes}
    nodes, edges = [], []

    for note in notes:
        nodes.append(_get_note_link(note))
        if note.link_id and note.link_id in note_ids:
            edges.append((str(note.note_id), str(note.link_id)))

    graph = nx.DiGraph()
    graph.add_nodes_from(nodes)
    graph.add_edges_from(edges)

    logger.debug("%s notes linked", len(notes))
    return graph


def create_material_graph(
    *,
    material_id: UUID,
    material_notes: set[UUID],
    notes: dict[UUID, Note],
) -> nx.DiGraph:
    if not (material_notes and notes):
        raise ValueError("No notes passed")

    graph = nx.DiGraph()
    while material_notes:
        note_id = material_notes.pop()
        note_graph = link_notes(note_id=note_id, notes=notes, color=None)

        for node in note_graph.nodes:
            material_notes.discard(node)

        graph = nx.compose(graph, note_graph)

    _highlight_other_material_notes(graph=graph, notes=notes, material_id=material_id)

    return graph


def _highlight_other_material_notes(
    *,
    graph: nx.DiGraph,
    material_id: UUID,
    notes: dict[UUID, Note],
    color: str | None = "black",
) -> None:
    notes_from_other_material = {
        note_id: {"color": color}
        for note_id in graph.nodes
        if notes[UUID(note_id)].material_id != material_id
    }

    nx.set_node_attributes(graph, notes_from_other_material)


def create_graphic(graph: nx.DiGraph, **kwargs) -> str:
    logger.debug(
        "Creating graphic for graph with %s nodes, %s edges",
        len(graph.nodes),
        len(graph.edges),
    )

    net = Network(
        cdn_resources="remote",
        directed=True,
        neighborhood_highlight=True,
        **kwargs,
    )
    net.options = {"interaction": {"hover": True}}
    net.from_nx(graph)

    resp = net.generate_html()

    logger.debug("Graphic created")
    return resp


async def get_sorted_tags(*, material_id: str | UUID | None) -> list[str]:
    """Get tags especially for the material.

    Means there should be tags from the notes
    for the material in the beginning of the result list.
    """
    logger.debug("Getting sorted tags for material_id=%s", material_id)

    if not material_id:
        tags = await _get_tags()
        return sorted(tags)

    async with asyncio.TaskGroup() as tg:
        get_tags_task = tg.create_task(_get_tags())
        get_materials_tags = tg.create_task(_get_material_tags(material_id))

    tags, materials_tags = get_tags_task.result(), get_materials_tags.result()
    tags -= set(materials_tags)

    result = materials_tags + sorted(tags)
    logger.debug("%s sorted tags got", len(result))

    return result


async def get_links_from_page(
    *,
    note_id: UUID | str,
    params: pagination.PageParams,
) -> pagination.Page[Note]:
    stmt = _get_note_stmt(link_id=note_id)
    notes_model = stmt.selected_columns
    return await pagination.fetch_page(
        stmt,
        cursor_expr=pagination.keyset(
            pagination.int_key(notes_model.note_number),
            pagination.text_key(notes_model.sort_key),
        ),
        request=pagination.page_request(
            params,
            default_order=pagination.Order.ASC,
            note_id=note_id,
        ),
        to_item=_to_note,
    )
