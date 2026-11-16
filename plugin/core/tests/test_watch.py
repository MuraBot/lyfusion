"""Regression coverage for run statistics and durable ledger metrics."""
from __future__ import annotations

import json
import time
from argparse import Namespace
from pathlib import Path

import pytest
from conftest import report
from fusion_core import cli, codex, store, views
from fusion_core import commands as C
from fusion_core import config as config_mod
from fusion_core import supervisor as supervisor_mod
from fusion_core.prompts import FIXED_RULES, WORK_RULES, explore_prompt
from fusion_core.runstats import summarize
from fusion_core.util import FusionError, timestamp


def _command(text, output="", code=0, event="item.completed"):
    return {"type": event, "item": {"type": "command_execution", "command": text,
                                      "aggregated_output": output, "exit_code": code}}


def _active_implementation(proj):
    ctx = proj.ctx()
    try:
        task_id = C._new_task(
            ctx, {"goal": "revise", "brief": "brief", "scope": [], "checks": []}, "explored"
        )
    finally:
        ctx.close()
    run_dir = proj.root / "fusion" / "runs" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text(
        json.dumps({"type": "thread.started", "thread_id": "thread-1"}), encoding="utf-8"
    )
    events = [
        {"type": "station_created", "data": {"station": {"name": "main#1", "line": "main",
         "worktree": str(proj.station), "model": "gpt-6-luna", "predecessor": None}}},
        {"type": "run_requested", "task": task_id, "data": {"run": "r1", "kind": "implement"}},
        {"type": "run_started", "task": task_id, "data": {"run": "r1", "station": "main#1", "pid": 999,
         "dir": str(run_dir), "resumed": False, "codex_version": "codex fake-1.0"}},
        {"type": "thread_bound", "data": {"station": "main#1", "thread": "thread-1"}},
    ]
    with store.transaction(proj.sup.conn):
        store.append(proj.sup.conn, events, "test")
    return task_id


def test_stats_counts_whole_command_output_and_recent_commands():
    events = [
        _command('"C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content x | Select-Object -First 40"',
                 "\n".join(str(i) for i in range(40))),
        _command("Get-Content a; Get-Content b; Get-Content c", "\n".join("x" for _ in range(300))),
        *[_command("rg foo") for _ in range(3)],
        *[_command("python -m pytest -q tests/test_x.py") for _ in range(3)],
        _command("Get-Content ignored", "x", event="item.started"),
    ]
    stats = summarize(events, {"small_read_lines": 80})
    assert stats == {"commands": 8, "small_reads": 1, "repeats": 2,
                     "recent": stats["recent"]}
    assert len(stats["recent"]) == 8
    assert "powershell.exe" not in stats["recent"][0].lower()
    assert "[碎读]" in stats["recent"][0]
    assert all("pytest" not in row or "[重复]" not in row for row in stats["recent"])


def test_read_aliases_only_match_at_command_positions():
    events = [
        _command("rg --type py foo", "\n".join("x" for _ in range(30))),
        _command("git log --format=%h | head", "\n".join("x" for _ in range(30))),
        _command("Get-Content a.py | Select-Object -First 30", "\n".join("x" for _ in range(30))),
    ]
    assert summarize(events)["small_reads"] == 2


def test_timestamp_uses_engine_event_format():
    assert timestamp("2026-11-13T12:34:56") is not None
    assert timestamp("not-a-time") is None


def test_run_metrics_are_replayed_and_rendered_in_ledger(proj):
    ctx = proj.ctx()
    try:
        tid = C._new_task(ctx, {"goal": "stats", "brief": "brief", "scope": [], "checks": []}, "explored")
    finally:
        ctx.close()
    proj.script([{"commands": [
        {"command": "Get-Content x", "output": "one\ntwo"},
        {"command": "rg foo"}, {"command": "rg foo"},
    ], "report": report("done")}])
    ctx = proj.ctx()
    try:
        C.cmd_delegate(ctx, {"goal": "stats", "brief": "brief", "scope": [], "checks": []}, tid)
    finally:
        ctx.close()
    proj.drain()
    state = proj.state()
    run = state["runs"]["r1"]
    assert run["runstats"]["commands"] == 3
    assert run["runstats"]["small_reads"] == 1
    assert run["runstats"]["repeats"] == 1
    assert isinstance(run["duration"], (int, float))
    assert run["codex_version"] == "codex fake-1.0"
    ledger = views.ledger(state, tid)
    assert "运行" in ledger and "codex fake-1.0" in ledger
    assert "| 3 | 1 | 1 |" in ledger


def test_old_run_without_metrics_displays_dashes():
    state = {"tasks": {}, "runs": {"r1": {"id": "r1", "task": "T1", "kind": "implement",
                                               "status": "ended", "result": "ok"}}}
    assert "| T1 | r1 | 实现 | ok | - | - | - | - | - |" in views.ledger(state)


def test_watch_signal_is_once_and_empty_last_file_does_not_finish(proj, monkeypatch):
    ctx = proj.ctx()
    try:
        tid = C._new_task(ctx, {"goal": "watch", "brief": "brief", "scope": [], "checks": []}, "explored")
    finally:
        ctx.close()
    cfg = config_mod.load(proj.root)
    cfg.update(watch_minutes=0, watch_small_reads=1, watch_repeats=0)
    run_dir = proj.root / "fusion" / "runs" / "r88"
    run_dir.mkdir(parents=True)
    (run_dir / "last.txt").write_text("", encoding="utf-8")
    (run_dir / "events.jsonl").write_text(json.dumps(_command("Get-Content a", "x")), encoding="utf-8")
    run = {"id": "r88", "task": tid, "dir": str(run_dir), "pid": 999999,
           "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "station": None}
    monkeypatch.setattr(supervisor_mod, "pid_alive", lambda pid: True)
    assert proj.sup.poll_run(proj.state(), cfg, run) is True
    assert proj.state()["tasks"][tid]["signals"][-1]["kind"] == "watch"
    detail = proj.state()["tasks"][tid]["signals"][-1]["detail"]
    assert "Get-Content a" in detail
    assert "碎读 1 次(阈值 1)" in detail and "watch_small_reads" not in detail
    assert not any(event["type"] == "run_ended" for event in proj.events())
    second = supervisor_mod.Supervisor(proj.root)
    try:
        assert second.poll_run(second.state(), cfg, run) is False
    finally:
        second.conn.close()
    assert len([s for s in proj.state()["tasks"][tid]["signals"] if s["kind"] == "watch"]) == 1


def test_watch_all_thresholds_disabled(proj, monkeypatch):
    ctx = proj.ctx()
    try:
        tid = C._new_task(ctx, {"goal": "watch", "brief": "brief", "scope": [], "checks": []}, "explored")
    finally:
        ctx.close()
    cfg = config_mod.load(proj.root)
    cfg.update(watch_minutes=0, watch_small_reads=0, watch_repeats=0)
    run_dir = proj.root / "fusion" / "runs" / "r89"
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text(json.dumps(_command("Get-Content a", "x")), encoding="utf-8")
    run = {"id": "r89", "task": tid, "dir": str(run_dir), "pid": 999999,
           "started": "2000-01-01T00:00:00", "station": None}
    monkeypatch.setattr(supervisor_mod, "pid_alive", lambda pid: True)
    assert proj.sup.poll_run(proj.state(), cfg, run) is False
    assert not proj.state()["tasks"][tid]["signals"]


def test_watch_handles_run_without_task(proj, monkeypatch):
    cfg = config_mod.load(proj.root)
    cfg.update(watch_minutes=0, watch_small_reads=1, watch_repeats=0)
    run_dir = proj.root / "fusion" / "runs" / "r93"
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text(json.dumps(_command("Get-Content a", "x")), encoding="utf-8")
    run = {"id": "r93", "task": None, "dir": str(run_dir), "pid": 999999,
           "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "station": None}
    monkeypatch.setattr(supervisor_mod, "pid_alive", lambda pid: True)
    assert proj.sup.poll_run(proj.state(), cfg, run) is False


def test_watch_minutes_threshold(proj, monkeypatch):
    ctx = proj.ctx()
    try:
        tid = C._new_task(ctx, {"goal": "watch", "brief": "brief", "scope": [], "checks": []}, "explored")
    finally:
        ctx.close()
    cfg = config_mod.load(proj.root)
    cfg.update(watch_minutes=1, watch_small_reads=0, watch_repeats=0)
    run_dir = proj.root / "fusion" / "runs" / "r90"
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")
    run = {"id": "r90", "task": tid, "dir": str(run_dir), "pid": 999999,
           "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 180)), "station": None}
    monkeypatch.setattr(supervisor_mod, "pid_alive", lambda pid: True)
    assert proj.sup.poll_run(proj.state(), cfg, run) is True
    signal = proj.state()["tasks"][tid]["signals"][-1]
    assert signal["kind"] == "watch"
    assert "用时 3.0 分钟(阈值 1)" in signal["detail"]


def test_turn_completed_waits_for_process_exit_before_reading_report(proj, monkeypatch):
    run_dir = proj.root / "fusion" / "runs" / "r91"
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text(json.dumps({"type": "turn.completed"}), encoding="utf-8")
    report_text = json.dumps(report("complete"), ensure_ascii=False)
    (run_dir / "last.txt").write_text(report_text, encoding="utf-8")
    run = {"id": "r91", "task": None, "dir": str(run_dir), "pid": 999999,
           "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "station": None}
    finished = []
    monkeypatch.setattr(supervisor_mod, "TURN_EXIT_GRACE_SECONDS", 60)
    monkeypatch.setattr(supervisor_mod, "pid_alive", lambda pid: True)
    monkeypatch.setattr(
        proj.sup, "finish_run",
        lambda s, cfg, current, evs: finished.append(codex.last_message(Path(current["dir"]))),
    )
    assert proj.sup.poll_run(proj.state(), config_mod.load(proj.root), run) is False
    assert not finished
    monkeypatch.setattr(supervisor_mod, "pid_alive", lambda pid: False)
    assert proj.sup.poll_run(proj.state(), config_mod.load(proj.root), run) is True
    assert finished == [report_text]


def test_turn_completed_stuck_process_is_killed_after_grace(proj, monkeypatch):
    run_dir = proj.root / "fusion" / "runs" / "r92"
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text(json.dumps({"type": "turn.failed"}), encoding="utf-8")
    run = {"id": "r92", "task": None, "dir": str(run_dir), "pid": 999999,
           "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "station": None}
    killed, finished = [], []
    monkeypatch.setattr(supervisor_mod, "TURN_EXIT_GRACE_SECONDS", 2)
    monkeypatch.setattr(supervisor_mod, "pid_alive", lambda pid: True)
    monkeypatch.setattr(supervisor_mod, "kill_tree", lambda pid: killed.append(pid))
    monkeypatch.setattr(proj.sup, "finish_run", lambda s, cfg, current, evs: finished.append(current))
    proj.sup._turn_exit_seen["r92"] = time.monotonic() - 3
    assert proj.sup.poll_run(proj.state(), config_mod.load(proj.root), run) is True
    assert killed == [999999] and finished == [run]


def test_revise_requests_supervisor_interrupt_and_reuses_its_thread(proj, monkeypatch):
    ctx = proj.ctx()
    try:
        tid = C._new_task(ctx, {"goal": "revise", "brief": "brief", "scope": [], "checks": []}, "explored")
    finally:
        ctx.close()
    run_dir = proj.root / "fusion" / "runs" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text(json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
                                           encoding="utf-8")
    events = [
        {"type": "station_created", "data": {"station": {"name": "main#1", "line": "main",
         "worktree": str(proj.station), "model": "gpt-6-luna", "predecessor": None}}},
        {"type": "run_requested", "task": tid, "data": {"run": "r1", "kind": "implement"}},
        {"type": "run_started", "task": tid, "data": {"run": "r1", "station": "main#1", "pid": 999,
         "dir": str(run_dir), "resumed": False, "codex_version": "codex fake-1.0"}},
        {"type": "thread_bound", "data": {"station": "main#1", "thread": "thread-1"}},
    ]
    with store.transaction(proj.sup.conn):
        store.append(proj.sup.conn, events, "test")
    killed = []
    monkeypatch.setattr(supervisor_mod, "kill_tree", lambda pid: killed.append(pid))
    ctx = proj.ctx()
    try:
        out = C.cmd_revise(ctx, tid, "  finish the remaining work  ")
    finally:
        ctx.close()
    assert out["interrupt"] == "r1"
    queued = proj.state()
    assert queued["runs"]["r2"]["status"] == "interrupt_requested"
    assert queued["runs"]["r2"]["interrupt"] == "r1"
    assert queued["runs"]["r2"]["lead_text"] == "  finish the remaining work  "
    assert killed == []
    assert proj.sup.tick() == 1
    state = proj.state()
    assert killed == [999]
    assert state["runs"]["r1"]["status"] == "interrupted"
    assert state["runs"]["r2"]["kind"] == "changes"
    assert state["runs"]["r2"]["message"].startswith("你上一轮被 lead 中途停下了")
    assert state["runs"]["r2"]["message"].endswith("  finish the remaining work  ")
    assert state["runs"]["r2"]["lead_text"] == "  finish the remaining work  "
    assert state["stations"]["main#1"]["thread"] == "thread-1"
    assert state["tasks"][tid]["change_rounds"] == 1


def test_interrupt_request_after_target_finished_starts_plain_revision(proj, monkeypatch):
    tid = _active_implementation(proj)
    ctx = proj.ctx()
    try:
        C.cmd_revise(ctx, tid, "continue from the current result")
    finally:
        ctx.close()
    with store.transaction(proj.sup.conn):
        store.append(proj.sup.conn, [{"type": "run_ended", "task": tid,
                                     "data": {"run": "r1", "result": "failed"}}], "test")
    killed = []
    monkeypatch.setattr(supervisor_mod, "kill_tree", lambda pid: killed.append(pid))
    assert proj.sup.tick() == 1
    state = proj.state()
    assert killed == []
    assert state["tasks"][tid]["state"] == "running"
    assert state["tasks"][tid]["change_rounds"] == 1
    assert state["runs"]["r2"]["status"] == "requested"
    assert state["runs"]["r2"]["message"] == "continue from the current result"
    assert "中途停下" not in state["runs"]["r2"]["message"]


def test_interrupt_request_for_cancelled_task_is_dropped_and_wakes_waiter(proj):
    tid = _active_implementation(proj)
    ctx = proj.ctx()
    try:
        C.cmd_revise(ctx, tid, "please adjust")
    finally:
        ctx.close()
    with store.transaction(proj.sup.conn):
        store.append(proj.sup.conn, [{"type": "cancelled", "task": tid,
                                     "data": {"reason": "lead cancelled"}}], "test")
    with pytest.raises(FusionError, match="修改意见没有生效:任务已取消") as error:
        cli._wait(proj.root, tid)
    assert error.value.code == 2
    state = proj.state()
    assert state["runs"]["r2"]["result"] == "dropped"
    assert any(signal["kind"] == "revise_dropped" for signal in state["tasks"][tid]["signals"])


def test_revise_during_explore_exits_with_error(proj, monkeypatch):
    monkeypatch.setattr(cli, "_existing_run", lambda root, kinds: ("T1", True, "explore"))
    with pytest.raises(FusionError, match="探索还在运行") as error:
        cli._do_revise(Namespace(source="-", task="T1"), proj.root)
    assert error.value.code == 1


@pytest.mark.parametrize("signal_kind", ["stalled", "watch"])
def test_same_active_change_text_continues_waiting(proj, signal_kind):
    ctx = proj.ctx()
    try:
        tid = C._new_task(ctx, {"goal": "revise", "brief": "brief", "scope": [], "checks": []}, "explored")
    finally:
        ctx.close()
    events = [
        {"type": "run_requested", "task": tid,
         "data": {"run": "r1", "kind": "changes", "message": "same text", "lead_text": "same text"}},
        {"type": "run_started", "task": tid,
         "data": {"run": "r1", "station": None, "pid": 999, "dir": "unused"}},
        {"type": "signal", "task": tid, "data": {"kind": signal_kind, "run": "r1"}},
    ]
    with store.transaction(proj.sup.conn):
        store.append(proj.sup.conn, events, "test")
    before = len(proj.events())
    ctx = proj.ctx()
    try:
        result = C.cmd_revise(ctx, tid, "  same text  ")
    finally:
        ctx.close()
    assert result == {"task": tid, "run": "r1", "continue_wait": True}
    assert len(proj.events()) == before


def test_revise_continue_wait_message_explains_matching_opinion(proj, monkeypatch, capsys):
    class Ctx:
        def close(self):
            pass

    monkeypatch.setattr(cli, "_existing_run", lambda root, kinds: ("T1", False, "changes"))
    monkeypatch.setattr(cli, "Ctx", lambda root: Ctx())
    monkeypatch.setattr(cli, "_input", lambda args: "same opinion")
    monkeypatch.setattr(cli, "cmd_revise", lambda ctx, tid, text: {
        "task": tid, "run": "r1", "continue_wait": True,
    })
    task = {"id": "T1", "change_rounds": 1, "latest": None, "latest_report": None}
    monkeypatch.setattr(cli, "_wait", lambda root, tid: {
        "tasks": {"T1": task}, "candidates": {}, "runs": {},
    })
    monkeypatch.setattr(cli, "_write_review", lambda root, *args: (root / "review.md", "fusion/tasks/T1/review-2.md"))
    monkeypatch.setattr(cli.aq, "next_step_text", lambda task, checks: "next")
    cli._do_revise(Namespace(source="-", task="T1"), proj.root)
    output = capsys.readouterr().out
    assert "修改意见和正在做的这一轮相同,接着等它" in output
    assert "这次的输入没有用" not in output


def test_wait_watch_exits_two_and_lists_actions(monkeypatch, tmp_path):
    class Connection:
        def close(self):
            pass

    class Supervisor:
        conn = Connection()
        holder = "test"
        calls = 0

        def __init__(self, root, poll):
            pass

        def state(self):
            self.calls += 1
            signals = [] if self.calls == 1 else [{"kind": "watch", "detail": "碎读 1 次(阈值 1)", "run": "r1"}]
            return {"tasks": {"T1": {"state": "running", "signals": signals}},
                    "runs": {"r1": {"kind": "changes"}}}

        def tick(self):
            return False

    monkeypatch.setattr(cli, "Supervisor", Supervisor)
    monkeypatch.setattr(store, "take_lease", lambda conn, holder: True)
    monkeypatch.setattr(store, "release_lease", lambda conn, holder: None)
    monkeypatch.setattr(cli.time, "sleep", lambda duration: None)
    with pytest.raises(FusionError, match="碎读") as error:
        cli._wait(tmp_path, "T1")
    assert error.value.code == 2
    assert "用同样的修改意见再运行一次" in str(error.value)
    assert "revise - <<'EOF'" in str(error.value) and "cancel --task T1" in str(error.value)


def test_work_and_explore_prompts_repeat_code_read_rules():
    prompt = explore_prompt("question", "decisions")
    for text in (WORK_RULES, FIXED_RULES):
            assert "整份文件或大段" in text
            assert "不要反复跑" in text
    assert "Read whole files or large sections" in prompt
    assert "Do not repeat the same command" in prompt
    assert "do not call Claude" in prompt and "auth.json" in prompt
