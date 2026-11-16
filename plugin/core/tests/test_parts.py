"""Validators, worktrees, MCP, hooks, event store, and reconciliation."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest
from conftest import CORE, report
from fusion_core import commands as C
from fusion_core import config as config_mod
from fusion_core import hooks, store, views
from fusion_core.supervisor import Supervisor
from fusion_core.util import FusionError, clean_env, glob_match, globs_overlap, norm
from test_flow import GOOD, plan_farewell, setup_task

# ---------------- Validators ----------------

def test_plan_validation_errors(proj):
    with pytest.raises(FusionError) as e:
        proj.do(C.cmd_delegate, {"goal": "x", "items": []})
    msg = str(e.value)
    assert "unexpected: items" in msg and "items" in msg


def test_wrong_state_rejected(proj):
    setup_task(proj)
    with pytest.raises(FusionError, match="cannot be revised"):
        proj.do(C.cmd_revise, "T1", "a")
    with pytest.raises(FusionError, match="does not exist"):
        proj.do(C.cmd_revise, "T9", "a")


def test_globs():
    assert glob_match("app/a/b.py", "app/**")
    assert glob_match("x.py", "**/*.py")
    assert not glob_match("app/a.py", "*.py")
    assert globs_overlap(["app/**"], ["app/x.py"])
    assert not globs_overlap(["app/x.py"], ["lib/y.py"])
    assert norm("./.github/x") == ".github/x"


# ---------------- Worktrees ----------------

def test_explore_creates_station_then_implement_reuses_thread(proj):
    proj.script([{"text": "app/greet.py 第 1 行定义了 hello"}, GOOD])
    proj.do(C.cmd_explore, "hello 在哪里?")
    proj.drain()
    s = proj.state()
    assert "第 1 行" in s["explore_answers"]["r1"]["answer"]
    thread = s["stations"]["main#1"]["thread"]
    assert thread
    calls = proj.calls()
    assert "read-only" in calls[0]["args"] and "--output-schema" not in calls[0]["args"]
    assert calls[0]["env"]["FUSION_SANDBOX"] == "1"
    assert calls[0]["env"]["TEMP"] != str(proj.station / ".fusion-tmp")
    assert not (proj.root / ".fusion-tmp").exists()
    assert not (proj.station / ".fusion-tmp").exists()
    proj.do(C.cmd_delegate, plan_farewell())
    proj.drain()
    calls = proj.calls()
    assert calls[1]["resume"] and calls[1]["thread"] == thread
    assert "Verify the test count" in calls[1]["prompt"]  # Send the full WORK_RULES when delegating.
    assert 'sandbox_mode="workspace-write"' in calls[1]["args"]
    assert "r1" in views.status(proj.root, {}, proj.state(), "r1")


def test_clean_env_removes_sandbox_marker_and_existing_prefixes(monkeypatch):
    monkeypatch.setenv("FUSION_SANDBOX", "1")
    monkeypatch.setenv("fusion_sandbox", "2")
    monkeypatch.setenv("CLAUDE_TEST", "claude")
    monkeypatch.setenv("ANTHROPIC_TEST", "anthropic")
    env = clean_env()
    assert not any(key.upper() == "FUSION_SANDBOX" for key in env)
    assert not any(key.upper().startswith(("CLAUDE", "ANTHROPIC")) for key in env)


def test_station_rotates_on_model_change_with_handoff(proj):
    setup_task(proj)
    proj.script([GOOD, GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    proj.do(C.cmd_accept, "T1")
    proj.drain()
    local = config_mod.load(proj.root)["local"]
    local["sidekick"]["model"] = "gpt-6.1-sol"
    config_mod.save_local(proj.root, local)
    proj.do(C._new_task, plan_farewell(goal="第二个"), "explored")
    proj.do(C.cmd_delegate, plan_farewell(goal="?" * 3), "T2")
    proj.drain()
    s = proj.state()
    assert s["stations"]["main#1"]["status"] == "retired"
    assert s["stations"]["main#2"]["predecessor"] == "main#1"
    call = proj.calls()[1]
    assert not call["resume"] and "Previous station handoff summary" in call["prompt"] and "gpt-6.1-sol" in call["args"]


def test_resume_failure_retires_station(proj):
    setup_task(proj)
    q = {"text": "要不要中文?", "blocking": True}
    proj.script([{"report": report(status="blocked", questions=[q])}, {"resume_fails": True}, GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    proj.do(C.cmd_revise, "T1", "不要")
    proj.drain()
    s = proj.state()
    assert s["stations"]["main#1"]["status"] == "retired"
    assert any(x["kind"] == "stalled" and "could not resume" in x["detail"] for x in s["tasks"]["T1"]["signals"])
    # A later revision starts a new worktree and includes the full task brief.
    assert s["tasks"]["T1"]["state"] == "in_review"
    proj.do(C.cmd_revise, "T1", "继续做完")
    proj.drain()
    s = proj.state()
    assert "main#2" in s["stations"]
    call = proj.calls()[2]
    assert not call["resume"] and "## Goal" in call["prompt"] and "继续做完" in call["prompt"]


# ---------------- Reconciliation ----------------

def test_supervisor_restart_picks_up_finished_run(proj):
    setup_task(proj)
    proj.script([dict(GOOD, sleep=1.5)])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.sup.tick()  # Start the run.
    assert proj.state()["runs"]["r1"]["status"] == "started"
    proj.sup.conn.close()
    import time
    time.sleep(3)  # The assistant finishes while the supervisor is away.
    proj.sup = Supervisor(proj.root, poll=0.05)
    proj.drain()
    assert proj.task()["state"] == "in_review" and proj.task()["latest"] == "T1.c1"


def test_lease_only_one_supervisor(proj):
    a, b = store.connect(proj.root), store.connect(proj.root)
    assert store.take_lease(a, "A")
    assert not store.take_lease(b, "B")
    assert store.take_lease(a, "A")  # Renew the lease.
    store.release_lease(a, "A")
    assert store.take_lease(b, "B")
    a.close()
    b.close()


def test_concurrent_writers(proj):
    code = (f"import sys; sys.path.insert(0, r'{CORE}'); from pathlib import Path; from fusion_core import store;"
            f"c = store.connect(Path(r'{proj.root}'))\n"
            "for i in range(40):\n"
            "    with store.transaction(c):\n"
            "        store.append(c, [{'type': 'usage', 'data': {'who': 'sidekick', 'input': 1}}], 'x')\n"
            )
    ps = [subprocess.Popen([sys.executable, "-c", code]) for _ in range(3)]
    for p in ps:
        assert p.wait(120) == 0
    s = proj.state()
    assert s["usage"]["_"]["sidekick"]["input"] == 120


# ---------------- Hooks ----------------

def test_hooks_inject_within_limits(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    text = hooks.run("session-start", {"cwd": str(proj.root), "session_id": "s1", "source": "compact"})
    assert text.count("\n") + 1 <= 30
    assert len(views.LEAD_GUIDE.splitlines()) <= 24
    assert "own the result" in text
    assert proj.state()["lead_sessions"][-1] == {**proj.state()["lead_sessions"][-1], "session_id": "s1"}
    before = len(proj.state()["lead_sessions"])
    hooks.run("session-start", {"cwd": str(proj.root), "source": "fusion-panel"})
    assert len(proj.state()["lead_sessions"]) == before
    assert hooks.run("prompt", {"cwd": str(proj.root)}) is None
    assert hooks.run("pre-edit", {"cwd": str(proj.root), "tool_input": {}}) is None


def test_hooks_silent_outside_fusion_and_when_off(proj, tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert hooks.run("session-start", {"cwd": str(tmp_path)}) is None
    local = config_mod.load(proj.root)["local"]
    local["enabled"] = False
    config_mod.save_local(proj.root, local)
    assert hooks.run("session-start", {"cwd": str(proj.root)}) is None


def test_hook_process_outputs_json(proj):
    p = subprocess.run([sys.executable, str(CORE / "fusion-core.py"), "hook", "session-start"],
                       check=False,
                       input=json.dumps({"cwd": str(proj.root)}).encode(), capture_output=True)
    out = json.loads(p.stdout.decode("utf-8"))
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"


# ---------------- Notifications and ledger ----------------

def test_questions_visible_in_ledger(proj):
    setup_task(proj)
    q = {"text": "要不要中文?", "blocking": True}
    proj.script([{"report": report(status="blocked", questions=[q])}, GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    assert proj.task()["state"] == "blocked"
    assert "T1" in views.ledger(proj.state())
    proj.do(C.cmd_revise, "T1", "不要")
    proj.drain()
    assert proj.task()["state"] == "in_review"
    assert "T1" in views.ledger(proj.state())


def test_redact():
    from fusion_core.util import redact
    text = ("Authorization: Bearer abc.def.ghi\nkey sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAA\n"
            "ghp_123456789012345678901234567890abcd ok")
    out = redact(text)
    assert "abc.def" not in out and "sk-ant" not in out and "ghp_1234" not in out and out.endswith("ok")


def test_forbidden_scan_ignores_command_output(proj):
    from fusion_core.checks import scan_forbidden
    assert scan_forbidden(config_mod.load(proj.root),
                          [{"command": "python -c print('ok')", "output": "--no-verify"}], []) == []


def test_old_database_event_types_are_ignored():
    from fusion_core.state import empty, replay
    state = replay([{"seq": 1, "type": "decision_ratified", "data": {}, "ts": "now"}], empty())
    assert state["tasks"] == {}




def test_v5a_database_with_task_planned_replays():
    """The v5.0.0-a database used task_planned to create tasks, followed by run_requested; replay must work and continue numbering."""
    from fusion_core.state import empty, replay
    events = [
        {"seq": 1, "type": "task_planned", "task": "T1", "ts": "t1",
         "data": {"version": 1, "plan": {"goal": "加 wrap", "notes": "按宽度折行", "items": [{"id": "W1"}]}}},
        {"seq": 2, "type": "intent_changed", "task": None, "ts": "t2", "data": {}},
        {"seq": 3, "type": "run_requested", "task": "T1", "ts": "t3", "data": {"run": "r1", "kind": "implement"}},
        {"seq": 4, "type": "debt_added", "task": "T1", "ts": "t4", "data": {}},
        {"seq": 5, "type": "review_viewed", "task": "T1", "ts": "t5", "data": {}},
    ]
    state = replay(events, empty())
    task = state["tasks"]["T1"]
    assert task["plan"] == {"goal": "加 wrap", "brief": "按宽度折行", "checks": [], "scope": []}
    assert task["runs"] == ["r1"]
    assert state["next_task"] == 2 and state["next_run"] == 2
