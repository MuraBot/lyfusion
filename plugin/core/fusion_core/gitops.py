"""git 操作:工位目录(worktree)、任务分支、候选提交、集成、快进。全部由引擎执行,助手碰不到 .git。"""
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
            raise FusionError(f"工位目录 {wt} 已存在但不是 git worktree,请先处理")
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
    """丢掉工位里没提交的改动(工位目录只归引擎和助手)。"""
    git("reset", "--hard", "-q", cwd=wt)
    git("clean", "-fdq", "-e", "fusion-keep", cwd=wt)


def head(cwd: Path, ref: str = "HEAD") -> str:
    return git("rev-parse", ref, cwd=cwd)


def current_branch(wt: Path) -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD", cwd=wt)


def prepare_branch(wt: Path, branch: str, base_branch: str, fresh: bool) -> str:
    """切到任务分支,返回分支的起点提交。

    fresh=True:任务第一次开工,丢掉工位里的残留,从 base_branch 开新分支(同名旧分支会被重置)。
    fresh=False:续做(回答问题、修复、修改意见),已经在分支上就什么都不动,保留没提交的半成品。
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
        raise FusionError(f"任务分支 {branch} 不见了,无法续做。可以退回任务后重新计划")
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
    """把工位里的改动提交成候选。没有改动返回 None。"""
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
        out = out[:max_chars] + f"\n…(diff 太长,截断在 {max_chars} 字;完整内容看第 3 层)"
    return out


def added_lines(cwd: Path, a: str, b: str) -> list[tuple[str, str]]:
    """diff 里新增的行:(文件, 内容)。"""
    out = git("diff", "-U0", a, b, cwd=cwd)
    cur, rows = None, []
    for line in out.splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("+") and not line.startswith("+++") and cur:
            rows.append((cur, line[1:]))
    return rows


def restore_old_tests(wt: Path, base: str, files: list[dict]) -> list[str]:
    """把派工前的测试文件放回工位(只改工作区,不提交)。返回放回的文件。"""
    restored = []
    for f in files:
        path = f["old"] if f["status"] == "R" else f["path"]
        if f["status"] in ("M", "D", "R"):
            git("checkout", base, "--", path, cwd=wt)
            restored.append(path)
    return restored


def merge_base_into(wt: Path, base_branch: str, identity: dict | None = None) -> tuple[bool, str]:
    """在工位里把 base_branch 合进任务分支。冲突时放弃合并,返回 (False, 冲突文件)。"""
    if git("merge-base", "--is-ancestor", base_branch, "HEAD", cwd=wt, check=False)[0] == 0:
        return True, "main 没有前进,不用合并"
    args = []
    if identity:
        args = ["-c", f"user.name={identity['name']}", "-c", f"user.email={identity['email']}"]
    code, out, err = git(*args, "merge", "--no-edit", "-q", base_branch, cwd=wt, check=False)
    if code != 0:
        conflicts = git("diff", "--name-only", "--diff-filter=U", cwd=wt, check=False)[1]
        git("merge", "--abort", cwd=wt, check=False)
        return False, conflicts.strip() or (out + err).strip()
    return True, "已合并 main"


def squash_onto(wt: Path, base_branch: str, message: str, identity: dict | None = None) -> str:
    """用当前树做一个父提交是 base_branch 的提交(不动任何工作目录)。"""
    tree = git("rev-parse", "HEAD^{tree}", cwd=wt)
    parent = head(wt, base_branch)
    env = dict(os.environ)
    if identity:
        env.update(GIT_AUTHOR_NAME=identity["name"], GIT_AUTHOR_EMAIL=identity["email"],
                   GIT_COMMITTER_NAME=identity["name"], GIT_COMMITTER_EMAIL=identity["email"])
    p = subprocess.run(["git", "commit-tree", tree, "-p", parent, "-F", "-"], cwd=wt, input=message.encode("utf-8"),
                       check=False, capture_output=True, env=env)
    if p.returncode != 0:
        raise FusionError("git commit-tree 失败:" + p.stderr.decode("utf-8", "replace"))
    return p.stdout.decode().strip()


def fast_forward(root: Path, base_branch: str, commit: str) -> tuple[bool, str]:
    """让 base_branch 快进到 commit。lead 的目录正在 base_branch 上就用 merge --ff-only(保护未提交改动)。"""
    current = git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
    if current == base_branch:
        code, out, err = git("merge", "--ff-only", "-q", commit, cwd=root, check=False)
        if code != 0:
            return False, ("lead 的工作目录里有未提交的改动和这次合并冲突,git 拒绝了快进。"
                           "请先提交或暂存这些改动,再验收一次。\n" + (out + err).strip())
        return True, "已快进"
    old = head(root, base_branch)
    code, _, err = git("update-ref", f"refs/heads/{base_branch}", commit, old, cwd=root, check=False)
    return (code == 0), ("已快进" if code == 0 else err)


def delete_branch(root: Path, branch: str) -> None:
    git("branch", "-D", branch, cwd=root, check=False)


def detach_station(wt: Path, base_branch: str) -> None:
    clean(wt)
    git("switch", "-q", "--detach", base_branch, cwd=wt)


def bring_changes(root: Path, wt_ref_cwd: Path, base: str, tip: str) -> tuple[list[str], list[str]]:
    """接管:把任务分支相对起点的改动搬到 lead 的目录(不提交)。lead 改过的文件不覆盖,列出来。"""
    copied, conflicts = [], []
    for f in changed_files(wt_ref_cwd, base, tip):
        path = f["path"]
        target = root / path
        lead_changed = git("diff", "--quiet", base, "--", path, cwd=root, check=False)[0] != 0
        in_base = git("cat-file", "-e", f"{base}:{path}", cwd=root, check=False)[0] == 0
        if lead_changed or (not in_base and target.exists()):
            conflicts.append(path)
            continue
        if f["status"] == "D":
            if target.exists():
                target.unlink()
        else:
            p = subprocess.run(["git", "show", f"{tip}:{path}"], cwd=wt_ref_cwd, check=False, capture_output=True)
            if p.returncode == 0:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(p.stdout)
        if f["status"] == "R" and f["old"]:
            old = root / f["old"]
            if old.exists():
                old.unlink()
        copied.append(path)
    return copied, conflicts
