from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

import config
import gitinfo
from status import derive

app = FastAPI(title="whats-deployed", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def collect():
    cfg = config.load()
    now = datetime.now(timezone.utc).astimezone()
    projects = []

    for p in cfg["projects"]:
        try:
            repo = gitinfo.read_repo(p["path"])
        except Exception:
            repo = None  # FR-4: unreadable is a status, never an error page.

        item = {
            "name": p["name"],
            "path": p["path"],
            # Milestone 2 fills these in; until then the checks that need them stay silent.
            "behind": None,
            "process_started_at": None,
            "repo": repo,
        }
        status, text, note = derive(item, cfg, now)
        r = repo or {}
        projects.append({
            "name": p["name"],
            "path": p["path"],
            "branch": r.get("branch"),
            "commit": r.get("commit"),
            "subject": r.get("subject"),
            "committed_at": r.get("committed_at"),
            "checked_out_at": r.get("checked_out_at"),
            "process_started_at": None,
            "behind": None,
            "dirty": None,
            "status": status,
            "status_text": text,
            "note": note,
        })

    return cfg, {
        "host": cfg["host_label"],
        "fetched_at": now.isoformat(),
        "projects": projects,
    }


def ago(ts):
    """'9d ago' — relative times, because nobody reads an absolute timestamp (FR-11)."""
    if not ts:
        return "—"
    try:
        t = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return "—"
    s = (datetime.now(timezone.utc).astimezone() - t).total_seconds()
    if s < 0:
        return "just now"
    for limit, div, unit in ((60, 1, "s"), (3600, 60, "m"), (86400, 3600, "h")):
        if s < limit:
            return "%d%s ago" % (int(s // div), unit)
    return "%dd ago" % int(s // 86400)


templates.env.filters["ago"] = ago


@app.get("/api")
def api():
    return JSONResponse(collect()[1])


@app.get("/")
def index(request: Request):
    cfg, data = collect()
    attention = sum(1 for p in data["projects"] if p["status"] in ("warn", "bad"))
    return templates.TemplateResponse(
        request, "index.html",
        {"data": data, "projects": data["projects"], "attention": attention,
         "cfg": cfg, "config_error": cfg["config_error"]},
    )
