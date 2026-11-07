"""Subprocess coverage for the public aq CLI and its artifacts."""

from __future__ import annotations

import json
import subprocess
import sys

from conftest import CORE, report


def cli(proj, *args, input_text=None):
    return subprocess.run(
        [
            sys.executable,
            str(CORE / "fusion-core.py"),
            "--project",
            str(proj.root),
            *args,
        ],
        check=False,
        input=None if input_text is None else input_text.encode("utf-8"),
        capture_output=True,
        timeout=180,
    )


def test_explore_stdin_utf8_writes_artifacts(proj):
    proj.script([{"text": "代码在 app/greet.py。"}])
    raw = "任务原话：修改问候。\nQ1：入口在哪？\n".encode("utf-8-sig")
    p = subprocess.run(
        [
            sys.executable,
            str(CORE / "fusion-core.py"),
            "--project",
            str(proj.root),
            "explore",
            "-",
        ],
        check=False,
        input=raw,
        capture_output=True,
        timeout=180,
    )
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    artifact = (proj.root / "fusion" / "tasks" / "T1" / "explore.md").read_text(
        encoding="utf-8"
    )
    assert "任务原话：修改问候。" in artifact and "代码在 app/greet.py。" in artifact
    assert artifact.splitlines()[0] == "任务编号:T1"
    assert artifact.splitlines()[1].startswith("助手会话编号:")
    assert (proj.root / "fusion/explore.md").read_text(encoding="utf-8") == artifact
    assert p.stdout.decode("utf-8").splitlines()[0] == "结果: fusion/explore.md"


def test_delegate_four_field_plan_and_resumes_explore(proj):
    (proj.root / "fusion" / "decisions.md").write_text(
        "# 设计决定\n\n只用新决定\n", encoding="utf-8"
    )
    proj.script(
        [
            {"text": "探索结论。"},
            {
                "write": {"app/new.py": "VALUE = 1\n"},
                "report": report(summary="完成", status="done"),
            },
        ]
    )
    p = cli(proj, "explore", "-", input_text="任务原话\nQ1：查入口")
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    plan = {"goal": "加模块", "brief": "## 目标\n加 app/new.py", "scope": ["app/**"]}
    p = cli(proj, "delegate", "-", input_text=json.dumps(plan, ensure_ascii=False))
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    assert (proj.root / "fusion/review.md").exists()
    calls = proj.calls()
    assert calls[0]["resume"] is False and calls[1]["resume"] is True
    assert "fusion/decisions.md 全文" in calls[1]["prompt"]


def test_plan_validation_and_regex_expect(proj):
    for bad, expected in [
        ({"brief": "正文"}, "goal 要是非空的一行文字"),
        (
            {"goal": "x", "brief": "正文", "checks": [{"run": "echo"}, {"run": ""}]},
            "checks[1].run",
        ),
        ({"goal": "x", "brief": "正文", "extra": True}, "只允许字段"),
    ]:
        p = cli(proj, "delegate", "-", input_text=json.dumps(bad))
        assert p.returncode == 1 and expected in p.stderr.decode("utf-8")
    assert not (proj.root / "fusion.db").exists() or proj.state()["next_task"] == 1


def test_revise_reuses_session_and_fourth_round_stops(proj):
    steps = [
        {"write": {"app/new.py": f"VALUE = {i}\n"}, "report": report(status="done")}
        for i in range(5)
    ]
    proj.script(steps)
    p = cli(
        proj,
        "delegate",
        "-",
        input_text=json.dumps(
            {"goal": "加模块", "brief": "改代码", "scope": ["app/**"]}
        ),
    )
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    for i in range(3):
        p = cli(proj, "revise", "-", input_text=f"第 {i + 1} 轮修改")
        assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    p = cli(proj, "revise", "-", input_text="第 4 轮")
    assert p.returncode == 2 and "3 轮" in p.stderr.decode("utf-8", "replace")
    assert "review-4.md" in {p.name for p in (proj.root / "fusion/tasks/T1").iterdir()}
    assert all(call["resume"] for call in proj.calls()[1:])


def test_accept_squashes_and_fast_forwards(proj):
    proj.script(
        [{"write": {"app/new.py": "VALUE = 2\n"}, "report": report(status="done")}]
    )
    p = cli(
        proj,
        "delegate",
        "-",
        input_text=json.dumps(
            {"goal": "加模块", "brief": "改代码", "scope": ["app/**"]}
        ),
    )
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    p = cli(proj, "accept")
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    task_log = proj.git("log", "--format=%B", "--grep", "Task: T1", "main")
    assert "Candidate:" in task_log
    assert (
        len(proj.git("log", "--format=%H", "--grep", "Task: T1", "main").split()) == 1
    )


def test_accept_refuses_forbidden_command_without_waive(proj):
    proj.script(
        [
            {
                "write": {"app/new.py": "VALUE = 2\n"},
                "commands": [{"command": "git commit -m bad"}],
                "report": report(status="done"),
            }
        ]
    )
    p = cli(
        proj,
        "delegate",
        "-",
        input_text=json.dumps(
            {"goal": "加模块", "brief": "改代码", "scope": ["app/**"]}
        ),
    )
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    p = cli(proj, "accept")
    assert p.returncode == 1 and "违规" in p.stderr.decode("utf-8")


def test_review_has_four_sections_and_scope_marking(proj):
    proj.script(
        [
            {
                "write": {"app/new.py": "VALUE = 2\n", "outside.txt": "bad\n"},
                "report": report(status="done", choices=[{"what": "value 2", "why": "和旧值对齐"}]),
            }
        ]
    )
    p = cli(
        proj,
        "delegate",
        "-",
        input_text=json.dumps(
            {"goal": "加模块", "brief": "改代码", "scope": ["app/**"]}
        ),
    )
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    text = (proj.root / "fusion/review.md").read_text(encoding="utf-8")
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert headings == ["## 检查", "## 助手的问题和自定的选择", "## 改动"]
    assert "outside.txt" in text and "范围外" in text
    assert "自定选择:value 2(理由:和旧值对齐)" in text


def test_review_omits_violation_section_and_large_diff(proj):
    huge = "".join(f"LINE_{i} = {i}\n" for i in range(450))
    proj.script([{"write": {"app/new.py": huge}, "report": report(status="done")}])
    p = cli(
        proj,
        "delegate",
        "-",
        input_text=json.dumps(
            {"goal": "加模块", "brief": "改代码", "scope": ["app/**"]}
        ),
    )
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    text = (proj.root / "fusion/review.md").read_text(encoding="utf-8")
    assert "## 违规" not in text
    assert "```diff" not in text and "app/new.py" in text


def test_existing_exploration_is_resumed_and_new_input_ignored(proj):
    proj.script([{"text": "已有探索结束。"}])
    ctx = proj.ctx()
    try:
        out = __import__("fusion_core.commands", fromlist=["cmd_explore"]).cmd_explore(
            ctx, "第一次原话"
        )
    finally:
        ctx.close()
    proj.sup.tick()
    p = cli(proj, "explore", "-", input_text="不应使用的新输入")
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    assert "已有运行在进行,接着等它;这次的输入没有用" in p.stdout.decode("utf-8")
    assert len(proj.calls()) == 1
    artifact = (proj.root / "fusion" / "tasks" / out["task"] / "explore.md").read_text(
        encoding="utf-8"
    )
    assert "第一次原话" in artifact and "不应使用的新输入" not in artifact


def test_on_restores_config_and_decision_defaults(proj):
    p = cli(proj, "on", "--test", "python -m unittest", "--lint", "ruff check .")
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    assert "Fusion 已在" in p.stdout.decode("utf-8")
    cfg = json.loads((proj.root / "fusion" / "config.json").read_text(encoding="utf-8"))
    assert cfg["test"] == "python -m unittest" and cfg["lint"] == "ruff check ."
    decisions = (proj.root / "fusion" / "decisions.md").read_text(encoding="utf-8")
    assert decisions.splitlines() == [
        "# 设计决定",
        "> lead 直接编辑这个文件。每次派工,引擎把全文带给助手。只写所有任务都要守的决定。",
    ]


def test_preflight_has_original_check_names(proj):
    p = cli(proj, "preflight")
    assert p.returncode == 0
    preflight = json.loads(p.stdout)
    assert {row["check"] for row in preflight["checks"]} >= {
        "git",
        "Codex",
        "工位目录不在临时目录",
    }


def test_delegate_returns_review_when_autofixes_fail(proj):
    failures = [
        {
            "write": {"app/new.py": f"VALUE = {i}\n"},
            "report": report(summary="尝试修复"),
        }
        for i in range(3)
    ]
    proj.script(failures)
    plan = {
        "goal": "添加模块",
        "brief": "新增 app/new.py",
        "scope": ["app/**"],
        "checks": [{"run": 'python -c "raise SystemExit(1)"', "expect": 0}],
    }
    p = cli(proj, "delegate", "-", input_text=json.dumps(plan, ensure_ascii=False))
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    review = (proj.root / "fusion/review.md").read_text(encoding="utf-8")
    assert "未通过" in review


def test_review_numstat_marks_out_of_scope_test_path(proj):
    proj.script(
        [
            {
                "write": {
                    "app/new.py": "VALUE = 1\n",
                    "tests/new_test.py": "VALUE = 2\n",
                },
                "report": report(status="done"),
            }
        ]
    )
    plan = {"goal": "添加模块", "brief": "新增文件", "scope": ["app/**"]}
    p = cli(proj, "delegate", "-", input_text=json.dumps(plan, ensure_ascii=False))
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    review = (proj.root / "fusion/review.md").read_text(encoding="utf-8")
    assert "- tests/new_test.py +1 -0 (范围外)" in review
    assert "files changed" not in review


def test_explore_prompt_is_plain_text_without_report_rules(proj):
    from fusion_core.prompts import explore_prompt

    prompt = explore_prompt("Q1: entry?", "# Decisions")
    assert "FIXED_RULES" not in prompt
    assert "最终回复只输出 JSON 报告" not in prompt
    for phrase in (
        "起止行",
        "不超过 15 行",
        "Q1~Q3",
        "约定和",
        "150 行",
        "不写实现方案",
    ):
        assert phrase in prompt


def test_blocked_review_uses_summary_and_next_step(proj):
    from fusion_core.aq import review_pack

    task = {
        "id": "T1",
        "plan": {"goal": "task"},
        "state": "blocked",
        "latest": None,
        "latest_report": {
            "status": "blocked",
            "summary": "需要 lead 回答",
            "questions": [],
            "choices": [],
            "problems": [],
        },
        "runs": ["r1"],
        "fix_attempts": 0,
    }
    review = review_pack(proj.root, task, {"candidates": {}}, 1)
    assert "状态:停下:需要 lead 回答" in review
    assert review.rstrip().endswith("下一步: fusion-core revise -(回答助手的问题)")


def test_accept_conflict_error_gives_revise_action(proj):
    proj.script(
        [{"write": {"app/new.py": "VALUE = 2\n"}, "report": report(status="done")}]
    )
    plan = {"goal": "add", "brief": "write app/new.py", "scope": ["app/**"]}
    delegated = cli(proj, "delegate", "-", input_text=json.dumps(plan))
    assert delegated.returncode == 0
    proj.write("app/new.py", "lead version\n")
    proj.commit("lead conflicting change")
    accepted = cli(proj, "accept")
    assert accepted.returncode == 2
    assert (
        "合并冲突,已退回审查:用 fusion-core revise 让助手在最新的主分支上解决"
        in accepted.stderr.decode("utf-8")
    )


def test_accept_dirty_lead_tree_error_gives_cleanup_action(proj):
    proj.script(
        [{"write": {"app/new.py": "VALUE = 2\n"}, "report": report(status="done")}]
    )
    plan = {"goal": "add", "brief": "write app/new.py", "scope": ["app/**"]}
    delegated = cli(proj, "delegate", "-", input_text=json.dumps(plan))
    assert delegated.returncode == 0
    proj.write("app/new.py", "uncommitted lead version\n")
    accepted = cli(proj, "accept")
    assert accepted.returncode == 2
    assert (
        "lead 工作目录有没提交的改动,快进会冲突:先提交或撤销,再运行 fusion-core accept"
        in accepted.stderr.decode("utf-8")
    )


def test_task_prompt_carries_v4_work_rules_and_project_commands():
    from fusion_core.prompts import changes_prompt, fix_prompt, task_prompt

    task = {"plan": {"goal": "加 truncate", "brief": "## 决定\n- 放在 textkit/truncate.py",
                     "checks": [{"run": "python -m unittest", "expect": 0}], "scope": []}}
    prompt = task_prompt(task, "# Decisions", None, ["python -m pytest -q", None])
    for phrase in (
        "核对通过的测试数量",  # 自己跑测试并核对数量
        "原有行为",  # 改造现有代码时保持原有行为
        "可以自己定",
        "blocking=true",
        "choices:没人要求、你自己定下的",
        "`python -m pytest -q`",  # 项目的测试命令进了提示
        "放在 textkit/truncate.py",
        "# Decisions",
    ):
        assert phrase in prompt, phrase
    # 续用同一个会话时只重申短规则,不重复整套做法
    for follow_up in (fix_prompt("失败输出", "# D"), changes_prompt("改一下", "# D")):
        assert "核对通过的测试数量" not in follow_up
        assert "最终回复只输出 JSON 报告" in follow_up
