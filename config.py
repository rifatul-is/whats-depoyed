"""Load configuration: scalar settings from .env, the project list from projects.json.

The list lives in JSON because it is a list of records - and because Milestone 4's
add-project UI has to write it back atomically, which .env would make needlessly hard.

Format is the systemd EnvironmentFile / dotenv convention: KEY=VALUE, one per line.
python-dotenv loads it into os.environ at import, so everything below just reads the
environment - a variable set by systemd or the shell wins over the file.
"""

import json
import os

from dotenv import load_dotenv

ENV_PATH = os.environ.get("DEPLOYINFO_ENV", ".env")
PROJECTS_PATH = os.environ.get("DEPLOYINFO_PROJECTS", "projects.json")

# Read .env into the process environment, once. override=False is the default and the
# point: a variable already set by systemd or the shell beats the file.
load_dotenv(ENV_PATH, override=False)

TRUE = {"1", "true", "yes", "on"}


def _projects(path):
    """
    The tracked projects, from a JSON array. Returns (projects, error_message).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return [], "%s not found - copy projects.json.example to it and add your repos" % path
    except (json.JSONDecodeError, OSError) as e:
        return [], "%s could not be read: %s" % (path, e)

    if not isinstance(raw, list):
        return [], "%s must be a JSON array of projects" % path

    out = []
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict) or not str(item.get("path", "")).strip():
            return [], '%s entry %d has no "path"' % (path, i)
        repo = str(item["path"]).strip()
        out.append({
            "name": str(item.get("name") or os.path.basename(repo.rstrip("/"))),
            "path": repo,
            "service": item.get("service") or None,
        })
    return out, None


def load(projects_path=None):
    """Config as a plain dict. Never raises: a broken setup is a message on the page,
    not a 500. Scalars come from the environment; the project list from projects.json."""
    projects, error = _projects(projects_path or PROJECTS_PATH)
    roots = os.environ.get("ALLOWED_ROOTS", "")
    return {
        "host_label": os.environ.get("HOST_LABEL", "localhost"),
        "main_branch": os.environ.get("MAIN_BRANCH", "main"),
        # Milestone 2 turns this on. Until then the remote is never consulted, so the
        # behind rules are skipped rather than reported as "unknown" for every project.
        "check_behind": os.environ.get("CHECK_BEHIND", "").lower() in TRUE,
        "allowed_roots": [r.strip() for r in roots.split(",") if r.strip()],
        "projects": projects,
        "config_error": error,
    }
