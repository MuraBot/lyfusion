"""校验器、工位、MCP、钩子、事件库、对账。"""
from __future__ import annotations

import io
import json
import subprocess
import sys

import pytest

from conftest import CORE, report
from fusion_core import commands as C, config as config_mod, hooks, store, views
from fusion_core.supervisor import Supervisor
from fusion_core.util import FusionError, glob_match, globs_overlap, norm
from test_flow import GOOD, plan_farewell, setup_task


# ---------------- 校验器 ----------------

def test_plan_validation_errors(proj):
    with pytest.raises(FusionError) as e:
        proj.do(C.cmd_plan, {"goal": "x", "items": [
            {"id": "W1", "type": "judgment", "owner": "sidekick", "title": "a", "files": ["a.py"]},
            {"id": "W2", "type": "mechanical", "title": "b", "files": ["b.py"]},
            {"id": "X", "type": "magic", "title": "c"}]})
    msg = str(e.value)
    assert "bounds" in msg and "judgment 工作项由 lead 负责" in msg
    assert "至少对应 1 条验收检查" in msg and "W1、W2" in msg


def test_wrong_state_rejected(proj):
    setup_task(proj)
    with pytest.raises(FusionError, match="待开工"):
        proj.do(C.cmd_request_changes, "T1", [{"text": "a", "expect": "b"}])
    with pytest.raises(FusionError, match="不存在"):
        proj.do(C.cmd_review, "T9")


def test_globs():
    assert glob_match("app/a/b.py", "app/**")
    assert glob_match("x.py", "**/*.py")
    assert not glob_match("app/a.py", "*.py")
    assert globs_overlap(["app/**"], ["app/x.py"])
    assert not globs_overlap(["app/x.py"], ["lib/y.py"])
    assert norm("./.github/x") == ".github/x"


# ---------------- 工位 ----------------

def test_explore_creates_station_then_implement_reuses_thread(proj):
    setup_task(proj)
    proj.script([{"text": "app/greet.py 第 1 行定义了 hello"}, GOOD])
    proj.do(C.cmd_explore, ["hello 在哪里?"], "T1")
    proj.drain()
    s = proj.state()
    assert "第 1 行" in s["explore_answers"]["r1"]["answer"]
    thread = s["stations"]["main#1"]["thread"]
    assert thread
    calls = proj.calls()
    assert "read-only" in calls[0]["args"] and "--output-schema" not in calls[0]["args"]
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    calls = proj.calls()
    assert calls[1]["resume"] and calls[1]["thread"] == thread
    assert "你是 lyfusion 的助手" in calls[1]["prompt"]  # 探索时没发过规则,第一次实现要发
    assert 'sandbox_mode="workspace-write"' in calls[1]["args"]
    assert "r1" in views.status(proj.root, {}, proj.state(), "r1")


def test_station_rotates_on_model_change_with_handoff(proj):
    setup_task(proj)
    proj.script([GOOD, GOOD])
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    proj.do(C.cmd_accept, "T1")
    proj.drain()
    local = config_mod.load(proj.root)["local"]
    local["sidekick"]["model"] = "gpt-6-astra"
    config_mod.save_local(proj.root, local)
    proj.do(C.cmd_plan, plan_farewell(goal="第二个"))
    proj.do(C.cmd_delegate, "T2", [])
    proj.drain()
    s = proj.state()
    assert s["stations"]["main#1"]["status"] == "retired"
    assert s["stations"]["main#2"]["predecessor"] == "main#1"
    call = proj.calls()[1]
    assert not call["resume"] and "上一个工位的交接摘要" in call["prompt"] and "gpt-6-astra" in call["args"]


def test_resume_failure_retires_station(proj):
    setup_task(proj)
    q = {"text": "要不要中文?", "blocking": True, "options": [], "recommendation": "不要", "proceeded_with": None}
    proj.script([{"report": report(questions=[q])}, {"resume_fails": True}, GOOD])
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    proj.do(C.cmd_answer, "Q1", "不要")
    proj.drain()
    s = proj.state()
    assert s["stations"]["main#1"]["status"] == "retired"
    assert any(x["kind"] == "stalled" and "续用失败" in x["detail"] for x in s["tasks"]["T1"]["signals"])
    # 之后再派(修改意见)会开新工位,并带上完整任务单
    assert s["tasks"]["T1"]["state"] == "in_review"
    proj.do(C.cmd_request_changes, "T1", [{"text": "继续做完", "expect": "bye 能用"}])
    proj.drain()
    s = proj.state()
    assert "main#2" in s["stations"]
    call = proj.calls()[2]
    assert not call["resume"] and "## 任务 T1" in call["prompt"] and "继续做完" in call["prompt"]


# ---------------- 对账 ----------------

def test_supervisor_restart_picks_up_finished_run(proj):
    setup_task(proj)
    proj.script([dict(GOOD, sleep=1.5)])
    proj.do(C.cmd_delegate, "T1", [])
    proj.sup.tick()  # 启动运行
    assert proj.state()["runs"]["r1"]["status"] == "started"
    proj.sup.conn.close()
    import time
    time.sleep(3)  # 监督者"不在"的时候,助手跑完了
    proj.sup = Supervisor(proj.root, poll=0.05)
    proj.drain()
    assert proj.task()["state"] == "in_review" and proj.task()["latest"] == "T1.c1"


def test_lease_only_one_supervisor(proj):
    a, b = store.connect(proj.root), store.connect(proj.root)
    assert store.take_lease(a, "A")
    assert not store.take_lease(b, "B")
    assert store.take_lease(a, "A")  # 续约
    store.release_lease(a, "A")
    assert store.take_lease(b, "B")
    a.close()
    b.close()


def test_concurrent_writers(proj):
    code = ("import sys; sys.path.insert(0, r'%s'); from pathlib import Path; from fusion_core import store;"
            "c = store.connect(Path(r'%s'))\n"
            "for i in range(40):\n"
            "    with store.transaction(c):\n"
            "        store.append(c, [{'type': 'usage', 'data': {'who': 'lead', 'input': 1}}], 'x')\n"
            ) % (CORE, proj.root)
    ps = [subprocess.Popen([sys.executable, "-c", code]) for _ in range(3)]
    for p in ps:
        assert p.wait(120) == 0
    s = proj.state()
    assert s["usage"]["_"]["lead"]["input"] == 120


# ---------------- 钩子 ----------------

def test_hooks_inject_within_limits(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, "T1", [])
    text = hooks.run("session-start", {"cwd": str(proj.root), "session_id": "s1", "source": "compact"})
    assert text.count("\n") + 1 <= 20
    assert len(views.LEAD_GUIDE.splitlines()) <= 20
    assert "只做 4 件事" in text
    assert proj.state()["lead_sessions"][-1] == {**proj.state()["lead_sessions"][-1], "session_id": "s1"}
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
                       input=json.dumps({"cwd": str(proj.root)}).encode(), capture_output=True)
    out = json.loads(p.stdout.decode("utf-8"))
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"


# ---------------- 通知和台账 ----------------

def test_notifications(proj):
    setup_task(proj)
    q = {"text": "要不要中文?", "blocking": True, "options": [], "recommendation": "不要", "proceeded_with": None}
    proj.script([{"report": report(questions=[q])}, GOOD])
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    lines = views.notifications(proj.state(), proj.events())
    assert any("阻塞问题 Q1" in x for x in lines)
    seq = proj.events()[-1]["seq"]
    proj.do(C.cmd_answer, "Q1", "不要")
    proj.drain()
    new = [e for e in proj.events() if e["seq"] > seq]
    lines = views.notifications(proj.state(), new)
    assert any("T1.c1 待审" in x for x in lines)
    assert "T1" in views.ledger(proj.state())


def test_redact():
    from fusion_core.util import redact
    text = ("Authorization: Bearer abc.def.ghi\nkey sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAA\n"
            "ghp_123456789012345678901234567890abcd ok")
    out = redact(text)
    assert "abc.def" not in out and "sk-ant" not in out and "ghp_1234" not in out and out.endswith("ok")


