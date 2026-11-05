"""The pure models of the workbench (src/verdict/static/model.js), run in Node: layout, editor groups, terminal panes, keys, find, outline, diff."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "harness.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


def call(fn, *args, module="model"):
    done = subprocess.run(["node", str(HARNESS), "call"], input=json.dumps({"module": module, "fn": fn, "args": list(args)}), capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


leaf = lambda i: {"leaf": i}
row = lambda *children, sizes=None: {"dir": "row", "children": list(children), "sizes": sizes or [1] * len(children)}
column = lambda *children, sizes=None: {"dir": "column", "children": list(children), "sizes": sizes or [1] * len(children)}


# ---------------------------------------------------------------- a grid of leaves (editor groups, terminal panes)


def test_splitting_the_only_leaf_makes_a_row_or_a_column_and_the_new_one_goes_on_the_side_asked():
    assert call("gridSplit", leaf("a"), "a", "right", "b") == row(leaf("a"), leaf("b"))
    assert call("gridSplit", leaf("a"), "a", "left", "b") == row(leaf("b"), leaf("a"))
    assert call("gridSplit", leaf("a"), "a", "down", "b") == column(leaf("a"), leaf("b"))
    assert call("gridSplit", leaf("a"), "a", "up", "b") == column(leaf("b"), leaf("a"))
    assert call("gridSplit", leaf("a"), "zzz", "right", "b") == leaf("a")                            # no such leaf: nothing changes
    assert call("gridSplit", None, "a", "right", "b") == leaf("b")


def test_splitting_in_the_direction_of_the_row_adds_a_sibling_that_takes_half_of_the_room():
    two = row(leaf("a"), leaf("b"), sizes=[2, 1])
    assert call("gridSplit", two, "a", "right", "c") == row(leaf("a"), leaf("c"), leaf("b"), sizes=[1, 1, 1])
    assert call("gridSplit", two, "b", "left", "c") == row(leaf("a"), leaf("c"), leaf("b"), sizes=[2, 0.5, 0.5])


def test_splitting_across_the_row_nests_a_column_in_the_place_of_the_leaf():
    two = row(leaf("a"), leaf("b"))
    assert call("gridSplit", two, "b", "down", "c") == row(leaf("a"), column(leaf("b"), leaf("c")))
    assert call("gridLeaves", call("gridSplit", two, "b", "down", "c")) == ["a", "b", "c"]


def test_removing_a_leaf_gives_its_room_to_the_others_and_flattens_what_is_left():
    assert call("gridRemove", row(leaf("a"), leaf("b")), "a") == leaf("b")
    assert call("gridRemove", leaf("a"), "a") is None
    assert call("gridRemove", row(leaf("a"), column(leaf("b"), leaf("c"))), "c") == row(leaf("a"), leaf("b"))
    assert call("gridRemove", row(leaf("a"), leaf("b"), leaf("c"), sizes=[1, 2, 3]), "b") == row(leaf("a"), leaf("c"), sizes=[1, 3])
    # a column that is left with a row inside a row merges into it
    nested = row(leaf("a"), column(leaf("x"), row(leaf("b"), leaf("c"))))
    assert call("gridRemove", nested, "x") == row(leaf("a"), leaf("b"), leaf("c"), sizes=[1, 0.5, 0.5])


def test_the_neighbour_in_a_direction():
    grid = row(leaf("a"), column(leaf("b"), leaf("c")))
    assert [call("gridNeighbor", grid, "a", d) for d in ("right", "left", "up", "down")] == ["b", None, None, None]
    assert [call("gridNeighbor", grid, "b", d) for d in ("left", "down", "up", "right")] == ["a", "c", None, None]
    assert [call("gridNeighbor", grid, "c", d) for d in ("left", "up", "down")] == ["a", "b", None]
    assert call("gridNeighbor", grid, "nope", "left") is None and call("gridNeighbor", None, "a", "left") is None
    deep = row(column(leaf("p"), leaf("q")), column(leaf("r"), leaf("s")))
    assert call("gridNeighbor", deep, "q", "right") == "r" and call("gridNeighbor", deep, "s", "left") == "p"
    loose = row(row(leaf("a"), leaf("b")), leaf("c"))                         # (a split inside a split of the same direction, as an old save could hold)
    assert call("gridNeighbor", loose, "c", "left") == "b" and call("gridNeighbor", row(leaf("c"), row(leaf("a"), leaf("b"))), "c", "right") == "a"


def test_sizes_can_be_set_for_a_split_and_equalised_and_nonsense_is_ignored():
    grid = row(leaf("a"), column(leaf("b"), leaf("c")))
    assert call("gridSetSizes", grid, [], [3, 1]) == row(leaf("a"), column(leaf("b"), leaf("c")), sizes=[3, 1])
    assert call("gridSetSizes", grid, [1], [1, 4])["children"][1]["sizes"] == [1, 4]
    for bad in ([1], [1, 0], [1, -2], [1, "x"], [1, None]):
        assert call("gridSetSizes", grid, [], bad) == grid
    assert call("gridSetSizes", grid, [5, 5], [1, 1]) == grid
    assert call("gridEqualize", row(leaf("a"), leaf("b"), sizes=[5, 1])) == row(leaf("a"), leaf("b"))


# ---------------------------------------------------------------- the layout


REGISTRY = {"containers": [
    {"id": "explorer", "title": "Explorer", "location": "sidebar", "order": 1, "views": [{"id": "open", "title": "Open Editors", "collapsed": True}, {"id": "files", "title": "Files"}, {"id": "outline", "title": "Outline", "collapsed": True}]},
    {"id": "search", "title": "Search", "location": "sidebar", "order": 2, "views": [{"id": "find", "title": "Search"}]},
    {"id": "run", "title": "Run", "location": "sidebar", "order": 3, "views": [{"id": "actions", "title": "Run"}]},
    {"id": "problems", "title": "Problems", "location": "panel", "order": 1, "views": [{"id": "checklist", "title": "Checklist"}]},
    {"id": "output", "title": "Output", "location": "panel", "order": 2, "views": [{"id": "log", "title": "Output"}]},
    {"id": "terminal", "title": "Terminal", "location": "panel", "order": 3, "views": [{"id": "shells", "title": "Terminal"}]},
]}


def default():
    return call("layoutDefault", REGISTRY)


def test_the_default_layout_puts_each_container_where_the_registry_says_in_the_order_given():
    layout = default()
    assert layout["locations"]["sidebar"]["order"] == ["explorer", "search", "run"] and layout["locations"]["sidebar"]["active"] == "explorer"
    assert layout["locations"]["panel"]["order"] == ["problems", "output", "terminal"] and layout["locations"]["secondary"]["order"] == []
    assert layout["locations"]["secondary"]["visible"] is False and layout["locations"]["sidebar"]["visible"] and layout["locations"]["panel"]["position"] == "bottom"
    assert layout["containers"]["explorer"]["views"] == ["open", "files", "outline"]
    assert layout["views"]["open"] == {"collapsed": True} and layout["views"]["files"] == {"collapsed": False}


def test_moving_a_container_to_another_place_shows_it_there_and_the_one_beside_it_takes_over_where_it_was():
    moved = call("layoutMoveContainer", default(), "search", "panel", 1)
    assert moved["locations"]["panel"]["order"] == ["problems", "search", "output", "terminal"] and moved["locations"]["panel"]["active"] == "search"
    assert moved["locations"]["sidebar"]["order"] == ["explorer", "run"] and moved["locations"]["sidebar"]["active"] == "explorer"
    first = call("layoutMoveContainer", default(), "explorer", "secondary")
    assert first["locations"]["sidebar"]["active"] == "search" and first["locations"]["secondary"] == {"order": ["explorer"], "active": "explorer", "visible": True, "size": 300}
    assert call("layoutMoveContainer", default(), "search", "nowhere") == default() and call("layoutMoveContainer", default(), "ghost", "panel") == default()
    reordered = call("layoutMoveContainer", default(), "run", "sidebar", 0)
    assert reordered["locations"]["sidebar"]["order"] == ["run", "explorer", "search"]


def test_moving_a_view_to_a_container_and_the_container_it_leaves_disappears_when_empty():
    layout = call("layoutMoveView", default(), "find", "explorer", 1)
    assert layout["containers"]["explorer"]["views"] == ["open", "find", "files", "outline"]
    assert "search" not in layout["containers"] and layout["locations"]["sidebar"]["order"] == ["explorer", "run"]
    assert layout["views"]["find"] == {"collapsed": False} and layout["locations"]["sidebar"]["active"] == "explorer"
    inside = call("layoutMoveView", default(), "outline", "explorer", 0)
    assert inside["containers"]["explorer"]["views"] == ["outline", "open", "files"]
    assert call("layoutMoveView", default(), "ghost", "explorer") == default() and call("layoutMoveView", default(), "find", "ghost") == default()


def test_a_view_dragged_out_becomes_a_container_of_its_own_unless_it_was_alone():
    layout = call("layoutViewToNewContainer", default(), "outline", "secondary", "Outline")
    assert layout["containers"]["custom-outline"] == {"views": ["outline"]} and layout["custom"]["custom-outline"] == {"title": "Outline"}
    assert layout["containers"]["explorer"]["views"] == ["open", "files"] and layout["locations"]["secondary"]["order"] == ["custom-outline"]
    assert layout["locations"]["secondary"]["visible"] is True
    alone = call("layoutViewToNewContainer", default(), "find", "panel", "Search")
    assert "custom-find" not in alone["containers"] and alone["locations"]["panel"]["order"] == ["problems", "output", "terminal", "search"]       # the whole container moved
    assert call("layoutViewToNewContainer", default(), "checklist", "panel", "x") == default()                                                    # it is alone, and already there


def test_toggling_resizing_and_the_panel_position():
    hidden = call("layoutToggle", default(), "sidebar")
    assert hidden["locations"]["sidebar"]["visible"] is False and call("layoutToggle", hidden, "sidebar")["locations"]["sidebar"]["visible"] is True
    assert call("layoutToggle", default(), "secondary", True)["locations"]["secondary"]["visible"] is True
    maximized = call("layoutSet", default(), "maximized", True)
    assert maximized["locations"]["panel"]["maximized"] is True and call("layoutToggle", maximized, "panel")["locations"]["panel"]["maximized"] is False
    assert call("layoutSetPanelPosition", default(), "right")["locations"]["panel"]["position"] == "right"
    assert call("layoutSetPanelPosition", default(), "top") == default()
    assert call("layoutResize", default(), "sidebar", 5000)["locations"]["sidebar"]["size"] == 900
    assert call("layoutResize", default(), "sidebar", 10)["locations"]["sidebar"]["size"] == 170
    assert call("layoutResize", default(), "panel", 333.4)["locations"]["panel"]["size"] == 333
    assert call("layoutResize", default(), "panel", None)["locations"]["panel"]["size"] == 280
    assert call("layoutSet", default(), "sidebarSide", "right")["sidebarSide"] == "right" and call("layoutSet", default(), "sidebarSide", "up")["sidebarSide"] == "left"
    assert call("layoutSet", default(), "minimap", False)["minimap"] is False and "bogus" not in call("layoutSet", default(), "bogus", True)


def test_revealing_a_view_shows_its_container_wherever_it_is_and_opens_it():
    moved = call("layoutMoveContainer", default(), "search", "secondary")
    hidden = call("layoutToggle", moved, "secondary", False)
    shown = call("layoutRevealView", call("layoutToggleCollapsed", hidden, "find", True), "find")
    assert shown["locations"]["secondary"]["visible"] and shown["locations"]["secondary"]["active"] == "search" and shown["views"]["find"]["collapsed"] is False
    assert call("layoutRevealView", default(), "ghost") == default()
    assert call("layoutToggleCollapsed", default(), "files")["views"]["files"]["collapsed"] is True
    assert call("layoutSetActive", default(), "sidebar", "run")["locations"]["sidebar"]["active"] == "run" and call("layoutSetActive", default(), "sidebar", "output") == default()


def test_zen_mode_shows_nothing_but_the_editor_without_forgetting_the_layout():
    zen = call("layoutSet", default(), "zen", True)
    effective = call("layoutEffective", zen)
    assert not effective["activityBar"] and not effective["statusBar"] and not effective["titleBar"]
    assert not any(effective["locations"][w]["visible"] for w in ("sidebar", "secondary", "panel"))
    assert zen["locations"]["sidebar"]["visible"] is True and call("layoutEffective", default()) == default()


def test_what_was_saved_is_made_valid_for_the_views_that_exist_now():
    saved = call("layoutMoveContainer", default(), "search", "panel", 0)
    assert call("layoutReconcile", saved, REGISTRY) == saved                                      # a good layout comes back as it was
    for junk in (None, 7, "x", [], {}, {"v": 1}, {"v": 2, "locations": 5, "containers": []}, {**saved, "v": 3}, {**saved, "v": 1}):
        assert call("layoutReconcile", junk, REGISTRY) == default()


def test_reconcile_drops_the_unknown_adds_the_missing_and_never_holds_a_thing_twice():
    saved = default()
    saved["locations"]["sidebar"]["order"] = ["explorer", "ghost", "search", "search", "run"]
    saved["locations"]["panel"]["order"] = ["problems", "run", "output"]                            # run is also in the side bar: the first place wins
    saved["containers"]["explorer"]["views"] = ["files", "files", "ghost-view", "find"]             # find belongs to search too; open and outline are lost
    saved["containers"]["ghost"] = {"views": ["files"]}
    fixed = call("layoutReconcile", saved, REGISTRY)
    assert fixed["locations"]["sidebar"]["order"] == ["explorer", "run"] and "run" not in fixed["locations"]["panel"]["order"]      # search lost its only view: gone
    assert fixed["locations"]["panel"]["order"] == ["problems", "output", "terminal"]                # terminal was missing: back in its place
    assert fixed["containers"]["explorer"]["views"] == ["files", "find", "open", "outline"]           # open and outline were lost: back home, after what was there
    assert "search" not in fixed["containers"] and [c for c, v in fixed["containers"].items() if "find" in v["views"]] == ["explorer"]
    every_view = sorted(v for c in fixed["containers"].values() for v in c["views"])
    assert every_view == sorted(["open", "files", "outline", "find", "actions", "checklist", "log", "shells"])
    placed = [c for w in ("sidebar", "secondary", "panel") for c in fixed["locations"][w]["order"]]
    assert sorted(placed) == sorted(set(placed)) == sorted(fixed["containers"])


def test_reconcile_keeps_custom_containers_with_a_title_and_a_view_and_clamps_what_was_typed():
    saved = call("layoutViewToNewContainer", default(), "outline", "secondary", "Outline")
    saved["locations"]["sidebar"]["size"] = 99999
    saved["locations"]["panel"]["size"] = "big"
    saved["locations"]["panel"]["position"] = "top"
    saved["locations"]["sidebar"]["active"] = "gone"
    fixed = call("layoutReconcile", saved, REGISTRY)
    assert fixed["custom"] == {"custom-outline": {"title": "Outline"}} and fixed["locations"]["secondary"]["order"] == ["custom-outline"]
    assert fixed["locations"]["sidebar"]["size"] == 900 and fixed["locations"]["panel"]["size"] == 280 and fixed["locations"]["panel"]["position"] == "bottom"
    assert fixed["locations"]["sidebar"]["active"] == "explorer"
    saved["custom"]["custom-outline"] = {"title": 5}
    gone = call("layoutReconcile", saved, REGISTRY)
    assert "custom-outline" not in gone["containers"] and "outline" in gone["containers"]["explorer"]["views"]                  # the view goes home


def test_a_view_that_a_newer_version_added_is_put_in_its_container():
    saved = default()
    registry = json.loads(json.dumps(REGISTRY))
    registry["containers"][1]["views"].append({"id": "history", "title": "History"})
    fixed = call("layoutReconcile", saved, registry)
    assert fixed["containers"]["search"]["views"] == ["find", "history"] and fixed["views"]["history"] == {"collapsed": False}


# ---------------------------------------------------------------- editor groups


def opened(*keys, group=None):
    state = call("groupsNew")
    for key in keys:
        state = call("groupsOpen", state, key, group)
    return state


def test_opening_tabs_fills_the_active_group_and_the_last_one_opened_is_in_front():
    state = opened("a", "b", "c")
    assert state["groups"]["g1"] == {"tabs": ["a", "b", "c"], "active": "c", "history": ["a", "b", "c"]}
    again = call("groupsOpen", state, "a")
    assert again["groups"]["g1"]["tabs"] == ["a", "b", "c"] and again["groups"]["g1"]["active"] == "a" and again["groups"]["g1"]["history"] == ["b", "c", "a"]
    assert call("groupsOpen", state, "d", None, 1)["groups"]["g1"]["tabs"] == ["a", "d", "b", "c"]


def test_closing_a_tab_shows_the_one_used_before_it_and_not_just_the_next():
    state = call("groupsOpen", call("groupsOpen", opened("a", "b", "c"), "a"), "c")           # used: b, a, c
    closed = call("groupsCloseTab", state, "c")
    assert closed["groups"]["g1"]["active"] == "a" and closed["groups"]["g1"]["tabs"] == ["a", "b"]
    middle = call("groupsCloseTab", opened("a", "b", "c"), "a")                                 # a was not in front: nothing changes in front
    assert middle["groups"]["g1"]["active"] == "c"
    last = call("groupsCloseTab", call("groupsCloseTab", call("groupsCloseTab", opened("a", "b", "c"), "c"), "b"), "a")
    assert last["groups"]["g1"] == {"tabs": [], "active": None, "history": []}                  # the only group stays, empty
    assert call("groupsCloseTab", state, "nope") == state


def test_splitting_makes_a_group_beside_and_the_tab_asked_moves_into_it():
    state = opened("a", "b")
    answer = call("groupsSplit", state, "g1", "right", "b")
    split = answer["state"]
    assert answer["group"] == "g2" and split["grid"] == row(leaf("g1"), leaf("g2")) and split["active"] == "g2"
    assert split["groups"]["g1"]["tabs"] == ["a"] and split["groups"]["g1"]["active"] == "a" and split["groups"]["g2"]["tabs"] == ["b"]
    empty = call("groupsSplit", state, "g1", "down")["state"]
    assert empty["groups"]["g2"]["tabs"] == [] and empty["grid"] == column(leaf("g1"), leaf("g2")) and empty["groups"]["g1"]["tabs"] == ["a", "b"]
    only = call("groupsSplit", opened("a"), "g1", "right", "a")["state"]                          # the only tab leaves: its old group is closed
    assert only["grid"] == leaf("g2") and list(only["groups"]) == ["g2"] and only["active"] == "g2"


def test_a_group_that_loses_its_last_tab_closes_and_the_neighbour_takes_the_focus():
    state = call("groupsSplit", opened("a", "b"), "g1", "right", "b")["state"]
    closed = call("groupsCloseTab", state, "b")
    assert closed["grid"] == leaf("g1") and list(closed["groups"]) == ["g1"] and closed["active"] == "g1"
    moved = call("groupsOpen", state, "a", "g2")
    assert moved["grid"] == leaf("g2") and moved["groups"]["g2"]["tabs"] == ["b", "a"] and moved["groups"]["g2"]["active"] == "a"           # a left g1, which closed


def test_moving_a_tab_between_groups_and_inside_a_group():
    state = call("groupsSplit", opened("a", "b", "c"), "g1", "right", "c")["state"]
    moved = call("groupsOpen", state, "a", "g2", 0)
    assert moved["groups"]["g2"]["tabs"] == ["a", "c"] and moved["groups"]["g1"]["tabs"] == ["b"] and call("groupsGroupOf", moved, "a") == "g2"
    assert call("groupsGroupOf", moved, "ghost") is None
    inside = call("groupsMoveWithin", opened("a", "b", "c"), "c", "a", False)
    assert inside["groups"]["g1"]["tabs"] == ["c", "a", "b"]


def test_closing_a_group_returns_the_tabs_it_held_and_the_last_group_only_empties():
    state = call("groupsSplit", opened("a", "b"), "g1", "right")["state"]
    state = call("groupsOpen", state, "z", "g2")
    answer = call("groupsCloseGroup", state, "g2")
    assert answer["closed"] == ["z"] and answer["state"]["grid"] == leaf("g1") and answer["state"]["active"] == "g1"
    last = call("groupsCloseGroup", opened("a", "b"), "g1")
    assert last["closed"] == ["a", "b"] and last["state"]["groups"]["g1"]["tabs"] == [] and last["state"]["grid"] == leaf("g1")
    assert call("groupsCloseGroup", opened("a"), "ghost")["closed"] == []


def test_focus_goes_to_the_group_in_a_direction_and_tabs_read_group_after_group():
    state = call("groupsSplit", opened("a", "b"), "g1", "right", "b")["state"]
    state = call("groupsSplit", state, "g2", "down", None)["state"]
    state = call("groupsOpen", state, "c", "g3")
    assert state["active"] == "g3" and call("groupsFocusDirection", state, "up") == "g2" and call("groupsFocusDirection", state, "left") == "g1"
    assert call("groupsFocusDirection", state, "down") is None
    assert call("groupsAllTabs", state) == ["a", "b", "c"]
    assert call("groupsActivateGroup", state, "g1")["active"] == "g1" and call("groupsActivateGroup", state, "ghost") == state


# ---------------------------------------------------------------- terminal panes


def terminals(*steps):
    state = call("termNew")
    panes = []
    for step in steps:
        if step[0] == "add":
            answer = call("termAdd", state)
        else:
            answer = call("termSplit", state, step[1], step[2] if len(step) > 2 else "right")
        state = answer["state"]
        panes.append(answer["pane"])
    return state, panes


def test_a_new_terminal_is_a_group_of_its_own_and_a_split_stays_in_the_group():
    state, (t1, t2, t3) = terminals(("add",), ("split", "t1"), ("add",))
    assert (t1, t2, t3) == ("t1", "t2", "t3")
    assert [g["id"] for g in state["groups"]] == ["tg1", "tg2"] and state["groups"][0]["grid"] == row(leaf("t1"), leaf("t2")) and state["groups"][0]["active"] == "t2"
    assert state["active"] == "tg2" and call("termPanes", state) == ["t1", "t2", "t3"] and call("termGroupOf", state, "t2") == "tg1"
    assert state["titles"] == {"t1": "zsh", "t2": "zsh", "t3": "zsh"}
    named = call("termRename", state, "t1", "build")
    assert call("termSplit", named, "t1")["state"]["titles"]["t4"] == "build"                                    # a split starts with the name of the pane it came from
    down = call("termSplit", state, "t2", "down")["state"]
    assert down["groups"][0]["grid"] == row(leaf("t1"), column(leaf("t2"), leaf("t4")))
    assert call("termSplit", state, "ghost")["pane"] == "t4"                                                    # no such pane: a terminal of its own


def test_killing_a_pane_gives_its_room_away_and_the_group_goes_with_its_last_pane():
    state, _ = terminals(("add",), ("split", "t1"), ("add",))
    after = call("termKill", state, "t2")
    assert after["groups"][0]["grid"] == leaf("t1") and after["groups"][0]["active"] == "t1" and "t2" not in after["titles"]
    gone = call("termKill", after, "t3")
    assert [g["id"] for g in gone["groups"]] == ["tg1"] and gone["active"] == "tg1"
    nothing = call("termKill", call("termKill", gone, "t1"), "t1")
    assert nothing["groups"] == [] and nothing["active"] is None
    assert call("termKill", state, "ghost") == state


def test_focus_rename_and_moving_between_panes_with_the_arrow_keys():
    state, _ = terminals(("add",), ("split", "t1", "right"), ("split", "t2", "down"))
    assert call("termActivePane", state) == "t3"
    assert call("termFocusDirection", state, "up") == "t2" and call("termFocusDirection", state, "left") == "t1" and call("termFocusDirection", state, "right") is None
    state = call("termFocus", state, "t1")
    assert call("termActivePane", state) == "t1" and call("termFocusDirection", state, "right") == "t2"
    assert call("termRename", state, "t1", "  build  ")["titles"]["t1"] == "build"
    assert call("termRename", state, "t1", "   ") == state and call("termRename", state, "ghost", "x") == state
    assert call("termFocus", state, "ghost") == state


def test_shells_found_running_on_the_server_are_adopted_without_changing_what_the_page_has():
    state, _ = terminals(("add",))
    adopted = call("termAdopt", state, ["t1", "t7", "", "weird"])
    assert call("termPanes", adopted) == ["t1", "t7", "weird"] and adopted["nextPane"] == 8
    assert call("termAdd", adopted)["pane"] == "t8"
    fresh = call("termAdopt", call("termNew"), ["t2"])
    assert fresh["active"] == "tg1" and fresh["titles"] == {"t2": "zsh"}


# ---------------------------------------------------------------- settings


SCHEMA = [
    {"id": "size", "type": "number", "default": 13, "min": 8, "max": 32},
    {"id": "map", "type": "boolean", "default": True},
    {"id": "theme", "type": "enum", "default": "dark", "options": ["dark", "light"]},
    {"id": "font", "type": "string", "default": "mono", "max": 10},
]


def test_settings_keep_what_is_valid_clamp_numbers_and_fall_back_to_the_default():
    assert call("normalizeSettings", {"size": 20, "map": False, "theme": "light", "font": "Menlo"}, SCHEMA) == {"size": 20, "map": False, "theme": "light", "font": "Menlo"}
    assert call("normalizeSettings", {"size": 99, "map": "no", "theme": "neon", "font": "x" * 11, "extra": 1}, SCHEMA) == {"size": 32, "map": True, "theme": "dark", "font": "mono"}
    assert call("normalizeSettings", {"size": 1}, SCHEMA)["size"] == 8
    for junk in (None, 3, "x", [], {"size": None}):
        assert call("normalizeSettings", junk, SCHEMA) == {"size": 13, "map": True, "theme": "dark", "font": "mono"}


# ---------------------------------------------------------------- keys


@pytest.mark.parametrize("text,expected", [
    ("mod+shift+p", "mod+shift+p"), ("Cmd+Shift+P", "mod+shift+p"), ("shift+mod+p", "mod+shift+p"), ("Ctrl+`", "ctrl+`"), ("alt+W", "alt+w"),
    ("mod+alt+b", "mod+alt+b"), ("alt+mod+B", "mod+alt+b"), ("F1", "f1"), ("ctrl+shift+Left", "ctrl+shift+left"), ("mod+ArrowLeft", "mod+left"),
    ("control+option+x", "ctrl+alt+x"), ("mod+shift+mod+p", "mod+shift+p"), ("Escape", "escape"), ("esc", "escape"), ("mod+space", "mod+space"),
])
def test_a_stroke_is_written_one_way(text, expected):
    assert call("normalizeStroke", text) == expected


def test_a_chord_is_strokes_separated_by_spaces():
    assert call("normalizeChord", "Cmd+K  Cmd+S") == ["mod+k", "mod+s"] and call("normalizeChord", "mod+k z") == ["mod+k", "z"] and call("normalizeChord", "  ") == []


def event(**kw):
    return {"key": "", "code": "", "ctrlKey": False, "metaKey": False, "altKey": False, "shiftKey": False, **kw}


def test_the_stroke_of_an_event_uses_the_physical_key_for_letters_and_punctuation_and_cmd_is_mod_on_a_mac():
    assert call("strokeFromEvent", event(key="p", code="KeyP", metaKey=True, shiftKey=True), True) == "mod+shift+p"
    assert call("strokeFromEvent", event(key="P", code="KeyP", ctrlKey=True, shiftKey=True), False) == "mod+shift+p"
    assert call("strokeFromEvent", event(key="∑", code="KeyW", altKey=True), True) == "alt+w"                    # Alt changes the character on a Mac
    assert call("strokeFromEvent", event(key="`", code="Backquote", ctrlKey=True), True) == "ctrl+`"
    assert call("strokeFromEvent", event(key="²", code="Backquote", ctrlKey=True), True) == "ctrl+`"            # Belgian keyboard
    assert call("strokeFromEvent", event(key="F1", code="F1"), False) == "f1"
    assert call("strokeFromEvent", event(key="ArrowLeft", code="ArrowLeft", altKey=True), False) == "alt+left"
    assert call("strokeFromEvent", event(key="1", code="Digit1", metaKey=True), True) == "mod+1"
    assert call("strokeFromEvent", event(key="Meta", code="MetaLeft", metaKey=True), True) is None               # a modifier on its own is not a stroke
    assert call("strokeFromEvent", event(key="Shift", code="ShiftLeft", shiftKey=True), False) is None
    assert call("strokeFromEvent", event(key="Meta", code="MetaLeft", metaKey=True), False) is None
    assert call("strokeFromEvent", event(key="x", code="KeyX", metaKey=True), False) == "meta+x"
    assert call("strokeFromEvent", event(key="x", code="KeyX", ctrlKey=True), True) == "ctrl+x"


DEFAULTS = [{"command": "palette", "key": "mod+shift+p"}, {"command": "palette", "key": "f1"}, {"command": "sidebar", "key": "mod+b"},
            {"command": "zen", "key": "mod+k z"}, {"command": "keys", "key": "mod+k mod+s"}, {"command": "clear", "key": "mod+k", "when": "terminalFocus"}]


def test_user_bindings_add_to_the_defaults_and_a_minus_removes_one():
    resolved = call("resolveBindings", DEFAULTS, [{"command": "sidebar", "key": "alt+s"}, {"command": "-palette", "key": "f1"}, {"command": "-sidebar", "key": "mod+b"}])
    pairs = [(b["command"], " ".join(b["strokes"]), b["source"]) for b in resolved]
    assert ("palette", "f1", "default") not in pairs and ("sidebar", "mod+b", "default") not in pairs
    assert ("sidebar", "alt+s", "user") in pairs and ("palette", "mod+shift+p", "default") in pairs and ("keys", "mod+k mod+s", "default") in pairs
    for junk in (None, 5, "x", [None, 3, {"command": 4}, {"command": "x"}, {"command": "x", "key": ""}]):
        assert len(call("resolveBindings", DEFAULTS, junk)) == len(DEFAULTS)


@pytest.mark.parametrize("expr,ctx,expected", [
    ("", {}, True), ("a", {"a": True}, True), ("a", {}, False), ("!a", {}, True), ("a && b", {"a": True, "b": True}, True), ("a && b", {"a": True}, False),
    ("a || b", {"b": True}, True), ("a && (b || c)", {"a": True, "c": True}, True), ("!(a || b)", {"a": True}, False), ("a && !b", {"a": True}, True),
    ("a &&", {"a": True}, False), ("&& a", {"a": True}, False), ("(a", {"a": True}, True), ("a b", {"a": True, "b": True}, False), ("editor.focus", {"editor.focus": True}, True),
])
def test_when_clauses(expr, ctx, expected):
    assert call("evalWhen", expr, ctx) is expected


def test_a_chord_is_matched_stroke_by_stroke_and_a_when_clause_decides():
    bindings = call("resolveBindings", DEFAULTS, [])
    assert call("matchChord", bindings, ["mod+k"], {}) == {"exact": None, "more": True}
    assert call("matchChord", bindings, ["mod+k", "z"], {})["exact"]["command"] == "zen"
    assert call("matchChord", bindings, ["mod+k", "mod+s"], {})["exact"]["command"] == "keys"
    assert call("matchChord", bindings, ["mod+k"], {"terminalFocus": True})["exact"]["command"] == "clear"
    inside = call("matchChord", bindings, ["mod+k"], {"terminalFocus": True})
    assert inside["more"] is True                                                    # (clear is mod+k alone, but mod+k z could still follow)
    assert call("matchChord", bindings, ["mod+k", "x"], {}) == {"exact": None, "more": False}
    assert call("matchChord", bindings, ["mod+b"], {})["exact"]["command"] == "sidebar" and call("matchChord", bindings, [], {}) ["more"] is True


# ---------------------------------------------------------------- find in a file


def test_find_gives_line_column_and_length_and_never_an_empty_match():
    text = "int Main;\nmain(main)\n\treturn;"
    assert call("findMatches", text, "main") == {"matches": [{"line": 1, "col": 4, "length": 4}, {"line": 2, "col": 0, "length": 4}, {"line": 2, "col": 5, "length": 4}], "error": ""}
    assert call("findMatches", text, "main", {"caseSensitive": True})["matches"] == [{"line": 2, "col": 0, "length": 4}, {"line": 2, "col": 5, "length": 4}]
    assert call("findMatches", text, "ret", {"word": True})["matches"] == [] and len(call("findMatches", text, "return", {"word": True})["matches"]) == 1
    assert call("findMatches", text, "ma.n", {"regex": True})["matches"][0]["col"] == 4 and call("findMatches", text, "ma.n")["matches"] == []
    assert call("findMatches", text, "x*", {"regex": True})["matches"] == []                                    # (every match of x* is empty)
    assert call("findMatches", text, "")["matches"] == []
    bad = call("findMatches", text, "(", {"regex": True})
    assert bad["matches"] == [] and bad["error"]
    assert len(call("findMatches", "a\n" * 10, "a", {}, 3)["matches"]) == 3


def test_a_column_on_screen_counts_a_tab_as_up_to_the_next_stop():
    assert call("visualColumn", "\treturn (0);", 1, 4) == 4 and call("visualColumn", "ab\tc", 3, 4) == 4 and call("visualColumn", "abcd\tc", 5, 4) == 8
    assert call("visualColumn", "\t\tx", 2, 8) == 16 and call("visualColumn", "abc", 99) == 3 and call("visualColumn", "", 0) == 0


def test_next_and_previous_match_wrap_round():
    ms = [{"line": 1, "col": 2, "length": 1}, {"line": 3, "col": 0, "length": 1}, {"line": 3, "col": 5, "length": 1}]
    assert call("nextMatch", ms, 1, 0) == 0 and call("nextMatch", ms, 1, 3) == 1 and call("nextMatch", ms, 3, 5) == 2 and call("nextMatch", ms, 4, 0) == 0
    assert call("nextMatch", ms, 3, 0, True) == 0 and call("nextMatch", ms, 1, 2, True) == 2 and call("nextMatch", ms, 3, 6, True) == 2
    assert call("nextMatch", [], 1, 0) == -1


# ---------------------------------------------------------------- outline


C_SOURCE = """#include <stdio.h>
#define MAX 10
#define SQUARE(x) ((x) * (x))

typedef struct s_point
{
	int	x;
}	t_point;

struct node;

static int	helper(int a, char *b);

/*
** int fake(void)
*/
int	main(int argc, char **argv)
{
	if (argc > 1)
		return (1);
	while (argc)
		argc--;
	return (0);
}

char	*ft_strdup(const char *s)
{
	return (NULL);
}
"""


def test_the_outline_of_a_c_file_lists_macros_types_and_functions_but_not_prototypes_comments_or_keywords():
    names = [(s["kind"], s["name"], s["line"]) for s in call("outlineOf", C_SOURCE, "c")]
    assert names == [("macro", "MAX", 2), ("macro", "SQUARE", 3), ("struct", "s_point", 5), ("function", "main", 17), ("function", "ft_strdup", 26)]


def test_the_outline_of_other_files():
    md = "# Title\ntext\n```\n# not a heading\n```\n## Part *one*\n###### deep\n"
    assert [(s["name"], s["depth"], s["line"]) for s in call("outlineOf", md, "markdown")] == [("Title", 0, 1), ("Part *one*", 1, 6), ("deep", 5, 7)]
    make = "NAME = fractol\nCFLAGS := -Wall\nall: $(NAME)\n\t@echo hi\n$(NAME): $(OBJ)\n\tcc -o $@ $^\n.PHONY: all clean\n"
    assert [(s["kind"], s["name"]) for s in call("outlineOf", make, "makefile")] == [("variable", "NAME"), ("variable", "CFLAGS"), ("target", "all"), ("target", "$(NAME)"), ("target", ".PHONY")]
    py = "class A:\n    def f(self):\n        pass\ndef g():\n    pass\n"
    assert [(s["kind"], s["name"], s["depth"]) for s in call("outlineOf", py, "python")] == [("class", "A", 0), ("function", "f", 1), ("function", "g", 0)]
    sh = "build() {\n  make\n}\nfunction run { :; }\necho hi\n"
    assert [s["name"] for s in call("outlineOf", sh, "shell")] == ["build", "run"]
    assert call("outlineOf", "anything", "plain text") == [] and call("outlineOf", "", "c") == []


# ---------------------------------------------------------------- diff


def lines(text):
    return text.split("\n")


def ops_of(a, b):
    return [(o["op"], o.get("a"), o.get("b")) for o in call("diffLines", lines(a), lines(b))]


def test_a_diff_of_equal_texts_is_all_equal_and_the_ends_are_trimmed_cheaply():
    assert ops_of("a\nb", "a\nb") == [("eq", 0, 0), ("eq", 1, 1)]
    assert [o[0] for o in ops_of("a\nb\nc\nd", "a\nb\nX\nd")] == ["eq", "eq", "del", "ins", "eq"]


def test_additions_removals_and_moves_are_found_with_their_line_numbers():
    assert ops_of("a\nb\nc", "a\nc") == [("eq", 0, 0), ("del", 1, None), ("eq", 2, 1)]
    assert ops_of("a\nc", "a\nb\nc") == [("eq", 0, 0), ("ins", None, 1), ("eq", 1, 2)]
    assert ops_of("", "x") == [("del", 0, None), ("ins", None, 0)]                                # "" is one empty line
    ops = ops_of("one\ntwo\nthree\nfour\nfive", "one\nthree\nfour\nsix\nfive")
    assert [o[0] for o in ops] == ["eq", "del", "eq", "eq", "ins", "eq"]
    ab = ops_of("x\na\nb\ny", "x\nb\na\ny")
    assert sum(o[0] == "eq" for o in ab) == 3 and sum(o[0] != "eq" for o in ab) == 2


def test_every_line_of_both_texts_is_in_the_edit_script_exactly_once():
    a, b = lines("a\nb\nc\nd\ne\nf\ng"), lines("a\nx\nc\nd\ny\ng\nh")
    ops = call("diffLines", a, b)
    assert [o["a"] for o in ops if o["op"] != "ins"] == list(range(len(a))) and [o["b"] for o in ops if o["op"] != "del"] == list(range(len(b)))
    assert all(a[o["a"]] == b[o["b"]] for o in ops if o["op"] == "eq")


def test_two_texts_with_nothing_in_common_are_replaced_whole_and_a_huge_difference_gives_up_quickly():
    assert [o["op"] for o in call("diffLines", ["a", "b"], ["x", "y", "z"])] == ["del", "del", "ins", "ins", "ins"]
    big = call("diffLines", [f"a{i}" for i in range(400)], [f"b{i}" for i in range(400)], 50)
    assert len(big) == 800 and {o["op"] for o in big} == {"del", "ins"}


def test_side_by_side_rows_pair_removed_lines_with_added_ones_and_number_both_sides():
    rows = call("diffRows", lines("a\nb\nc\nd"), lines("a\nX\nY\nc\nd\ne"))
    assert [(r["kind"], r["left"] and r["left"]["n"], r["right"] and r["right"]["n"]) for r in rows] == [
        ("eq", 1, 1), ("chg", 2, 2), ("ins", None, 3), ("eq", 3, 4), ("eq", 4, 5), ("ins", None, 6)]
    assert rows[1]["left"]["text"] == "b" and rows[1]["right"]["text"] == "X"
    only_del = call("diffRows", lines("a\nb"), lines("a"))
    assert [r["kind"] for r in only_del] == ["eq", "del"] and only_del[1]["right"] is None
    assert call("diffHunks", rows) == [1, 5] and call("diffHunks", call("diffRows", ["a"], ["a"])) == []
    assert call("diffHunks", call("diffRows", ["x"], ["y"])) == [0]


# ---------------------------------------------------------------- small things


def test_breadcrumbs_line_and_column_and_tab_order():
    assert call("breadcrumbParts", "src/utils/split.c") == [{"name": "src", "path": "src", "last": False}, {"name": "utils", "path": "src/utils", "last": False}, {"name": "split.c", "path": "src/utils/split.c", "last": True}]
    assert call("breadcrumbParts", "Makefile") == [{"name": "Makefile", "path": "Makefile", "last": True}] and call("breadcrumbParts", "") == []
    assert call("lineColumn", "ab\ncde\nf", 0) == {"line": 1, "col": 1} and call("lineColumn", "ab\ncde\nf", 4) == {"line": 2, "col": 2} and call("lineColumn", "ab\ncde\nf", 3) == {"line": 2, "col": 1}
    assert call("lineColumn", "ab", 99) == {"line": 1, "col": 3} and call("lineColumn", "ab", -4) == {"line": 1, "col": 1}
    assert call("moveKey", ["a", "b", "c"], "c", "a", False) == ["c", "a", "b"] and call("moveKey", ["a", "b", "c"], "a", "b", True) == ["b", "a", "c"]


# ---------------------------------------------------------------- dropping a tab, and the editor layouts of the View menu


BOX = {"left": 100, "top": 50, "right": 500, "bottom": 450}


@pytest.mark.parametrize("x,y,zone", [
    (300, 250, "center"), (110, 250, "left"), (490, 250, "right"), (300, 60, "up"), (300, 440, "down"),
    (210, 250, "center"), (390, 250, "center"), (101, 51, "left"), (499, 449, "right"), (100, 450, "left"),
])
def test_where_in_a_group_a_tab_is_dropped(x, y, zone):
    assert call("dropZone", x, y, BOX) == zone


def test_a_group_without_size_takes_the_tab_in_the_middle():
    assert call("dropZone", 5, 5, {"left": 0, "top": 0, "right": 0, "bottom": 0}) == "center"


def test_the_layout_presets_keep_every_tab_and_the_one_in_front():
    state = call("groupsSplit", opened("a", "b", "c"), "g1", "right", "c")["state"]
    single = call("groupsPreset", state, "single")
    assert single["grid"] == leaf("g1") and single["groups"]["g1"]["tabs"] == ["a", "b", "c"] and single["groups"]["g1"]["active"] == "c" and single["active"] == "g1"
    columns = call("groupsPreset", single, "columns")
    assert columns["grid"] == row(leaf("g1"), leaf("g2")) and columns["groups"]["g1"]["tabs"] == ["a", "b", "c"] and columns["groups"]["g2"]["tabs"] == []
    kept = call("groupsPreset", state, "columns")
    assert kept["groups"]["g1"]["tabs"] == ["a", "b"] and kept["groups"]["g2"]["tabs"] == ["c"] and kept["active"] == "g2"             # each tab stays where it was
    assert call("groupsPreset", state, "rows")["grid"] == column(leaf("g1"), leaf("g2"))
    grid = call("groupsPreset", state, "grid")
    assert call("gridLeaves", grid["grid"]) == ["g1", "g3", "g2", "g4"] and sorted(grid["groups"]) == ["g1", "g2", "g3", "g4"] and grid["next"] == 5
    assert call("groupsPreset", state, "nonsense") == state
    assert call("groupsAllTabs", call("groupsPreset", call("groupsPreset", state, "grid"), "single")) == ["a", "b", "c"]


# ---------------------------------------------------------------- folding the rows of a diff that did not change


def rows_of(kinds):
    return [{"left": {"n": i + 1, "text": "x"}, "right": {"n": i + 1, "text": "x"}, "kind": k} for i, k in enumerate(kinds)]


def test_a_diff_shows_the_changes_with_three_rows_around_them_and_folds_the_long_stretches_between():
    kinds = ["eq"] * 10 + ["chg"] + ["eq"] * 3 + ["ins"] + ["eq"] * 12                             # 27 rows, changes at 10 and 14
    folded = call("diffFold", rows_of(kinds))
    assert folded == [{"kind": "fold", "from": 0, "to": 7}, {"kind": "rows", "from": 7, "to": 18}, {"kind": "fold", "from": 18, "to": 27}]
    assert all(a["to"] == b["from"] for a, b in zip(folded, folded[1:]))                           # nothing is lost or repeated


def test_a_stretch_of_three_or_fewer_unchanged_rows_is_not_worth_folding():
    kinds = ["chg"] + ["eq"] * 7 + ["chg"]                                                           # 7 rows between: 3 + 3 shown, 1 would be hidden
    assert call("diffFold", rows_of(kinds)) == [{"kind": "rows", "from": 0, "to": 9}]
    kinds = ["chg"] + ["eq"] * 10 + ["chg"]                                                          # 4 hidden
    assert [seg["kind"] for seg in call("diffFold", rows_of(kinds))] == ["rows", "fold", "rows"]


def test_a_fold_the_user_opened_is_shown():
    kinds = ["eq"] * 10 + ["chg"]
    assert call("diffFold", rows_of(kinds), 3, [0]) == [{"kind": "rows", "from": 0, "to": 11}]
    assert call("diffFold", rows_of(kinds), 3, [5]) == [{"kind": "fold", "from": 0, "to": 7}, {"kind": "rows", "from": 7, "to": 11}]


def test_identical_texts_show_everything_and_nothing_gives_nothing():
    assert call("diffFold", rows_of(["eq"] * 50)) == [{"kind": "rows", "from": 0, "to": 50}]
    assert call("diffFold", []) == []
    assert call("diffFold", rows_of(["ins"] * 30)) == [{"kind": "rows", "from": 0, "to": 30}]


# ---------------------------------------------------------------- the Source Control view


def change(path, x, y, kind, **more):
    return {"path": path, "x": x, "y": y, "kind": kind, **more}


def test_changes_are_grouped_as_staged_and_not_and_a_file_changed_in_both_places_is_in_both():
    files = [change("a.c", "", "M", "modified"), change("b.c", "A", "", "added"), change("c.c", "M", "M", "modified"), change("d.txt", "?", "?", "untracked"),
             change("e.c", "R", "", "renamed", **{"from": "old.c"}), change("f.c", "", "D", "deleted")]
    groups = call("scmGroups", files)
    assert [g["id"] for g in groups] == ["staged", "changes"]
    staged, changes = groups
    assert [(e["path"], e["letter"]) for e in staged["entries"]] == [("b.c", "A"), ("c.c", "M"), ("e.c", "R")]
    assert [(e["path"], e["letter"]) for e in changes["entries"]] == [("a.c", "M"), ("c.c", "M"), ("d.txt", "U"), ("f.c", "D")]
    assert all(e["staged"] for e in staged["entries"]) and not any(e["staged"] for e in changes["entries"])
    assert staged["entries"][2]["from"] == "old.c"


def test_a_conflict_is_only_in_the_merge_group_and_no_changes_gives_no_groups():
    groups = call("scmGroups", [change("m.c", "U", "U", "conflict"), change("n.c", "", "M", "modified")])
    assert [g["id"] for g in groups] == ["merge", "changes"]
    assert groups[0]["entries"][0]["letter"] == "!"
    assert call("scmGroups", []) == []


def test_the_explorer_marks_the_files_that_changed_and_the_folders_that_hold_them():
    result = call("scmDecorations", [change("src/a/b.c", "", "M", "modified"), change("src/new.c", "?", "?", "untracked"), change("top.c", "A", "", "added")])
    assert result["byPath"] == {"src/a/b.c": {"letter": "M", "kind": "modified"}, "src/new.c": {"letter": "U", "kind": "untracked"}, "top.c": {"letter": "A", "kind": "added"}}
    assert result["folders"] == ["src", "src/a"]


# ---------------------------------------------------------------- icons taken off the activity bar and tabs off the panel


def test_an_icon_can_be_taken_off_the_activity_bar_and_comes_back():
    hidden = call("layoutSetContainerHidden", default(), "search", True)
    assert hidden["hidden"] == {"search": True} and hidden["locations"]["sidebar"]["order"] == ["explorer", "search", "run"], "(it is still there, only not shown)"
    assert call("layoutSetContainerHidden", hidden, "search", False)["hidden"] == {}


def test_the_icon_on_show_gives_way_to_its_neighbour_when_it_is_taken_off():
    layout = call("layoutSetActive", default(), "sidebar", "search")
    assert call("layoutSetContainerHidden", layout, "search", True)["locations"]["sidebar"]["active"] == "run"
    layout = call("layoutSetActive", default(), "sidebar", "run")
    assert call("layoutSetContainerHidden", layout, "run", True)["locations"]["sidebar"]["active"] == "explorer"


def test_the_last_icon_of_a_place_cannot_be_taken_off():
    layout = default()
    for taken in ("search", "run"):
        layout = call("layoutSetContainerHidden", layout, taken, True)
    assert call("layoutSetContainerHidden", layout, "explorer", True) == layout
    assert call("layoutSetContainerHidden", layout, "nope", True) == layout


def test_showing_a_view_or_dropping_its_container_somewhere_brings_its_icon_back():
    hidden = call("layoutSetContainerHidden", default(), "search", True)
    assert call("layoutReveal", hidden, "search")["hidden"] == {}
    assert call("layoutRevealView", hidden, "find")["hidden"] == {}
    assert call("layoutMoveContainer", hidden, "search", "panel")["hidden"] == {}


def test_what_was_hidden_is_remembered_but_only_for_containers_that_exist_and_never_all_of_a_place():
    hidden = call("layoutSetContainerHidden", default(), "search", True)
    assert call("layoutReconcile", hidden, REGISTRY)["hidden"] == {"search": True}
    saved = {**hidden, "hidden": {"search": True, "ghost": True, "run": "yes"}}
    assert call("layoutReconcile", saved, REGISTRY)["hidden"] == {"search": True}
    everything = {**default(), "hidden": {"explorer": True, "search": True, "run": True}}
    fixed = call("layoutReconcile", everything, REGISTRY)
    assert fixed["hidden"] == {"search": True, "run": True} and fixed["locations"]["sidebar"]["active"] == "explorer"
    active_hidden = {**call("layoutSetActive", default(), "sidebar", "search"), "hidden": {"search": True}}
    assert call("layoutReconcile", active_hidden, REGISTRY)["locations"]["sidebar"]["active"] == "explorer"


def test_a_view_dropped_on_a_header_goes_before_that_view_wherever_it_came_from():
    order = lambda layout: layout["containers"]["explorer"]["views"]
    assert order(default()) == ["open", "files", "outline"]
    assert order(call("layoutMoveView", default(), "open", "explorer", 2)) == ["files", "open", "outline"], "(before the one that was third)"
    assert order(call("layoutMoveView", default(), "open", "explorer", 3)) == ["files", "outline", "open"], "(after the last)"
    assert order(call("layoutMoveView", default(), "outline", "explorer", 1)) == ["open", "outline", "files"]
    assert order(call("layoutMoveView", default(), "outline", "explorer", 0)) == ["outline", "open", "files"]
    assert order(call("layoutMoveView", default(), "files", "explorer", 2)) == ["open", "files", "outline"], "(before the one it is already before: nothing moves)"
    assert order(call("layoutMoveView", default(), "files", "explorer", 99)) == ["open", "outline", "files"]
    assert call("layoutMoveView", default(), "find", "explorer", 1)["containers"]["explorer"]["views"] == ["open", "find", "files", "outline"]


def test_a_file_name_dropped_on_a_terminal_is_quoted_only_when_the_shell_needs_it():
    assert call("shellQuote", "src/util.c") == "src/util.c"
    assert call("shellQuote", "libft_v2/ft-put.c") == "libft_v2/ft-put.c"
    assert call("shellQuote", "my file.c") == "'my file.c'"
    assert call("shellQuote", "it's.c") == "'it'\\''s.c'"
    assert call("shellQuote", "$(rm -rf x).c") == "'$(rm -rf x).c'"
    assert call("shellQuote", "a;b") == "'a;b'" and call("shellQuote", "a&b") == "'a&b'" and call("shellQuote", "a\nb") == "'a\nb'"
    assert call("shellQuote", "-rf") == "'-rf'", "(a name that starts with a dash is not taken for an option)"
    assert call("shellQuote", "") == "''"
