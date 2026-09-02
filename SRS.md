# SRS — whats-deployed

**Read this top to bottom once, then work through §7 in order.**
Scope note: **§7 Milestone 1 is a single day's work.** Everything after it is deliberately later.

---

## 1. Purpose
A read-only agent, running on a server, that reports the git state of every deployed project on that host
and **judges whether anything is wrong** — behind the remote, on the wrong branch, or pulled without a restart.

## 2. Scope

**In scope (eventually):** reading git state · deriving status · one HTML page · adding/removing tracked
projects from that page · systemd + nginx deployment.

**Out of scope, permanently:** triggering deploys · writing to any repository · a database · user accounts ·
aggregating multiple hosts · anything that changes the state of the machine it observes.

## 3. Definitions
| Term | Meaning |
|---|---|
| **Project** | A directory on this host that is a git checkout of a deployed application |
| **Checked out** | The commit currently on disk (`HEAD`) |
| **Behind** | Commits on `origin/<main_branch>` not in `HEAD` |
| **Drift** | Any deviation from "on main, up to date, restarted" |
| **Stale** | No new checkout for more than `stale_days` |

## 4. Functional requirements

### Reading git state
- **FR-1** For each configured project, report: branch · short SHA · commit subject · commit time · checkout time.
- **FR-2** Checkout time is the mtime of `.git/HEAD` (when the checkout last changed) — **not** the commit time.
- **FR-3** Use cheap plumbing commands only. **Never `git status`** unless `check_dirty` is enabled for that project:
  ```
  git -C <path> rev-parse --abbrev-ref HEAD
  git -C <path> rev-parse --short HEAD
  git -C <path> log -1 --format=%s%n%cI
  ```
- **FR-4** A project whose path is missing, unreadable, or has no `.git` reports status `none` — **never an error page.**
- **FR-5** Results are cached in memory for `cache_seconds`.

### Judging
- **FR-6** Derive exactly one status per project, first match wins:

  | Condition | Status | Text |
  |---|---|---|
  | no `.git` / unreadable | `none` | `no git repo` |
  | `branch != main_branch` | `bad` | `not on main` |
  | `process_started_at < checked_out_at` | `warn` | `pulled, not restarted` |
  | `behind > behind_warn` | `warn` | `N behind` |
  | `checked_out_at` older than `stale_days` | `bad` | `stale (Nd)` |
  | `behind` could not be resolved | `none` | `? unknown` |
  | otherwise | `ok` | `in sync` |

- **FR-7** `behind` = `git rev-list --count HEAD..origin/<main_branch>`. If the ref is missing or the count fails,
  `behind = null` → `? unknown`. **Never render a guessed number.**
- **FR-8** `process_started_at` comes from `systemctl --user show -p ActiveEnterTimestamp <service>` (or the system
  bus). If no `service` is configured, skip the restart check entirely — do not infer it.

### Presenting
- **FR-9** `GET /` renders the page: a summary line, then one row per project.
- **FR-10** The summary states the conclusion first: `N projects · M need attention`.
- **FR-11** Each row shows the **commit subject**, not only the SHA, and **relative times** (`9d ago`).
- **FR-12** `GET /fragment` renders only the table, for refresh without a full page reload.
- **FR-13** `GET /api` returns the same data as JSON.
- **FR-14** The page refreshes itself every 30s by swapping `/fragment`.

### Managing projects (Milestone 4 — not day one)
- **FR-15** `GET /api/discover` scans `allowed_roots` and returns git repos **not already tracked**, each with
  `id`, `path`, `branch`, `commit`, `subject`, `age`, where **`id = sha256(realpath)`**.
- **FR-16** `POST /api/projects` accepts `{id, name, service}`. **It must never accept a path.**
- **FR-17** Before accepting: `os.path.realpath()` **then** verify the result is inside `allowed_roots`, is a git
  repo, and is not already tracked. Reject otherwise.
- **FR-18** `DELETE /api/projects/{name}` stops tracking. **It must not touch the repository.**
- **FR-19** Config writes are atomic (temp file + `os.replace`). Every add/remove is logged with the source IP.
- **FR-20** `allow_ui_edit: false` hides the panel and makes the write endpoints return 403.

## 5. Non-functional requirements

### Security — these are not optional
- **NFR-1** Bind to `127.0.0.1` only. nginx is the sole route in.
- **NFR-2** `subprocess.run([...])` with a fixed argv list. **Never `shell=True`.** Never interpolate into a shell.
- **NFR-3** Never return raw stderr to the client — it leaks filesystem paths. Log it; return a generic message.
- **NFR-4** Read endpoints: token or IP allowlist. **Write endpoints: a separate admin token.**
- **NFR-5** Runs as an unprivileged user with read access only.

### Other
- **NFR-6** A page load must not take more than ~2s for 10 projects (hence FR-5's cache).
- **NFR-7** Exactly **one** uvicorn worker — config and cache are in-process.
- **NFR-8** Dependencies: `fastapi`, `uvicorn[standard]`, `jinja2`. **No others without a real reason.**
- **NFR-9** No frontend framework, no build step, no static asset files. CSS and JS inline in the template.
- **NFR-10** Python 3.11+.

## 6. Data contract
```json
{
  "host": "prod-01",
  "fetched_at": "2026-09-02T09:14:03+06:00",
  "projects": [{
    "name": "raptor",
    "path": "/srv/raptor",
    "branch": "main",
    "commit": "a3f9c21",
    "subject": "fix: celery retry on redis timeout",
    "committed_at": "2026-09-02T07:02:11+06:00",
    "checked_out_at": "2026-09-02T07:14:55+06:00",
    "process_started_at": "2026-09-02T07:15:30+06:00",
    "behind": 0,
    "dirty": false,
    "status": "ok",
    "status_text": "in sync",
    "note": null
  }]
}
```

---

## 7. BUILD ORDER

### 🎯 Milestone 1 — a working local page. **This is the one-day target.**
No auth, no drift, no discovery, no deployment. Just: config → git → status → page, on localhost.
**Each step ends with something you can run.** Do not move on until it runs.

- [ ] **1. Skeleton (~15 min).** venv, `pip install fastapi "uvicorn[standard]" jinja2`, `requirements.txt`.
      A `GET /` returning `"hello"`. Run it. See it in a browser.
- [ ] **2. `gitinfo.py` (~45 min).** One function: `read_repo(path) -> dict | None`. Runs the three FR-3 commands,
      returns branch/commit/subject/committed_at/checked_out_at. Returns `None` if there's no `.git`.
      **Test it from the Python REPL against a real repo on your machine before wiring anything up.**
- [ ] **3. `config.py` (~20 min).** Load `config.json`, return a dict. Write `config.example.json`.
- [ ] **4. `status.py` (~30 min).** One pure function: `derive(project, cfg) -> (status, text, note)`, implementing
      the FR-6 table. **Pure input → output, no I/O.** Easiest part of the codebase to be sure about.
      For M1, pass `behind=None` and `process_started_at=None`; those branches simply won't fire yet.
- [ ] **5. Wire it (~30 min).** `GET /api` → loop config projects → `read_repo` → `derive` → return the §6 JSON.
      Check it in the browser before touching any HTML.
- [ ] **6. The page (~60 min).** Copy `design/mockup.html` to `deployinfo/templates/index.html`, delete the fake
      rows, wrap the remaining one in `{% for p in projects %}`. Render with `Jinja2Templates`.
- [ ] **7. Make it unbreakable (~30 min).** Missing path · no `.git` · git returns non-zero · empty repo with no
      commits. **Each must show a row with `no git repo` or `? unknown`. A 500 page is a bug.**
- [ ] **8. Cache (~20 min).** Module-level dict, `{path: (timestamp, result)}`, honouring `cache_seconds`.

**Milestone 1 is done when:** you point `config.json` at 2–3 real repos on your laptop, load
`http://127.0.0.1:8787`, and see correct branches, commit subjects and relative times — and deleting one of the
paths shows `no git repo` instead of a crash.

### Milestone 2 — the judgement (half a day)
- [ ] `behind` via `git rev-list --count HEAD..origin/<main>`, `null` on failure
- [ ] Decide fetching: a background timer running `git fetch --quiet`, behind a config flag. **Never `pull`.**
- [ ] `process_started_at` via `systemctl show`, enabling `pulled, not restarted`
- [ ] `GET /fragment` + the ~15 lines of JS that swap it every 30s

### Milestone 3 — deployment (half a day)
- [ ] Token auth + bind to 127.0.0.1 · `deployinfo.service` · `install.sh` · nginx block
- [ ] Two gotchas that **will** bite:
      **(a)** `git config --global --add safe.directory <path>` as the agent's user, or git refuses repos owned
      by someone else — *"detected dubious ownership"*.
      **(b)** `sudo loginctl enable-linger <user>`, or a systemd **user** service dies when your SSH session ends
      and never starts at boot.

### Milestone 4 — managing projects from the UI (one day)
- [ ] `/api/discover`, `POST /api/projects`, `DELETE`, the add panel, `allow_ui_edit`
- [ ] FR-15 to FR-20 in full — **especially FR-16: an id, never a path**

---

## 8. Before writing any code
- [ ] **Confirm how the target servers actually deploy — git checkout, or container image?**
      If it's containers, `.git` doesn't exist on the box and this design reports `no git repo` for everything.
      **Ten minutes of checking that decides whether the tool is useful at all.**

## 9. Deliberate non-goals
No auth system. No database. No multi-host view. No deploy button. No dark/light toggle. No Docker image.
**Every one of these is a thing that would turn a one-day tool into a three-week project.**
