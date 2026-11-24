from verdict.checks import Ctx

from tests.verdict.checks.helpers import archive_repo, needs_build_tools


@needs_build_tools
def test_objects_and_libraries_are_not_executables(tmp_path, local_sandbox):
    repo = archive_repo(tmp_path)
    ctx = Ctx(repo=repo.resolve(), rules=[], sandbox=local_sandbox, lang="c")
    assert ctx.build(".").ok and (repo / "gnl.o").is_file()
    assert ctx.executables(".") == []
    assert [p.name for p in ctx.libraries(".")] == ["gnl.a"]


@needs_build_tools
def test_shared_libraries_are_not_executables(tmp_path, local_sandbox):
    (tmp_path / "lib.c").write_text("int\tf(void)\n{\n\treturn (0);\n}\n")
    assert local_sandbox.exec(["cc", "-shared", "-fPIC", "lib.c", "-o", "libf.so"], tmp_path).ok
    ctx = Ctx(repo=tmp_path.resolve(), rules=[], sandbox=local_sandbox, lang="c")
    assert ctx.executables(".") == []
    assert [p.name for p in ctx.libraries(".")] == ["libf.so"]
