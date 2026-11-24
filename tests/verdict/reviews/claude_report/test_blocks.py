from verdict.reviews.claude_report import extract_block
from tests.verdict.reviews.claude_report.samples import GOOD, report


def test_only_the_last_valid_json_block_counts():
    other = '```json\n{"unrelated": true}\n```\n```python\nprint(1)\n```\n'
    broken = '```json\n{not json}\n```\n'
    text = report({"items": [{"n": 1, "status": "ok"}]}, prose="first") + other + report(GOOD, prose="second") + broken
    assert extract_block(text) == GOOD
    assert extract_block("no fences here") is None and extract_block('```json\n{"x": 1}\n```') is None


def test_other_code_blocks_in_the_prose_do_not_confuse_the_reader():
    prose = ("# Review\n\nThe bug:\n\n```c\nint f(void)\n{\n\treturn (0);\n}\n```\n\nAnd a shell session:\n\n```sh\nmake re\n```\n\n"
             "~~~\nplain tilde block with ``` inside\n~~~\n\n## Verdict\ndo not pass\n")
    data = extract_block(report(GOOD, prose=prose))
    assert data == GOOD


def test_a_json_example_inside_the_prose_is_not_mistaken_for_the_data():
    prose = 'I will end the file with:\n\n```json\n{"items": [{"n": 1, "status": "ok"}]}\n```\n'
    assert extract_block(report(GOOD, prose=prose)) == GOOD                      # the last block wins
    assert extract_block(prose) == {"items": [{"n": 1, "status": "ok"}]}


def test_an_unclosed_block_is_not_data():
    assert extract_block('```json\n{"items": []}\n') is None


def test_the_block_may_have_no_language_tag_but_other_languages_are_skipped():
    assert extract_block('```\n{"items": []}\n```') == {"items": []}
    assert extract_block('```yaml\n{"items": []}\n```') is None
