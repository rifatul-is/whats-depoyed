# whats-deployed

A small read-only agent that answers one question on a server:

> **What git branch and commit is actually deployed here — and is it out of date?**

It runs as a sidecar next to your applications. **It never modifies them, never pulls, never deploys.**
It reads a few cheap `git` commands, decides whether anything looks wrong, and serves one page.

```
  raptor                                  origin/main @ a3f9c21

  PROJECT       BRANCH   COMMIT                          CHECKED OUT   STATUS
  raptor        main     a3f9c21  fix: celery retry ...  2h ago        in sync
  traderbro     main     8b21d04  feat: add RBAC roles   9d ago        12 behind
  raptor-worker hotfix   c0d4e77  hotfix: queue drain    31m ago       not on main
  cwt-portal    main     4e77a10  chore: bump django     14m ago       pulled, not restarted
```

## Why not just SSH in and run `git status`?

That answers *"what branch"*. It doesn't answer the question that actually causes incidents:
**is production behind, and did the last pull ever get restarted?** Those need a remote comparison and
a process start time — which is exactly what this does, for every project on the host, on one page.

## Why a sidecar and not a `/version` endpoint in each app?

- No application code changes, ever
- No deploy-pipeline changes
- One agent covers every project on the host
- Works regardless of language or framework — Django, .NET, Node, anything

**The trade-off, stated honestly:** git on disk tells you what was *checked out*, not what is *running*.
The agent compensates by comparing the service's process start time against the checkout time — see
`pulled, not restarted` above. **It requires deployments to be git checkouts on the server**; a container
with no `.git` will show as `no git repo`.

## Status meanings

| Status | Meaning |
|---|---|
| `in sync` | On the main branch, up to date, recently deployed |
| `N behind` | The main branch has moved on since this was deployed |
| `not on main` | Running a feature or hotfix branch |
| `pulled, not restarted` | Working tree changed after the process started — restart it |
| `stale (Nd)` | No deploy in a long time |
| `no git repo` | Path has no `.git` — probably a container deploy |
| `? unknown` | Could not determine. **Never guessed.** |

## Quickstart (local)

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp projects.json.example projects.json   # point at real repos on your machine
uvicorn main:app --host 127.0.0.1 --port 8787 --workers 1
```
Open http://127.0.0.1:8787

## Configuration

Two files, both gitignored — copy the `.example` versions.

**`.env`** — scalar settings. Real environment variables override it, so
`HOST_LABEL=staging uvicorn ...` or a systemd `Environment=` line wins without editing it.

```ini
HOST_LABEL=prod-01
MAIN_BRANCH=main
CHECK_BEHIND=false
ALLOWED_ROOTS=/srv,/opt/apps
```

The stale and behind thresholds are constants at the top of `status.py`, not settings —
nothing yet suggests they need to differ per host.

**`projects.json`** — what to track. A JSON array; `path` is required, `name` defaults to the
directory name, `service` is optional and enables the "pulled, not restarted" check.

```json
[
  { "name": "raptor", "path": "/srv/raptor", "service": "raptor.service" },
  { "path": "/srv/traderbro" }
]
```

The list is JSON rather than more `.env` keys because it is a list of records, and because
Milestone 4's add-project UI must rewrite it atomically — which JSON makes trivial.

## Rules this project holds to

1. **Read-only.** Never writes to a repository. Never pulls, never deploys.
2. **Never accepts a filesystem path over HTTP.** Paths come from `projects.json` only.
3. **Never guesses.** Unknown is a valid, visible status.
4. **One uvicorn worker.** Config lives in process memory.
5. **No frontend framework, no build step, no static assets.** One HTML template, CSS and JS inline.

## Where things are

| Path | What |
|---|---|
| `SRS.md` | What to build, in order. **Start here.** |
| `design/mockup.html` | The UI design. Static, opens in a browser. Becomes the Jinja template. |
| `main.py` | FastAPI app and routes |
| `gitinfo.py` | Reads git state from a checkout |
| `status.py` | Derives the status. Pure, no I/O |
| `config.py` | Loads `.env` and `projects.json` |
| `templates/index.html` | The page |
