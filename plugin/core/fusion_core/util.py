"""Utilities: time, JSON, glob matching, and subprocesses."""
from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

IS_WIN = os.name == "nt"


class FusionError(Exception):
    """Errors for the lead: explain the cause so it can be fixed immediately."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


class FormatTooNew(FusionError):
    """The project's state was written by a newer plugin version."""

    def __init__(self, path: str, version: int):
        from . import SCHEMA, VERSION

        self.path = path
        self.version = version
        super().__init__(
            f"{path} has format version {version}; this plugin ({VERSION}) supports up to {SCHEMA}: "
            "This project has used a newer version of lyfusion-plugin. Ask the user to upgrade the plugin before continuing; "
            "do not edit the version manually or delete files in fusion/.",
            code=2,
        )


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def timestamp(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return time.mktime(time.strptime(value, "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return None


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def norm(path: str) -> str:
    """Normalize a relative path to forward slashes."""
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


@lru_cache(maxsize=512)
def _glob_re(pattern: str) -> re.Pattern:
    p = norm(pattern)
    out, i = "", 0
    while i < len(p):
        if p.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif p.startswith("**", i):
            out += ".*"
            i += 2
        elif p[i] == "*":
            out += "[^/]*"
            i += 1
        elif p[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(p[i])
            i += 1
    return re.compile(out + r"\Z")


def glob_match(path: str, pattern: str) -> bool:
    return bool(_glob_re(pattern).match(norm(path)))


def any_match(path: str, patterns) -> bool:
    return any(glob_match(path, p) for p in patterns or [])


def globs_overlap(a, b) -> bool:
    """Whether two glob patterns might match the same file (conservative check)."""
    for x in a or []:
        for y in b or []:
            x2, y2 = norm(x), norm(y)
            if glob_match(x2, y2) or glob_match(y2, x2):
                return True
            px, py = x2.split("*")[0], y2.split("*")[0]
            if (px.startswith(py) or py.startswith(px)) and ("*" in x2 or "*" in y2):
                return True
    return False


def clean_env(extra: dict | None = None) -> dict:
    """Remove Claude, Anthropic, and inherited Fusion sandbox markers from child environments."""
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(("CLAUDE", "ANTHROPIC")) and k.upper() != "FUSION_SANDBOX"}
    env.update({k: str(v) for k, v in (extra or {}).items()})
    return env


def run(cmd, cwd, timeout=600, env=None, shell=False, out_file: Path | None = None) -> dict:
    """Run one command. Write output to a file (to avoid Windows pipe hangs) and return the exit code and output."""
    started = time.time()
    if out_file is None:
        try:
            p = subprocess.run(cmd, cwd=cwd, shell=shell, env=env, stdin=subprocess.DEVNULL,
                               check=False, capture_output=True, timeout=timeout)
            out = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
            code = p.returncode
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b"").decode("utf-8", "replace") + f"\n[timed out after {timeout} seconds]"
            code = -9
        return {"exit": code, "output": out, "seconds": round(time.time() - started, 1)}
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "wb") as fo:
        try:
            p = subprocess.run(cmd, cwd=cwd, shell=shell, env=env, stdin=subprocess.DEVNULL,
                               check=False, stdout=fo, stderr=subprocess.STDOUT, timeout=timeout)
            code = p.returncode
        except subprocess.TimeoutExpired:
            code = -9
    out = out_file.read_bytes().decode("utf-8", "replace")
    if code == -9:
        out += f"\n[timed out after {timeout} seconds]"
    return {"exit": code, "output": out, "seconds": round(time.time() - started, 1)}


def git(*args, cwd, check=True) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, stdin=subprocess.DEVNULL, check=False, capture_output=True)
    out = p.stdout.decode("utf-8", "replace")
    if check and p.returncode != 0:
        raise FusionError(f"git {' '.join(args)} failed:{p.stderr.decode('utf-8', 'replace').strip()}")
    return out.strip() if check else (p.returncode, out, p.stderr.decode("utf-8", "replace"))


def spawn_detached(cmd, cwd, env, stdin_path: Path, stdout_path: Path, stderr_path: Path) -> int:
    """Start an independent subprocess: inherit only three files, not the caller standard streams (which may be an MCP channel).

    Codex exec must receive the prompt file as stdin or it will wait for more pipe input.
    """
    with open(stdin_path, "rb") as fi, open(stdout_path, "wb") as fo, open(stderr_path, "wb") as fe:
        kwargs = {"cwd": cwd, "env": env, "stdin": fi, "stdout": fo, "stderr": fe, "close_fds": True}
        if IS_WIN:
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            try:
                p = subprocess.Popen(cmd, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kwargs)
            except OSError:
                p = subprocess.Popen(cmd, creationflags=flags, **kwargs)
        else:
            p = subprocess.Popen(cmd, start_new_session=True, **kwargs)
    return p.pid


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if IS_WIN:
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        h = kernel32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        ok = kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        kernel32.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def kill_tree(pid: int | None) -> None:
    if not pid or not pid_alive(pid):
        return
    if IS_WIN:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
    else:
        import signal
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except OSError:
            pass
    deadline = time.monotonic() + 10
    while pid_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)


def python_exe() -> str:
    return sys.executable or "python"


# Commands for the lead to run the engine in Bash. Plugins cannot include bin/ (not allowed for claude.ai hosted plugins),
# so use the absolute path to fusion-core.py in the install directory; SessionStart instructions and command next steps use it.
CMD = f'python "{(Path(__file__).resolve().parent.parent / "fusion-core.py").as_posix()}"'


# ---- Redaction: mask common secret formats in runs/ logs. This is imperfect, so runs/ is never tracked by Git. ----
_SECRETS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[redacted private key]"),
    (re.compile(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?(?:bearer|basic|token)\s+)[^\s\"',]+"), r"\1[redacted]"),
    (re.compile(r"\b(?:sk|rk)-[A-Za-z0-9_\-]{20,}"), "[redacted secret]"),
    (re.compile(r"\b(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{30,}"), "[redacted token]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}"), "[redacted token]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "[redacted token]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[redacted secret]"),
    (re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"), "[redacted secret]"),
]


def redact(text: str) -> str:
    for rx, rep in _SECRETS:
        text = rx.sub(rep, text)
    return text


def redact_file(path: Path) -> None:
    try:
        if not path.exists() or path.stat().st_size > 50_000_000:
            return
        raw = path.read_bytes().decode("utf-8", "replace")
        new = redact(raw)
        if new != raw:
            path.write_bytes(new.encode("utf-8"))
    except OSError:
        pass
