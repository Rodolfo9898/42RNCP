# verdict

Upload one or more 42 subject PDFs, give it a repository, and get a `verdict.md`:
what the subject requires, what the repo does, and what still needs a human.

```sh
make run           # http://localhost:8000
```

`make` takes care of SSH: it makes sure an ssh-agent is running (yours, or one it starts at `~/.ssh/verdict-agent.sock`),
loads your keys into it (`~/.ssh/id_*`, asking each passphrase once; pick others with `make SSH_KEYS="~/.ssh/work"`), and
mounts the agent's socket into the web container. Clones authenticate through the agent: private keys are never copied
into a container. `make ssh` does only that step.

Settings live in `.env` (never committed). `make run` creates it if it is missing; to change options, start from
`.env.example` (`cp .env.example .env`): it says what is required, what is recommended and what you can leave out.

The subject library is `samples/`, one folder per track:

```
samples/
  en.norm.pdf          the Norm: added by itself to every review where C code is detected
  common-core/
  post-common-core/
  rncp/
```

Click a subject in the sidebar (or a "From libft.pdf p.4" reference under a result) to read the PDF in a tab, like a
file. Pick subjects from **Library…** (grouped by track), or use **Upload PDFs** (or drop PDFs on the sidebar): you choose
Common Core, Post Common Core or RNCP, and the PDF is added to the review and saved in that folder. An existing file
with different content is never replaced.

C is detected when a subject says the project must be written in C or, when no subject names a language, when the
repository has `.c` files and no C++ (vendored minilibx is ignored). The Norm then adds the norminette check and, as
manual items, only the rules the Norm marks with (*), the ones norminette cannot check.
Clone with an SSH URL, e.g. `git@github.com:user/repo.git`.

## Output

`verdict.md` is **one page** that answers three questions, whoever found the answer (a script or claude's review):

- **❌ Lacking — fix these:** failed checks, and requirements claude judged a problem.
- **⚠️ Second look — a human should verify these:** warnings, checks that could not run, requirements claude is unsure about
  or has not assessed yet, and every place where claude says an automated result is wrong.
- **✅ Ok:** checks that passed and requirements claude found ok (or not applicable to the project).

It opens with a headline and a count table, then has the bonus part, the improvements (claude's own list once its review is
merged, otherwise script heuristics) and ends with a **Final verdict**: the checks' result, claude's decision, and "what to do
next". The page is shown in the app (a rendered `verdict.md` tab) and saved in the cloned repository. If the project already
has its own `verdict.md` (or a symlink), it is never touched and `verdict-report.md` is used instead.

Claude's review goes into `verdict.md` only: no separate report file is added to the repository (a `claude-review.md` left
by an earlier version is removed; a project's own file of that name is never touched). Its **structured block** is merged into
`verdict.md`: the prompt asks claude to end the report with one json block answering every numbered requirement
(`likely ok` / `likely a problem` / `unclear` / `not applicable`, a note, what to check by hand, `file:line` evidence), listing
corrections to automated results, improvements and a verdict. Unknown requirement numbers are ignored and any file or line that
does not exist is dropped. If the block is missing, the prose is appended as text instead, with a warning saying why.

Checks run in a disposable copy of the clone, so the clone always shows exactly what was committed. For libraries, the
required functions must be present in the **built** `.a` (found with `nm`), not just defined in the sources.

- **Syntax highlighting:** the file viewer highlights every language Pygments knows (C, C++, Makefile, Python, shell,
  Dockerfile, YAML, JSON, Markdown, ...), tokenized in a throw-away subprocess with a timeout because repository files are untrusted.

## AI review (optional)

Off by default; nothing leaves your computer unless you use it. Configure **one** provider in `.env`
(read automatically by `make run`):

```sh
# Anthropic (default)
ANTHROPIC_API_KEY=sk-ant-...            # optional: LLM_MODEL=claude-sonnet-5-5 for a cheaper run

# ...or any OpenAI-compatible server: api.airforce, OpenRouter, Groq, a local Ollama, ...
LLM_BASE_URL=https://api.airforce/v1    # setting this selects the OpenAI-compatible provider
LLM_API_KEY=sk-...
LLM_MODEL=deepseek-v3
# local server, no key needed:  LLM_BASE_URL=http://host.docker.internal:11434/v1  LLM_MODEL=llama3.1
```

**✨ AI review** asks for confirmation (naming the server that will receive the code), then sends up to ~100,000–150,000
characters of the repository and the subject's manual-review sentences. It returns a description of what is in the
repository, an assessment of each manual-review item ("likely ok / likely a problem / unclear", why a human must check,
and where to look) and extra improvement ideas. Its assessments count in the result (see **Verdict** below) but never change
a check result, every file/line it cites is checked against what it was shown, and uncited claims about the code are dropped. Repository
content is treated as untrusted data in the prompt. The key reaches the web container only, never the sandbox that runs
student code. Models other than Claude have no schema-constrained output: the reply is validated and retried once, and
smaller models may still give weaker answers. A third-party server receives the student's code, so check who runs it.
Plain `http://` is only accepted for a local server. Lower `LLM_MAX_CHARS` if a model's context window is small.
Free servers are flaky and slow, so prefer small *non-reasoning* models (reasoning models such as gpt-oss or glm "think" for minutes
before answering and often hit a gateway's 60-second timeout), keep `LLM_MAX_CHARS` modest (40000), and set `LLM_STREAM=true`:
the answer is then streamed, which keeps the connection alive and lets the app show progress while it arrives.
Free servers are flaky: temporary errors (429, 5xx) are retried with a pause (honouring `Retry-After`; at least 15 s for a rate limit), and
`LLM_FALLBACK_MODELS=model-b,model-c` lists models to try, in order, when the main one is down, rate limited or
needs a balance. The model that actually answered is the one shown in the app and in `verdict.md`.

## norminette

The sandbox image builds norminette from its official repository (https://github.com/42School/norminette) at the pinned
tag `3.3.60`, over SSH when your agent is available at build time (falls back to HTTPS), and aborts if the commit is not
the reviewed one. Bump `NORMINETTE_REF` and `NORMINETTE_COMMIT` in `sandbox/Dockerfile` to upgrade.

## Docker, C, C++ and make: the environment

The sandbox (and claude's terminal) provide the basics: **cc, c++, make**, valgrind, norminette, and the **Docker client**
with `docker compose`. Anything a project needs beyond that is expected to come from a Dockerfile or compose file the student
ships: the review builds and runs it, rather than the app trying to install everything.

- **🔧 Environment** (title bar) checks it for real, in both the sandbox and claude's terminal: each tool's version, a C and a
  C++ program compiled with the strict flags and run through `make`, the Docker daemon, and building and running a tiny
  Dockerfile (the first run downloads a base image, so it needs internet). Only ✖ items make it "not ready"; it also
  appears as one line in the ✨ AI review dialog, so a problem is visible *before* claude starts.
- **claude** is told to confirm the environment first (`cc --version`, `c++ --version`, `make --version`, `docker info`), then to
  look for the student's Dockerfile or compose file and build and run the project with it, telling you each command first.
- **The daemon is separate and rootless** (`dind`, image `docker:dind-rootless`). It is *not* your Mac's Docker: the host's
  `/var/run/docker.sock` is never mounted anywhere. It sees nothing of yours (no projects folder, `.env` or ssh-agent); it only
  receives what a docker client sends it, and keeps its images in the `docker-data` volume. Rootless means a container that
  escapes lands as an unprivileged user. It needs `privileged` to run inside Docker, and it is the only service that has it.
  Tests in `tests/test_images.py` fail if that ever widens.
- **Trade-offs to know:** the sandbox still has no internet, but a student's Makefile can now call `docker`, and containers on the
  daemon *do* have internet (Dockerfiles install packages). If the daemon cannot start on your machine, everything else still
  works and the Environment check says "Docker client is there but no daemon answers". To turn it off, delete the `dind` service
  and the two `DOCKER_HOST` lines from `docker-compose.yml`.

## Claude in a terminal, and the one-click review through it

Three containers run: `web` (the app), `sandbox` (builds and runs student code, no network) and `terminal` (the
`claude` command, with internet but none of the app's secrets).

- **⌨ Claude** opens a real terminal tab on the cloned repository. The first time, type `/login` inside claude and
  sign in with your Claude account; the login is kept in the `claude-home` Docker volume (`make fclean` deletes it).
- **✨ AI review** (with `LLM_PROVIDER=claude-cli` in `.env`; `CLAUDE_MODEL` optionally names a claude model, and no other `LLM_*`
  setting is read) runs the review in the terminal, using your Claude login. **Run** opens the Claude tab and claude starts
  with a prompt built from this run. It lists what the scripts verified (so claude does not redo it) and asks claude to judge
  what they could not: the subject requirements that need a human, plus correctness on edge cases, error handling, memory,
  design and readability. Each point must cite file:line, "unclear" is an accepted answer, and it asks before running
  anything. If a claude tab is already open, the prompt is pasted into it instead. claude saves its report as
  `claude-review.md` in its throw-away copy (you approve that one write); it is picked up automatically, or with
  **💾 Save review to verdict.md** or by closing the tab, and merged into `verdict.md` between the improvements and the closing **Final verdict** section. The report is treated
  as untrusted text (markup defused, headings demoted).
  Check Anthropic's terms for your plan before automating a subscription login this way.
- **Safety:** claude never runs in the original repository. It runs in a throw-away copy (in memory, wiped when you close
  the tab) from which `.git`, `.claude/`, `CLAUDE.md`, `.mcp.json` and every symlink are left out, with `--setting-sources user`
  so hooks and settings shipped in a student's repo are ignored. The interactive terminal asks before each command or edit;
  anything you approve affects only the copy. A student's repo can still try to talk the model into proposing something
  harmful, so read each request before approving it, and never approve one that reads `~/.claude` or sends data out.
- The terminal websocket only accepts pages served by this app (Origin check) and the two containers share a random
  `TERMINAL_TOKEN`, created in `.env` by `make`.

## SSH troubleshooting

The status bar shows `ssh: N key(s)` when the container can use your agent, or `ssh: ⚠ not ready` with the reason
on hover (and in the Clone dialog). On your computer: `ssh-add -l` must list a key that can read the repository; `make ssh` loads them.
Still stuck? This shows what the container sees:

```sh
docker compose run --rm --entrypoint sh web -c 'id; ls -l /run/host-services/; ssh-add -l'
```

`make` mounts your `$SSH_AUTH_SOCK` on Linux and Docker Desktop's `/run/host-services/ssh-auth.sock` on macOS
(`SSH_AGENT_MOUNT` overrides it). Running `docker compose` by hand skips that: use `make`, or export `SSH_AGENT_MOUNT`.

## How it works

1. **Subject parsing** (`src/verdict/spec.py`): no LLM. The field tables (`Program Name`, `Files to Submit`,
   `Makefile`, `External Function`, …) are parsed structurally; the shared "general rules" prose is matched
   against known rules; every other requirement-looking sentence is kept as a *manual review* item.
2. **Checks** (`src/verdict/checks/`): file presence, Makefile rules, compile flags, build, relinking,
   `make clean/fclean/re`, norminette, authorized functions (`nm`), C++ bans, a crash smoke test and a
   valgrind run. Anything that builds or runs the repo goes through the `sandbox` container, which has no
   network, no capabilities and a read-only root filesystem.
3. **Verdict**: it follows the two lists of `verdict.md` for the mandatory part, claude's answers included. `FAIL` when
   anything is under **❌ Lacking** (whatever else there is), `PASS WITH ISSUES` when nothing is lacking but something is
   under **⚠️ Second look** (warnings, requirements nobody or claude could not settle, claude disagreeing with a check),
   `PASS` when both lists are empty. Bonus results are reported separately and never fail the verdict.
   A review (claude's or the AI's) belongs to one repository, commit and set of subjects: changing any of them drops it,
   so the next project never inherits the previous one's answers.

## Limits

- The smoke tests run each program with a few generic arguments. They catch crashes and obvious leaks,
  not wrong behaviour. Per-project functional tests (sorting correctness for push_swap, etc.) are not written yet.
- born2beroot, netpractice, inception and ft_transcendence are not repository checks; their rules are listed for manual review.
- Dev: `uv sync && uv run pytest`. The sandbox-dependent checks are only fully exercised inside Docker.
