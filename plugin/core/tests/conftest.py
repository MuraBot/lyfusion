"""Test fixtures: a small Git project and fake Codex for each test.

Projects live under tests/_work/ (not the system temp directory; the engine refuses to create a worktree there).
"""
from __future__ import annotations

import errno
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CORE))

from fusion_core import config as config_mod
from fusion_core.commands import Ctx
from fusion_core.supervisor import Supervisor

WORK = Path(__file__).resolve().parent / "_work"
FAKE = Path(__file__).resolve().parent / "fake_codex.py"
collect_ignore_glob = ["_work/*"]


@pytest.fixture(autouse=True)
def isolated_codex_home(tmp_path, monkeypatch):
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    models = []
    for priority, (slug, info) in enumerate(config_mod.MODEL_INFO.items()):
        models.append({
            "slug": slug,
            "display_name": info["name"],
            "visibility": "list",
            "priority": priority,
            "supported_reasoning_levels": [{"effort": effort} for effort in info["efforts"]],
            "additional_speed_tiers": ["fast"] if info["fast"] else [],
            "max_context_window": info["max_compact"],
        })
    (codex_home / "models_cache.json").write_text(
        json.dumps({"models": models}), encoding="utf-8"
    )


GREET = 'def hello(name):\n    return f"Hello, {name}"\n'
TEST_GREET = ('import unittest\nfrom app.greet import hello\n\n\nclass T(unittest.TestCase):\n'
              '    def test_hello(self):\n        self.assertEqual(hello("A"), "Hello, A")\n')


def sh(*args, cwd):
    p = subprocess.run(list(args), cwd=cwd, check=False, capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(f"{args} failed:{p.stderr}")
    return p.stdout.strip()


def report(summary="Done", **kw):
    r = {"status": "done", "summary": summary, "choices": [], "questions": [], "problems": []}
    r.update(kw)
    return r


class Proj:
    def __init__(self, base: Path):
        self.base = base
        self.root = base / "proj"
        self.script_path = base / "script.json"
        self.root.mkdir(parents=True)
        sh("git", "init", "-q", "-b", "main", cwd=self.root)
        sh("git", "config", "user.name", "Test", cwd=self.root)
        sh("git", "config", "user.email", "test@example.invalid", cwd=self.root)
        sh("git", "config", "core.autocrlf", "false", cwd=self.root)
        self.write("app/__init__.py", "")
        self.write("app/greet.py", GREET)
        self.write("tests/__init__.py", "")
        self.write("tests/test_greet.py", TEST_GREET)
        self.commit("Initial commit")
        test_cmd = f'"{sys.executable}" -m unittest discover -s tests -t . -q'
        config_mod.init(self.root, test=test_cmd)
        local = config_mod.load(self.root)["local"]
        local["codex"] = [sys.executable, str(FAKE)]
        local["env"] = {"FAKE_CODEX_SCRIPT": str(self.script_path)}
        config_mod.save_local(self.root, local)
        self.commit("fusion init")
        self.script([])
        self.sup = Supervisor(self.root, poll=0.05)

    # ---- Files and Git ----
    def write(self, rel, text, root=None):
        p = (root or self.root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def read(self, rel, root=None):
        return ((root or self.root) / rel).read_text(encoding="utf-8")

    def commit(self, msg):
        sh("git", "add", "-A", cwd=self.root)
        sh("git", "commit", "-q", "-m", msg, cwd=self.root)
        return sh("git", "rev-parse", "HEAD", cwd=self.root)

    def git(self, *args, cwd=None):
        return sh("git", *args, cwd=cwd or self.root)

    @property
    def station(self) -> Path:
        return self.root.parent / "proj-fusion"

    # ---- Fake Codex ----
    def script(self, steps):
        self.script_path.write_text(json.dumps(steps, ensure_ascii=False), encoding="utf-8")
        for suffix in (".n", ".calls.jsonl"):
            p = self.script_path.with_suffix(suffix)
            if p.exists():
                p.unlink()

    def calls(self):
        p = self.script_path.with_suffix(".calls.jsonl")
        if not p.exists():
            return []
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]

    # ---- Engine ----
    def ctx(self):
        return Ctx(self.root)

    def do(self, fn, *args, **kw):
        ctx = self.ctx()
        try:
            return fn(ctx, *args, **kw)
        finally:
            ctx.close()

    def state(self):
        return self.sup.state()

    def task(self, tid="T1"):
        return self.state()["tasks"][tid]

    def drain(self):
        self.sup.drain(limit=2000, wait=0.05)

    def events(self, type_=None, task=None):
        from fusion_core import store
        evs = store.read(self.sup.conn)
        return [e for e in evs if (type_ is None or e["type"] == type_) and (task is None or e["task"] == task)]


@pytest.fixture
def proj(request):
    base = WORK / request.node.name.replace("[", "_").replace("]", "")
    if base.exists():
        _rm(base)
    p = Proj(base)
    yield p
    p.sup.conn.close()
    _rm(base)


def _rm(path: Path):
    # Remove the worktree registration before deleting the directory.
    def onerr(func, p, exc):
        import os
        import stat
        os.chmod(p, stat.S_IWRITE)

        def retryable(error):
            return (isinstance(error, PermissionError)
                    or error.errno == errno.ENOTEMPTY
                    or getattr(error, "winerror", None) == 145)

        try:
            func(p)
        except OSError as error:
            if not retryable(error):
                raise
            deadline = time.monotonic() + 5
            while True:
                time.sleep(0.2)
                try:
                    func(p)
                    return
                except OSError as error:
                    if not retryable(error):
                        raise
                    if time.monotonic() >= deadline:
                        raise
    shutil.rmtree(path, onerror=onerr)
