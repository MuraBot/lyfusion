"""端到端流程:派工 → 候选 → 检查 → 审查 → 验收,以及各条分支。"""
from __future__ import annotations

import sys

import pytest
from conftest import report
from fusion_core import commands as C
from fusion_core.util import FusionError

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
    # 第一次运行是新会话,带规则;工位记住了会话编号
    calls = proj.calls()
    assert calls[0]["resume"] is False and "## 目标" in calls[0]["prompt"]
    st = proj.state()["stations"]["main#1"]
    assert st["thread"] and st["briefed"]
    # 审查包展示检查结果,不再包含决定债。
    from fusion_core.aq import review_pack
    text = review_pack(proj.root, t, proj.state(), 1)
    assert "检查" in text and "T1.E1" not in text
    proj.do(C.cmd_accept, "T1")
    proj.drain()
    t = proj.task()
    assert t["state"] == "accepted", t.get("integration")
    log = proj.git("log", "-2", "--format=%B", "main")
    assert "Task: T1" in log and "Candidate: T1.c1" in log
    assert proj.read("app/farewell.py") == FAREWELL  # lead 的目录在 main 上,快进后文件在
    assert proj.git("branch", "--list", "fusion/T1") == ""
    # 重复验收返回原结果
    assert proj.do(C.cmd_accept, "T1")["commit"] == t["accepted_commit"]


def test_blocked_then_answer_resumes_same_thread(proj):
    setup_task(proj)
    q = {"text": "bye 要不要支持中文?", "blocking": True}
    proj.script([{"write": {"app/farewell.py": "# 半成品\n"}, "report": report("先问一下", status="blocked", questions=[q])}, GOOD])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    t = proj.task()
    assert t["state"] == "blocked"
    assert proj.read("app/farewell.py", proj.station) == "# 半成品\n"  # 半成品留在工位
    with pytest.raises(FusionError):
        proj.do(C.cmd_accept, "T1")
    out = proj.do(C.cmd_revise, "T1", "不要")
    assert out["run"]
    proj.drain()
    calls = proj.calls()
    assert calls[1]["resume"] and calls[1]["thread"] == proj.state()["stations"]["main#1"]["thread"]
    assert "不要" in calls[1]["prompt"] and "你是 lyfusion 的助手" not in calls[1]["prompt"]
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
    assert "## 检查失败" in proj.calls()[1]["prompt"]


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
    assert "关闭了 git 的证书检查" in whys and "助手执行了 git 写操作" in whys


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
    assert "冲突" in t["integration"]["detail"]
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
    assert len(proj.git("log", "-1", "--format=%P", squashed[0]).split()) == 1  # 压成一个提交


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
    assert "未提交" in t["integration"]["detail"]
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
    proj.script([{"sleep": 60, "report": report()}])
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
    assert not pid_alive(s["runs"]["r1"]["pid"])


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
    with pytest.raises(FusionError, match="先停下来问用户"):
        proj.do(C.cmd_revise, "T1", "round 4")
    assert "round 1" in proj.calls()[1]["prompt"]


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
    with pytest.raises(FusionError, match="1 个进行中的任务"):
        proj.do(C.cmd_delegate, plan_farewell(goal="second task"))


def test_fix_without_changes_signals(proj):
    setup_task(proj)
    bad = {"write": {"app/farewell.py": BROKEN, "tests/test_farewell.py": TEST_FAREWELL}, "report": report()}
    proj.script([bad, {"report": report("没改")}])
    proj.do(C.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    t = proj.task()
    assert t["state"] == "in_review"
    assert any(s["kind"] == "check_failed" and "没有改动" in s["detail"] for s in t["signals"])


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
