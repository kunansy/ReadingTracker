import asyncio
import datetime
from collections import defaultdict
from typing import Any
from uuid import UUID

import networkx as nx
import sqlalchemy.sql as sa
from pyvis.network import Network

from tracker.common import database
from tracker.common.log import logger
from tracker.common.schemas import CustomBaseModel
from tracker.models import models, enums
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
    def info(self) -> str:
        return f"ID: {self.note_id}\n" \
               f"Number: {self.note_number}\n" \
               f"Material ID: {self.material_id}\n\n" \
               f"{self}"

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


@database.cache
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


@database.cache
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


@database.cache
async def get_material_with_notes_titles() -> dict[str, str]:
    """ Get materials that have a note. """
    logger.debug("Getting material with note titles")

    stmt = sa.select([sa.text("distinct on (materials.material_id) materials.material_id"),
                      models.Materials.c.title])\
        .join(models.Notes,
              models.Notes.c.material_id == models.Materials.c.material_id)

    async with database.session() as ses:
        titles = {
            str(row.material_id): row.title
            for row in (await ses.execute(stmt)).mappings().all()
        }

    logger.debug("Material with note titles got")
    return titles


def _get_note_stmt(*,
                   note_id: UUID | str | None = None,
                   material_id: UUID | str | None = None) -> sa.Select:
    links_count_query = "(select count(1) as links_count from notes where link_id = n.note_id)"

    notes_model = models.Notes.alias('n')
    stmt = sa.select([notes_model, sa.text(links_count_query)]) \
        .where(~notes_model.c.is_deleted) \
        .order_by(notes_model.c.note_number)

    if note_id:
        stmt = stmt.where(notes_model.c.note_id == str(note_id))
    if material_id:
        stmt = stmt.where(notes_model.c.material_id == str(material_id))

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
                   note_id: UUID) -> Note | None:
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

    values = {
        "is_deleted": True
    }
    stmt = models.Notes \
        .update().values(values) \
        .where(models.Notes.c.note_id == note_id)

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Note deleted")


async def get_tags(*,
                   material_id: str | UUID | None = None) -> set[str]:
    logger.debug("Getting tags for material_id=%s", material_id)

    stmt = sa.select(models.Notes.c.tags)\
        .where(models.Notes.c.tags != [])

    if material_id:
        stmt = stmt.where(models.Notes.c.material_id == str(material_id))

    async with database.session() as ses:
        tags: list[str] = sum([
            row[0]
            for row in (await ses.execute(stmt)).all()
        ], [])

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

    logger.debug("%s possible links got")
    return links


def _get_note_links(*,
                    note_id: str,
                    notes: dict[str, Note]) -> list[str]:
    """ Get all notes linked with the given one """

    return [
        note_id_
        for note_id_, note in notes.items()
        if note.link_id == note_id
    ]


def _get_note_link(note: Note, **attrs) -> tuple[str, dict[str, Any]]:
    return (note.note_id, {
        **attrs,
        "material_id": note.material_id,
        "note_number": note.note_number,
        "label": note.content_md[:50],
    })


def link_notes(*,
               note_id: str,
               notes: dict[str, Note]) -> nx.Graph:
    logger.debug("Linking %s notes from the %s", len(notes), note_id)

    nodes, edges = [], []
    nodes += [_get_note_link(notes[note_id], color="black")]

    note = notes[note_id]
    while True:
        if link_id := note.link_id:
            nodes += [_get_note_link(notes[link_id])]
            edges += [(note.note_id, link_id)]
        else:
            break

        note = notes[link_id]

    # TODO
    if links := _get_note_links(note_id=note_id, notes=notes):
        nodes += [
            _get_note_link(notes[link_id])
            for link_id in links
        ]
        edges += [(note_id, link) for link in links]

    graph = nx.Graph()
    graph.add_nodes_from(nodes)
    graph.add_edges_from(edges)

    logger.debug("Notes linked, %s nodes, %s edges",
                 len(graph.nodes), len(graph.edges))

    return graph


def link_all_notes(notes: list[Note]) -> nx.Graph:
    if not notes:
        return nx.Graph()

    logger.debug("Linking all %s notes started", len(notes))

    nodes, edges = [], []

    for note in notes:
        nodes += [_get_note_link(note)]
        if note.link_id:
            edges += [(note.link_id, note.note_id)]

    graph = nx.Graph()
    graph.add_nodes_from(nodes)
    graph.add_edges_from(edges)

    logger.debug("%s notes linked", len(notes))
    return graph


def create_graphic(graph: nx.Graph, **kwargs) -> str:
    logger.debug("Creating graphic for graph with %s nodes, %s edges",
                 len(graph.nodes), len(graph.edges))

    net = Network(
        cdn_resources="remote",
        directed=True,
        neighborhood_highlight=True,
        **kwargs
    )
    net.from_nx(graph)

    net.show("tmp.html")
    with open('tmp.html') as f:
        resp = f.read()

    logger.debug("Graphic created")
    return resp


async def get_sorted_tags(*,
                          material_id: str | UUID | None) -> list[str]:
    """ Get tags especially for the material, means there should be tags
    from the notes for the material in the beginning of the result list. """
    logger.debug("Getting sorted tags for material_id=%s", material_id)

    if not material_id:
        tags = await get_tags()
        return list(sorted(tags))

    async with asyncio.TaskGroup() as tg:
        get_tags_task = tg.create_task(get_tags())
        get_materials_tags = tg.create_task(get_tags(material_id=material_id))

    tags, materials_tags = get_tags_task.result(), get_materials_tags.result()
    tags -= materials_tags

    result = sorted(materials_tags) + sorted(tags)
    logger.debug("%s sorted tags got", len(result))

    return result
