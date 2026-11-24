"""What a repository must not contain, whatever its subject: build artifacts and secrets."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from verdict.checks.context.ctx import Ctx
from verdict.checks.engine.checker import Audit
from verdict.checks.engine.results import result
from verdict.core.models import CheckResult, Evidence

BINARY_MAGIC = (b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"MZ")
ARTIFACT_SUFFIXES = frozenset({".o", ".a", ".so", ".dylib", ".out", ".exe"})
SECRET_PATTERNS = (
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "GitHub token"),
    (re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"), "API key"),
)
SECRET_FILENAMES = frozenset({".env", "id_rsa", "id_ed25519", ".npmrc", ".pypirc"})
MAX_SCANNED = 4000
MAX_SCANNED_BYTES = 500_000


class RepoHygiene(Audit):
    """Compiled files and credentials that were committed (an audit of the whole tree, outside any rule of the subject)."""

    def run(self, ctx: Ctx) -> Iterable[CheckResult]:
        artifacts, secrets = self._scan(ctx)
        yield result(
            None, "warn" if artifacts else "pass",
            f"{len(artifacts)} compiled/system file(s) committed; only sources should be submitted." if artifacts
            else "No object files, binaries or .DS_Store committed.",
            title="Repository contains no build artifacts", evidence=artifacts[:30],
        )
        yield result(
            None, "fail" if secrets else "pass",
            f"{len(secrets)} possible secret(s) found." if secrets else "No credentials or private keys found.",
            title="Repository contains no secrets", evidence=secrets[:30],
        )

    def _scan(self, ctx: Ctx) -> tuple[list[Evidence], list[Evidence]]:
        artifacts: list[Evidence] = []
        secrets: list[Evidence] = []
        scanned = 0
        for rel in ctx.files():
            posix = rel.as_posix()
            if ctx.is_vendored(posix):
                continue
            path = ctx.repo / rel
            try:
                head = path.open("rb").read(4)
            except OSError:
                continue
            if rel.suffix in ARTIFACT_SUFFIXES or rel.name == ".DS_Store" or any(head.startswith(m) for m in BINARY_MAGIC):
                artifacts.append(Evidence(file=posix, snippet="compiled or system file committed"))
            if rel.name in SECRET_FILENAMES or rel.suffix in (".pem", ".key"):
                secrets.append(Evidence(file=posix, snippet="file usually holds credentials"))
            if scanned < MAX_SCANNED and path.stat().st_size < MAX_SCANNED_BYTES and head[:1] != b"\x7f":
                scanned += 1
                secrets += self._leaked_in(ctx, rel, posix)
        return artifacts, secrets

    @staticmethod
    def _leaked_in(ctx: Ctx, rel: Path, posix: str) -> list[Evidence]:
        text = ctx.read(rel)
        found = []
        for pattern, kind in SECRET_PATTERNS:
            m = pattern.search(text)
            if m:
                found.append(Evidence(file=posix, line=text.count("\n", 0, m.start()) + 1, snippet=f"looks like a {kind}"))
        return found
