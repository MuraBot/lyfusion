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
    p = {"goal": "加一个告别函数 bye", "decisions": ["D1"],
         "bounds": {"must": ["不改 hello"], "free": ["内部写法"], "escalate": ["要改 hello 的签名"]},
         "items": [{"id": "W1", "type": "mechanical", "title": "写 app/farewell.py 和测试",
                    "files": ["app/farewell.py", "tests/test_farewell.py"], "checks": ["C1"]}],
         "checks": [{"id": "C1", "kind": "command",
                     "run": f"{PY} -c \"from app.farewell import bye; assert bye('A') == 'Bye, A'\""}]}
    p.update(extra)
    return p


def setup_task(proj, **extra):
    proj.do(C.cmd_intent, {"category": "interface", "content": "问候函数都是 f(name) -> str", "reason": "统一"})
    out = proj.do(C.cmd_plan, plan_farewell(**extra))
    assert out["task"] == "T1"
    return out


GOOD = {"write": {"app/farewell.py": FAREWELL, "tests/test_farewell.py": TEST_FAREWELL},
        "commands": [{"command": "python -m unittest", "exit": 0}],
        "report": report("写好了 bye", items=[{"id": "W1", "status": "done", "note": ""}],
                         choices=[{"what": "告别语用英文 Bye", "options": ["Bye", "再见"], "why": "和 hello 一致",
                                   "files": ["app/farewell.py"]}])}


def test_happy_path(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    t = proj.task()
    assert t["state"] == "in_review", t
    assert t["latest"] == "T1.c1"
    cand = proj.state()["candidates"]["T1.c1"]
    assert cand["checks"]["passed"], cand["checks"]
    assert len(t["debt"]) == 1
    # 第一次运行是新会话,带规则;工位记住了会话编号
    calls = proj.calls()
    assert calls[0]["resume"] is False and "你是 lyfusion 的助手" in calls[0]["prompt"]
    st = proj.state()["stations"]["main#1"]
    assert st["thread"] and st["briefed"]
    # 审查第 2 层带决定债明细
    text = proj.do(C.cmd_review, "T1")["text"]
    assert "T1.E1" in text and "检查" in text
    # 决定债没处理不能验收
    with pytest.raises(FusionError, match="T1.E1"):
        proj.do(C.cmd_accept, "T1")
    proj.do(C.cmd_accept, "T1", "T1.c1", ratify=["T1.E1"])
    proj.drain()
    t = proj.task()
    assert t["state"] == "accepted", t.get("integration")
    log = proj.git("log", "-2", "--format=%B", "main")
    assert "Task: T1" in log and "Candidate: T1.c1" in log
    assert proj.read("app/farewell.py") == FAREWELL  # lead 的目录在 main 上,快进后文件在
    assert proj.git("branch", "--list", "fusion/T1") == ""
    # 重复验收返回原结果
    assert "已经验收过了" in proj.do(C.cmd_accept, "T1")["text"]
    # intent.md 进了 git
    assert "fusion/intent.md" in proj.git("log", "--name-only", "--format=", "-3")


def test_blocked_then_answer_resumes_same_thread(proj):
    setup_task(proj)
    q = {"text": "bye 要不要支持中文?", "blocking": True, "options": ["要", "不要"], "recommendation": "不要",
         "proceeded_with": None}
    proj.script([{"write": {"app/farewell.py": "# 半成品\n"}, "report": report("先问一下", questions=[q])}, GOOD])
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    t = proj.task()
    assert t["state"] == "blocked"
    assert proj.read("app/farewell.py", proj.station) == "# 半成品\n"  # 半成品留在工位
    with pytest.raises(FusionError):
        proj.do(C.cmd_accept, "T1")
    out = proj.do(C.cmd_answer, "Q1", "不要")
    assert out["run"]
    proj.drain()
    calls = proj.calls()
    assert calls[1]["resume"] and calls[1]["thread"] == proj.state()["stations"]["main#1"]["thread"]
    assert "不要" in calls[1]["prompt"] and "你是 lyfusion 的助手" not in calls[1]["prompt"]
    assert proj.task()["state"] == "in_review"


def test_fix_loop_then_check_failed(proj):
    setup_task(proj)
    bad = [{"write": {"app/farewell.py": BROKEN + f"# {i}\n", "tests/test_farewell.py": TEST_FAREWELL},
            "report": report()} for i in range(3)]
    proj.script(bad)
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    t = proj.task()
    assert t["state"] == "in_review"
    assert t["fix_attempts"] == 2
    kinds = [proj.state()["runs"][r]["kind"] for r in t["runs"]]
    assert kinds == ["implement", "fix", "fix"]
    assert any(s["kind"] == "check_failed" for s in t["signals"])
    assert "检查没有通过" in proj.calls()[1]["prompt"]


def test_fix_succeeds(proj):
    setup_task(proj)
    bad = {"write": {"app/farewell.py": BROKEN, "tests/test_farewell.py": TEST_FAREWELL}, "report": report()}
    proj.script([bad, GOOD])
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    t = proj.task()
    assert t["state"] == "in_review" and t["latest"] == "T1.c2"
    assert proj.state()["candidates"]["T1.c2"]["checks"]["passed"]


def test_weakened_test_is_violation(proj):
    setup_task(proj)
    weak = dict(GOOD)
    weak["write"] = dict(GOOD["write"])
    weak["write"]["tests/test_greet.py"] = "import unittest\n"
    weak["write"]["app/greet.py"] = 'def hello(name):\n    return "x"\n'
    weak["report"] = report()
    proj.script([weak])
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    t = proj.task()
    chk = proj.state()["candidates"][t["latest"]]["checks"]
    assert any(v["kind"] == "old_tests" for v in chk["violations"])
    assert any(s["kind"] == "violation" for s in t["signals"])
    with pytest.raises(FusionError, match="违规"):
        proj.do(C.cmd_accept, "T1")


def test_forbidden_command(proj):
    setup_task(proj)
    step = dict(GOOD)
    step["commands"] = [{"command": "git -c http.sslVerify=false fetch"}, {"command": "git commit -m x"}]
    step["report"] = report()
    proj.script([step])
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    chk = proj.state()["candidates"]["T1.c1"]["checks"]
    whys = {v["why"] for v in chk["violations"]}
    assert "关闭了 git 的证书检查" in whys and "助手执行了 git 写操作" in whys


def test_integration_conflict_returns_to_review(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    proj.write("app/farewell.py", "def bye(name):\n    return 'lead 的版本'\n")
    proj.commit("lead 也写了 farewell")
    proj.do(C.cmd_accept, "T1", ratify=["T1.E1"])
    proj.drain()
    t = proj.task()
    assert t["state"] == "in_review"
    assert "冲突" in t["integration"]["detail"]
    assert proj.git("rev-parse", "HEAD", cwd=proj.station) == proj.state()["candidates"]["T1.c1"]["commit"]


def test_main_moved_without_conflict_merges(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    proj.write("README.md", "lead 改了别的文件\n")
    proj.commit("lead 的提交")
    proj.do(C.cmd_accept, "T1", ratify=["T1.E1"])
    proj.drain()
    assert proj.task()["state"] == "accepted"
    assert proj.read("README.md") == "lead 改了别的文件\n" and proj.read("app/farewell.py") == FAREWELL
    squashed = proj.git("log", "--format=%H", "--grep", "Task: T1", "main").split()
    assert len(squashed) == 1
    assert len(proj.git("log", "-1", "--format=%P", squashed[0]).split()) == 1  # 压成一个提交


def test_fast_forward_refused_by_dirty_lead_tree(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    proj.write("app/farewell.py", "lead 没提交的改动\n")
    proj.do(C.cmd_accept, "T1", ratify=["T1.E1"])
    proj.drain()
    t = proj.task()
    assert t["state"] == "in_review"
    assert "未提交" in t["integration"]["detail"]
    assert proj.read("app/farewell.py") == "lead 没提交的改动\n"


def test_takeover_brings_changes(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    proj.do(C.cmd_takeover, "T1", True, "我自己来收尾")
    proj.drain()
    t = proj.task()
    assert t["state"] == "planned" and t["direct"]
    assert proj.read("app/farewell.py") == FAREWELL
    assert t["items"]["W1"]["owner"] == "lead"
    proj.commit("lead 收尾")
    proj.do(C.cmd_accept, "T1")
    proj.drain()
    assert proj.task()["state"] == "accepted"


def test_reject_cleans_up(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    proj.do(C.cmd_reject, "T1", "方向不对")
    proj.drain()
    assert proj.git("branch", "--list", "fusion/T1") == ""
    assert (proj.root / "fusion" / "runs" / "T1-rejected.diff").read_text(encoding="utf-8")
    assert not (proj.station / "app" / "farewell.py").exists()


def test_cancel_kills_running(proj):
    setup_task(proj)
    proj.script([{"sleep": 60, "report": report()}])
    proj.do(C.cmd_delegate, "T1", [])
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
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    t = proj.task()
    kinds = [proj.state()["runs"][r]["kind"] for r in t["runs"]]
    assert kinds == ["implement", "report"]
    assert t["state"] == "in_review" and t["latest"] == "T1.c1"
    assert t["fix_attempts"] == 0


def test_change_rounds_limit(proj):
    setup_task(proj)
    proj.script([GOOD] * 5)
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    for i in range(3):
        proj.do(C.cmd_request_changes, "T1", [{"text": f"第 {i + 1} 处", "expect": "改好"}])
        proj.drain()
    with pytest.raises(FusionError, match="先停下来问用户"):
        proj.do(C.cmd_request_changes, "T1", [{"text": "第 4 处", "expect": "改好"}])
    assert "第 1 处" in proj.calls()[1]["prompt"]


def test_nonblocking_disagree_becomes_change(proj):
    setup_task(proj)
    q = {"text": "空名字怎么办?", "blocking": False, "options": ["报错", "返回 Bye"], "recommendation": "返回 Bye",
         "proceeded_with": "返回 Bye"}
    step = dict(GOOD)
    step["report"] = report(questions=[q])
    proj.script([step, GOOD])
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    t = proj.task()
    debt_q = [d for d in t["debt"].values() if d.get("question") == "Q1"]
    assert debt_q
    with pytest.raises(FusionError, match="agree"):
        proj.do(C.cmd_answer, "Q1", "报错")
    out = proj.do(C.cmd_answer, "Q1", "报错", agree=False)
    assert "修改意见" in out["text"]
    proj.drain()
    assert "驳回你自定的选择" in proj.calls()[1]["prompt"]


def test_recheck_when_check_config_changes(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    import json
    path = proj.root / "fusion" / "config.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg["lint"] = f"{PY} -c \"print('lint ok')\""
    path.write_text(json.dumps(cfg), encoding="utf-8")
    proj.drain()
    chk = proj.state()["candidates"]["T1.c1"]["checks"]
    assert chk["recheck"] and any(r["name"] == "lint" for r in chk["results"])


def test_direct_task(proj):
    out = proj.do(C.cmd_plan, {"goal": "改个注释", "direct": True})
    proj.write("app/greet.py", "# 注释\n" + proj.read("app/greet.py"))
    proj.commit("注释")
    proj.do(C.cmd_accept, out["task"])
    proj.drain()
    assert proj.task(out["task"])["state"] == "accepted"


def test_wip_one_line(proj):
    setup_task(proj)
    proj.script([GOOD])
    proj.do(C.cmd_delegate, "T1", [])
    proj.do(C.cmd_plan, plan_farewell(goal="第二个任务"))
    with pytest.raises(FusionError, match="1 条工作线"):
        proj.do(C.cmd_delegate, "T2", [])


def test_fix_without_changes_signals(proj):
    setup_task(proj)
    bad = {"write": {"app/farewell.py": BROKEN, "tests/test_farewell.py": TEST_FAREWELL}, "report": report()}
    proj.script([bad, {"report": report("没改")}])
    proj.do(C.cmd_delegate, "T1", [])
    proj.drain()
    t = proj.task()
    assert t["state"] == "in_review"
    assert any(s["kind"] == "check_failed" and "没有改动" in s["detail"] for s in t["signals"])
