"""What counts as the project's own files: MiniLibX, submodules, the generated verdict."""

from verdict.checks import Ctx, minilibx_dirs
from verdict.repository.repo import tracked_files

from tests.verdict.checks.helpers import MLX, fractol_like, project


HEADER = """/* ************************************************************************** */
/*                                                                            */
/*   ft_strlen.c                                        :+:      :+:    :+:   */
/*                                                    +:+ +:+         +:+     */
/*   By: student <student@student.42.fr>            +#+  +:+       +#+        */
/*                                                +#+#+#+#+#+   +#+           */
/*   Created: 2025/01/01 00:00:00 by student          #+#    #+#             */
/*   Updated: 2025/01/01 00:00:00 by student         ###   ########.fr       */
/*                                                                            */
/* ************************************************************************** */
"""


def test_minilibx_is_found_by_its_files_not_its_folder_name(tmp_path):
    repo = project(tmp_path, {**MLX, "src/main.c": "int main;\n", "include/so_long.h": "x\n", "mlx.h": "x\n", "mlx_tools.c": "x\n"})
    assert minilibx_dirs(repo, tracked_files(repo)) == ["deps/MLX42", "gfx/mlx_custom"]   # never the project's own root
    ctx = Ctx(repo=repo.resolve(), rules=[], sandbox=None, lang="c")
    sources = {p.as_posix() for p in ctx.source_files()}
    assert "src/main.c" in sources and not any(s.startswith(("gfx/", "deps/")) for s in sources)


def test_the_students_own_submodules_are_under_the_norm_but_minilibx_is_not(tmp_path):
    repo = project(tmp_path, {
        ".gitmodules": '[submodule "libft"]\n\tpath = libft\n\turl = git@github.com:me/libft.git\n'
                       '[submodule "mlx"]\n\tpath = minilib\n\turl = https://github.com/42Paris/minilibx-linux.git\n'
                       '[submodule "unity"]\n\tpath = vendor/unity\n\turl = https://github.com/ThrowTheSwitch/Unity.git\n',
        "libft/ft_strlen.c": HEADER + "int ft_strlen;\n", "libft/libft.h": HEADER,
        "minilib/mlx.h": "x\n", "minilib/mlx_init.c": "int a;\n",
        "vendor/unity/unity.c": "int u;\n",                                                 # third-party, no 42 header
        "main.c": "int main;\n",
    })
    ctx = Ctx(repo=repo.resolve(), rules=[], sandbox=None, lang="c")
    assert sorted(p.as_posix() for p in ctx.student_submodule_files()) == ["libft/ft_strlen.c", "libft/libft.h"]


def test_what_lives_in_a_submodule_is_not_the_projects_own_file(tmp_path):
    repo = fractol_like(tmp_path, "all:\n")
    (repo / "libs" / "libft" / "ft_split.c").write_text("int x;\n")
    (repo / "libs" / "libft" / "Makefile").write_text("all:\n")
    (repo / "src").mkdir()
    (repo / "src" / "fractol.c").write_text("int y;\n")
    ctx = Ctx(repo=repo.resolve(), rules=[], sandbox=None, lang="c")
    names = {p.as_posix() for p in ctx.files()}
    assert "src/fractol.c" in names and "Makefile" in names and not any(n.startswith("libs/libft/") for n in names)
    assert [p.as_posix() for p in ctx.source_files()] == ["main.c", "src/fractol.c"]
