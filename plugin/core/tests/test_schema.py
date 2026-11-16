"""State-format compatibility tests with a frozen aq.2 database schema."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import CORE

# Copied verbatim from plugin/core/fusion_core/store.py at git tag v5.0.0-aq.2.
AQ2_DDL = """
CREATE TABLE IF NOT EXISTS events (
    seq   INTEGER PRIMARY KEY AUTOINCREMENT,
    ts    TEXT NOT NULL,
    v     INTEGER NOT NULL,
    type  TEXT NOT NULL,
    task  TEXT,
    item  TEXT,
    actor TEXT NOT NULL,
    data  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lease (
    name      TEXT PRIMARY KEY,
    holder    TEXT NOT NULL,
    heartbeat REAL NOT NULL
);
"""


def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
    (root / "fusion").mkdir()
    (root / "seed.txt").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "seed.txt"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "seed"], check=True)
    return root


def cli(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CORE / "fusion-core.py"), "--project", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def old_files(root: Path) -> None:
    (root / "fusion" / "config.json").write_text(
        json.dumps({"base_branch": "main", "test": "echo ok", "context_limit": 123}),
        encoding="utf-8",
    )
    (root / "fusion" / "local.json").write_text(
        json.dumps({"enabled": True, "sidekick": {"model": "gpt-6-luna", "effort": "low", "fast": True}}),
        encoding="utf-8",
    )


def old_database(root: Path) -> None:
    conn = sqlite3.connect(root / "fusion" / "fusion.db")
    conn.executescript(AQ2_DDL)
    events = [
        ("task_created", "T1", {"state": "exploring", "plan": None}),
        ("run_requested", "T1", {"run": "r1", "kind": "explore"}),
        ("run_started", "T1", {"run": "r1"}),
        ("run_ended", "T1", {"run": "r1", "result": "ok"}),
    ]
    for seq, (kind, task, data) in enumerate(events, 1):
        conn.execute(
            "INSERT INTO events(seq,ts,v,type,task,actor,data) VALUES(?,?,?,?,?,?,?)",
            (seq, f"2026-01-01T00:00:0{seq}", 1, kind, task, "lead", json.dumps(data)),
        )
    conn.commit()
    conn.close()


def test_aq2_files_read_without_rewrite_then_write_adds_version(tmp_path):
    root = project(tmp_path)
    old_files(root)
    old_database(root)
    config_before = (root / "fusion" / "config.json").read_bytes()
    local_before = (root / "fusion" / "local.json").read_bytes()

    result = cli(root, "status")
    assert result.returncode == 0, result.stderr
    assert (root / "fusion" / "config.json").read_bytes() == config_before
    assert (root / "fusion" / "local.json").read_bytes() == local_before

    result = cli(root, "config", "effort", "max")
    assert result.returncode == 0, result.stderr
    assert json.loads((root / "fusion" / "local.json").read_text(encoding="utf-8"))["schema_version"] == 2
    result = cli(root, "config", "set", '{"config":{"test":"echo changed"}}')
    assert result.returncode == 0, result.stderr
    assert json.loads((root / "fusion" / "config.json").read_text(encoding="utf-8"))["schema_version"] == 2

    from fusion_core import store
    from fusion_core.state import replay

    conn = store.connect(root)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    state = replay(store.read(conn))
    assert state["tasks"]["T1"]["runs"] == ["r1"]
    conn.close()


def test_on_creates_all_files_with_current_version(tmp_path):
    root = project(tmp_path)
    result = cli(root, "on")
    assert result.returncode == 0, result.stderr
    for name in ("config.json", "local.json"):
        assert json.loads((root / "fusion" / name).read_text(encoding="utf-8"))["schema_version"] == 2
    conn = sqlite3.connect(root / "fusion" / "fusion.db")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    conn.close()

    from fusion_core import store

    conn = store.connect(root)
    with store.transaction(conn):
        event = store.append(conn, [{"type": "lead_session"}], "lead")[0]
    assert event["v"] == 2
    conn.close()


@pytest.mark.parametrize("bad_version", ["abc", 0, -1])
def test_invalid_json_schema_versions_name_the_file(tmp_path, bad_version):
    root = project(tmp_path)
    old_files(root)
    for name in ("config.json", "local.json"):
        old_files(root)
        path = root / "fusion" / name
        data = json.loads(path.read_text(encoding="utf-8"))
        data["schema_version"] = bad_version
        path.write_text(json.dumps(data), encoding="utf-8")
        result = cli(root, "status")
        assert result.returncode == 1
        assert name in result.stderr and "schema_version" in result.stderr


def test_newer_config_and_database_rejected_and_preflight_reports_them(tmp_path):
    root = project(tmp_path)
    old_files(root)
    config_path = root / "fusion" / "config.json"
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    cfg["schema_version"] = 3
    config_path.write_text(json.dumps(cfg), encoding="utf-8")
    result = cli(root, "status")
    assert result.returncode == 2 and "Ask the user to upgrade the plugin" in result.stderr and "config.json" in result.stderr
    preflight_result = cli(root, "preflight")
    assert preflight_result.returncode == 0, preflight_result.stderr
    preflight = json.loads(preflight_result.stdout)
    format_row = next(row for row in preflight["checks"] if row["check"] == "State format")
    assert not format_row["ok"] and "config.json" in format_row["detail"]
    cfg["schema_version"] = 2
    config_path.write_text(json.dumps(cfg), encoding="utf-8")

    local_path = root / "fusion" / "local.json"
    local = json.loads(local_path.read_text(encoding="utf-8"))
    local["schema_version"] = 3
    local_path.write_text(json.dumps(local), encoding="utf-8")
    result = cli(root, "status")
    assert result.returncode == 2 and "Ask the user to upgrade the plugin" in result.stderr and "local.json" in result.stderr
    preflight_result = cli(root, "preflight")
    assert preflight_result.returncode == 0, preflight_result.stderr
    preflight = json.loads(preflight_result.stdout)
    format_row = next(row for row in preflight["checks"] if row["check"] == "State format")
    assert not format_row["ok"] and "local.json" in format_row["detail"]
    local["schema_version"] = 2
    local_path.write_text(json.dumps(local), encoding="utf-8")

    cfg["schema_version"] = 2
    config_path.write_text(json.dumps(cfg), encoding="utf-8")
    old_database(root)
    db_path = root / "fusion" / "fusion.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA user_version=3")
    conn.commit()
    conn.close()
    before = db_path.read_bytes()
    result = cli(root, "status")
    assert result.returncode == 2 and "Ask the user to upgrade the plugin" in result.stderr and "fusion.db" in result.stderr
    conn = sqlite3.connect(db_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 4
    conn.close()
    assert db_path.read_bytes() == before
    preflight_result = cli(root, "preflight")
    assert preflight_result.returncode == 0, preflight_result.stderr
    preflight = json.loads(preflight_result.stdout)
    format_row = next(row for row in preflight["checks"] if row["check"] == "State format")
    assert not format_row["ok"] and "fusion.db" in format_row["detail"]


def test_newer_event_version_defensively_rejected(tmp_path):
    root = project(tmp_path)
    old_files(root)
    old_database(root)
    db_path = root / "fusion" / "fusion.db"
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE events SET v=3 WHERE seq=1")
    conn.commit()
    conn.close()
    result = cli(root, "status")
    assert result.returncode == 2 and "Ask the user to upgrade the plugin" in result.stderr


def test_hook_reports_newer_format_without_usage_guide(tmp_path):
    root = project(tmp_path)
    old_files(root)
    local_path = root / "fusion" / "local.json"
    local = json.loads(local_path.read_text(encoding="utf-8"))
    local["schema_version"] = 3
    local_path.write_text(json.dumps(local), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(CORE / "fusion-core.py"), "hook", "session-start"],
        input=json.dumps({"cwd": str(root)}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "Upgrade lyfusion-plugin" in context and "four actions" not in context
