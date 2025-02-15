import asyncio
import datetime
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any
from uuid import UUID

import networkx as nx
import orjson
import sqlalchemy.sql as sa
from fastapi.encoders import jsonable_encoder
from pydantic import field_serializer, field_validator
from pyvis.network import Network

from tracker.common import database, settings
from tracker.common.logger import logger
from tracker.common.schemas import CustomBaseModel
from tracker.models import enums, models
from tracker.notes import schemas


_TAG_PATTERN = r"(\B)#({tag})(\b)"


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
    def load_tags(cls, tags: set[str] | str) -> set[str]:
        if isinstance(tags, str):
            return set(orjson.loads(tags))
        return tags

    @field_serializer("tags", when_used="json")
    def serialize_tags(self, tags: set[str]) -> bytes:
        # for cache
        return orjson.dumps(sorted(tags))

    @field_serializer("is_deleted", when_used="json")
    def serialize_is_deleted(self, is_deleted: bool) -> int:  # noqa: FBT001
        # for cache
        return int(is_deleted)

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
        if chapter := self.chapter:
            return int("".join(symb for symb in chapter if symb.isdigit()))
        return 0

    def get_material_id(self) -> str:
        return str(self.material_id)

    def highlight(self, from_: str, to: str) -> None:
        self.content = self.content.replace(from_, to)

    def __str__(self) -> str:
        return schemas.demark_note(self.content)

    @classmethod
    def _mark_tags_with_ref(cls, text: str, tags: set[str]) -> str:
        from tracker.notes.routes import get_notes, router

        search_url = router.url_path_for(get_notes.__name__)

        link_text_template = (
            f"<a href={settings.TRACKER_URL}{search_url}?"
            'tags_query={tag} target="_blank">#{tag}</a>'
        )

        for tag in sorted(tags, key=lambda tag: len(tag), reverse=True):
            link_text = link_text_template.format(tag=tag)

            text = re.sub(_TAG_PATTERN.format(tag=tag), rf"\1{link_text}\3", text)

        return text

    @property
    def link_html(self) -> str:
        if not self.link_id:
            return ""

        from tracker.notes.routes import get_note, router

        note_url = router.url_path_for(get_note.__name__)
        link_text = f"[[{self.link_id}]]"

        return f'<a class="link-ref" href={settings.TRACKER_URL}{note_url}?note_id={self.link_id} target="_blank">{link_text}</a>'  # noqa: E501

    @property
    def content_html(self) -> str:
        return self.content

    @property
    def tags_str(self) -> str:
        return " ".join(f"#{tag}" for tag in sorted(self.tags))

    @property
    def tags_html(self) -> str:
        return self._mark_tags_with_ref(self.tags_str, self.tags)


def get_distinct_chapters(notes: list[Note]) -> defaultdict[UUID, list[str]]:
    logger.debug("Getting distinct chapters")

    # chapters of the shown materials,
    #  it should help to create menu
    chapters: defaultdict[UUID, list[str]] = defaultdict(list)
    for note in notes:
        # the notes list is expected to be sorted
        if (chapter := note.chapter) not in chapters[note.material_id]:
            chapters[note.material_id].append(chapter)

    logger.debug("Distinct chapters got")
    return chapters


async def get_material_type(*, material_id: UUID | str) -> str | None:
    logger.debug("Getting material_id=%s type", material_id)
    if not material_id:
        return None

    stmt = sa.select(models.Materials.c.material_type).where(
        models.Materials.c.material_id == str(material_id),
    )

    async with database.session() as ses:
        if material_type := await ses.scalar(stmt):
            logger.debug("Material type got: %s", material_type)
            return material_type.name

    logger.debug("Material=%s has no type", material_id)
    return None


async def get_material_types() -> dict[str, enums.MaterialTypesEnum]:
    logger.debug("Getting material types")

    stmt = sa.select(models.Materials.c.material_id, models.Materials.c.material_type)

    async with database.session() as ses:
        types = {
            str(material_id): material_type
            for material_id, material_type in await ses.execute(stmt)
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


async def get_note(*, note_id: UUID | str) -> Note | None:
    logger.debug("Getting note_id='%s'", note_id)

    stmt = _get_note_stmt(note_id=note_id)

    async with database.session() as ses:
        if note := (await ses.execute(stmt)).one_or_none():
            logger.debug("Note got")
            return Note.model_validate(note, from_attributes=True)

    logger.debug("Note_id='%s' not found", note_id)
    return None


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


async def add_note(
    *,
    material_id: UUID,
    link_id: UUID | None,
    title: str | None,
    content: str,
    chapter: str,
    page: int,
    tags: list[str] | None,
) -> str:
    logger.debug("Adding note for material_id='%s'", material_id)

    values = {
        "material_id": str(material_id),
        "title": title,
        "content": content,
        "chapter": chapter,
        "page": page,
        "tags": tags or [],
        "link_id": str(link_id) if link_id else None,
    }

    stmt = models.Notes.insert().values(values).returning(models.Notes.c.note_id)

    async with database.session() as ses:
        note_id = await ses.scalar(stmt)

    logger.debug("Note_id='%s' added", note_id)
    return str(note_id)


async def update_note(
    *,
    note_id: UUID,
    material_id: str,
    link_id: UUID | None,
    title: str | None,
    content: str,
    page: int,
    chapter: str,
    tags: list[str] | None,
) -> None:
    logger.debug("Updating note_id='%s'", note_id)

    values = {
        "material_id": material_id,
        "title": title,
        "content": content,
        "page": page,
        "chapter": chapter,
        "tags": tags or [],
        "link_id": str(link_id) if link_id else None,
    }

    stmt = models.Notes.update().values(values).where(models.Notes.c.note_id == note_id)

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Note updated")


async def _del_or_restore(*, note_id: UUID, is_deleted: bool) -> None:
    values = {"is_deleted": is_deleted}
    stmt = models.Notes.update().values(values).where(models.Notes.c.note_id == note_id)

    async with database.session() as ses:
        await ses.execute(stmt)


async def delete_note(*, note_id: UUID) -> None:
    logger.debug("Deleting note_id='%s'", note_id)
    await _del_or_restore(note_id=note_id, is_deleted=True)
    logger.debug("Note deleted")


async def restore_note(*, note_id: UUID) -> None:
    logger.debug("Restoring note_id='%s'", note_id)
    await _del_or_restore(note_id=note_id, is_deleted=False)
    logger.debug("Note restored")


async def _get_tags() -> set[str]:
    logger.debug("Getting tags")

    stmt = sa.select(models.Notes.c.tags).where(models.Notes.c.tags != [])

    async with database.session() as ses:
        tags: list[str] = sum((await ses.scalars(stmt)).all(), [])

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
        tags: list[str] = sum((await ses.scalars(stmt)).all(), [])

    tags_counter = Counter(tags)
    logger.debug("Total %s unique tags got", len(tags_counter))

    # sort by frequency
    return [tag for tag, _ in tags_counter.most_common()]


async def get_possible_links(note: Note) -> list[Note]:
    """Get notes with which the given one might be linked.

    So possibility coeff = size of tags set intersection.
    """
    logger.debug("Getting possible links for note=%s, tags=%s", note.note_id, note.tags)

    stmt = (
        sa.select(models.Notes)
        .where(~models.Notes.c.is_deleted)
        .where(models.Notes.c.note_id != note.note_id)
        .where(
            sa.text(
                f"tags ?| array(SELECT jsonb_array_elements_text(tags) FROM notes WHERE note_id = '{note.note_id}')",  # noqa: S608, E501
            ),
        )
    )

    async with database.session() as ses:
        links = [
            Note.model_validate(link, from_attributes=True)
            for link in (await ses.execute(stmt)).all()
        ]

    # most possible first
    links.sort(key=lambda link: len(link.tags & note.tags), reverse=True)

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
    if not (link_id := notes[note_id].link_id) or link_id in even_added_notes:
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

    link_id = notes[note_id].link_id
    links_from = _get_links_from(note_id=note_id, notes=notes.values())

    if link_id:
        graph.add_nodes_from([_get_note_link(notes[link_id])])
        graph.add_edge(str(note_id), str(link_id))

        _link_cohesive_notes(graph, notes, link_id, visited=visited)

    # mark note as visited in reverse recursion road
    visited.add(note_id)

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

    nodes, edges = [], []

    for note in notes:
        nodes.append(_get_note_link(note))
        if note.link_id:
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


async def get_links_from(*, note_id: UUID | str) -> list[Note]:
    """Get notes which linked to the given one."""
    stmt = _get_note_stmt(link_id=note_id)

    async with database.session() as ses:
        return [
            Note.model_validate(row, from_attributes=True)
            for row in (await ses.execute(stmt)).all()
        ]


async def is_deleted(note_id: str) -> bool:
    stmt = sa.select(models.Notes.c.is_deleted).where(
        models.Notes.c.note_id == note_id,
    )

    async with database.session() as ses:
        if (r := await ses.scalar(stmt)) is None:
            raise ValueError(f"Note id={note_id} not found")

    return r
