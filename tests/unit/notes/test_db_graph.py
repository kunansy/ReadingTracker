from uuid import UUID

import networkx as nx
import pytest

from tests.unit.notes.conftest import (
    MATERIAL_ID,
    OTHER_MATERIAL_ID,
    build_note,
    by_id,
    note_id,
)
from tracker.notes import db


def _edge(src: int, dst: int) -> tuple[str, str]:
    return str(note_id(src)), str(note_id(dst))


def _node(number: int) -> str:
    return str(note_id(number))


def _attrs(number: int, material_id: UUID = MATERIAL_ID, **extra) -> dict:
    return {
        "title": f"note {number}",
        "material_id": str(material_id),
        "note_number": number,
        "label": f"note {number}...",
        **extra,
    }


class TestGetLinksFrom:
    def test_returns_notes_linked_to_the_given_one_in_input_order(self):
        notes = [build_note(3, link=1), build_note(2), build_note(4, link=1)]

        links = db._get_links_from(note_id=note_id(1), notes=notes)

        assert [link.note_id for link in links] == [note_id(3), note_id(4)]

    def test_returns_nothing_when_no_note_links_to_it(self):
        notes = [build_note(1, link=2), build_note(2)]

        assert db._get_links_from(note_id=note_id(1), notes=notes) == []

    def test_returns_nothing_for_empty_notes(self):
        assert db._get_links_from(note_id=note_id(1), notes=[]) == []

    def test_self_linked_note_links_to_itself(self):
        note = build_note(1, link=1)

        assert db._get_links_from(note_id=note_id(1), notes=[note]) == [note]


class TestGetNoteLink:
    def test_builds_json_safe_node(self):
        note = build_note(1, content="a &lt; b")

        assert db._get_note_link(note) == (
            _node(1),
            {
                "title": "a < b",
                "material_id": str(MATERIAL_ID),
                "note_number": 1,
                "label": "a < b...",
            },
        )

    def test_extra_attributes_are_added(self):
        _, attrs = db._get_note_link(build_note(1), color="red", shape="box")

        assert attrs == _attrs(1, color="red", shape="box")

    def test_note_fields_override_extra_attributes(self):
        _, attrs = db._get_note_link(build_note(1), title="overridden")

        assert attrs["title"] == "note 1"


class TestAddLinksTo:
    def test_follows_the_chain_of_links(self):
        notes = by_id(build_note(1, link=2), build_note(2, link=3), build_note(3))
        graph = nx.DiGraph()
        added: set[UUID] = set()

        db._add_links_to(graph, notes, note_id(1), added)

        assert set(graph.edges) == {_edge(1, 2), _edge(2, 3)}
        assert graph.nodes[_node(2)] == _attrs(2)
        assert graph.nodes[_node(3)] == _attrs(3)
        assert added == {note_id(2), note_id(3)}

    def test_note_without_link_adds_nothing(self):
        graph = nx.DiGraph()

        db._add_links_to(graph, by_id(build_note(1)), note_id(1), set())

        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0

    def test_already_added_link_is_skipped(self):
        notes = by_id(build_note(1, link=2), build_note(2, link=3), build_note(3))
        graph = nx.DiGraph()

        db._add_links_to(graph, notes, note_id(1), {note_id(2)})

        assert len(graph.edges) == 0

    def test_cycle_terminates(self):
        notes = by_id(build_note(1, link=2), build_note(2, link=1))
        graph = nx.DiGraph()

        db._add_links_to(graph, notes, note_id(1), set())

        assert sorted(graph.edges) == [_edge(1, 2), _edge(2, 1)]

    def test_self_link_terminates(self):
        graph = nx.DiGraph()

        db._add_links_to(graph, by_id(build_note(1, link=1)), note_id(1), set())

        assert list(graph.edges) == [_edge(1, 1)]

    def test_link_to_missing_note_does_not_crash(self):
        graph = nx.DiGraph()

        db._add_links_to(graph, by_id(build_note(1, link=9)), note_id(1), set())

        assert _node(9) not in graph.nodes or graph.nodes[_node(9)] == {}


class TestLinkNotes:
    # 1 -> 2 -> 3 <- 4, 5 -> 4, 6 is isolated
    def _notes(self) -> dict[UUID, db.Note]:
        return by_id(
            build_note(1, link=2),
            build_note(2, link=3),
            build_note(3),
            build_note(4, link=3),
            build_note(5, link=4),
            build_note(6),
        )

    @pytest.mark.parametrize("start", [1, 2, 3, 4, 5])
    def test_whole_component_is_linked_from_any_of_its_notes(self, start):
        graph = db.link_notes(note_id=note_id(start), notes=self._notes())

        assert set(graph.nodes) == {_node(number) for number in (1, 2, 3, 4, 5)}
        assert set(graph.edges) == {_edge(1, 2), _edge(2, 3), _edge(4, 3), _edge(5, 4)}

    def test_only_the_starting_note_is_colored(self):
        graph = db.link_notes(note_id=note_id(2), notes=self._notes())

        assert graph.nodes[_node(2)] == _attrs(2, color="black")
        assert graph.nodes[_node(1)] == _attrs(1)
        assert graph.nodes[_node(3)] == _attrs(3)

    def test_custom_color(self):
        graph = db.link_notes(note_id=note_id(6), notes=self._notes(), color="red")

        assert graph.nodes[_node(6)]["color"] == "red"

    def test_note_without_links_is_a_single_node(self):
        graph = db.link_notes(note_id=note_id(6), notes=self._notes())

        assert dict(graph.nodes(data=True)) == {_node(6): _attrs(6, color="black")}
        assert len(graph.edges) == 0

    def test_single_note_dict(self):
        graph = db.link_notes(note_id=note_id(1), notes=by_id(build_note(1)))

        assert list(graph.nodes) == [_node(1)]

    def test_unknown_note_id_raises_key_error(self):
        with pytest.raises(KeyError):
            db.link_notes(note_id=note_id(404), notes=self._notes())

    def test_empty_notes_raise_key_error(self):
        with pytest.raises(KeyError):
            db.link_notes(note_id=note_id(1), notes={})

    def test_cycle_terminates(self):
        notes = by_id(build_note(1, link=2), build_note(2, link=1))

        graph = db.link_notes(note_id=note_id(1), notes=notes)

        assert set(graph.edges) == {_edge(1, 2), _edge(2, 1)}

    def test_self_link_terminates(self):
        graph = db.link_notes(note_id=note_id(1), notes=by_id(build_note(1, link=1)))

        assert set(graph.edges) == {_edge(1, 1)}

    def test_link_to_missing_note_does_not_crash(self):
        graph = db.link_notes(note_id=note_id(1), notes=by_id(build_note(1, link=9)))

        assert graph.nodes[_node(1)] == _attrs(1, color="black")


class TestLinkAllNotes:
    def test_empty_list_gives_empty_graph(self):
        graph = db.link_all_notes([])

        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0

    def test_every_note_is_a_node_and_every_link_an_edge(self):
        notes = [build_note(1, link=2), build_note(2), build_note(3, link=2)]

        graph = db.link_all_notes(notes)

        assert dict(graph.nodes(data=True)) == {
            _node(1): _attrs(1),
            _node(2): _attrs(2),
            _node(3): _attrs(3),
        }
        assert list(graph.edges) == [_edge(1, 2), _edge(3, 2)]

    def test_notes_without_links_have_no_edges(self):
        graph = db.link_all_notes([build_note(1), build_note(2)])

        assert len(graph.nodes) == 2
        assert len(graph.edges) == 0

    def test_cycle_and_self_link_are_plain_edges(self):
        notes = [build_note(1, link=2), build_note(2, link=1), build_note(3, link=3)]

        graph = db.link_all_notes(notes)

        assert set(graph.edges) == {_edge(1, 2), _edge(2, 1), _edge(3, 3)}

    def test_link_to_missing_note_is_skipped(self):
        graph = db.link_all_notes([build_note(1, link=9)])

        assert dict(graph.nodes(data=True)) == {_node(1): _attrs(1)}
        assert list(graph.edges) == []


class TestCreateMaterialGraph:
    @pytest.mark.parametrize(
        ("material_notes", "notes"),
        [
            (set(), by_id(build_note(1))),
            ({note_id(1)}, {}),
            (set(), {}),
        ],
        ids=["no-material-notes", "no-notes", "nothing"],
    )
    def test_no_notes_raise_value_error(self, material_notes, notes):
        with pytest.raises(ValueError, match="No notes passed"):
            db.create_material_graph(
                material_id=MATERIAL_ID,
                material_notes=material_notes,
                notes=notes,
            )

    def test_components_of_every_material_note_are_composed(self):
        notes = by_id(
            build_note(1, link=2),
            build_note(2),
            build_note(3),
            build_note(4, material_id=OTHER_MATERIAL_ID),
        )

        graph = db.create_material_graph(
            material_id=MATERIAL_ID,
            material_notes={note_id(1), note_id(2), note_id(3)},
            notes=notes,
        )

        assert set(graph.nodes) == {_node(1), _node(2), _node(3)}
        assert list(graph.edges) == [_edge(1, 2)]

    def test_linked_notes_of_other_materials_are_included_and_colored_black(self):
        notes = by_id(
            build_note(1, link=2),
            build_note(2, material_id=OTHER_MATERIAL_ID),
            build_note(3, link=1, material_id=OTHER_MATERIAL_ID),
        )

        graph = db.create_material_graph(
            material_id=MATERIAL_ID,
            material_notes={note_id(1)},
            notes=notes,
        )

        assert dict(graph.nodes(data=True)) == {
            _node(1): _attrs(1, color=None),
            _node(2): _attrs(2, OTHER_MATERIAL_ID, color="black"),
            _node(3): _attrs(3, OTHER_MATERIAL_ID, color="black"),
        }
        assert set(graph.edges) == {_edge(1, 2), _edge(3, 1)}

    def test_material_notes_set_is_drained(self):
        material_notes = {note_id(1), note_id(2)}

        db.create_material_graph(
            material_id=MATERIAL_ID,
            material_notes=material_notes,
            notes=by_id(build_note(1, link=2), build_note(2)),
        )

        assert material_notes == set()

    def test_linked_material_notes_are_each_linked_again_current_behaviour(self, mocker):
        # graph node ids are strings while material_notes holds UUIDs, so discard() never matches
        link_notes = mocker.spy(db, "link_notes")

        db.create_material_graph(
            material_id=MATERIAL_ID,
            material_notes={note_id(1), note_id(2)},
            notes=by_id(build_note(1, link=2), build_note(2)),
        )

        assert link_notes.call_count == 2

    def test_link_to_missing_note_does_not_crash(self):
        graph = db.create_material_graph(
            material_id=MATERIAL_ID,
            material_notes={note_id(1)},
            notes=by_id(build_note(1, link=9)),
        )

        assert _node(1) in graph.nodes


class TestHighlightOtherMaterialNotes:
    def _graph(self) -> tuple[nx.DiGraph, dict[UUID, db.Note]]:
        notes = [build_note(1), build_note(2, material_id=OTHER_MATERIAL_ID)]
        return db.link_all_notes(notes), by_id(*notes)

    def test_only_notes_of_other_materials_get_the_color(self):
        graph, notes = self._graph()

        db._highlight_other_material_notes(
            graph=graph,
            material_id=MATERIAL_ID,
            notes=notes,
            color="red",
        )

        assert "color" not in graph.nodes[_node(1)]
        assert graph.nodes[_node(2)]["color"] == "red"

    def test_default_color_is_black(self):
        graph, notes = self._graph()

        db._highlight_other_material_notes(
            graph=graph,
            material_id=MATERIAL_ID,
            notes=notes,
        )

        assert graph.nodes[_node(2)]["color"] == "black"

    def test_empty_graph_is_left_empty(self):
        graph = nx.DiGraph()

        db._highlight_other_material_notes(
            graph=graph,
            material_id=MATERIAL_ID,
            notes={},
        )

        assert len(graph.nodes) == 0

    def test_node_missing_from_notes_raises_key_error_current_behaviour(self):
        graph = db.link_all_notes([build_note(1)])
        graph.add_edge(_node(1), _node(9))

        with pytest.raises(KeyError):
            db._highlight_other_material_notes(
                graph=graph,
                material_id=MATERIAL_ID,
                notes=by_id(build_note(1, link=9)),
            )


class TestCreateGraphic:
    def test_html_contains_every_node_id(self):
        graph = db.link_all_notes([build_note(1, link=2), build_note(2)])

        html = db.create_graphic(graph)

        assert html.startswith("<html>")
        assert f'"id": "{_node(1)}"' in html
        assert f'"id": "{_node(2)}"' in html
        assert f'"from": "{_node(1)}"' in html
        assert f'"to": "{_node(2)}"' in html

    def test_hover_interaction_is_enabled(self):
        html = db.create_graphic(db.link_all_notes([build_note(1)]))

        assert '"interaction": {"hover": true}' in html

    def test_empty_graph_renders_no_nodes(self):
        html = db.create_graphic(nx.DiGraph())

        assert html.startswith("<html>")
        assert "nodes = new vis.DataSet([]);" in html
        assert "edges = new vis.DataSet([]);" in html

    def test_kwargs_are_passed_to_the_network(self):
        html = db.create_graphic(nx.DiGraph(), height="123px", width="45%")

        assert "height: 123px;" in html
        assert "width: 45%;" in html

    def test_node_missing_from_notes_is_rendered(self):
        graph = db.link_all_notes([build_note(1)])
        graph.add_edge(_node(1), _node(9))

        html = db.create_graphic(graph)

        assert f'"id": "{_node(9)}"' in html
