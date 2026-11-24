import pytest

from verdict.reports.progress import NOT_RUN, ProgressError, ProgressTable, symbol_for, update


def test_the_table_is_read_once_and_the_rows_are_found_by_name_whatever_the_case():
    table = ProgressTable("| Project | Run |\n|---|:---:|\n| libft | ⬜ |\n| Push_Swap | ✅ |\n")
    assert [table.lines[i] for i in table.rows] == ["| libft | ⬜ |", "| Push_Swap | ✅ |"]
    new, before = table.update("push_swap", "❌")
    assert before == "✅" and "| Push_Swap | ❌ |" in new


def test_the_text_of_a_table_is_not_modified_by_looking_at_it():
    text = "| Project | Run |\n|---|:---:|\n| libft | ⬜ |\n"
    assert ProgressTable(text).text == text and update(text, "libft", "⬜")[0] == text


def test_a_symbol_for_not_run_exists_but_no_result_maps_to_it():
    assert NOT_RUN == "⬜"
    for result in ("NOT RUN", "", "pass"):
        with pytest.raises(ProgressError):
            symbol_for(result)
