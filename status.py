"""Derive one status per project (FR-6).

Pure: input in, decision out, no I/O and no clock reads beyond the `now` passed in.
That makes this the one file in the codebase you can be certain about.
"""

from datetime import datetime, timezone

# status -> (chip class). "none" covers both "no repo" and "could not tell".
OK, WARN, BAD, NONE = "ok", "warn", "bad", "none"

# Thresholds. Constants rather than config: nothing yet suggests they need to differ
# per host, and an unused knob is a thing that can be set wrong.
STALE_DAYS = 7      # no new checkout for longer than this and nobody is deploying it
BEHIND_WARN = 5     # a handful of commits is normal drift; a dozen is a forgotten deploy


def _parse(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def derive(project, cfg, now=None):
    """Return (status, status_text, note). First match wins — the order is the spec."""
    now = now or datetime.now(timezone.utc).astimezone()
    main = cfg["main_branch"]

    repo = project.get("repo")
    if repo is None:
        return NONE, "no git repo", "Path is missing, unreadable, or has no .git."

    branch = repo.get("branch")
    checked_out = _parse(repo.get("checked_out_at"))

    # A real repo whose HEAD names no commit: freshly initialised, or damaged.
    # Both are honestly "we cannot tell", which is a valid answer here.
    if repo.get("commit") is None:
        return NONE, "? unknown", "No commit on HEAD - empty or unreadable repository."

    if branch is None or branch == "HEAD":
        return BAD, "detached HEAD", "Not on any branch. Redeploy from %s." % main

    if branch != main:
        return BAD, "not on main", "Running %s. Merge back or redeploy %s." % (branch, main)

    started = _parse(project.get("process_started_at"))
    if started and checked_out and started < checked_out:
        return WARN, "pulled, not restarted", "Process started before this checkout. Restart the service."

    behind = project.get("behind")
    if cfg.get("check_behind") and behind is not None and behind > BEHIND_WARN:
        return WARN, "%d behind" % behind, "origin/%s has moved on." % main

    if checked_out:
        days = (now - checked_out).days
        if days > STALE_DAYS:
            return BAD, "stale (%dd)" % days, "No new checkout in %d days." % days

    # Last, not earlier: an unreachable remote must not mask a staleness we can see
    # without it. Only reached when nothing else had anything to say.
    if cfg.get("check_behind") and behind is None:
        return NONE, "? unknown", "Could not compare against origin/%s." % main

    return OK, "in sync", None
