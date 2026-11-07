"""校验器、工位、MCP、钩子、事件库、对账。"""
from __future__ import annotations

import io
import json
import subprocess
import sys

import pytest

from conftest import CORE, report
from fusion_core import commands as C, config as config_mod, hooks, store, views
from fusion_core.mcp import Server
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


def test_plan_overlap_and_follows(proj):
    base = {"goal": "x", "bounds": {"must": [], "free": [], "escalate": []},
            "checks": [{"id": "C1", "kind": "command", "run": "echo"}]}
    with pytest.raises(FusionError, match="范围重叠"):
        proj.do(C.cmd_plan, {**base, "items": [
            {"id": "W1", "type": "judgment", "title": "样例", "files": ["app/**"]},
            {"id": "W2", "type": "mechanical", "title": "其他", "files": ["app/x.py"], "checks": ["C1"]}]})
    out = proj.do(C.cmd_plan, {**base, "items": [
        {"id": "W1", "type": "judgment", "title": "样例", "files": ["app/**"]},
        {"id": "W2", "type": "mechanical", "title": "其他", "files": ["app/x.py"], "checks": ["C1"],
         "follows": "W1"}]})
    assert out["task"] == "T1"
    # follows 要先提交样例
    with pytest.raises(FusionError, match="先提交样例"):
        proj.do(C.cmd_delegate, "T1", ["W2"])


def test_perceivable_needs_experience_decision(proj):
    base = {"goal": "x", "bounds": {"must": [], "free": [], "escalate": []},
            "checks": [{"id": "C1", "kind": "command", "run": "echo"}],
            "items": [{"id": "W1", "type": "mechanical", "title": "a", "files": ["ui/a.html"], "checks": ["C1"],
                       "perceivable": True}]}
    with pytest.raises(FusionError, match="experience"):
        proj.do(C.cmd_plan, base)
    proj.do(C.cmd_intent, {"category": "experience", "content": "按钮在右下", "reason": "用户说的"})
    assert proj.do(C.cmd_plan, {**base, "decisions": ["D1"]})["task"] == "T1"


def test_decision_versions_and_stale_refs(proj):
    setup_task(proj)
    t = proj.task()
    assert t["plan"]["decisions"] == ["D1@1"]
    out = proj.do(C.cmd_intent, {"op": "revise", "id": "D1", "content": "新的说法", "reason": "用户改主意"})
    assert out["decision"] == "D1@2" and out["affected"] == ["T1"]
    with pytest.raises(FusionError, match="D1@2"):
        proj.do(C.cmd_plan, plan_farewell(decisions=["D1@1"]), "T1")
    assert "D1@2" in proj.read("fusion/intent.md")
    from fusion_core import intent
    assert intent.recover(proj.root)[0]["version"] == 2


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
    proj.do(C.cmd_accept, "T1", ratify=["T1.E1"])
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


# ---------------- MCP ----------------

def _mcp(root, msgs, supervise=False):
    inp = io.BytesIO("".join(json.dumps(m) + "\n" for m in msgs).encode("utf-8"))
    out = io.BytesIO()
    srv = Server(root, stdin=inp, stdout=out, supervise=supervise)
    srv.serve()
    return [json.loads(x) for x in out.getvalue().decode("utf-8").splitlines() if x.strip()]


def test_mcp_protocol(proj):
    res = _mcp(proj.root, [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "fusion_plan", "arguments": {
            "plan": {"goal": "直接做", "direct": True}}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "fusion_accept", "arguments": {
            "task": "T9"}}},
        {"jsonrpc": "2.0", "id": 5, "method": "nope"}])
    by = {r.get("id"): r for r in res}
    assert by[1]["result"]["serverInfo"]["name"] == "fusion"
    names = [t["name"] for t in by[2]["result"]["tools"]]
    assert "fusion_plan" in names and len(names) == 12
    assert "T1" in by[3]["result"]["content"][0]["text"] and not by[3]["result"]["isError"]
    assert by[4]["result"]["isError"]
    assert by[5]["error"]["code"] == -32601


def test_mcp_empty_outside_fusion(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    res = _mcp(tmp_path, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    assert res[0]["result"]["tools"] == []
    res = _mcp(None, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    assert res[0]["result"]["tools"] == []


# ---------------- 钩子 ----------------

def test_hooks_inject_within_limits(proj):
    for i in range(30):
        proj.do(C.cmd_intent, {"category": "rule", "content": f"规则 {i}", "reason": "测试"})
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, "T1", [])
    text = hooks.run("session-start", {"cwd": str(proj.root), "session_id": "s1", "source": "compact"})
    assert text.count("\n") + 1 <= views.SESSION_LIMIT
    assert len(views.LEAD_GUIDE.splitlines()) <= 60
    assert "对话压缩后恢复" in text and "T1" in text
    assert proj.state()["lead_sessions"][-1] == {**proj.state()["lead_sessions"][-1], "session_id": "s1"}
    line = hooks.run("prompt", {"cwd": str(proj.root)})
    assert line.startswith("Fusion:") and "\n" not in line
    hint = hooks.run("pre-edit", {"cwd": str(proj.root), "tool_input": {
        "file_path": str(proj.root / "app" / "farewell.py")}})
    assert hint and "T1" in hint
    assert hooks.run("pre-edit", {"cwd": str(proj.root), "tool_input": {
        "file_path": str(proj.root / "README.md")}}) is None


def test_hooks_silent_outside_fusion_and_when_off(proj, tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert hooks.run("session-start", {"cwd": str(tmp_path)}) is None
    local = config_mod.load(proj.root)["local"]
    local["enabled"] = False
    config_mod.save_local(proj.root, local)
    assert hooks.run("prompt", {"cwd": str(proj.root)}) is None


def test_hook_process_outputs_json(proj):
    p = subprocess.run([sys.executable, str(CORE / "fusion-core.py"), "hook", "prompt"],
                       input=json.dumps({"cwd": str(proj.root)}).encode(), capture_output=True)
    out = json.loads(p.stdout.decode("utf-8"))
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"


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


def test_cli_roundtrip(proj):
    def cli(*args, stdin=None):
        p = subprocess.run([sys.executable, str(CORE / "fusion-core.py"), "--project", str(proj.root), *args],
                           input=(stdin or "").encode("utf-8"), capture_output=True)
        return json.loads(p.stdout.decode("utf-8"))
    out = cli("plan", stdin=json.dumps({"plan": {"goal": "命令行建的任务", "direct": True}}))
    assert out["task"] == "T1"
    assert "T1" in cli("status")["text"]
    assert cli("accept", stdin='{"task": "T1"}')["task"] == "T1"
    assert cli("config", "get")["local"]["enabled"] is True
    pre = cli("preflight")
    assert {r["check"] for r in pre["checks"]} >= {"git", "Codex", "工位目录不在临时目录"}
    assert cli("off")["ok"] and cli("on")["ok"]


def test_redact():
    from fusion_core.util import redact
    text = ("Authorization: Bearer abc.def.ghi\nkey sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAA\n"
            "ghp_123456789012345678901234567890abcd ok")
    out = redact(text)
    assert "abc.def" not in out and "sk-ant" not in out and "ghp_1234" not in out and out.endswith("ok")


def test_cli_wait_returns_on_review(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, "T1", [])
    p = subprocess.run([sys.executable, str(CORE / "fusion-core.py"), "--project", str(proj.root), "wait",
                        "--timeout", "120", "--after", "0"], capture_output=True, timeout=180)
    out = json.loads(p.stdout.decode("utf-8"))
    assert any("T1.c1 待审" in x for x in out["notifications"]), out
    p = subprocess.run([sys.executable, str(CORE / "fusion-core.py"), "--project", str(proj.root), "wait"],
                       capture_output=True, timeout=60)
    assert json.loads(p.stdout.decode("utf-8"))["idle"]


def test_events_follow_inert_outside_git(tmp_path):
    p = subprocess.Popen([sys.executable, str(CORE / "fusion-core.py"), "--project", str(tmp_path), "events",
                          "--follow"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    import time
    time.sleep(3)
    assert p.poll() is None  # 安静地等,不退出、不报错
    p.kill()
    out, err = p.communicate()
    assert out == b"" and err == b""
