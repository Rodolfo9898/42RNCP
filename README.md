# verdict

Upload one or more 42 subject PDFs, give it a repository, and get a `verdict.md`:
what the subject requires, what the repo does, and what still needs a human.

```sh
make run           # prints the link to open: http://localhost:8000/?tkn=...
```

The app is **VS Code in your browser** ([OpenVSCode Server](https://github.com/gitpod-io/openvscode-server)) with a
**Verdict** extension: the shield in the activity bar. Pick a project, add its subject, **Run Checks**, ask claude, read
`verdict.md`. Everything else is plain VS Code: the editor, the terminals (with claude and the 42 toolchain), Source Control,
the Marketplace (see *Interface* at the end). `make url` prints the link again.

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

The **Subjects** view of Verdict lists the PDFs of this review. Add them with **Add from the Library** (grouped by track; the
project's own subject, `push_swap.pdf` for push_swap, comes ticked) or **Upload a PDF**: you choose Common Core, Post Common Core
or RNCP, and the PDF is added to the review and saved in that folder. An existing file with different content is never replaced.

C is detected when a subject says the project must be written in C or, when no subject names a language, when the
repository has `.c` files and no C++ (vendored minilibx is ignored). The Norm then adds the norminette check and, as
manual items, only the rules the Norm marks with (*), the ones norminette cannot check.
Clone with an SSH URL, e.g. `git@github.com:user/repo.git`. The clone is a full git repository (whole history, with its
`.git`), and git is installed in the sandbox and in claude's terminal: the checks' work copy and claude's copy are git
repositories too (without hooks).

**Open Project** (Verdict view) lists the folders already in the projects folder (`./projects`, or `PROJECTS_DIR`): pick one and
it is reviewed where it is. Nothing is cloned, copied or deleted, and `verdict.md` is saved inside that folder. **Clone a
Repository** clones into it first. Only folders inside the projects folder can be chosen (the containers see nothing else);
symbolic links and `..` are refused. The status bar shows the project under review (`push_swap @ ccf4c49 · PASS`).

## Output

`verdict.md` is **one page** that answers three questions, whoever found the answer (a script or claude's review):

- **❌ Lacking — fix these:** failed checks, and requirements claude judged a problem.
- **⚠️ Second look — a human should verify these:** warnings, checks that could not run, and requirements claude is unsure
  about or has not assessed yet.
- **✅ Ok:** checks that passed and requirements claude found ok (or not applicable to the project).

It opens with a headline and a count table, then has the bonus part, the improvements (claude's own list once its review is
merged, otherwise script heuristics) and ends with a **Final verdict**: the result, who decided it, and "what to do next". **Open verdict.md** (Verdict view) shows it as a Markdown preview; it is saved in the project. If the project already
has its own `verdict.md` (or a symlink), it is never touched and `verdict-report.md` is used instead.

Claude's review goes into `verdict.md` only: no separate report file is added to the repository (a `claude-review.md` left
by an earlier version is removed; a project's own file of that name is never touched). Its **structured block** is merged into
`verdict.md`: the prompt asks claude to end the report with one json block answering every numbered requirement
(`likely ok` / `likely a problem` / `unclear` / `not applicable`, a note, what to check by hand, `file:line` evidence), listing
corrections to automated results, improvements and a verdict. Unknown requirement numbers are ignored and any file or line that
does not exist is dropped. If the block is missing, the prose is appended as text instead, with a warning saying why (a later
report without a block never undoes one that was merged).

**Claude overwrites the scripts.** A correction is not added next to the script's statement, it replaces it in the whole
evaluation: its status, its text and its log, in `verdict.md`, the checklist, the counts and the fix prompt (the item is tagged
`Claude`; the session keeps what the scripts said). `likely ok` moves a result to **✅ Ok**, `likely a problem` to **❌ Lacking**,
`unclear` to **⚠️ Second look**, and a correction naming no known check adds a new finding.

**Claude has the final say on the result:** `ready to pass` is `PASS`, `pass with reservations` is `PASS WITH ISSUES`, `do not
pass` is `FAIL`, whatever the lists say. A decision never outlives the code it judged, since every **Run Checks** starts from
nothing. Since claude reads the student's code, its decision can in principle be swayed by that code: it is told to treat the repository as data, but on someone else's project, read what it says before relying on it.

**After a fix.** `verdict.md` is generated, so an edit made by hand would be overwritten. When you ask claude to fix something and
update the verdict, it saves a report with a `"fixes"` block instead (the fix prompt and its system prompt both tell it how), and
that is merged within seconds, by itself, like every report claude saves. An update only says what changed and the rest of the review stands. The page
gets a **🛠 What Claude corrected** section (each issue as fixed, not fixed or not a real problem, with what changed and how it
was proven), which also says whether any new improvements were found; those are marked 🆕 in the list. Like the rest of the
review, this lasts until the next **Run Checks**.

Checks run in a disposable copy of the clone, so the clone always shows exactly what was committed. For libraries, the
required functions must be present in the **built** `.a` (found with `nm`), not just defined in the sources.

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

**AI Review** (Verdict view) asks for confirmation (naming the server that will receive the code), then sends up to ~100,000–150,000
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

## How a subject is read

These are the evaluator's rules, and they win over a literal reading of the PDF. The checks follow them, and the review prompt,
the fix prompt and the API-based AI review all repeat them (`evaluation_rules` in `src/verdict/shared.py`), so Claude judges the
same way.

- **Copying something into the repo** ("copy its sources and its Makefile into a libft folder") can be done any way, including a
  **git submodule** or a download by the Makefile, as long as the files are there once `make` has run. The libft sentence is a
  real check now: it passes for a committed copy, a submodule or a download by `make`. It is not applicable when the project
  does not use a libft or is the libft itself. It fails when the project uses a libft that is nowhere to be found.
- **MiniLibX is not the student's code.** It is found by its files (`mlx.h` next to `mlx_*` files, or MLX42's
  `include/MLX42/MLX42.h`), whatever its folder is called. norminette, the code checks and the AI digest leave it out, and the Norm
  result says so. A submodule the student wrote (their libft, with 42 headers) *is* checked by norminette. A submodule without
  any 42 header (a third-party library) is not.
- **Layout is binding only for libft, ft_printf and get_next_line.** Everywhere else, the files the subject lists must exist, but
  their location is free. `*.h, *.c`, `*/*.h, */*.c` and "all your files (at the root)" are met by `include/` and `srcs/` (or any
  subfolders). Code shared between programs (DRY) beats the subject's folders: if `philo_bonus/` does not exist, its files and
  its build are looked for in `philo/` (or at the root). This only applies to program folders. A missing C++ exercise folder is
  still missing work. In the strict projects, a file in the wrong place stays a second look, or a failure when the subject says
  "at the root".
- **Files added for the evaluation** (a test suite, scripts, a Dockerfile or compose file that installs the dependencies) are
  allowed but must work. When the repo has any, the review gets the item "Files added for the evaluation work". Claude has to
  try them, and if one is broken, the project fails. Test scripts in other languages no longer make "Written in C" a warning.

## norminette

The sandbox image builds norminette from its official repository (https://github.com/42School/norminette) at the pinned
tag `3.3.60`, over SSH when your agent is available at build time (falls back to HTTPS), and aborts if the commit is not
the reviewed one. Bump `NORMINETTE_REF` and `NORMINETTE_COMMIT` in `sandbox/Dockerfile` to upgrade.

## Docker, C, C++ and make: the environment

The sandbox (and claude's terminal) provide the basics: **cc, c++, make**, valgrind, norminette, and the **Docker client**
with `docker compose`. Anything a project needs beyond that is expected to come from a Dockerfile or compose file the student
ships: the review builds and runs it, rather than the app trying to install everything.

- **Check the Environment** (the `…` menu of the Verdict view, or `Verdict: Check the Environment` in the command palette) checks it for real, in both the sandbox and claude's terminal: each tool's version, a C and a
  C++ program compiled with the strict flags and run through `make`, the Docker daemon, and building and running a tiny
  Dockerfile (the first run downloads a base image, so it needs internet). Only ✖ items make it "not ready"; it also
  appears as one line in the AI Review dialog, so a problem is visible *before* claude starts.
- **claude** is told to confirm the environment first (`cc --version`, `c++ --version`, `make --version`, `docker info`), then to
  look for the student's Dockerfile or compose file and build and run the project with it, telling you each command first.
- **A virtual display for programs with a window.** MiniLibX programs (fract-ol, so_long, cub3D…) connect to an X server, and a
  container has none: on Linux that is hidden by sharing the host's, but Docker on a Mac has none to share, so `mlx_init()` fails
  and the program stops with an error of its own ("mlx_init failed (no display available?)"). Both images now carry **Xvfb**: the
  sandbox's runner and the terminal service start one virtual server (`DISPLAY=:99`, no network listener) and give it to every
  command, claude and the shell, restarting it if it dies. Nobody sees the windows; the program draws into memory, so it starts,
  can be crash-tested and run under valgrind. The environment check lists it ("virtual display"); it is optional, so an image
  without it is still "ready". A program that opens a window and waits for input never exits by itself: the smoke runs
  (no argument, bad arguments, a few numbers) do not reach that point for a program that validates its arguments, and a run that
  is still going at its time limit is killed and not counted as a crash.
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

- **claude** is a command in every terminal of the editor. The first time, run `claude` and type `/login` to sign in with your
  Claude account; the login is kept in the `claude-home` Docker volume (`make fclean` deletes it).
- **AI Review** (with `LLM_PROVIDER=claude-cli` in `.env`; `CLAUDE_MODEL` optionally names a claude model, and no other `LLM_*`
  setting is read) runs the review in a terminal of the editor, **claude: review**, using your Claude login. claude starts in the
  project with a prompt built from this run. It lists what the scripts verified (so claude does not redo it) and asks claude to
  judge what they could not: the subject requirements that need a human, plus correctness on edge cases, error handling, memory,
  design and readability. Each point must cite file:line, "unclear" is an accepted answer, and it asks before running anything.
  claude saves its report as `claude-review.md` in a folder outside your project (so no file is added to your repository), and
  you approve that one write. **Every time claude saves it, the report is merged into `verdict.md` by itself**, within a few
  seconds, between the improvements and the closing **Final verdict** section: the first pass, and each later one (a fix and
  update, a second look). A message says what was merged, and `verdict.md` opens as a page without taking the focus from the
  terminal claude is typing in (or updates in place if it is already open). Starting **AI Review** again begins a new pass without
  the last report. A report written for an earlier run of the checks, or for another project, is not merged: the **Verdict: AI
  review** channel says so, and you ask claude again. **Merge claude's Review** (Verdict view) forces the merge when you want it.
  The report is treated as untrusted text (markup defused, headings demoted). The **Verdict: AI review** channel of the Output
  panel logs each step. Check Anthropic's terms for your plan before automating a subscription login this way.
- **Tests happen where the project is.** Every prompt (claude's system prompts, the review prompt, the fix prompt) tells claude to
  build, run and test in the current directory, never in a copy in `/tmp` or another folder, and to keep any scratch files
  inside it and remove them afterwards. In live mode that means the build output lands in your project (claude says so
  before the first build and runs `make fclean` after it when the Makefile has one).
- **Safety:** by default claude works **in your project folder** (see *Your project, live* below), so what it changes is on
  your machine at once. With `TERMINAL_WORKDIR=copy` it never runs in the original: it runs in a throw-away copy (in memory,
  wiped when you close the tab) from which `.claude/`, `CLAUDE.md`, `.mcp.json` and every symlink are left out. The copy keeps
  the clone's `.git` (git works there) but never its hooks or its config, which is replaced by a minimal one, so `.git` cannot
  make git run a program. In both modes claude runs with `--setting-sources user` so hooks and settings shipped in a student's
  repo are ignored, and with `--strict-mcp-config`. The interactive terminal asks before each command or edit; in copy mode
  anything you approve affects only the copy, and nothing done there goes back to your project. A
  student's repo can still try to talk the model into proposing something harmful, so read each request before approving it,
  and never approve one that reads `~/.claude` or sends data out.
- The editor only opens with its token (`?tkn=EDITOR_TOKEN` in the link, once per browser) and listens on this machine only
  (`127.0.0.1`). The web app and the terminal service share another random `TERMINAL_TOKEN`; both are created in `.env` by
  `make`. The editor and its terminals get none of the app's secrets (no API key, no token).

## Terminals, to try things by hand

**Terminal > New Terminal** (Ctrl+\`) opens a `zsh` in the editor's container, in the projects folder: `cd` into a project and
run `make`, valgrind, norminette or claude yourself. Splits, tabs, moving a terminal into the editor area and every other VS Code
terminal feature work as usual. With `TERMINAL_WORKDIR=copy`, the claude of **AI Review** works in a throw-away copy instead of
the project (see *Safety* above); terminals you open yourself are always in the real folders.

It is the terminal container, not the sandbox: same toolchain (cc, c++, make, valgrind, gdb, norminette, the readline and X11
headers) and the same `docker` client pointed at the separate rootless daemon, but with internet. The sandbox that runs the
checks has no network, so it cannot answer questions like "does `apt-get install` work here". Two limits to know when you
experiment:

- The container is read-only and not root, so `apt install` is not possible. Test what a project needs where it will really
  run: `docker build -t try . && docker run --rm -it try sh` (or `docker compose up --build`) from the shell. The daemon only
  receives the build context, so bind mounts such as `-v "$PWD":/work` do not see your files; put them in the image with
  `COPY`. `pip install --user` and `npm install` into your home work (it is the `claude-home` volume).
- Only the copy in `/scratch` is writable apart from your home and `/tmp`; it is memory, so a very large build can fill it.

### The subject PDFs, inside the sandbox and the terminal

Both places can read the PDFs of the review you are doing: the subjects you chose from the library or uploaded, and
`en.norm.pdf` whenever the Norm applies (C detected). They are the same files that the app shows in its PDF tabs, and they
follow the review: add or remove a subject and the folder changes the next time the checks run or a terminal tab opens.
The folder is named by the **`$SUBJECTS_DIR`** environment variable:

- **The checks (Run Checks).** Every command the checks run in the sandbox sees `SUBJECTS_DIR=/workspace/<session>/subjects`
  (the runner accepts that one variable and only for an existing folder inside its allowed roots, so a request cannot
  set `PATH`, `LD_PRELOAD` or anything else). A script or tester that needs the subject can open `"$SUBJECTS_DIR/libft.pdf"`.
- **claude and the terminals.** `SUBJECTS_DIR=/scratch/subjects/<session>`; the shell's first line prints it, and the review
  prompt tells claude where the PDFs are so it can read the pages the requirements cite ("libft.pdf p.4") instead of guessing.
  The terminal container still mounts neither the workspace nor `samples/`: the web app hands it exactly this review's PDFs
  over the same token-protected channel as everything else (only what is missing or different is sent), the files are
  read-only (0444) and are checked on arrival (a plain `*.pdf` name, starts with `%PDF`, size limits), and they are deleted
  when the review's last claude or shell tab closes. They live outside the working copy and the project.
- Copies, not the library: changing a PDF in `samples/` does not change a review that already has its copy. The read-only
  permission protects against accidents; the sandbox's workspace volume is shared by all reviews, so code that is deliberately
  hostile could still overwrite a PDF there (as it could before). The checks do not depend on the file contents: the rules
  were read from the PDF when it was added.

Rebuild the images once to get this (`make build`, then `make run`; `make re` is not needed and would also wipe your sessions and
your Claude login).

### Your project, live: the tunnel to your machine

By default **Claude and the terminals work directly in your project folder**: the terminal container mounts `./projects` read-write,
and its tabs start in `/projects/<name>`, which *is* `./projects/<name>` on your machine. Nothing is copied and nothing is sent
back later: a file claude edits, creates or deletes, or that you change in the Shell, is changed on your machine at that moment,
and your editor sees it as it happens (the app's file tree refreshes every few seconds while a terminal tab is open). The
terminal tab says so in its top bar and the shell prints it on its first line.

What stays isolated is where things **run**, not where files **live**: claude, the shell and everything they build and run
(`make`, your programs, `docker build`) execute inside the containers, with their own toolchain and no access to the rest of your
machine, so "does it build and run with only what is installed there?" is answered honestly. Only the project folder is shared.

- **Run Checks still uses a disposable copy.** The checks run `make clean`, `make fclean`, `make re` and the project's own
  Makefile rules, and building leaves objects and binaries behind. Doing that in your real folder could delete or clutter your
  files, so each run copies the folder (as it is at that moment, with everything claude has just changed) into the sandbox and
  works there. Run the checks again after claude edits something to see the new result.
- **Build output lands in your project.** When claude or you build in the Shell, `.o` files and binaries are created in
  `./projects/<name>`. `make fclean` removes them; they show up in `git status` unless the project's `.gitignore` covers them.
- **Claude's review report is not written into your repository.** Working in place, claude saves `claude-review.md` in a folder
  outside the project (`$REPORT_DIR`), the app merges it into `verdict.md` as before, and it is deleted with the session.
- **git works in the project.** The project is declared safe for git inside the container (that one folder, for that process
  only, nothing written to any git config), so `git status`, `git diff`, `git pull` and, with `TERMINAL_SSH=1`, `git push` work in
  it directly, with the project's real `origin`.
- **What you give up.** There is no review step between claude's edit and your files (you still approve each edit in the
  terminal), `git diff` is how you review afterwards, and the protections of the throw-away copy do not apply: a student's
  `CLAUDE.md` and `.claude/` are in the folder claude starts in. `--setting-sources user` still keeps project settings and hooks
  out and `--strict-mcp-config` project MCP servers, but a `CLAUDE.md` is plain instructions that claude may read; claude is told
  to treat the folder as untrusted. And anything that runs in the terminal container can change every repository in
  `./projects`, `.git/hooks` included (see *the projects folder is read-write* below).
- **Back to the safe way:** `TERMINAL_WORKDIR=copy make run` (or that line in `.env`) makes claude and the shell work on
  throw-away copies again: a scratch space, where nothing done goes back to your project. Use it for code you do not trust.

### The projects folder is read-write everywhere

The web app, the sandbox and the terminal container all mount `./projects` read-write, so from a terminal of the panel you can work
directly in `/projects/<name>` (`git pull`, edit, `git status`), and whatever lands there is writable. The price: anything that
runs in the terminal container, including a peer's code that claude builds or runs there, can change **every** repository in
that folder, `.git/hooks` and `.claude/` included, and those run on your machine the next time you `git commit` or open the
project. A read-write mount cannot be limited to one project. If you review code you do not trust, start with
`TERMINAL_PROJECTS_MODE=ro TERMINAL_WORKDIR=copy make run` (or those lines in `.env`): the terminal then reads the projects folder
but cannot write to it, and nothing done in it can reach a project.

The Verdict extension looks at claude's report (`/scratch/reports/<session>/claude-review.md`) every two seconds and, each time it
has been saved and has stopped changing, calls `POST /api/sessions/{id}/claude-review/collect`: a report that was asked for by this
review (same project, commit, subjects and run) is merged into `verdict.md`; any other is reported as `stale` and left out. If
claude's report was not picked up anyway (after a new run, or from another commit), `POST /api/sessions/{id}/claude-review/save`
merges the one it saved into `verdict.md` for the project as it is now, whatever the app thought of it before.

### `git push` from the terminal (opt-in)

Off by default: the terminal container has none of your credentials. To clone or push from claude's terminal or the shell, switch it on.
A new key does not change that: the **Clone** dialog of the page works because the *web* container shares your ssh-agent, but a
`git clone` typed in a terminal of the editor (or by claude) answers "Permission denied (publickey) … make sure you have the correct
access rights" until this is on. Each of those tabs says which it is in the bar above the terminal ("git over ssh is off here" /
"works here"). Only keys that are in your ssh-agent count (`ssh-add -l` on your computer); a key file in `~/.ssh` is not enough,
and `make ssh` only loads files named `~/.ssh/id_*` (or `make ssh SSH_KEYS="~/.ssh/other"`).

```sh
make run TERMINAL_SSH=1        # or put a line TERMINAL_SSH=1 in .env, then make run
```

This adds `docker-compose.ssh.yml`, which gives **only the terminal container** the same ssh-agent socket the web container
already uses for cloning (no `.env`, no API keys; the sandbox that runs student code gets nothing). **What you are agreeing to:**
while it is on, anything that runs in that container can use your keys through the agent, including a peer's code that claude
builds or runs there. The agent never reveals the key, but it signs for GitHub as you, so such code could push to any repository
your key can write to. So load a **dedicated key** that only reaches the repositories you push to (`ssh-add -D`, then
`ssh-add ~/.ssh/that_key`), and turn the switch off (`make run` without it) when you review code you do not trust. The line in `.env` may have spaces or quotes around the `1`;
anything else than `1` leaves it off, and the terminal tab says so.

### Submodules during the checks: `SANDBOX_GITHUB=1`

A project whose Makefile runs `git submodule update` fails **make builds** by default, because the sandbox has no route out. To let
it fetch public submodules from GitHub:

```sh
make run SANDBOX_GITHUB=1      # or put a line SANDBOX_GITHUB=1 in .env, then make run
```

This adds `docker-compose.sandbox-github.yml`, which gives the sandbox one new route: `github-gateway`, which forwards to
`github.com:443` and nothing else, so there is still no general internet. No key is involved: the sandbox has no ssh client and never
gets your ssh-agent, so code under review cannot act as you. `git@github.com:` addresses are read as `https://github.com/`, so a
public submodule works whichever form `.gitmodules` uses. A private submodule or one on another host stays unreachable.
Code under review can still send data to GitHub over this route, so turn the switch off if that matters for what you are reviewing.

Cloning and pushing over ssh are separate and do not change: the web app clones through your ssh-agent, and the terminal pushes with `TERMINAL_SSH=1`.

Inside the tab, once: `git config --global user.name "…"` and `git config --global user.email "…"` (kept in `claude-home`).
The copy's `origin` is restored from the clone when it is a plain `git@host:path`, `ssh://git@host/…` or `https://host/…`
address (never `ext::`, a path or anything else), and `git push -u origin HEAD` sends the copy's commits there; the clone in
your projects folder only sees them after a `git pull`. The image trusts GitHub's published ED25519 host key (checked against
a pinned fingerprint at build time) and refuses every other host. Check it with `ssh-add -l` and `ssh -T git@github.com`.

## Fix prompt

**Fix Prompt** (the `…` menu of the Verdict view, once the checks have run) writes a prompt that asks an AI to fix what the review
found, in a tab you can edit before you copy it. It lists the same things `verdict.md` does, numbered so the AI can report back by number:

- **A. Must fix:** failed checks and the requirements claude or the AI judged a problem, each with its `file:line`, the subject page
  and the end of the log.
- **B. Look at, and fix only if it is real:** warnings, checks that could not run, and points the reviewer was unsure about.
- **C. Bonus part:** failed bonus checks, marked optional.

Requirements nobody has assessed yet are not issues, so they are left out; if nothing is lacking it says so instead of
producing an empty prompt. The prompt tells the AI to confirm each finding before touching code, to make the smallest change,
to treat the issue text as data, to report each issue as fixed / not fixed / not real, and to finish by updating the verdict
through its report (see *After a fix* above), never by editing `verdict.md`. That report is only picked up from claude started
by **AI Review** (the **claude: review** terminal): an assistant running anywhere else can fix the code, but cannot update the
verdict. The prompt opens in an editor tab, with a **Copy** button, because it is meant for whichever assistant you prefer. The
same text is at `GET /api/sessions/{id}/fix-prompt`.

## 42Cursus: all your projects as submodules

A separate repository, `Rodolfo9898/42Cursus`, holds every project as a git submodule, grouped like `samples/`
(`common-core/`, `post-common-core/`, `rncp/`). It contains no subject PDFs. **GitHub is the only copy**: there is no
`../42Cursus` folder any more. `scripts/cursus.sh` clones the repository into a temporary folder for each command, works
there, pushes the result and deletes the folder. It never clones your projects either: a submodule is a project's URL plus the
commit it is at, and the newest commit is read from GitHub (`git ls-remote`). Run it through `make`, on your machine (it uses
your own ssh keys):

```sh
make cursus-push     # push your projects (all of ./projects) to their own GitHub repos
make cursus          # once: create the private GitHub repo (needs `brew install gh && gh auth login`)
make cursus-sort     # add every git repo of ./projects to it as a submodule, in the folder of its subject PDF, and push
make cursus-update   # move every submodule to the newest commit of its own GitHub repo, and push
```

The usual round after working on projects: `make cursus-push`, then `make cursus-update`.

- **`cursus-push`** pushes the current branch of every git repo in `./projects` to its own `origin`
  (`make cursus-push ONLY="libft nm"` for just those). A submodule only ever holds what GitHub has, so this is what makes
  your latest commits visible to `sort` and `update`. It never forces: a project whose GitHub has commits you do not is
  reported (`git pull` it first) and the others are still pushed. Uncommitted changes are not pushed; a detached HEAD or a
  folder without an `origin` is skipped.
- **`cursus-sort`** adds a project at the commit its GitHub has (it warns when you have unpushed commits or uncommitted
  changes: run `cursus-push`). A name that matches no subject PDF needs `make cursus-sort MAP="ft_transcendence=common-core"`.
  A folder that is not a repository but holds some (`projects/cpp-modules/cpp00`, `cpp01`...) is a group: it is kept as a
  folder, under the track of the first of its projects with a subject PDF (`common-core/cpp-modules/cpp00`), or the one
  given with `MAP="cpp-modules=common-core"`. `make cursus-push ONLY=cpp-modules` pushes all of its projects,
  `ONLY=cpp-modules/cpp00` just that one.
- **`cursus-update`** moves each submodule to the newest commit of its own repository (its default branch, or the `branch`
  set for it in `.gitmodules`) and commits the new positions in one commit (`Update N project(s)`, listing them). The report
  says per project what it did: `up common-core/libft: 69ba8fd -> 3c1e0a2`, `ok … already the newest`, `skip …`, `fail …`.
  A project that cannot be read (network, ssh key, deleted repository) is reported, makes the command end with an error,
  and does not stop the rest.
- **Add `CURSUS_DRY_RUN=1`** (e.g. `make cursus-update CURSUS_DRY_RUN=1`) to see what would happen without pushing or creating
  anything. If a push is refused (someone else pushed meanwhile), run the command again.
- Addresses are only followed over `file`, `git`, `http(s)` and `ssh`, never `ext::`, because project URLs come from repositories
  other people wrote. `CURSUS_REPO`, `CURSUS_URL`, `CURSUS_VISIBILITY` and `PROJECTS_DIR` change what is used; `CURSUS_DIR` and
  `CURSUS_PUSH` no longer exist. If you still have the old `../42Cursus` folder, check `git -C ../42Cursus status -sb` shows
  nothing ahead of `origin`, then delete it.

## SSH troubleshooting

The status bar shows `ssh: N key(s)` when the container can use your agent, or `ssh: ⚠ not ready` with the reason
on hover (and in the Clone dialog). On your computer: `ssh-add -l` must list a key that can read the repository; `make ssh` loads them.
Still stuck? This shows what the container sees:

```sh
docker compose run --rm --entrypoint sh web -c 'id; ls -l /run/host-services/; ssh-add -l'
```

A failed clone now says what the container's ssh did: when GitHub refuses the sign-in, the app tries once more (a server can
answer differently from one connection to the next), then shows the fingerprints of the keys the agent offered and whether GitHub
accepted none of them, knew one but got no signature from the agent, or signed you in as an account that cannot read the
repository. Compare the fingerprints with https://github.com/settings/keys (`ssh-keygen -lf ~/.ssh/<name>.pub` prints yours). To see
the same from the container by hand:

```sh
docker compose run --rm --entrypoint sh web -c 'ssh -vT -o BatchMode=yes git@github.com 2>&1 | grep -E "Offering|accepts|Authenticated|Hi |denied"'
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
   **Submodules.** The sandbox has no network on purpose, but many projects keep their libs (libft, ft_printf, MiniLibX) as
   submodules that the Makefile downloads. So before the build the app downloads them into the disposable copy, at the commits the
   project records: over https without credentials (or, for github.com, through your ssh-agent when the repository is private),
   only from github.com, gitlab.com, bitbucket.org, codeberg.org and the project's own host, at most 10 and two levels deep (never an
   `ext::` address, a path or an option). What lives in a submodule belongs to another repository, so it is not part of the project's
   own files (no Norm, no function check, no required-files look at it). A build that still fails *because it needed the network*, or
   because a submodule it needs is missing, is not called ❌ Lacking: it goes under **⚠️ Second look** with the reason and what was
   tried, since only a build with a network can settle it (`git submodule update --init` and `make` in Claude or a terminal).
   **File presence follows what the subject allows about structure.** A list such as ft_printf's
   `Makefile, *.h, */*.h, *.c, */*.c` means "at the root *or* in a subfolder", so `*.c` and `*/*.c` are one requirement and
   either place satisfies it (a project that keeps everything at the root is fine). A required file that exists but not where the
   list says (`libft.h` found as `includes/libft.h`) is not called missing: it goes under **⚠️ Second look**, naming where it is,
   because only the subject's wording (and a human, or claude) can say whether that layout is allowed. Only a file found
   nowhere (vendored folders such as minilibx do not count) is **❌ Lacking**.
   **The subject's text counts, not only its tables.** Many subjects give their files only in sentences or lists, so those become
   **Required files named in the subject** too, but only under strict conditions: an obligation (*must, have to, required,
   expected to, should*) that names a concrete file or folder, never a condition ("if you use OCaml…"), an example, something
   optional or forbidden, or a bonus. What is read: "you must submit a Makefile" (also "turn in", "provide", "use", "A Makefile
   is required"), "a `signature.txt` file at the root of your repository", "a file called `author`", "a header named
   `libftpp.hpp`", the top-level items of a list introduced as the mandatory files ("The following files are mandatory": never
   the *Optional but Recommended* one), the chapter about turning the work in, and a listing of the expected layout
   (`$> ls -alR`, or `$> ls`). The README keeps its own check, and what a table already asks for is not asked twice.
   Three details: "**at the root**" is taken literally (a file found elsewhere then fails, instead of being a second look); a
   name that only appears in an **example layout** (inception's `ls -alR`, boot2root's `ls`) is a hint: if missing it is a
   **⚠️ Second look**, never Lacking; and a "Files to Submit" cell that says "all at the root of the repository" now enforces it.
   On the library this gives 20 subjects a check they never had (for example `ft_ping`, `ft_nmap`, `strace`, `nm`, `h42n42`,
   `born2beroot`'s and `leaffliction`'s `signature.txt`, `ft_select`'s `author`, `libftpp`'s headers); a test pins the exact
   result for every subject, so a parser change that adds or drops one shows up for review. Since the rules are read again from
   the PDFs at every **Run Checks**, an existing review gets them without adding the subject again.
3. **Verdict**: until claude's review is merged it follows the two lists of `verdict.md` for the mandatory part. `FAIL` when
   anything is under **❌ Lacking** (whatever else there is), `PASS WITH ISSUES` when nothing is lacking but something is
   under **⚠️ Second look** (warnings, requirements nobody or claude could not settle),
   `PASS` when both lists are empty. Bonus results are reported separately and never fail the verdict.
   **After claude's merge, claude has the final say**: its decision is the result (`ready to pass` is `PASS`, `pass with
   reservations` is `PASS WITH ISSUES`, `do not pass` is `FAIL`), even when the lists alone would say something else. The Verdict
   window and `verdict.md` then read "decided by Claude", give its reason and say what the lists alone would have said, so you
   can see the disagreement. A report without a verdict in it decides nothing: the lists do.
4. **Every Run Checks starts from nothing.** The server first ends claude's session (its report is thrown away, not
   collected), forgets claude's review and the AI review, deletes the `verdict.md` it wrote into the project (a `verdict.md`
   of your own, without this app's marker, is never touched), and runs a `git pull` (fast-forward only) in the project, so the
   checks look at what is on GitHub now. A pull that cannot be done (no remote, no network, local changes in the way) is
   reported in the status bar (`git pull skipped: …`) and the checks run anyway. In the page, claude's tab, the verdict window,
   the open files and diffs are closed, the search is cleared, and the explorer and Source Control are read again; the subject PDFs
   and the terminals stay. A terminal opened
   before the run can never bring its old report back. Close and reopen Claude after the run to review the new state.

## Limits

- The smoke tests run each program with a few generic arguments. They catch crashes and obvious leaks,
  not wrong behaviour. Per-project functional tests (sorting correctness for push_swap, etc.) are not written yet.
- born2beroot, netpractice, inception and ft_transcendence are not repository checks; their rules are listed for manual review.
- Dev: `uv sync && uv run pytest`. The sandbox-dependent checks are only fully exercised inside Docker, and the Verdict
  extension (`terminal/vscode/verdict/`) only inside the editor. Its logic (the merge after every pass, the JSON view, the
  markdown buttons) is run in node against a fake editor by `tests/js` (`uv run pytest` does it when node 20+ is there); `make
  test-extension` also installs the TextMate engine that checks the colours of the ignore files. How the real editor draws it is
  not covered: look at it once after changing the extension.

## Interface

The app is [OpenVSCode Server](https://github.com/gitpod-io/openvscode-server) (VS Code in the browser, the same version for
everyone: it is pinned and its checksum verified in `terminal/Dockerfile`). It runs in the `terminal` container, opened on the
projects folder, so its terminals have claude and the whole toolchain. Everything VS Code does works: editing, Source Control,
search, splits, themes, keys, Settings.

**Verdict** (the shield in the activity bar, `terminal/vscode/verdict/`) is the review:

| Where | What |
|---|---|
| Review view | the result, the checks grouped by status (a `file:line` opens the file at that line), the AI review; its title bar has **Run Checks**, **AI Review**, **Merge claude's Review** (only to force it: claude's reports are merged by themselves), **Open verdict.md**, **Open Project**, and in `…` **Fix Prompt**, **Clone a Repository**, **Refresh**, **Check the Environment** |
| Subjects view | the PDFs of this review: **Add from the Library**, **Upload a PDF**, ✕ to remove one |
| Output panel | **Verdict: Checks** (what the run logged) and **Verdict: AI review** (each step of the AI review) |
| Status bar | the project under review, its commit and the result; a click opens the Review view |

Every action is also a command: ⇧⌘P / Ctrl+Shift+P, then type `Verdict:`.

### Reading files

- **Markdown opens as the page** (VS Code's own Markdown preview, set as the editor of `*.md`), styled like GitHub by the
  [Markdown Preview Github Styling](https://open-vsx.org/extension/bierner/markdown-preview-github-styles) extension of the list
  below. The title bar has a **`</>` Show Markdown Source** button, and the source has an **Open Markdown Page** button to go back
  (VS Code's own "Show Source" does not work when the page is the default, so these replace it). The same two are in the Command
  Palette; **View: Reopen Editor With…** also works.
- **JSON is shown pretty-printed.** A `.json` file saved on one line, or in very long lines, opens as `name (pretty).json`: indented, one
  value per line, with the JSON colours, folding and search. It is read-only and the file on disk is never changed (numbers
  and keys are printed exactly as they are in the file). The title bar has **Open the Raw JSON File** to edit it; a file that
  is shown raw and is hard to read has **Show Pretty JSON** to go back. A pretty view follows its file when it changes. A file that
  is readable already opens as usual; turn the whole thing off with the setting `verdict.json.prettyOnOpen`.
- **`.gitignore`, `.dockerignore` and the other `*ignore` files** (`.npmignore`, `.eslintignore`, `.prettierignore`, …) are coloured: comments,
  `!` negations, `*` `**` `?` wildcards, `[a-z]` classes, `\` escapes, `/`. (VS Code alone colours only the `#` comments of a `.gitignore`,
  and does not know `.dockerignore` at all.) **`.gitmodules`** is read as a properties file: sections, keys and values are coloured.
  The associations are in `terminal/vscode/settings.json` (`files.associations`).

### Extensions

Extensions come from [Open VSX](https://open-vsx.org) (the Microsoft Marketplace is not open to other editors; almost every
popular extension is published on both). `config/extensions.txt` is their list:

- at every start, each one listed and not yet installed is installed, so a new machine (or `make fclean`) gets them back without
  you looking for them again;
- an extension you install in the editor is **added to the list by itself**, one you uninstall is taken off (within ~10 seconds);
- edit the file by hand too: one id (`publisher.name`, as on the extension's page) per line, `#` starts a comment.

[Git Graph](https://open-vsx.org/extension/mhutchie/git-graph) and the GitHub styles for the Markdown page are listed by default. Rainbow brackets need no extension: they are
VS Code's own bracket pair colours, on by default (`editor.bracketPairColorization`), with indent guides for the bracket pair
under the cursor. The classic *Rainbow Brackets* extension is not on Open VSX.

The installed extensions and your settings live in the `claude-home` volume (`~/.openvscode-server`), so they survive a restart;
the defaults this app starts with are in `terminal/vscode/settings.json` (what you change in Settings wins over them).

### Workspace Trust

The first time, VS Code asks whether you trust the authors of the files in `/projects`. **No** (Restricted Mode) is the safe
answer for someone else's project: VS Code then runs no task, debugger or workspace setting from it, and some extensions are
off. Verdict works in both modes (it never runs the project's code itself). **Yes** enables everything; you can change it later
from the shield in the status bar.
