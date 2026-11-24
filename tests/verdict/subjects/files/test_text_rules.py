from verdict.subjects.spec import parse_subject


def text_rules(pages, name="x.pdf"):
    return [r for r in parse_subject(name, pages).rules if r.kind == "required_files" and r.params.get("from_text")]


def test_a_list_of_mandatory_files_is_read_but_not_the_optional_one_and_it_belongs_to_the_whole_project_not_the_bonus():
    pages = ["Chapter VII\nBonus part\nSome bonus feature.\n",
             "Chapter VIII\nDeliverables\nYour repository must contain all the necessary files. The following files are mandatory:\nVIII.1\nRequired Files\n"
             "• README.md: Documentation of the project\n• Dockerfile: Your Docker configuration\n• docker-compose.yml: Compose configuration\n"
             "• Makefile: Build automation\n• src/: Directory containing your sources\n• Configuration files: .conf.in files\n"
             "VIII.2\nOptional but Recommended\n• .gitignore: To exclude build artifacts\n• CHANGELOG.md: Notes for the next version\n• tests/: Your own tests\n"]
    [rule] = text_rules(pages)
    assert [e[0] for e in rule.params["files"]] == ["Dockerfile", "docker-compose.yml", "Makefile", "src/"]      # no README, no "Configuration", no optional ones
    assert "CHANGELOG.md" not in str(rule.params) and "tests/" not in str(rule.params)                          # (optional entries with ordinary names too)
    assert rule.section == "mandatory"                                                                          # (the previous chapter was the bonus)


def test_a_listing_of_the_expected_layout_is_a_hint_and_a_sentence_that_asks_for_a_file_outright_stays_a_requirement():
    pages = ["Chapter III\nGeneral guidelines\nA Makefile is also required and must be located at the root of your directory.\n",
             "Below is an example of the expected directory structure:\n$> ls -alR\ntotal XX\n"
             "drwxrwxr-x 3 wil wil 4096 avril 42 20:42 .\ndrwxrwxrwt 17 wil wil 4096 avril 42 20:42 ..\n"
             "-rw-rw-r-- 1 wil wil XXXX avril 42 20:42 Makefile\ndrwxrwxr-x 3 wil wil 4096 avril 42 20:42 srcs\n"
             "./srcs:\ntotal XX\ndrwxrwxr-x 3 wil wil 4096 avril 42 20:42 .\n-rw-rw-r-- 1 wil wil XXXX avril 42 20:42 docker-compose.yml\n"
             "drwxrwxr-x 5 wil wil 4096 avril 42 20:42 requirements\n./srcs/requirements:\ntotal XX\n"
             "drwxrwxr-x 5 wil wil 4096 avril 42 20:42 nginx\n"]
    [rule] = text_rules(pages)
    assert [e[0] for e in rule.params["files"]] == ["Makefile", "srcs/", "srcs/docker-compose.yml", "srcs/requirements/"]   # nothing deeper than two levels
    assert rule.params["root"] == ["Makefile"] and rule.params["soft"] == ["srcs/", "srcs/docker-compose.yml", "srcs/requirements/"]


def test_a_plain_ls_names_files_softly_and_bracketed_names_are_optional():
    pages = ["Chapter VII\nSubmission\n• Your repository layout must include:\n$> ls\nwriteup1\nwriteup2\n[scripts/]\n[bonus/]\nThe scripts/ folder is optional.\n"]
    [rule] = text_rules(pages)
    assert [e[0] for e in rule.params["files"]] == ["writeup1", "writeup2"] and rule.params["soft"] == ["writeup1", "writeup2"]


def test_a_listing_that_is_not_about_the_layout_is_ignored():
    pages = ["Chapter V\nMandatory part\nRun it like this and read the output:\n$> ls\nfoo\nbar\n"]
    assert text_rules(pages) == []


def test_the_turn_in_chapter_is_read_for_files_even_though_it_is_skipped_for_everything_else_and_belongs_to_the_mandatory_part():
    pages = ["Chapter V\nBonus part\nA bonus feature.\n", "Chapter VI\nSubmission and peer-evaluation\nYou must turn in your code, a Makefile and a basic virtual image.\n"]
    [rule] = text_rules(pages)
    assert [e[0] for e in rule.params["files"]] == ["Makefile"] and rule.section == "mandatory"
    assert not [r for r in parse_subject("x.pdf", pages).rules if r.kind == "manual"]                      # it does not become a vague manual item


def test_what_a_table_already_requires_is_not_asked_twice_and_the_sentence_is_not_left_as_a_manual_item():
    pages = ["Chapter V\nMandatory part\nProgram Name\nlibftprintf.a\nTurn in files\nMakefile, *.h, *.c\nDescription\n"
             "You must submit a Makefile that compiles your source files.\n"]
    spec = parse_subject("x.pdf", pages)
    assert [r.params["files"] for r in spec.rules if r.kind == "required_files"] == [[["Makefile"], ["*.h"], ["*.c"]]]
    assert not [r for r in spec.rules if r.kind == "manual" and "Makefile" in r.text]
