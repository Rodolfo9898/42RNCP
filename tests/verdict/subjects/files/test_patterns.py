from verdict.subjects.spec.files import expand_files, file_params


def test_expand_files_alternatives_and_notes():
    required, notes = expand_files("Makefile, *.h, *.{h, hpp}, ft_*.c, all at the root of the repository")
    assert required == [["Makefile"], ["*.h"], ["*.h", "*.hpp"], ["ft_*.c"]]
    assert notes == ["all at the root of the repository"]


def test_expand_files_previous_exercise_prefix():
    required, notes = expand_files("Files from the previous exercise + ScavTrap.{h, hpp}, ScavTrap.cpp")
    assert ["ScavTrap.h", "ScavTrap.hpp"] in required and ["ScavTrap.cpp"] in required
    assert "Files from the previous exercise" in notes


def test_a_name_and_its_subfolder_twin_are_one_requirement_the_root_or_a_subfolder():
    # ft_printf: "Makefile, *.h, */*.h, *.c, */*.c" means headers and sources at the root OR one folder down, not both
    assert expand_files("Makefile, *.h, */*.h, *.c, */*.c")[0] == [["Makefile"], ["*.h", "*/*.h"], ["*.c", "*/*.c"]]
    assert expand_files("*/*.c, *.c")[0] == [["*.c", "*/*.c"]]                                  # whichever is listed first
    assert expand_files("*.{h, hpp}, */*.{h, hpp}")[0] == [["*.h", "*.hpp", "*/*.h", "*/*.hpp"]]
    assert expand_files("*/*.c")[0] == [["*/*.c"]]                                              # alone, nothing to fold into
    assert expand_files("src/*.c, *.c")[0] == [["src/*.c"], ["*.c"]]                            # an explicit folder is not a twin
    assert expand_files("Makefile, libft.h, ft_*.c")[0] == [["Makefile"], ["libft.h"], ["ft_*.c"]]


def test_a_table_note_saying_at_the_root_is_a_requirement_for_those_files():
    required, notes = expand_files("get_next_line.c, get_next_line.h, all at the root of the repository")
    assert file_params(required, notes)["root"] == ["get_next_line.c", "get_next_line.h"]
    assert "root" not in file_params(*expand_files("Makefile, *.h, *.c"))
