from verdict.checks import strip_code


def test_strip_code_blanks_comments_and_strings_but_keeps_lines():
    src = 'a(); // printf("x")\n/* free(p);\n */ b("malloc(", \'"\');\n'
    out = strip_code(src)
    assert out.count("\n") == src.count("\n")
    assert "printf" not in out and "free" not in out and "malloc" not in out
    assert "a();" in out and "b(" in out
