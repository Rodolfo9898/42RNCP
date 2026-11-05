"""The browser-side helpers (markdown preview, rainbow brackets), run for real under Node with a tiny fake DOM."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "harness.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


def run_js(command, text):
    done = subprocess.run(["node", str(HARNESS), command], input=text, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return done.stdout


def md(text):
    return run_js("markdown", text)


def tokens(*lines):
    return json.loads(run_js("rainbow", json.dumps(lines)))


def tags(html, tag):
    return re.findall(rf"<{tag}[ >]", html)


# ---------------------------------------------------------------- markdown: blocks


def test_headings_rules_and_paragraphs():
    html = md("# One\n\n## Two ##\n\n###### Six\n\nSetext\n======\n\nSecond\n------\n\n---\n\nfirst line\nsecond line\n")
    assert [m for m in re.findall(r"<(h[1-6])>", html)] == ["h1", "h2", "h6", "h1", "h2"]
    assert "<h2>Two</h2>" in html                                      # the closing hashes are dropped
    assert "<hr></hr>" in html and "<p>first line second line</p>" in html


def test_bullet_ordered_and_task_lists_with_nesting():
    html = md("- a\n  - b\n    - c\n- d\n\n3. three\n4. four\n   - nested bullet\n\n- [ ] todo\n- [x] done\n")
    assert "<ul><li>a<ul><li>b<ul><li>c</li></ul></li></ul></li><li>d</li></ul>" in html
    assert '<ol start="3"><li>three</li><li>four<ul><li>nested bullet</li></ul></li></ol>' in html
    assert "☐ todo" in html and "☑ done" in html


def test_a_blank_line_between_items_keeps_one_list_and_a_continuation_joins_the_item():
    html = md("- first\n\n- second\n  continued here\n\ntext after\n")
    assert tags(html, "ul") == ["<ul>"] and "<li>second continued here</li>" in html and "<p>text after</p>" in html


def test_code_fences_keep_their_content_literally():
    html = md("```c\nint main(void)\n{\n\treturn (0);\n}\n```\n\n~~~\n# not a heading\n**not bold**\n~~~\n")
    assert 'data-lang="c"' in html and "int main(void)\n{\n\treturn (0);\n}" in html
    assert "# not a heading\n**not bold**" in html and tags(html, "h1") == [] and tags(html, "strong") == []


def test_a_fence_that_never_closes_runs_to_the_end_without_swallowing_the_page_forever():
    html = md("```\nopen\n# inside\n")
    assert html.count("<pre") == 1 and "# inside" in html and tags(html, "h1") == []


def test_code_blocks_inside_list_items():
    html = md("- step\n\n  ```sh\n  make re\n  ```\n- next\n")
    assert "<li>step<pre" in html and "make re" in html and "<li>next</li>" in html


def test_tables_and_blockquotes():
    html = md("| a | b |\n|---|---:|\n| 1 | **2** |\n\n> quoted\n> - item in quote\n")
    assert "<th>a</th><th>b</th>" in html and "<td>1</td><td><strong>2</strong></td>" in html
    assert "<blockquote><p>quoted</p><ul><li>item in quote</li></ul></blockquote>" in html


# ---------------------------------------------------------------- markdown: inline


def test_emphasis_code_strike_and_escapes():
    html = md("**bold** *it* _it2_ ~~gone~~ `a*b*c` snake_case_name and 2 * 3\n\nescaped \\_ \\* \\[x\\]\n")
    assert "<strong>bold</strong>" in html and "<em>it</em>" in html and "<em>it2</em>" in html and "<del>gone</del>" in html
    assert "<code>a*b*c</code>" in html and "snake_case_name" in html and tags(html, "em").__len__() == 2
    assert "escaped _ * [x]" in html


def test_links_open_safely_and_unsafe_ones_are_only_text():
    html = md("[ok](https://example.com/a_(b) \"Title\") [mail](mailto:a@b.c) [bad](javascript:alert(1)) [rel](./docs/x.md) [top](#intro) <https://auto.link>")
    assert re.search(r'<a href="https://example.com/a_\(b\)" target="_blank" rel="noopener noreferrer nofollow" title="Title">ok</a>', html)
    assert '<a href="mailto:a@b.c"' in html and '<a href="https://auto.link"' in html
    for unsafe in ("javascript:", "./docs/x.md", "#intro"):
        assert f'href="{unsafe}' not in html
    assert '<span class="md-link-plain" title="javascript:alert(1)">bad</span>' in html and ">rel</span>" in html


def test_images_are_never_loaded():
    html = md("![logo](https://tracker.example/pixel.png) and ![](x.png)")
    assert tags(html, "img") == [] and "src=" not in html
    assert '<span class="md-image" title="https://tracker.example/pixel.png">🖼 logo</span>' in html and "🖼 image" in html


def test_html_in_a_readme_is_shown_as_text_never_interpreted():
    html = md("<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n\n<div onclick=x>hi</div>\n\ntext <b>b</b> end\n")
    for element in ("script", "img", "b"):
        assert tags(html, element) == [], element
    assert tags(html, "div") == ["<div "] and "onclick" not in re.sub(r"&lt;.*?&gt;", "", html)     # the only <div> is the renderer's own wrapper
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "onerror" not in re.sub(r"&lt;.*?&gt;", "", html)             # the word only survives inside escaped text


def test_nasty_input_does_not_hang_or_throw():
    nasty = ["*" * 5000, "[" * 3000 + "](" + "(" * 3000, "_a " * 4000, "`" * 2001, "- " * 2000 + "x", "> " * 1500 + "x", "| a |\n" * 500, "![" * 2000]
    for text in nasty:
        md(text)


def test_the_apps_own_verdict_document_renders_cleanly():
    from tests.test_report import merged_document
    html = md(merged_document())
    assert re.findall(r"<h2>(.*?)</h2>", html)[:3] == ["At a glance", "❌ Lacking — fix these", "⚠️ Second look — a human should verify these"]
    assert "<table>" in html and "<strong>" in html and "<code>" in html
    text = re.sub(r"<[^>]+>", "", html)
    assert "\\_" not in text and "**" not in text and "<!--" not in html          # escapes resolved, no raw markdown, marker hidden
    assert 'The strchr function must find any byte.' in text


# ---------------------------------------------------------------- opening a markdown file


@pytest.mark.parametrize("path,line,mode", [
    ("README.md", None, "preview"), ("docs/guide.MD", None, "preview"), ("notes.markdown", None, "preview"),
    ("README.md", 12, "code"),                               # a file:line reference means "show me that line of source"
    ("main.c", None, "code"), ("Makefile", None, "code"), ("readme.md.bak", None, "code"), ("notes.mdx", None, "code"), ("md", None, "code"),
])
def test_markdown_opens_rendered_unless_a_line_is_asked_for(path, line, mode):
    assert run_js("mode", json.dumps([path, line])) == mode


# ---------------------------------------------------------------- rainbow brackets


def levels(result, line=0):
    return [(text, piece[2]) for piece in result[line] for text in [piece[1]] if len(piece) > 2]


def test_nesting_depth_gives_the_colour_and_matching_pairs_share_it():
    out = tokens([["", "((()))"]])
    assert levels(out) == [("(", 0), ("(", 1), ("(", 2), (")", 2), (")", 1), (")", 0)]


def test_the_colours_cycle_after_six_levels():
    out = tokens([["", "(" * 8 + ")" * 8]])
    assert [lv for _, lv in levels(out)][:8] == [0, 1, 2, 3, 4, 5, 0, 1] and [lv for _, lv in levels(out)][8:] == [1, 0, 5, 4, 3, 2, 1, 0]


def test_all_three_kinds_are_matched_and_text_in_between_is_kept():
    out = tokens([["k", "if"], ["", " ("], ["", "a[0]"], ["o", " + "], ["", "f("], ["", "x"], ["", "))"], ["", " {"]], [["", "}"]])
    assert levels(out, 0) == [("(", 0), ("[", 1), ("]", 1), ("(", 1), (")", 1), (")", 0), ("{", 0)]       # the { closes on the next line
    assert levels(out, 1) == [("}", 0)]
    assert "".join(p[1] for p in out[0]) == "if (a[0] + f(x)) {"


def test_brackets_may_close_on_a_later_line():
    out = tokens([["", "int f(void) {"]], [["", "  return (1);"]], [["", "}"]])
    opener = [p for p in out[0] if p[1] == "{"][0][2]
    closer = [p for p in out[2] if p[1] == "}"][0][2]
    assert opener == closer == 0 and opener != -1
    inner = [p[2] for p in out[1] if len(p) > 2]
    assert inner == [1, 1]                                   # nested one level inside the braces


def test_a_wrong_closer_and_leftover_openers_are_marked_unmatched():
    assert levels(tokens([["", "(]"]])) == [("(", -1), ("]", -1)]
    assert levels(tokens([["", "))"]])) == [(")", -1), (")", -1)]                        # nothing to close
    assert levels(tokens([["", "{ ( )"]])) == [("{", -1), ("(", 1), (")", 1)]            # the { never closes


def test_brackets_in_strings_and_comments_are_left_alone():
    line = [["k", "puts"], ["", "("], ["s", '"(((" ]'], ["", ")"], ["c", " // ) }"]]
    out = tokens(line)
    assert out[0] == [["k", "puts"], ["", "(", 0], ["s", '"(((" ]'], ["", ")", 0], ["c", " // ) }"]]


def test_nothing_is_lost_or_reordered():
    source = [[["pp", "#define MAX(a, b) ((a) > (b))"]], [["", "x = {1, 2, [3]};"], ["c", " /* ( */"]], [["", ") ]"]]]
    out = tokens(*source)
    for original, produced in zip(source, out):
        assert "".join(t[1] for t in produced) == "".join(t[1] for t in original)


def test_other_token_classes_keep_their_class_on_every_piece():
    out = tokens([["pp", "#define F(x) (x)"]])
    assert {p[0] for p in out[0]} == {"pp"} and [p[1] for p in out[0] if len(p) > 2] == ["(", ")", "(", ")"]


def test_rainbow_is_only_for_code():
    assert json.loads(run_js("enabled", json.dumps(["C", "Python", "Makefile", "JSON", "Markdown", "Text only", "reStructuredText", None, "", "Diff"]))) == [
        True, True, True, True, False, False, False, False, False, False]


# ---------------------------------------------------------------- never write "null" into the page


def test_appending_nothing_adds_nothing():
    html = run_js("append", json.dumps([None, False, "text", [None, {"el": "b", "text": "bold"}, [False, "deep"]], None]))
    assert html == "<div>text<b>bold</b>deep</div>"
    assert "null" not in html and "false" not in html


STATIC = Path(__file__).resolve().parent.parent / "src/verdict/static"


def static(name):
    return (STATIC / name).read_text()


def test_the_file_view_code_never_hands_a_possibly_missing_node_to_append():
    """The bug that put the word 'null' on every file: view.append(notice) with notice === null."""
    source = static("fileview.js")
    body = source[source.index("function buildFileView"):source.index("async function openFile")]
    assert "view.append(" not in body.replace('view.append(h("div", { class: "notice" }, `${path} is a binary', "")
    assert body.count("appendNodes(view") == 2


# ---------------------------------------------------------------- workbench helpers: fuzzy search, keyboard shortcuts, tab order


def fuzzy(query, text):
    return json.loads(run_js("fuzzy", json.dumps([[query, text]])))[0]


def shown(query, text):
    """The text with the matched characters in [brackets], or None when it does not match."""
    match = fuzzy(query, text)
    return None if match is None else "".join(f"[{c}]" if i in match["positions"] else c for i, c in enumerate(text))


def test_fuzzy_matching_needs_every_character_in_order_and_ignores_case_and_spaces():
    assert shown("main", "src/main.c") == "src/[m][a][i][n].c"
    assert shown("MAIN", "src/main.c") == "src/[m][a][i][n].c" and shown("ma in", "src/main.c") == "src/[m][a][i][n].c"
    assert shown("xyz", "src/main.c") is None and shown("nm", "src/main.c") is None       # (n then m: the order is wrong)
    assert shown("longerthanthetext", "ab") is None
    assert fuzzy("", "anything") == {"score": 0, "positions": []}


def test_the_best_alignment_wins_not_the_first_one_found():
    assert shown("fr", "src/frontend.js") == "src/[f][r]ontend.js"                          # the start of a word, both letters together
    assert shown("fr", "afar/readme.md") == "a[f]ar/[r]eadme.md"                            # the only way, and it is still a match
    assert shown("mt", "src/main/test.c") == "src/[m]ain/[t]est.c"                          # starts of words rather than the m and t of "something"
    assert shown("gnl", "get_next_line.c") == "[g]et_[n]ext_[l]ine.c"
    assert shown("sc", "SubjectCard.tsx") == "[S]ubject[C]ard.tsx"                           # a capital starts a word too


def test_a_closer_match_scores_higher_than_a_scattered_one_and_so_does_a_shorter_path():
    exact, scattered = fuzzy("main", "main.c"), fuzzy("main", "my_array_index_n.c")
    assert exact["score"] > scattered["score"]
    assert fuzzy("ft", "ft_printf.c")["score"] > fuzzy("ft", "src/utils/some_file_tool.c")["score"]
    assert fuzzy("a", "a.c")["score"] > fuzzy("a", "x/y/z/a.c")["score"]


def keys(*rows):
    return json.loads(run_js("key", json.dumps(rows)))


def ev(key, code="", **mods):
    return {"key": key, "code": code, **mods}


def test_shortcuts_match_command_on_a_mac_and_control_elsewhere():
    assert keys([ev("b", "KeyB", metaKey=True), "mod+b", True], [ev("b", "KeyB", ctrlKey=True), "mod+b", False]) == [True, True]
    assert keys([ev("b", "KeyB", ctrlKey=True), "mod+b", True], [ev("b", "KeyB", metaKey=True), "mod+b", False]) == [False, False]     # the other one does not
    assert keys([ev("P", "KeyP", metaKey=True, shiftKey=True), "mod+shift+p", True]) == [True]
    assert keys([ev("p", "KeyP", metaKey=True), "mod+shift+p", True], [ev("P", "KeyP", metaKey=True, shiftKey=True), "mod+p", True]) == [False, False]


def test_extra_modifiers_never_match_so_a_browser_or_system_shortcut_is_left_alone():
    assert keys([ev("b", "KeyB", metaKey=True, altKey=True), "mod+b", True], [ev("b", "KeyB", metaKey=True, shiftKey=True), "mod+b", True],
                [ev("b", "KeyB", metaKey=True, ctrlKey=True), "mod+b", True], [ev("b", "KeyB"), "mod+b", True]) == [False] * 4


def test_the_physical_key_counts_because_alt_changes_the_character_on_a_mac_and_keyboards_differ():
    assert keys([ev("∑", "KeyW", altKey=True), "alt+w", True]) == [True]                    # Alt+W types ∑ on a Mac
    assert keys([ev("²", "Backquote", ctrlKey=True), "ctrl+`", False]) == [True]             # the key under Esc on a Belgian keyboard
    assert keys([ev("`", "Backquote", ctrlKey=True), "ctrl+`", False]) == [True]
    assert keys([ev("F1", "F1"), "f1", False], [ev("Escape", "Escape"), "escape", False]) == [True, True]
    assert keys([ev("F2", "F2"), "f1", False]) == [False]


def test_shortcuts_are_shown_the_way_each_platform_writes_them():
    texts = json.loads(run_js("showkey", json.dumps([["mod+shift+p", True], ["mod+shift+p", False], ["mod+b", True], ["alt+w", True], ["alt+w", False], ["f1", False], ["ctrl+`", True]])))
    assert texts == ["⇧⌘P", "Ctrl+Shift+P", "⌘B", "⌥W", "Alt+W", "F1", "⌃`"]


TABS = [{"key": "overview", "closable": False, "session": False}, {"key": "a.c", "closable": True, "session": False},
        {"key": "b.c", "closable": True, "session": False}, {"key": "terminal", "closable": True, "session": True},
        {"key": "pdf:x.pdf", "closable": True, "session": False}, {"key": "shell", "closable": True, "session": True}]


def closing(mode, key):
    return json.loads(run_js("close", json.dumps([TABS, mode, key])))


def test_closing_others_to_the_right_or_all_leaves_the_overview_and_the_running_sessions_alone():
    assert closing("others", "b.c") == ["a.c", "pdf:x.pdf"]
    assert closing("right", "a.c") == ["b.c", "pdf:x.pdf"]
    assert closing("right", "pdf:x.pdf") == [] and closing("right", "shell") == []
    assert closing("all", "a.c") == ["a.c", "b.c", "pdf:x.pdf"]                            # (claude and the shell are conversations: they stay)


def moved(keys, source, target, after=False):
    return json.loads(run_js("move", json.dumps([keys, source, target, after])))


def test_dragging_a_tab_puts_it_before_or_after_the_one_it_is_dropped_on():
    order = ["a", "b", "c", "d"]
    assert moved(order, "d", "b") == ["a", "d", "b", "c"] and moved(order, "a", "c", True) == ["b", "c", "a", "d"]
    assert moved(order, "a", "b") == ["a", "b", "c", "d"]                                  # dropped before the one it is already before
    assert moved(order, "b", "a", True) == ["a", "b", "c", "d"] and moved(order, "c", "c") == order
    assert moved(order, "x", "b") == order and moved(order, "a", "x") == order            # unknown tabs change nothing


# ---------------------------------------------------------------- how the scripts are wired to the page and to each other
# (what the parts do is tried in a DOM by test_ui.py; these keep the files from drifting apart unnoticed)

ORDER = ["lib.js", "model.js", "core.js", "commands.js", "fileicons.js", "layout.js", "menus.js", "editors.js", "fileview.js", "minimap.js", "terminals.js",
         "views.js", "scm.js", "quickinput.js", "statusbar.js", "settings-ui.js", "app.js", "workbench-commands.js", "boot.js"]


def test_the_page_loads_every_script_once_in_an_order_that_works_and_starts_last():
    scripts = re.findall(r'<script src="([^"]+)"', static("index.html"))
    assert scripts[:2] == ["vendor/xterm.js", "vendor/addon-fit.js"] and scripts[2:] == ORDER
    assert all((STATIC / name).is_file() for name in scripts)
    assert not {p.name for p in STATIC.glob("*.js")} - set(scripts), "a script of the folder that the page never loads"
    app = static("app.js")
    for moved in ("function h(", "function inlineMarkdown(", "function renderMarkdown(", "const tabs = ", "function showTab(", "function openFile("):
        assert moved not in app, f"{moved} lives in another file; a second copy would silently win"


def test_no_script_declares_a_global_another_one_declares_too():
    """Scripts share one global scope: a second `const x` is a SyntaxError that stops the whole file, a second `function x` silently wins."""
    seen = {}
    for name in ORDER:
        for declared in re.findall(r"^(?:const|let|var|function\*?|async function|class)\s+([A-Za-z_$][\w$]*)", static(name), re.MULTILINE):
            assert declared not in seen, f"{declared} is declared in {seen[declared]} and in {name}"
            seen[declared] = name


def test_every_element_the_scripts_look_up_by_id_is_in_the_page_or_made_by_them():
    ids = set(re.findall(r'id="([^"]+)"', static("index.html")))
    made, wanted = set(), set()
    for name in ORDER:
        made |= set(re.findall(r'\bid: "([\w-]+)"', static(name)))
        wanted |= set(re.findall(r'\$\("#([\w-]+)', static(name)))
    assert wanted and wanted <= ids | made, wanted - ids - made


def test_every_command_a_menu_or_the_status_bar_runs_is_registered():
    registered = set(re.findall(r'\bid: "([\w.-]+)", title:', static("workbench-commands.js")))
    used = set()
    for name in ("menus.js", "statusbar.js", "views.js", "layout.js", "terminals.js", "editors.js", "fileview.js", "scm.js", "app.js", "settings-ui.js"):
        used |= set(re.findall(r'(?:command: |runCommand\()"([\w-]+(?:\.[\w-]+)+)"', static(name)))
    assert used and used <= registered, used - registered


def test_nothing_hands_text_from_a_repository_to_innerhtml():
    for name in ORDER:
        assert not re.search(r"\.(innerHTML|outerHTML)\b|insertAdjacentHTML\(|document\.write\(|new Function\(|\beval\(", static(name)), name


def test_the_terminal_tab_says_whether_git_over_ssh_works_there():
    on, off = json.loads(run_js("sshnote", json.dumps([True, False])))
    assert on == "git over ssh works here: your ssh-agent is shared with this tab."
    assert "git over ssh is off here" in off and "git clone and git push cannot sign in" in off and "TERMINAL_SSH=1" in off and "make run" in off
    terminals = static("terminals.js")
    body = terminals[terminals.index("async function openTerminal"):terminals.index('addTab("terminal"')]
    assert "sshNote(status.ssh === true)" in body                                                    # only a clear yes counts as on
    assert "gitNote" in body.split('class: "term-bar"')[1]                                           # it is in the bar of claude's tab
    assert "sshNote(sess.status?.ssh === true)" in terminals                                          # and of a shell moved into the editor area


def test_the_verdict_window_says_when_claude_decided_and_what_the_lists_alone_say():
    cases = [None, {"decided_by": "scripts", "overall": "FAIL", "lists": "FAIL"}, {"decided_by": "claude", "overall": "PASS", "lists": "PASS"},
             {"decided_by": "claude", "overall": "PASS WITH ISSUES", "lists": "FAIL"}]
    assert json.loads(run_js("decided", json.dumps(cases))) == ["", "", "Decided by Claude.", "Decided by Claude. The lists alone say FAIL."]


def test_a_run_clears_claudes_tab_the_verdict_and_the_open_files_and_does_not_collect_what_claude_saved():
    app = static("app.js")
    clear = app[app.index("function clearForNewRun"):app.index("async function run()")]
    assert 'claude.discard = true; closeTab("terminal")' in clear and 'closeTab("verdict.md")' in clear and "tab.repoFile" in clear
    body = app[app.index("async function run()"):app.index("async function poll()")]
    assert body.index("post(`sessions/${sid}/run`)") < body.index("clearForNewRun()") < body.index("poll()")          # (nothing is closed if the server refuses)
    terminals = static("terminals.js")
    opened = terminals.index("tab.onClose = () => {")
    close = terminals[opened:terminals.index('showTab("terminal");', opened)]
    assert "claude.discard = !!tab.discard" in close and "if (tab.discard) return;" in close                       # (no /end call, no collecting timer)
