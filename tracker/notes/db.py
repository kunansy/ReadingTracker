import asyncio
import datetime
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID

import networkx as nx
import sqlalchemy.sql as sa
from pyvis.network import Network

from tracker.common import database
from tracker.common.log import logger
from tracker.common.schemas import CustomBaseModel
from tracker.models import enums, models
from tracker.notes import schemas


class Note(CustomBaseModel):
    note_id: str
    link_id: str | None
    material_id: str
    content: str
    added_at: datetime.datetime
    chapter: int
    page: int
    tags: set[str]
    is_deleted: bool
    note_number: int
    links_count: int | None

    @property
    def content_md(self) -> str:
        return str(self)

    @property
    def short_content(self) -> str:
        return f"{self.content_md[:50]}..."

    @property
    def info(self) -> str:
        return (f"ID: {self.note_id}\n"
                f"Number: {self.note_number}\n"
                f"Material ID: {self.material_id}\n\n"
                f"{self}")

    def highlight(self, from_: str, to: str) -> None:
        self.content = self.content.replace(from_, to)

    def __str__(self) -> str:
        return schemas.demark_note(self.content)


def get_distinct_chapters(notes: list[Note]) -> defaultdict[str, set[int]]:
    logger.debug("Getting distinct chapters")

    # chapters of the shown materials,
    #  it should help to create menu
    chapters = defaultdict(set)
    for note in notes:
        chapters[note.material_id].add(note.chapter)

    logger.debug("Distinct chapters got")
    return chapters


async def get_material_type(*,
                            material_id: UUID | str) -> str | None:
    logger.debug("Getting material_id=%s type", material_id)

    stmt = sa.select(models.Materials.c.material_type)\
        .where(models.Materials.c.material_id == str(material_id))

    async with database.session() as ses:
        if material_type := await ses.scalar(stmt):
            logger.debug("Material type got: %s", material_type)
            return material_type.name

    logger.debug("Material=%s has no type", material_id)
    return None


async def get_material_types() -> dict[str, enums.MaterialTypesEnum]:
    logger.debug("Getting material types")

    stmt = sa.select([models.Materials.c.material_id,
                      models.Materials.c.material_type])

    async with database.session() as ses:
        types = {
            str(material_id): material_type
            for material_id, material_type in await ses.execute(stmt)
        }

    logger.debug("Material types got")
    return types


async def get_material_titles() -> dict[str, str]:
    logger.debug("Getting material titles")

    stmt = sa.select([models.Materials.c.material_id,
                      models.Materials.c.title])

    async with database.session() as ses:
        titles = {
            str(row.material_id): row.title
            for row in (await ses.execute(stmt)).mappings().all()
        }

    logger.debug("Titles got")
    return titles


async def get_material_with_notes_titles() -> dict[str, str]:
    """ Get materials that have a note. """
    logger.debug("Getting material with note titles")

    stmt = sa.select([sa.text("distinct on (materials.material_id) materials.material_id"),
                      models.Materials.c.title])\
        .join(models.Notes,
              models.Notes.c.material_id == models.Materials.c.material_id)\
        .where(~models.Notes.c.is_deleted)

    async with database.session() as ses:
        titles = {
            str(row.material_id): row.title
            for row in (await ses.execute(stmt)).mappings().all()
        }

    logger.debug("Material with note titles got")
    return titles


def _get_note_stmt(*,
                   note_id: UUID | str | None = None,
                   material_id: UUID | str | None = None,
                   link_id: UUID | str | None = None) -> sa.Select:
    links_count_query = "(select count(1) as links_count from notes where link_id = n.note_id)"

    notes_model = models.Notes.alias('n')
    stmt = sa.select([notes_model, sa.text(links_count_query)]) \
        .where(~notes_model.c.is_deleted) \
        .order_by(notes_model.c.note_number)

    if note_id:
        stmt = stmt.where(notes_model.c.note_id == str(note_id))
    if material_id:
        stmt = stmt.where(notes_model.c.material_id == str(material_id))
    if link_id:
        stmt = stmt.where(notes_model.c.link_id == str(link_id))

    return stmt


async def get_notes(*,
                    material_id: UUID | str | None = None) -> list[Note]:
    logger.debug("Getting notes material_id=%s", material_id)

    stmt = _get_note_stmt(material_id=material_id)

    async with database.session() as ses:
        notes = [
            Note(**row)
            for row in (await ses.execute(stmt)).mappings().all()
        ]
    logger.debug("%s notes got", len(notes))
    return notes


async def get_note(*,
                   note_id: UUID | str) -> Note | None:
    logger.debug("Getting note_id='%s'", note_id)

    stmt = _get_note_stmt(note_id=note_id)

    async with database.session() as ses:
        if note := (await ses.execute(stmt)).mappings().one_or_none():
            logger.debug("Note got")
            return Note(**note)

    logger.debug("Note_id='%s' not found", note_id)
    return None


async def get_all_notes_count() -> dict[str, int]:
    """ Get notes count for the materials. """

    logger.debug("Getting notes count for all materials")

    stmt = sa.select([models.Notes.c.material_id.label('material_id'),
                      sa.func.count(1).label('count')]) \
        .select_from(models.Notes) \
        .where(~models.Notes.c.is_deleted) \
        .group_by(models.Notes.c.material_id)

    async with database.session() as ses:
        return {
            str(material_id): count
            for material_id, count in (await ses.execute(stmt)).all()
        }


async def add_note(*,
                   material_id: UUID,
                   link_id: UUID | None,
                   content: str,
                   chapter: int,
                   page: int,
                   tags: list[str],
                   date: datetime.datetime | None = None) -> str:
    date = date or database.utcnow()
    logger.debug("Adding note for material_id='%s'", material_id)

    values = {
        'material_id': str(material_id),
        'content': content,
        'chapter': chapter,
        'page': page,
        'added_at': date,
        'tags': tags,
        'link_id': str(link_id) if link_id else None
    }

    stmt = models.Notes.\
        insert().values(values)\
        .returning(models.Notes.c.note_id)

    async with database.session() as ses:
        note_id = await ses.scalar(stmt)

    logger.debug("Note_id='%s' added", note_id)
    return str(note_id)


async def update_note(*,
                      note_id: str,
                      link_id: UUID | None,
                      content: str,
                      page: int,
                      chapter: int,
                      tags: list[str]) -> None:
    logger.debug("Updating note_id='%s'", note_id)

    values = {
        'content': content,
        'page': page,
        'chapter': chapter,
        'tags': tags,
        'link_id': str(link_id) if link_id else None
    }

    stmt = models.Notes. \
        update().values(values) \
        .where(models.Notes.c.note_id == note_id)

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Note updated")


async def _del_or_restore(*,
                          note_id: str,
                          is_deleted: bool) -> None:
    values = {
        "is_deleted": is_deleted
    }
    stmt = models.Notes \
        .update().values(values) \
        .where(models.Notes.c.note_id == note_id)

    async with database.session() as ses:
        await ses.execute(stmt)


async def delete_note(*,
                      note_id: str) -> None:
    logger.debug("Deleting note_id='%s'", note_id)
    await _del_or_restore(note_id=note_id, is_deleted=True)
    logger.debug("Note deleted")


async def restore_note(*,
                       note_id: str) -> None:
    logger.debug("Restoring note_id='%s'", note_id)
    await _del_or_restore(note_id=note_id, is_deleted=False)
    logger.debug("Note restored")


async def get_tags(*,
                   material_id: str | UUID | None = None) -> set[str]:
    logger.debug("Getting tags for material_id=%s", material_id)

    stmt = sa.select(models.Notes.c.tags)\
        .where(models.Notes.c.tags != [])

    if material_id:
        stmt = stmt.where(models.Notes.c.material_id == str(material_id))

    async with database.session() as ses:
        tags: list[str] = sum((await ses.scalars(stmt)).all(), [])

    tags_set = set(tags)
    logger.debug("Total %s unique tags got", len(tags_set))

    return tags_set


async def get_possible_links(note: Note) -> list[Note]:
    """ Get notes with which the given one might be linked.
     So possibility coeff = size of tags set intersection. """

    logger.debug("Getting possible links for note=%s, tags=%s",
                 note.note_id, note.tags)

    stmt = sa.select(models.Notes) \
        .where(~models.Notes.c.is_deleted) \
        .where(models.Notes.c.note_id != note.note_id) \
        .where(sa.text(f"tags ?| array(SELECT jsonb_array_elements_text(tags) FROM notes WHERE note_id = '{note.note_id}')"))

    async with database.session() as ses:
        links = [
            Note(**link)
            for link in (await ses.execute(stmt)).mappings().all()
        ]

    # most possible first
    links.sort(key=lambda link: len(link.tags & note.tags), reverse=True)

    logger.debug("%s possible links got", len(links))
    return links


def _get_links_from(*,
                    note_id: str,
                    notes: Iterable[Note]) -> list[Note]:
    """ Get all notes linked with the given one """

    return [
        note
        for note in notes
        if note.link_id == note_id
    ]


def _get_note_link(note: Note, **attrs) -> tuple[str, dict[str, Any]]:
    return (note.note_id, {
        **attrs,
        "material_id": note.material_id,
        "note_number": note.note_number,
        "label": note.short_content,
    })


def _add_links_to(graph: nx.DiGraph,
                  notes: dict[str, Note],
                  note_id: str,
                  even_added_notes: set[str]) -> None:
    if not (link_id := notes[note_id].link_id) or link_id in even_added_notes:
        return None

    # to resolve circular recursion
    even_added_notes.add(link_id)

    graph.add_nodes_from([_get_note_link(notes[link_id])])
    graph.add_edge(note_id, link_id)

    _add_links_to(graph, notes, link_id, even_added_notes)


def _link_cohesive_notes(graph: nx.DiGraph,
                         notes: dict[str, Note],
                         note_id: str,
                         *,
                         visited: set[str]) -> None:
    """ Iter over graph and find all note links """

    if note_id in visited:
        return None

    link_id = notes[note_id].link_id
    links_from = _get_links_from(note_id=note_id, notes=notes.values())

    if link_id:
        graph.add_nodes_from([_get_note_link(notes[link_id])])
        graph.add_edge(note_id, link_id)

        _link_cohesive_notes(graph, notes, link_id, visited=visited)

    # mark note as visited in reverse recursion road
    visited.add(note_id)

    for link in links_from:
        graph.add_nodes_from([_get_note_link(notes[link.note_id])])
        graph.add_edge(link.note_id, note_id)

        _link_cohesive_notes(graph, notes, link.note_id, visited=visited)


def link_notes(*,
               note_id: str,
               notes: dict[str, Note]) -> nx.DiGraph:
    logger.debug("Linking %s notes from the %s", len(notes), note_id)

    graph = nx.DiGraph()
    graph.add_nodes_from([_get_note_link(notes[note_id])], color='black')

    # link together all cohesive notes, which bounds with the given one
    _link_cohesive_notes(graph, notes, note_id, visited=set())

    logger.debug("Notes linked, %s nodes, %s edges",
                 len(graph.nodes), len(graph.edges))

    return graph


def link_all_notes(notes: list[Note]) -> nx.DiGraph:
    if not notes:
        return nx.DiGraph()

    logger.debug("Linking all %s notes started", len(notes))

    nodes, edges = [], []

    for note in notes:
        nodes += [_get_note_link(note)]
        if note.link_id:
            edges += [(note.note_id, note.link_id)]

    graph = nx.DiGraph()
    graph.add_nodes_from(nodes)
    graph.add_edges_from(edges)

    logger.debug("%s notes linked", len(notes))
    return graph


def create_graphic(graph: nx.DiGraph, **kwargs) -> str:
    logger.debug("Creating graphic for graph with %s nodes, %s edges",
                 len(graph.nodes), len(graph.edges))

    net = Network(
        cdn_resources="remote",
        directed=True,
        neighborhood_highlight=True,
        **kwargs
    )
    net.options = {"interaction": {"hover": True}}
    net.from_nx(graph)

    tmp_file = Path("tmp.html")

    net.show(str(tmp_file))
    resp = tmp_file.read_text()

    tmp_file.unlink()

    logger.debug("Graphic created")
    return resp


async def get_sorted_tags(*,
                          material_id: str | UUID | None) -> list[str]:
    """ Get tags especially for the material, means there should be tags
    from the notes for the material in the beginning of the result list. """
    logger.debug("Getting sorted tags for material_id=%s", material_id)

    if not material_id:
        tags = await get_tags()
        return sorted(tags)

    async with asyncio.TaskGroup() as tg:
        get_tags_task = tg.create_task(get_tags())
        get_materials_tags = tg.create_task(get_tags(material_id=material_id))

    tags, materials_tags = get_tags_task.result(), get_materials_tags.result()
    tags -= materials_tags

    result = sorted(materials_tags) + sorted(tags)
    logger.debug("%s sorted tags got", len(result))

    return result


async def get_links_from(*,
                         note_id: UUID | str) -> list[Note]:
    """ Get notes which linked to the given one """
    stmt = _get_note_stmt(link_id=note_id)

    async with database.session() as ses:
        return [
            Note(**row)
            for row in (await ses.execute(stmt)).mappings().all()
        ]
