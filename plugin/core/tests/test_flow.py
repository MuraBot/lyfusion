"""End-to-end flow: delegation → candidate → checks → review → acceptance, and alternate branches."""
from __future__ import annotations

import os
import sys
import time

import pytest
from conftest import report
from fusion_core import commands as C
from fusion_core.util import CMD, FusionError

PY = f'"{sys.executable}"'
FAREWELL = 'def bye(name):\n    return f"Bye, {name}"\n'
TEST_FAREWELL = ('import unittest\nfrom app.farewell import bye\n\n\nclass T(unittest.TestCase):\n'
                 '    def test_bye(self):\n        self.assertEqual(bye("A"), "Bye, A")\n')
BROKEN = 'def bye(name):\n    return "oops"\n'


def plan_farewell(**extra):
    p = {"goal": "加一个告别函数 bye", "brief": "写 app/farewell.py 和测试,不改 hello。",
         "scope": ["app/farewell.py", "tests/test_farewell.py"],
         "checks": [{"run": f"{PY} -c \"from app.farewell import bye; assert bye('A') == 'Bye, A'\"", "expect": 0}]}
    p.update(extra)
    return p


def setup_task(proj, **extra):
    ctx = proj.ctx()
    try:
        tid = C._new_task(ctx, plan_farewell(**extra), "explored")
        assert tid == "T1"
        return {"task": tid}
    finally:
        ctx.close()


GOOD = {"write": {"app/farewell.py": FAREWELL, "tests/test_farewell.py": TEST_FAREWELL},
        "commands": [{"command": "python -m unittest", "exit": 0}], "report": report("写好了 bye")}


def test_happy_path(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    t = proj.task()
    assert t["state"] == "in_review", t
    assert t["latest"] == "T1.c1"
    cand = proj.state()["candidates"]["T1.c1"]
    assert cand["checks"]["passed"], cand["checks"]
    # The first run starts a new session with the rules; the worktree stores its session ID.
    calls = proj.calls()
    assert calls[0]["resume"] is False and "## Goal" in calls[0]["prompt"]
    assert calls[0]["env"]["FUSION_SANDBOX"] == "1"
    temp_path = str(proj.station / ".fusion-tmp")
    assert all(calls[0]["env"][key] == temp_path for key in ("TEMP", "TMP", "TMPDIR"))
    assert (proj.station / ".fusion-tmp" / ".gitignore").read_text() == "*\n"
    st = proj.state()["stations"]["main#1"]
    assert st["thread"] and st["briefed"]
    # The review pack shows check results and no longer includes the decision debt.
    from fusion_core.aq import review_pack
    text = review_pack(proj.root, t, proj.state(), 1)
    assert "Checks" in text and "T1.E1" not in text
    proj.do(C.cmd_accept, "T1")
    proj.drain()
    t = proj.task()
    assert t["state"] == "accepted", t.get("integration")
    log = proj.git("log", "-2", "--format=%B", "main")
    assert "Task: T1" in log and "Candidate: T1.c1" in log
    assert proj.read("app/farewell.py") == FAREWELL  # The lead worktree is on main, so the file is present after fast-forward.
    assert proj.git("branch", "--list", "fusion/T1") == ""
    # Repeated acceptance returns the original result.
    assert proj.do(C.cmd_accept, "T1")["commit"] == t["accepted_commit"]


def test_blocked_then_answer_resumes_same_thread(proj):
    setup_task(proj)
    q = {"text": "bye 要不要支持中文?", "blocking": True}
    proj.script([{"write": {"app/farewell.py": "# 半成品\n"}, "report": report("先问一下", status="blocked", questions=[q])}, GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    t = proj.task()
    assert t["state"] == "blocked"
    assert proj.read("app/farewell.py", proj.station) == "# 半成品\n"  # Keep the unfinished file in the worktree.
    with pytest.raises(FusionError):
        proj.do(C.cmd_accept, "T1")
    out = proj.do(C.cmd_revise, "T1", "不要")
    assert out["run"]
    proj.drain()
    calls = proj.calls()
    assert calls[1]["resume"] and calls[1]["thread"] == proj.state()["stations"]["main#1"]["thread"]
    assert "不要" in calls[1]["prompt"] and "You are the lyfusion assistant" not in calls[1]["prompt"]
    assert proj.task()["state"] == "in_review"


def test_blocked_without_question_auto_continues_once(proj):
    setup_task(proj)
    proj.script([{"report": report("continue", status="blocked")}, GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    task = proj.task()
    kinds = [proj.state()["runs"][run_id]["kind"] for run_id in task["runs"]]
    assert kinds == ["implement", "continue"]
    assert task["state"] == "in_review"
    assert "You reported blocked but listed no blocking question." in proj.calls()[1]["prompt"]


def test_minor_fix_resets_auto_continue_count_in_replayed_state():
    from fusion_core.state import replay

    events = [
        {"seq": 1, "type": "task_created", "task": "T1", "ts": "1", "data": {}},
        {"seq": 2, "type": "run_requested", "task": "T1", "ts": "2",
         "data": {"run": "r1", "kind": "implement"}},
        {"seq": 3, "type": "run_ended", "task": "T1", "ts": "3",
         "data": {"run": "r1", "result": "blocked"}},
        {"seq": 4, "type": "run_requested", "task": "T1", "ts": "4",
         "data": {"run": "r2", "kind": "continue"}},
        {"seq": 5, "type": "run_requested", "task": "T1", "ts": "5",
         "data": {"run": "r3", "kind": "minor_fix"}},
    ]
    assert replay(events[:-1])["tasks"]["T1"]["auto_continue_count"] == 1
    task = replay(events)["tasks"]["T1"]
    assert task["runs"] == ["r1", "r2", "r3"]
    assert task["auto_continue_count"] == 0


def test_blocked_without_question_auto_continue_stops_at_limit(proj):
    setup_task(proj)
    proj.script([{"report": report("still blocked", status="blocked")} for _ in range(3)])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    task = proj.task()
    kinds = [proj.state()["runs"][run_id]["kind"] for run_id in task["runs"]]
    assert kinds == ["implement", "continue", "continue"]
    assert task["state"] == "blocked"


def test_auto_continue_can_be_disabled(proj):
    from fusion_core import config

    cfg = config.load(proj.root)
    cfg["auto_continue"] = 0
    config.save_project(proj.root, {key: value for key, value in cfg.items() if key != "local"})
    setup_task(proj)
    proj.script([{"report": report("blocked", status="blocked")}])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    assert [run["kind"] for run in proj.state()["runs"].values()] == ["implement"]
    assert proj.task()["state"] == "blocked"


def test_fix_loop_then_check_failed(proj):
    setup_task(proj)
    bad = [{"write": {"app/farewell.py": BROKEN + f"# {i}\n", "tests/test_farewell.py": TEST_FAREWELL},
            "report": report()} for i in range(3)]
    proj.script(bad)
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    t = proj.task()
    assert t["state"] == "in_review"
    assert t["fix_attempts"] == 2
    kinds = [proj.state()["runs"][r]["kind"] for r in t["runs"]]
    assert kinds == ["implement", "fix", "fix"]
    assert any(s["kind"] == "check_failed" for s in t["signals"])
    assert "## Check failures" in proj.calls()[1]["prompt"]


def test_fix_succeeds(proj):
    setup_task(proj)
    bad = {"write": {"app/farewell.py": BROKEN, "tests/test_farewell.py": TEST_FAREWELL}, "report": report()}
    proj.script([bad, GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    t = proj.task()
    assert t["state"] == "in_review" and t["latest"] == "T1.c2"
    assert proj.state()["candidates"]["T1.c2"]["checks"]["passed"]


def test_old_test_failure_is_information_and_does_not_block_accept(proj):
    proj.write("app/farewell.py", FAREWELL)
    proj.write("tests/test_farewell.py", TEST_FAREWELL)
    proj.commit("add baseline farewell")
    setup_task(proj, checks=[])
    step = {
        "write": {
            "app/farewell.py": BROKEN,
            "tests/test_farewell.py": (
                "from app.farewell import bye\n\n"
                "def test_bye():\n    assert bye(\"A\") == \"oops\"\n"
            ),
        },
        "commands": [{"command": "python -m unittest", "exit": 0}],
        "report": report(),
    }
    proj.script([step])
    proj.do(C.cmd_delegate, plan_farewell(checks=[]), "T1")
    proj.drain()
    task = proj.task()
    check = proj.state()["candidates"][task["latest"]]["checks"]
    assert check["passed"]
    assert not any(item["kind"] == "old_tests" for item in check["violations"])
    assert not any(signal["kind"] == "violation" for signal in task["signals"])
    from fusion_core.aq import review_pack
    pack = review_pack(proj.root, task, proj.state(), 1)
    assert "## Changed test expectations" in pack
    assert "Old test failed on new code: tests/test_farewell.py::test_bye" in pack
    assert "tests/test_farewell.py::test_bye" in pack
    assert 'assert bye("A") == "oops"' in pack
    proj.do(C.cmd_accept, "T1")
    proj.drain()
    assert proj.task()["state"] == "accepted"


def test_missing_brief_check_does_not_fail_run(proj):
    setup_task(proj)
    proj.script([{
        "write": {"app/farewell.py": FAREWELL, "tests/test_farewell.py": TEST_FAREWELL},
        "report": {"status": "done", "summary": "Completed", "questions": [], "choices": [], "problems": []},
    }])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    assert proj.task()["state"] == "in_review"
    check = proj.state()["candidates"][proj.task()["latest"]]["checks"]
    assert check["passed"]


def test_forbidden_command(proj):
    setup_task(proj)
    step = dict(GOOD)
    step["commands"] = [{"command": "git -c http.sslVerify=false fetch"}, {"command": "git commit -m x"}]
    step["report"] = report()
    proj.script([step])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    chk = proj.state()["candidates"]["T1.c1"]["checks"]
    whys = {v["why"] for v in chk["violations"]}
    assert "Git certificate verification is disabled" in whys and "The assistant ran a Git write command" in whys


def test_integration_conflict_returns_to_review(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    proj.write("app/farewell.py", "def bye(name):\n    return 'lead 的版本'\n")
    proj.commit("lead 也写了 farewell")
    proj.do(C.cmd_accept, "T1")
    proj.drain()
    t = proj.task()
    assert t["state"] == "in_review"
    assert "conflict" in t["integration"]["detail"]
    assert proj.git("rev-parse", "HEAD", cwd=proj.station) == proj.state()["candidates"]["T1.c1"]["commit"]


def test_main_moved_without_conflict_merges(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    proj.write("README.md", "lead 改了别的文件\n")
    proj.commit("lead 的提交")
    proj.do(C.cmd_accept, "T1")
    proj.drain()
    assert proj.task()["state"] == "accepted"
    assert proj.read("README.md") == "lead 改了别的文件\n" and proj.read("app/farewell.py") == FAREWELL
    squashed = proj.git("log", "--format=%H", "--grep", "Task: T1", "main").split()
    assert len(squashed) == 1
    assert len(proj.git("log", "-1", "--format=%P", squashed[0]).split()) == 1  # Squash to one commit.


def test_fast_forward_refused_by_dirty_lead_tree(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    proj.write("app/farewell.py", "lead 没提交的改动\n")
    proj.do(C.cmd_accept, "T1")
    proj.drain()
    t = proj.task()
    assert t["state"] == "in_review"
    assert "uncommitted changes" in t["integration"]["detail"]
    assert proj.read("app/farewell.py") == "lead 没提交的改动\n"


def test_reject_cleans_up(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    proj.do(C.cmd_cancel, "T1", "方向不对")
    proj.drain()
    assert proj.git("branch", "--list", "fusion/T1") == ""
    assert (proj.root / "fusion" / "runs" / "T1-cancelled.diff").read_text(encoding="utf-8")
    assert not (proj.station / "app" / "farewell.py").exists()


def test_cancel_kills_running(proj):
    setup_task(proj)
    proj.script([{"sleep": 20, "report": report()}])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    for _ in range(50):
        proj.sup.tick()
        if proj.state()["runs"]["r1"]["status"] == "started":
            break
    proj.do(C.cmd_cancel, "T1", "不做了")
    proj.drain()
    s = proj.state()
    assert s["tasks"]["T1"]["state"] == "cancelled" and s["tasks"]["T1"]["cleaned"]
    assert s["runs"]["r1"]["result"] == "cancelled"
    from fusion_core.util import pid_alive
    pid = s["runs"]["r1"]["pid"]
    if pid_alive(pid) and os.environ.get("FUSION_SANDBOX") == "1":
        deadline = time.monotonic() + 40
        while pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        if not pid_alive(pid):
            pytest.skip("Codex sandbox cannot terminate processes; the engine reruns this test outside the sandbox")
    assert not pid_alive(pid)


def test_sandbox_temp_files_do_not_enter_candidate(proj):
    setup_task(proj)
    proj.script([{"write": {".fusion-tmp/junk.txt": "temporary\n", "app/farewell.py": FAREWELL},
                  "report": report()}])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    candidate = proj.state()["candidates"]["T1.c1"]
    assert all(".fusion-tmp" not in path for path in candidate["checks"]["changed"])


def test_sandbox_temp_only_writes_take_no_changes_path(proj):
    setup_task(proj)
    proj.script([{"write": {".fusion-tmp/junk.txt": "temporary\n"}, "report": report()}])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    state = proj.state()
    assert not state["candidates"]
    assert any(event["type"] == "no_changes" for event in proj.events())


def test_workspace_write_local_temp_override_wins(proj):
    from fusion_core import config

    local = config.load(proj.root)["local"]
    local["env"]["TEMP"] = "X"
    config.save_local(proj.root, local)
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    assert proj.calls()[0]["env"]["TEMP"] == "X"


def test_check_command_does_not_inherit_sandbox_marker(proj, monkeypatch):
    monkeypatch.setenv("FUSION_SANDBOX", "1")
    setup_task(proj)
    check = f'{PY} -c "import os,sys; sys.exit(1 if os.environ.get(\'FUSION_SANDBOX\') else 0)"'
    proj.script([GOOD])
    proj.do(C.cmd_delegate, plan_farewell(checks=[{"run": check}]), "T1")
    proj.drain()
    candidate = proj.state()["candidates"]["T1.c1"]
    assert next(row for row in candidate["checks"]["results"] if row["name"] == "Check 1")["passed"]


def test_missing_report_asks_once(proj):
    setup_task(proj)
    proj.script([{"write": GOOD["write"], "text": "我做完了!"}, {"report": report("补交报告")}])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    t = proj.task()
    kinds = [proj.state()["runs"][r]["kind"] for r in t["runs"]]
    assert kinds == ["implement", "report"]
    assert t["state"] == "in_review" and t["latest"] == "T1.c1"
    assert t["fix_attempts"] == 0


def test_change_rounds_limit(proj):
    setup_task(proj)
    proj.script([GOOD] * 5)
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    for i in range(3):
        proj.do(C.cmd_revise, "T1", f"round {i + 1}")
        proj.drain()
    with pytest.raises(FusionError, match="Choose one: ask the user"):
        proj.do(C.cmd_revise, "T1", "round 4")
    assert "round 1" in proj.calls()[1]["prompt"]
    from fusion_core.aq import review_pack
    text = review_pack(proj.root, proj.task(), proj.state(), 4)
    # The candidate is green: it can still be accepted, so the round limit is not a struggle signal
    assert text.splitlines()[-1] == f"Next: {CMD} accept (revision rounds are used up)"
    assert "takeover" not in text


def test_takeover_applies_latest_candidate_and_cleans_sidekick(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    head = proj.git("rev-parse", "HEAD")
    out = proj.do(C.cmd_takeover, "T1")
    assert out["candidate"] == "T1.c1"
    assert proj.read("app/farewell.py") == FAREWELL
    assert "?? app/farewell.py" in proj.git("status", "--porcelain")
    assert proj.git("rev-parse", "HEAD") == head
    proj.drain()
    task = proj.task()
    assert task["state"] == "taken_over" and task["cleaned"]
    assert proj.git("branch", "--list", "fusion/T1") == ""
    diff = proj.root / "fusion" / "runs" / "T1-taken_over.diff"
    assert diff.exists() and diff.stat().st_size > 0
    event = next(event for event in proj.events("taken_over", "T1"))
    assert event["data"]["cand"] == "T1.c1"
    assert event["data"]["failed_checks"] == []
    assert proj.do(C._new_task, None, "explored") == "T2"
    with pytest.raises(FusionError, match="already Taken over"):
        proj.do(C.cmd_takeover, "T1")


def test_takeover_event_lists_failed_candidate_checks(proj):
    setup_task(proj)
    proj.script([{"write": {"app/farewell.py": BROKEN}, "report": report("Implemented") }])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    candidate = proj.state()["candidates"]["T1.c1"]
    assert not candidate["checks"]["passed"]
    out = proj.do(C.cmd_takeover, "T1")
    assert out["failed_checks"] == [{"name": "Check 1", "cmd": plan_farewell()["checks"][0]["run"]}]
    event = next(event for event in proj.events("taken_over", "T1"))
    assert event["data"]["failed_checks"] == out["failed_checks"]


def test_takeover_refuses_dirty_tracked_lead_tree(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    proj.write("app/greet.py", "lead edit\n")
    with pytest.raises(FusionError, match="uncommitted changes to tracked files"):
        proj.do(C.cmd_takeover, "T1")
    assert proj.task()["state"] == "in_review"
    assert proj.read("app/greet.py") == "lead edit\n"
    assert not proj.events("taken_over", "T1")


def test_takeover_refuses_candidate_that_no_longer_applies(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    proj.write("app/farewell.py", "lead version\n")
    proj.commit("lead conflict")
    with pytest.raises(FusionError, match="do not apply"):
        proj.do(C.cmd_takeover, "T1")
    assert proj.task()["state"] == "in_review"
    assert proj.read("app/farewell.py") == "lead version\n"
    assert not proj.events("taken_over", "T1")


def test_takeover_cli_prints_handoff_and_finishes_cleanup(proj):
    import subprocess

    from conftest import CORE

    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    result = subprocess.run([sys.executable, str(CORE / "fusion-core.py"), "--project", str(proj.root),
                             "takeover", "--task", "T1"], check=False, capture_output=True, text=True,
                            encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert "Taken over: T1" in result.stdout
    assert "Candidate: T1.c1" in result.stdout
    assert "- app/farewell.py +2 -0" in result.stdout
    assert result.stdout.rstrip().endswith(
        "Finish it yourself, run the tests and lint, and commit; the engine no longer manages this task."
    )
    assert proj.task()["state"] == "taken_over" and proj.task()["cleaned"]


def test_takeover_cli_stops_a_running_sidekick(proj):
    import subprocess

    from conftest import CORE
    from fusion_core.util import pid_alive

    setup_task(proj)
    proj.script([{"sleep": 20, "report": report()}])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    for _ in range(50):
        proj.sup.tick()
        if proj.state()["runs"]["r1"]["status"] == "started":
            break
        time.sleep(0.05)
    state = proj.state()
    pid = state["runs"]["r1"]["pid"]
    result = subprocess.run([sys.executable, str(CORE / "fusion-core.py"), "--project", str(proj.root),
                             "takeover", "--task", "T1"], check=False, capture_output=True, text=True,
                            encoding="utf-8")
    assert result.returncode == 0, result.stderr
    finished = proj.state()
    assert finished["runs"]["r1"]["result"] == "cancelled"
    assert finished["tasks"]["T1"]["state"] == "taken_over" and finished["tasks"]["T1"]["cleaned"]
    if pid_alive(pid) and os.environ.get("FUSION_SANDBOX") == "1":
        deadline = time.monotonic() + 40
        while pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        if not pid_alive(pid):
            pytest.skip("Codex sandbox cannot terminate processes; the engine reruns this test outside the sandbox")
    assert not pid_alive(pid)


def test_takeover_without_candidate_closes_blocked_task(proj):
    setup_task(proj)
    proj.script([{"report": report("Need input", status="blocked",
                                    questions=[{"text": "Which option?", "blocking": True}])}])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    out = proj.do(C.cmd_takeover, "T1")
    assert out["candidate"] is None and out["files"] == []
    assert proj.git("status", "--porcelain") == ""
    proj.drain()
    assert proj.task()["state"] == "taken_over" and proj.task()["cleaned"]


def test_two_blocked_stops_show_struggle_signal(proj):
    from fusion_core.aq import review_pack

    setup_task(proj)
    blocked = {"report": report("Need input", status="blocked",
                                questions=[{"text": "Which option?", "blocking": True}])}
    proj.script([blocked, blocked])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    proj.do(C.cmd_revise, "T1", "Answering the question")
    proj.drain()
    task = proj.task()
    assert sum(signal["kind"] == "blocked" for signal in task["signals"]) == 2
    text = review_pack(proj.root, task, proj.state(), 2)
    assert "the sidekick stopped 2 times" in text
    assert "Sidekick is struggling (" in text and "takeover" in text


def test_nonblocking_question_does_not_block_acceptance(proj):
    setup_task(proj)
    q = {"text": "空名字怎么办?", "blocking": False, "options": ["报错", "返回 Bye"], "recommendation": "返回 Bye",
         "proceeded_with": "返回 Bye"}
    step = dict(GOOD)
    step["report"] = report(questions=[q])
    proj.script([step, GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    t = proj.task()
    assert t["questions"] and t["questions"][0]["status"] == "open"
    proj.do(C.cmd_accept, "T1")
    proj.drain()
    assert proj.task()["state"] == "accepted"


def test_recheck_when_check_config_changes(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    import json
    path = proj.root / "fusion" / "config.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg["lint"] = f"{PY} -c \"print('lint ok')\""
    path.write_text(json.dumps(cfg), encoding="utf-8")
    proj.drain()
    chk = proj.state()["candidates"]["T1.c1"]["checks"]
    assert chk["recheck"] and any(r["name"] == "lint" for r in chk["results"])


def test_wip_one_line(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    with pytest.raises(FusionError, match="Only one task may be active"):
        proj.do(C.cmd_delegate, plan_farewell(goal="second task"))


def test_fix_without_changes_signals(proj):
    setup_task(proj)
    bad = {"write": {"app/farewell.py": BROKEN, "tests/test_farewell.py": TEST_FAREWELL}, "report": report()}
    proj.script([bad, {"report": report("没改")}])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    t = proj.task()
    assert t["state"] == "in_review"
    assert any(s["kind"] == "check_failed" and "changed no files" in s["detail"] for s in t["signals"])


def test_revise_reads_decisions_file_again(proj):
    setup_task(proj)
    proj.script([GOOD, GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    decisions = proj.root / "fusion" / "decisions.md"
    decisions.write_text("# 设计决定\n派工之后才写入的新决定\n", encoding="utf-8")
    proj.do(C.cmd_revise, "T1", "保留原行为")
    proj.drain()
    assert "派工之后才写入的新决定" in proj.calls()[1]["prompt"]
