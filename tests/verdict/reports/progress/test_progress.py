"""Progress.md: the table of which projects were run, updated from the editor once the result is one you accept."""

import re

import pytest

from verdict.reports import progress

TABLE = """# Projects

Which projects were run.

| Project | Run |
|---|:---:|
| born2beroot | ⬜ |
| libft | ⬜ |
| push_swap | ✅ |

✅ run and accepted · ⬜ not run
"""


def test_a_result_has_a_symbol_and_nothing_else_does():
    assert [progress.symbol_for(r) for r in ("PASS", "PASS WITH ISSUES", "FAIL")] == ["✅", "⚠️", "❌"]
    for nothing in ("NOT RUN", "", "pass"):
        with pytest.raises(progress.ProgressError, match="no result to record"):
            progress.symbol_for(nothing)


def test_only_the_row_of_the_project_changes():
    new, before = progress.update(TABLE, "libft", "⚠️")
    assert before == "⬜" and new == TABLE.replace("| libft | ⬜ |", "| libft | ⚠️ |")
    assert progress.update(new, "libft", "⚠️") == (new, "⚠️")                  # the same again: nothing changes
    assert progress.update(TABLE, "LIBFT", "❌")[0] == TABLE.replace("| libft | ⬜ |", "| libft | ❌ |")      # found whatever the case, name kept


def test_a_project_without_a_row_is_added_in_its_alphabetical_place():
    new, before = progress.update(TABLE, "cub3d", "✅")
    assert before is None
    rows = re.findall(r"^\| ([\w.-]+) \|", new, re.M)
    assert rows == ["Project", "born2beroot", "cub3d", "libft", "push_swap"]
    assert progress.update(TABLE, "zappy", "✅")[0].index("| zappy | ✅ |") > progress.update(TABLE, "zappy", "✅")[0].index("| push_swap |")
    assert progress.update(TABLE, "zappy", "✅")[0].endswith("\n✅ run and accepted · ⬜ not run\n")        # the legend stays below the table


def test_everything_around_the_table_is_kept_byte_for_byte():
    text = "intro the person wrote\r\n\n" + TABLE.split("\n\n", 1)[1] + "\nmy notes: |x|y|\n"
    new, _ = progress.update(text, "libft", "✅")
    assert new == text.replace("| libft | ⬜ |", "| libft | ✅ |")


def test_an_empty_or_table_less_file_gets_a_table():
    new, before = progress.update("", "libft", "✅")
    assert before is None and new.startswith("# Projects") and "| Project | Run |\n|---|:---:|\n| libft | ✅ |" in new and "run and accepted" in new
    again, _ = progress.update(new, "libft", "❌")
    assert again.count("| libft |") == 1 and "| libft | ❌ |" in again
    notes, _ = progress.update("just some notes\n", "libft", "✅")
    assert notes.startswith("just some notes\n") and "| libft | ✅ |" in notes


@pytest.mark.parametrize("name", ["", "a|b", "a b", "../x", "x\ny", "| ✅ |"])
def test_a_name_that_could_break_the_table_is_refused(name):
    with pytest.raises(progress.ProgressError):
        progress.update(TABLE, name, "✅")
