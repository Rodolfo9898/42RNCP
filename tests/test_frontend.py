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


def test_the_file_view_code_never_hands_a_possibly_missing_node_to_append():
    """The bug that put the word 'null' on every file: view.append(notice) with notice === null."""
    source = (Path(__file__).resolve().parent.parent / "src/verdict/static/app.js").read_text()
    body = source[source.index("async function openFile"):source.index("async function loadTree")]
    assert "view.append(" not in body.replace('view.append(h("div", { class: "notice" }, `${path} is a binary', "")
    assert body.count("appendNodes(view") == 2


def test_the_page_loads_the_shared_helpers_before_the_app():
    html = (Path(__file__).resolve().parent.parent / "src/verdict/static/index.html").read_text()
    scripts = re.findall(r'<script src="([^"]+)"', html)
    assert scripts.index("lib.js") < scripts.index("app.js") and scripts[-1] == "app.js"
    app = (Path(__file__).resolve().parent.parent / "src/verdict/static/app.js").read_text()
    for moved in ("function h(", "function inlineMarkdown(", "function renderMarkdown("):
        assert moved not in app, f"{moved} now lives in lib.js; a second copy would silently win"
