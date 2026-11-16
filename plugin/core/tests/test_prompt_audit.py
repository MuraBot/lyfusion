from __future__ import annotations

import shutil
from pathlib import Path

from conftest import report, sh
from fusion_core import aq, commands, gitops, hooks
from fusion_core import config as config_mod
from fusion_core.aq import _is_test_path
from fusion_core.prompts import FIXED_RULES, FORBIDDEN, WORK_RULES, model_notes
from fusion_core.views import LEAD_GUIDE
from test_flow import GOOD, plan_farewell, setup_task


def test_forbidden_rules_are_shared_and_model_notes_are_loaded(proj):
    for item in FORBIDDEN:
        assert item in WORK_RULES
        assert item in FIXED_RULES
    (proj.root / "fusion/models").mkdir(parents=True)
    (proj.root / "fusion/models/gpt-6-luna.md").write_text(
        "## 给助手\n项目备注\n\n## 给 lead\nLead 备注\n", encoding="utf-8"
    )
    notes = model_notes(proj.root, "gpt-6-luna")
    assert "删除旧功能时直接删" in notes["sidekick"]
    assert "项目备注" in notes["sidekick"]
    assert "use a prohibition and one checkable criterion" in notes["lead"]
    assert model_notes(proj.root, "../gpt-6-luna") == {"sidekick": "", "lead": ""}
    assert "全量测试和 lint 只在结束前各跑一次" in FIXED_RULES
    assert "沙箱不能结束别的进程" in WORK_RULES
    added_rules = WORK_RULES[WORK_RULES.index("## Brief conventions"):]
    model_text = (Path(__file__).resolve().parents[1] / "fusion_core/prompts/models/gpt-6-luna.md").read_text(encoding="utf-8")
    new_text = "\n".join(FORBIDDEN) + added_rules + model_text
    assert not any(mark in new_text for mark in ("，", "；", "（", "）", "“", "”"))
    source = (Path(__file__).resolve().parents[1] / "fusion_core/prompts.py").read_text(encoding="utf-8")
    assert "_forbidden_section" not in source
    assert WORK_RULES.count("不调用 Claude") == 1 and FIXED_RULES.count("不调用 Claude") == 1


def test_model_notes_reach_assistant_and_lead(proj):
    cfg = config_mod.load(proj.root)
    cfg["local"]["sidekick"]["model"] = "gpt-6-luna"
    config_mod.save_local(proj.root, cfg["local"])
    (proj.root / "fusion/models").mkdir(parents=True)
    (proj.root / "fusion/models/gpt-6-luna.md").write_text(
        "## 给助手\n项目助手备注\n\n## 给 lead\n项目 lead 备注\n", encoding="utf-8"
    )
    setup_task(proj)
    proj.script([GOOD])
    proj.do(commands.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    assert "## 助手 gpt-6-luna 的备注" in proj.calls()[0]["prompt"]
    assert "项目助手备注" in proj.calls()[0]["prompt"]
    assert proj.calls()[0]["prompt"].index("## 助手 gpt-6-luna 的备注") > proj.calls()[0]["prompt"].index("## 不能做的事")
    assert proj.calls()[0]["prompt"].index("## 助手 gpt-6-luna 的备注") < proj.calls()[0]["prompt"].index("## 目标")
    context = hooks.run("session-start", {"cwd": str(proj.root)})
    assert "项目 lead 备注" in context


def test_starting_runs_replace_old_result_artifacts(proj):
    proj.write("fusion/review.md", "old review")
    commands_ctx = proj.ctx()
    try:
        result = commands.cmd_delegate(commands_ctx, plan_farewell())
    finally:
        commands_ctx.close()
    assert proj.read("fusion/review.md") == f"# {result['task']} 第 1 轮:助手还在做,结果出来后覆盖这个文件\n"


def test_explore_replaces_its_previous_artifact(proj):
    proj.write("fusion/explore.md", "old exploration")
    result = proj.do(commands.cmd_explore, "检查模块")
    assert proj.read("fusion/explore.md") == f"# {result['task']} 第 1 轮:助手还在做,结果出来后覆盖这个文件\n"


def test_guide_omits_workstation_path_without_old_status_tools(proj):
    assert "workstation path" not in LEAD_GUIDE
    assert "Abandon a task: fusion-core cancel." in LEAD_GUIDE
    assert "fusion-core ledger" not in LEAD_GUIDE
    assert "fusion-core status" not in LEAD_GUIDE


def test_candidate_commit_failure_blocks_with_reason_and_can_resume(proj):
    setup_task(proj)
    proj.script([{"write": {"app/new.py": "VALUE = 2\n"}, "report": report()}, GOOD])
    proj.do(commands.cmd_delegate, plan_farewell(), "T1")
    station = gitops.ensure_station(proj.root, config_mod.load(proj.root))
    nested = station / "nested"
    nested.mkdir()
    sh("git", "init", "-q", cwd=nested)
    (nested / "uncommitted.txt").write_text("pending\n", encoding="utf-8")
    proj.drain()
    assert proj.task()["state"] == "blocked"
    event = next(e for e in proj.events("signal", "T1") if e["data"]["kind"] == "candidate_failed")
    assert "git add" in event["data"]["detail"]
    pack = aq.review_pack(proj.root, proj.task(), proj.state(), 1)
    assert "Candidate was not created" in pack and "revise" in pack and "cancel" in pack
    shutil.rmtree(nested / ".git")
    proj.do(commands.cmd_revise, "T1", "继续完成任务")
    proj.drain()
    assert proj.task()["state"] == "in_review"
    assert proj.calls()[-1]["resume"]


def test_test_diff_path_classification():
    for path in ("tests/a.py", "src/test_util.py", "src/util_test.py", "src/util.test.js"):
        assert _is_test_path(path)
    assert not _is_test_path("src/util.py")


def test_review_pack_marks_blocking_questions_and_omits_large_test_diff(proj):
    base = proj.git("rev-parse", "HEAD")
    proj.write("src/change.py", "VALUE = 2\n")
    proj.write("tests/test_large.py", "\n".join(f"# {i}" for i in range(405)) + "\n")
    proj.commit("candidate")
    commit = proj.git("rev-parse", "HEAD")
    task = {
        "id": "T1", "state": "blocked", "latest": "T1.c1", "fix_attempts": 0,
        "signals": [], "runs": [], "plan": {"goal": "review", "scope": []},
        "latest_report": {"status": "blocked", "summary": "waiting", "questions": [
            {"text": "need input", "blocking": True}
        ], "choices": [], "problems": []},
    }
    state = {"candidates": {"T1.c1": {"commit": commit, "base": base, "checks": {"passed": True, "results": []}}},
             "runs": {}, "stations": {}}
    text = aq.review_pack(proj.root, task, state, 1)
    assert "- [blocking] Question: need input" in text
    assert "## Changed test expectations" in text
    assert "tests/test_large.py" in text
    assert "+VALUE = 2" in text
    assert "# 404" not in text


def test_review_pack_uses_engine_checks_for_named_cancellation_failure(proj):
    base = proj.git("rev-parse", "HEAD")
    task = {"id": "T1", "state": "in_review", "latest": "T1.c1", "runs": [], "signals": [],
            "fix_attempts": 0, "plan": {"goal": "check"},
            "latest_report": {"status": "done", "summary": "", "questions": [], "choices": [],
                              "problems": ["The test `test_cancel_kills_running` failed because the cancelled process remained alive."]}}
    state = {"candidates": {"T1.c1": {"base": base, "commit": base, "checks": {"passed": True, "results": []}}},
             "runs": {}, "stations": {}}
    text = aq.review_pack(proj.root, task, state, 1)
    assert "The sidekick reported a test failure, but the engine checks passed; trust the engine checks." in text


def test_latest_candidate_failure_hides_previous_candidate_diff(proj):
    base = proj.git("rev-parse", "HEAD")
    proj.write("src/round.py", "FIRST_ROUND = True\n")
    proj.commit("first round")
    commit = proj.git("rev-parse", "HEAD")
    task = {"id": "T1", "state": "blocked", "latest": "T1.c1", "runs": ["r1", "r2"],
            "signals": [{"kind": "candidate_failed", "run": "r2", "detail": "git add failed"}],
            "fix_attempts": 0, "plan": {"goal": "rounds"}, "latest_report": None}
    state = {"candidates": {"T1.c1": {"commit": commit, "base": base, "run": "r1", "checks": {}}},
             "runs": {"r1": {"dir": None}, "r2": {"dir": None}}, "stations": {}}
    text = aq.review_pack(proj.root, task, state, 2)
    assert "Candidate was not created: git add failed" in text
    assert "FIRST_ROUND" not in text


def test_old_test_failure_log_is_safe_when_run_dir_is_missing(proj):
    base = proj.git("rev-parse", "HEAD")
    proj.write("tests/old_test.py", "def test_old():\n    assert True\n")
    proj.commit("change test for old-test result")
    commit = proj.git("rev-parse", "HEAD")
    task = {"id": "T1", "state": "in_review", "latest": "T1.c1", "runs": ["r1"], "signals": [],
            "fix_attempts": 0, "plan": {"goal": "logs"}, "latest_report": {"status": "done", "summary": "", "questions": [], "choices": [], "problems": []}}
    state = {"candidates": {"T1.c1": {"commit": commit, "base": base, "run": "r1", "checks": {
        "passed": False, "results": [{"name": "旧测试跑新代码", "cmd": "pytest", "passed": False, "exit": 1, "restored": True}]
    }}}, "runs": {"r1": {"dir": None}}, "stations": {}}
    initial = aq.review_pack(proj.root, task, state, 1)
    checks = initial.split("## Checks\n", 1)[1].split("\n## ", 1)[0]
    assert "Old tests on new code" not in checks
    assert "Old test failed on new code:" not in initial
    run_dir = proj.root / "fusion/runs/r1"
    log = run_dir / "checks/old-tests.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("FAILED tests/old_test.py::test_old - AssertionError\n" + "\n".join(f"tail {i}" for i in range(22)), encoding="utf-8")
    state["runs"]["r1"]["dir"] = str(run_dir)
    text = aq.review_pack(proj.root, task, state, 1)
    assert "Old tests on new code" not in text
    assert "Old test failed on new code: tests/old_test.py::test_old" in text
    assert "FAILED tests/old_test.py::test_old" not in text


def test_revision_replaces_review_placeholder_before_run(proj):
    setup_task(proj)
    proj.script([{"report": report(status="blocked", questions=[{"text": "input", "blocking": True}])}, GOOD])
    proj.do(commands.cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    proj.do(commands.cmd_revise, "T1", "继续")
    assert proj.read("fusion/review.md").startswith("# T1 第 2 轮:助手还在做")
