from verdict.subjects.spec.lines import is_toc_page, read_lines


def texts(lines):
    return [l.text for l in lines]


def test_the_table_of_contents_the_page_numbers_and_the_chapter_marks_are_not_content():
    pages = ["Contents\nI\nIntroduction\n2\nII\nRules\n3\n", "7\nChapter I\nRules\nFirst content line.\nSecond content line.\n",
             "Third content line.\n42\nFourth content line.\nFifth content line.\n"]
    assert texts(read_lines(pages)) == ["First content line.", "Second content line.", "Third content line.", "Fourth content line.",
                                        "Fifth content line."]


def test_a_toc_page_is_recognised_by_its_title_or_by_following_one_and_being_mostly_numbers():
    assert is_toc_page(["Contents", "I"], False) and is_toc_page(["Table of Contents"], False)
    assert is_toc_page(["1", "2", "iii", "text"], True) and not is_toc_page(["1", "2", "iii", "text"], False)
    assert not is_toc_page([], True)


def test_a_line_that_repeats_on_many_pages_is_a_running_header_unless_it_labels_a_table():
    pages = [f"Header of the book\nProgram Name\ncontent {i}\n" for i in range(4)]
    assert texts(read_lines(pages)) == ["Program Name", "content 0", "Program Name", "content 1", "Program Name", "content 2", "Program Name", "content 3"]


def test_each_line_knows_its_page_its_chapter_and_its_part():
    pages = ["Chapter I\nGeneral rules\nA rule of the mandatory part.\n", "Chapter II\nBonus part\nA bonus line.\n"]
    lines = read_lines(pages)
    assert [(l.text, l.page, l.section, l.chapter) for l in lines] == [
        ("A rule of the mandatory part.", 1, "mandatory", "general rules"), ("A bonus line.", 2, "bonus", "bonus part")]


def test_a_chapter_about_what_to_hand_in_belongs_to_the_whole_project_not_to_the_bonus_that_came_before():
    pages = ["Chapter V\nBonus part\nA bonus line.\n", "Chapter VI\nSubmission and peer-evaluation\nA line about handing in.\n"]
    assert [(l.text, l.section) for l in read_lines(pages)] == [("A bonus line.", "bonus"), ("A line about handing in.", "mandatory")]
