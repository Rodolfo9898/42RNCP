"""What the self-test looks for and what it builds: the tools, and a tiny C, C++ and Docker project."""

from __future__ import annotations

# (name, command, required). "required" tools decide whether the environment is "ready".
PROBES = [
    ("C compiler (cc)", ["cc", "--version"], True),
    ("C++ compiler (c++)", ["c++", "--version"], True),
    ("make", ["make", "--version"], True),
    ("git", ["git", "--version"], True),
    ("docker client", ["docker", "--version"], True),
    ("docker compose", ["docker", "compose", "version"], True),
    ("docker daemon", ["docker", "info", "--format", "{{.ServerVersion}}"], True),
    ("nasm (assembler)", ["nasm", "--version"], False),
    ("valgrind", ["valgrind", "--version"], False),
    ("norminette", ["norminette", "--version"], False),
    ("virtual display (Xvfb, for programs with a window)", ["xdpyinfo"], False),
]

HELLO_C = '#include <stdio.h>\nint main(void) { puts("hello from C"); return 0; }\n'
HELLO_CPP = '#include <iostream>\nint main() { std::cout << "hello from C++\\n"; return 0; }\n'
HELLO_MAKEFILE = (
    "all: c cpp\n"
    "c: hello_c.c\n\tcc -Wall -Wextra -Werror hello_c.c -o c\n"
    "cpp: hello_cpp.cpp\n\tc++ -Wall -Wextra -Werror -std=c++98 hello_cpp.cpp -o cpp\n"
)
HELLO_DOCKERFILE = 'FROM busybox\nRUN echo built-inside-docker > /proof\nCMD ["cat", "/proof"]\n'
