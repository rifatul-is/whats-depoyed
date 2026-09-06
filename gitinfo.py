"""Read git state from a checkout on disk. Read-only, always.

Every command here is cheap plumbing (FR-3). `git status` is deliberately absent:
it walks the whole working tree, which is the one thing that makes this slow.
"""

import os
import subprocess
from datetime import datetime, timezone

# A hung git call must not hang the page (NFR-6).
TIMEOUT = 5


def _git(path, *args):
    """Run one git command. Returns stdout stripped, or None on any failure.

    NFR-2: fixed argv list, never a shell. NFR-3: stderr never reaches the caller.
    """
    try:
        p = subprocess.run(
            ["git", "-C", path, *args],
            capture_output=True, text=True, timeout=TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    return p.stdout.strip()


def _git_dir(path):
    """Absolute path of the repo's git dir, or None if this isn't a checkout.

    `.git` is a directory in a normal clone, but a *file* in a linked worktree or a
    submodule, so the cheap isdir check has to fall back to asking git.
    """
    if not os.path.isdir(path):
        return None
    dot = os.path.join(path, ".git")
    if os.path.isdir(dot):
        return dot
    if os.path.exists(dot):
        return _git(path, "rev-parse", "--absolute-git-dir")
    return None


def _mtime(p):
    try:
        return datetime.fromtimestamp(os.path.getmtime(p), tz=timezone.utc).astimezone()
    except OSError:
        return None


def read_repo(path):
    """Git state of the checkout at `path`, or None if there is no repo there.

    None means "no git repo" — a legitimate answer, not an error (FR-4).
    A returned dict may still carry None fields: a repo with no commits yet has a
    path and a git dir but no HEAD to describe. Unknown stays unknown (FR-7).
    """
    gitdir = _git_dir(path)
    if gitdir is None:
        return None

    checked_out_at = _mtime(os.path.join(gitdir, "HEAD"))

    branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    commit = _git(path, "rev-parse", "--short", "HEAD")
    log = _git(path, "log", "-1", "--format=%s%n%cI")

    subject = committed_at = None
    if log:
        # %s can itself contain newlines only in pathological cases; %cI never does.
        head, _, tail = log.rpartition("\n")
        subject, committed_at = (head or tail), (tail if head else None)

    if commit is None:
        # No HEAD commit — an initialised but empty repo. Say so rather than guess.
        branch = branch if branch not in ("HEAD", None) else None

    return {
        "branch": branch,
        "commit": commit,
        "subject": subject,
        "committed_at": committed_at,
        "checked_out_at": checked_out_at.isoformat() if checked_out_at else None,
    }
