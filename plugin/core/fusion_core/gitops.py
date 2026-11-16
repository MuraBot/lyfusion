"""Git operations: worktrees, task branches, candidate commits, integration, and fast-forward. The engine handles these; the assistant cannot access .git."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .util import FusionError, git


def station_dir(root: Path, line: str = "main") -> Path:
    suffix = "fusion" if line == "main" else f"fusion-{line}"
    return root.parent / f"{root.name}-{suffix}"


def in_temp(path: Path) -> bool:
    tmp = Path(tempfile.gettempdir()).resolve()
    try:
        path.resolve().relative_to(tmp)
        return True
    except ValueError:
        return False


def ensure_station(root: Path, cfg: dict, line: str = "main") -> Path:
    wt = station_dir(root, line)
    base = cfg["base_branch"]
    if not (wt / ".git").exists():
        if wt.exists() and any(wt.iterdir()):
            raise FusionError(f"Worktree path {wt} already exists but is not a Git worktree; resolve it first")
        git("worktree", "prune", cwd=root)
        git("worktree", "add", "--detach", str(wt), base, cwd=root)
        for rel in cfg.get("station_copy") or []:
            src = root / rel
            if src.exists():
                dst = wt / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
    return wt


def clean(wt: Path) -> None:
    """Discard uncommitted worktree changes (the worktree belongs to the engine and assistant)."""
    git("reset", "--hard", "-q", cwd=wt)
    git("clean", "-fdq", "-e", "fusion-keep", cwd=wt)


def head(cwd: Path, ref: str = "HEAD") -> str:
    return git("rev-parse", ref, cwd=cwd)


def current_branch(wt: Path) -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD", cwd=wt)


def prepare_branch(wt: Path, branch: str, base_branch: str, fresh: bool) -> str:
    """Switch to the task branch and return its starting commit.

    fresh=True: first run; discard worktree leftovers and create a branch from base_branch (an old branch with the same name is reset).
    fresh=False: resume (answer questions, fix, or revise); if already on the branch, preserve all uncommitted work.
    """
    if fresh:
        clean(wt)
        base = head(wt, base_branch)
        git("switch", "-q", "-C", branch, base, cwd=wt)
        return base
    if current_branch(wt) == branch:
        return git("merge-base", branch, base_branch, cwd=wt)
    code, _, _ = git("rev-parse", "--verify", "-q", f"refs/heads/{branch}", cwd=wt, check=False)
    if code != 0:
        raise FusionError(f"Task branch {branch} is missing, so it cannot resume. Return the task and plan again.")
    clean(wt)
    git("switch", "-q", branch, cwd=wt)
    return git("merge-base", branch, base_branch, cwd=wt)


def changed_files(cwd: Path, a: str, b: str = "HEAD") -> list[dict]:
    out = git("diff", "--name-status", "-M", a, b, cwd=cwd)
    files = []
    for line in out.splitlines():
        parts = line.split("\t")
        status = parts[0][0]
        files.append({"status": status, "path": parts[-1], "old": parts[1] if status == "R" else None})
    return files


def worktree_dirty(wt: Path) -> bool:
    return bool(git("status", "--porcelain", "--untracked-files=all", cwd=wt))


def commit_all(wt: Path, message: str, identity: dict | None = None) -> str | None:
    """Commit worktree changes as a candidate. Return None if there are no changes."""
    if not worktree_dirty(wt):
        return None
    git("add", "-A", cwd=wt)
    args = []
    if identity:
        args = ["-c", f"user.name={identity['name']}", "-c", f"user.email={identity['email']}"]
    git(*args, "commit", "-q", "--no-verify", "-m", message, cwd=wt)
    return head(wt)


def diff_text(cwd: Path, a: str, b: str, paths: list[str] | None = None, max_chars: int = 60000) -> str:
    args = ["diff", "-M", a, b]
    if paths:
        args += ["--", *paths]
    out = git(*args, cwd=cwd)
    if len(out) > max_chars:
        out = out[:max_chars] + f"\n…(diff is too long; truncated at {max_chars} characters. See layer 3 for the full diff)"
    return out


def added_lines(cwd: Path, a: str, b: str) -> list[tuple[str, str]]:
    """Added diff lines: (file, content)."""
    out = git("diff", "-U0", a, b, cwd=cwd)
    cur, rows = None, []
    for line in out.splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("+") and not line.startswith("+++") and cur:
            rows.append((cur, line[1:]))
    return rows


def restore_old_tests(wt: Path, base: str, files: list[dict]) -> list[str]:
    """Restore test files from before delegation to the worktree (working tree only, no commit). Return restored files."""
    restored = []
    for f in files:
        path = f["old"] if f["status"] == "R" else f["path"]
        if f["status"] in ("M", "D", "R"):
            git("checkout", base, "--", path, cwd=wt)
            restored.append(path)
    return restored


def merge_base_into(wt: Path, base_branch: str, identity: dict | None = None) -> tuple[bool, str]:
    """Merge base_branch into the task branch in the worktree. Abort on conflict and return (False, conflicting files)."""
    if git("merge-base", "--is-ancestor", base_branch, "HEAD", cwd=wt, check=False)[0] == 0:
        return True, "main has not advanced; no merge needed"
    args = []
    if identity:
        args = ["-c", f"user.name={identity['name']}", "-c", f"user.email={identity['email']}"]
    code, out, err = git(*args, "merge", "--no-edit", "-q", base_branch, cwd=wt, check=False)
    if code != 0:
        conflicts = git("diff", "--name-only", "--diff-filter=U", cwd=wt, check=False)[1]
        git("merge", "--abort", cwd=wt, check=False)
        return False, conflicts.strip() or (out + err).strip()
    return True, "Merged main"


def squash_onto(wt: Path, base_branch: str, message: str, identity: dict | None = None) -> str:
    """Create a commit from the current tree with base_branch as its parent (without changing any working directory)."""
    tree = git("rev-parse", "HEAD^{tree}", cwd=wt)
    parent = head(wt, base_branch)
    env = dict(os.environ)
    if identity:
        env.update(GIT_AUTHOR_NAME=identity["name"], GIT_AUTHOR_EMAIL=identity["email"],
                   GIT_COMMITTER_NAME=identity["name"], GIT_COMMITTER_EMAIL=identity["email"])
    p = subprocess.run(["git", "commit-tree", tree, "-p", parent, "-F", "-"], cwd=wt, input=message.encode("utf-8"),
                       check=False, capture_output=True, env=env)
    if p.returncode != 0:
        raise FusionError("git commit-tree failed:" + p.stderr.decode("utf-8", "replace"))
    return p.stdout.decode().strip()


def fast_forward(root: Path, base_branch: str, commit: str) -> tuple[bool, str]:
    """Fast-forward base_branch to commit. If the lead worktree is on base_branch, use merge --ff-only to protect uncommitted changes."""
    current = git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
    if current == base_branch:
        code, out, err = git("merge", "--ff-only", "-q", commit, cwd=root, check=False)
        if code != 0:
            return False, ("The lead worktree has uncommitted changes that conflict with this merge; Git refused to fast-forward. "
                           "Commit or stash these changes, then accept again.\n" + (out + err).strip())
        return True, "Fast-forwarded"
    old = head(root, base_branch)
    code, _, err = git("update-ref", f"refs/heads/{base_branch}", commit, old, cwd=root, check=False)
    return (code == 0), ("Fast-forwarded" if code == 0 else err)


def delete_branch(root: Path, branch: str) -> None:
    git("branch", "-D", branch, cwd=root, check=False)


def detach_station(wt: Path, base_branch: str) -> None:
    clean(wt)
    git("switch", "-q", "--detach", base_branch, cwd=wt)
