"""Subprocess coverage for the public aq CLI and its artifacts."""

from __future__ import annotations

import json
import subprocess
import sys

from conftest import CORE, report
from fusion_core import cli as cli_module
from fusion_core import config, store
from fusion_core.util import CMD


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


def start_minor_task(proj, followup, initial=None, *, no_auto_fix=False):
    initial = initial or GREET_WITH_TASK_MARKER
    proj.script([
        {"write": {"app/greet.py": initial}, "report": report(status="done")},
        followup,
    ])
    if no_auto_fix:
        cfg = config.load(proj.root)
        cfg["max_fix_attempts"] = 0
        config.save_project(proj.root, cfg)
    started = cli(proj, "delegate", "-", input_text=json.dumps({
        "goal": "Update greeting", "brief": "Make a small change", "scope": ["app/**"]
    }))
    assert started.returncode == 0, started.stderr.decode("utf-8", "replace")


GREET_WITH_TASK_MARKER = 'def hello(name):\n    return f"Hello, {name}"\n\n# task marker\n'


def test_minor_fix_merges_and_prints_its_diff(proj):
    start_minor_task(proj, {"write": {"app/greet.py": GREET_WITH_TASK_MARKER.replace("# task marker", "# fixed marker")},
                            "report": report(status="done")})
    accepted = cli(proj, "accept", "--minor-fix", "Update the marker")
    assert accepted.returncode == 0, accepted.stderr.decode("utf-8", "replace")
    assert "## Minor fix diff" in accepted.stdout.decode("utf-8")
    assert "+# fixed marker" in accepted.stdout.decode("utf-8")
    prompt = proj.calls()[1]["prompt"].replace("\r\n", "\n")
    assert "Make exactly this fix: Update the marker" in prompt
    assert "Change only these files:\n- app/greet.py" in prompt
    assert "Change at most 20 lines total" in prompt
    from fusion_core.views import ledger
    assert "minor fix" in ledger(proj.state())
    assert proj.git("rev-parse", "main") == proj.git("rev-parse", "HEAD")
    assert "Task: T1" in proj.git("log", "-1", "--format=%B", "main")


def test_minor_fix_can_start_from_a_failing_candidate(proj):
    broken = GREET_WITH_TASK_MARKER.replace('return f"Hello, {name}"', 'return "broken"')
    start_minor_task(proj, {"write": {"app/greet.py": GREET_WITH_TASK_MARKER.replace("# task marker", "# fixed")},
                            "report": report(status="done")}, initial=broken, no_auto_fix=True)
    state = proj.state()
    assert not state["candidates"][state["tasks"]["T1"]["latest"]]["checks"]["passed"]
    fixed = cli(proj, "accept", "--minor-fix", "Restore the greeting")
    assert fixed.returncode == 0, fixed.stderr.decode("utf-8", "replace")
    assert "## Minor fix diff" in fixed.stdout.decode("utf-8")
    assert proj.git("rev-parse", "main") == proj.git("rev-parse", "HEAD", cwd=proj.root)


def test_minor_fix_extra_file_is_rejected_and_counts_as_round(proj):
    start_minor_task(proj, {"write": {"app/greet.py": GREET_WITH_TASK_MARKER,
                                      "outside.py": "value = 1\n"}, "report": report(status="done")})
    result = cli(proj, "accept", "--minor-fix", "Add an outside file")
    stdout = result.stdout.decode("utf-8")
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "# T1 Review" in stdout
    assert "Minor fix not merged: extra files: outside.py" in stdout
    assert proj.git("rev-parse", "main") == proj.git("rev-parse", "HEAD", cwd=proj.root)
    conn = store.connect(proj.root)
    try:
        from fusion_core.state import replay
        state = replay(store.read(conn))
    finally:
        conn.close()
    assert state["tasks"]["T1"]["state"] == "in_review"
    assert state["tasks"]["T1"]["change_rounds"] == 1


def test_minor_fix_over_twenty_lines_is_rejected(proj):
    long_update = GREET_WITH_TASK_MARKER + "".join(f"# added {i}\n" for i in range(21))
    start_minor_task(proj, {"write": {"app/greet.py": long_update}, "report": report(status="done")})
    result = cli(proj, "accept", "--minor-fix", "Add comments")
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "changed 21 lines; limit is 20" in result.stdout.decode("utf-8")
    assert proj.git("rev-parse", "main") == proj.git("rev-parse", "HEAD", cwd=proj.root)


def test_minor_fix_failed_check_names_the_check(proj):
    broken = GREET_WITH_TASK_MARKER.replace('return f"Hello, {name}"', 'return "broken"')
    start_minor_task(proj, {"write": {"app/greet.py": broken}, "report": report(status="done")})
    result = cli(proj, "accept", "--minor-fix", "Break the greeting")
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "checks failed: Tests" in result.stdout.decode("utf-8")


def test_minor_fix_without_a_candidate_is_rejected(proj):
    start_minor_task(proj, {"report": report(status="done")})
    result = cli(proj, "accept", "--minor-fix", "Make no edits")
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "Minor fix not merged: minor-fix run produced no candidate" in result.stdout.decode("utf-8")
    assert proj.state()["tasks"]["T1"]["change_rounds"] == 1


def test_minor_fix_argument_validation(proj):
    empty = cli(proj, "accept", "--minor-fix", "")
    both = cli(proj, "accept", "--minor-fix", "x", "--waive", "y")
    assert empty.returncode != 0 and "--minor-fix must be non-empty" in empty.stderr.decode("utf-8")
    assert both.returncode != 0 and "--minor-fix cannot be combined with --waive" in both.stderr.decode("utf-8")


def test_minor_fix_wait_continues_after_foreground_timeout(proj):
    start_minor_task(proj, {"sleep": 1, "write": {"app/greet.py": GREET_WITH_TASK_MARKER.replace("# task marker", "# waited")},
                            "report": report(status="done")})
    cfg = config.load(proj.root)
    cfg["wait_minutes"] = 0.002
    config.save_project(proj.root, cfg)
    pending = cli(proj, "accept", "--minor-fix", "Change the marker")
    assert pending.returncode == 3, pending.stderr.decode("utf-8", "replace")
    waited = cli(proj, "wait", "--task", "T1")
    assert waited.returncode == 3, waited.stderr.decode("utf-8", "replace")
    for _ in range(20):
        waited = cli(proj, "wait", "--task", "T1")
        if waited.returncode == 0:
            break
        assert waited.returncode == 3, waited.stderr.decode("utf-8", "replace")
    assert waited.returncode == 0, waited.stderr.decode("utf-8", "replace")
    assert "## Minor fix diff" in waited.stdout.decode("utf-8")
    assert "+# waited" in waited.stdout.decode("utf-8")


def test_delegate_and_wait_both_obey_wait_minutes(proj):
    proj.script([{"sleep": 1, "write": {"app/greet.py": GREET_WITH_TASK_MARKER},
                  "report": report(status="done")}])
    cfg = config.load(proj.root)
    cfg["wait_minutes"] = 0.002
    config.save_project(proj.root, cfg)
    delegated = cli(proj, "delegate", "-", input_text=json.dumps({
        "goal": "Update greeting", "brief": "Make a small change", "scope": ["app/**"]
    }))
    assert delegated.returncode == 3, delegated.stderr.decode("utf-8", "replace")
    first_wait = cli(proj, "wait", "--task", "T1")
    assert first_wait.returncode == 3, first_wait.stderr.decode("utf-8", "replace")
    assert "review pack" not in first_wait.stdout.decode("utf-8").lower()
    for _ in range(20):
        later_wait = cli(proj, "wait", "--task", "T1")
        if later_wait.returncode == 0:
            break
        assert later_wait.returncode == 3, later_wait.stderr.decode("utf-8", "replace")
    assert later_wait.returncode == 0, later_wait.stderr.decode("utf-8", "replace")
    assert "## Checks" in later_wait.stdout.decode("utf-8")


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
    assert artifact.splitlines()[0] == "Task ID: T1"
    assert artifact.splitlines()[1].startswith("Assistant session ID: ")
    assert not (proj.root / "fusion/explore.md").exists()
    assert not (proj.root / "fusion/review.md").exists()
    assert p.stdout.decode("utf-8").splitlines()[0] == "Result: fusion/tasks/T1/explore.md"
    assert "plan as Markdown" in p.stdout.decode("utf-8")
    stdout = p.stdout.decode("utf-8")
    assert "## Assistant response" in stdout and "代码在 app/greet.py。" in stdout
    assert stdout.count("Next:") == 1
    gitignore = (proj.root / "fusion/.gitignore").read_text(encoding="utf-8")
    assert "explore.md" not in gitignore and "review.md" not in gitignore


def test_wait_limit_releases_lease_and_resumes_explore_and_delegate(proj):
    cfg = config.load(proj.root)
    cfg["wait_minutes"] = 0.02
    config.save_project(proj.root, {key: value for key, value in cfg.items() if key != "local"})
    proj.script([{"sleep": 1.2, "text": "延迟后的探索结论"},
                 {"sleep": 1.2, "write": {"app/new.py": "VALUE = 2\n"},
                  "report": report(summary="延迟实现完成")}])
    p = cli(proj, "explore", "-", input_text="任务原话")
    assert p.returncode == 3
    output = p.stdout.decode("utf-8")
    assert "Sidekick still working" in output and 'fusion-core.py" wait' in output
    assert "Next:" not in output
    conn = store.connect(proj.root)
    try:
        assert store.take_lease(conn, "test-holder")
        store.release_lease(conn, "test-holder")
    finally:
        conn.close()
    assert proj.task()["state"] == "exploring"
    p = cli(proj, "wait")
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    output = p.stdout.decode("utf-8")
    assert "延迟后的探索结论" in output and "## Assistant response" in output
    assert (proj.root / "fusion/tasks/T1/explore.md").exists()
    assert not (proj.root / "fusion/explore.md").exists()
    assert output.count("Next:") == 1

    plan = {"goal": "加模块", "brief": "改代码", "scope": ["app/**"]}
    p = cli(proj, "delegate", "-", input_text=json.dumps(plan, ensure_ascii=False))
    assert p.returncode == 3
    assert "Sidekick still working" in p.stdout.decode("utf-8")
    p = cli(proj, "wait", "--task", "T1")
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    output = p.stdout.decode("utf-8")
    assert "## Checks" in output and "## Sidekick" in output
    assert output.count("Next:") == 1


def test_wait_with_no_run_reports_status(proj):
    p = cli(proj, "wait")
    assert p.returncode == 0
    assert "Nothing to wait for" in p.stdout.decode("utf-8")


def test_wait_picks_up_integration_without_active_run(proj):
    from fusion_core.commands import Ctx, cmd_accept

    proj.script([{"write": {"app/new.py": "VALUE = 2\n"}, "report": report()}])
    plan = {"goal": "加模块", "brief": "改代码", "scope": ["app/**"]}
    delegated = cli(proj, "delegate", "-", input_text=json.dumps(plan, ensure_ascii=False))
    assert delegated.returncode == 0, delegated.stderr.decode("utf-8", "replace")
    ctx = Ctx(proj.root)
    try:
        cmd_accept(ctx)
    finally:
        ctx.close()
    task = proj.state()["tasks"]["T1"]
    assert task["state"] == "integrating" and task["active_run"] is None
    waited = cli(proj, "wait")
    assert waited.returncode == 0, waited.stderr.decode("utf-8", "replace")
    assert "Commit:" in waited.stdout.decode("utf-8")


def test_old_test_failure_is_not_counted_or_shown_as_check(proj):
    candidate_test = (
        "import unittest\nfrom app.greet import hello\n\n\nclass T(unittest.TestCase):\n"
        '    def test_hello(self):\n        self.assertEqual(hello("A"), "Hi, A")\n'
    )
    proj.script([{
        "write": {
            "app/greet.py": 'def hello(name):\n    return f"Hi, {name}"\n',
            "tests/test_greet.py": candidate_test,
        },
        "report": report(),
    }])
    plan = {"goal": "Change greeting", "brief": "Update greeting behavior and test.",
            "scope": ["app/greet.py", "tests/test_greet.py"]}
    result = cli(proj, "delegate", "-", input_text=json.dumps(plan))
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    stdout = result.stdout.decode("utf-8")
    assert "Checks: 1/1 passed" in stdout
    candidate = proj.state()["candidates"][proj.task()["latest"]]
    assert candidate["checks"]["passed"]
    old_test = next(row for row in candidate["checks"]["results"] if row.get("restored") is not None)
    assert not old_test["passed"]
    review = (proj.root / "fusion/tasks/T1/review-1.md").read_text(encoding="utf-8")
    checks = review.split("## Checks\n", 1)[1].split("\n## ", 1)[0]
    assert "Old tests on new code" not in checks and "FAIL" not in checks
    assert "Old test failed on new code: tests/test_greet.py::test_hello" in review
    next_step = review.rsplit("Next: ", 1)[1]
    assert f'{CMD} accept' in next_step and "--waive" not in next_step
    accepted = cli(proj, "accept")
    assert accepted.returncode == 0, accepted.stderr.decode("utf-8", "replace")


def test_delegate_truncated_stdout_points_to_written_pack(proj):
    proj.script([{"write": {"app/new.py": "VALUE = 2\n"},
                  "report": report(summary="S" * 20500)}])
    plan = {"goal": "Add module", "brief": "Write app/new.py", "scope": ["app/**"]}
    result = cli(proj, "delegate", "-", input_text=json.dumps(plan))
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    output = result.stdout.decode("utf-8")
    pack_path = next(line.removeprefix("Full pack: ") for line in output.splitlines()
                     if line.startswith("Full pack: "))
    assert (proj.root / pack_path).is_file()


def test_review_stdout_drops_diff_and_met_list_before_truncating(monkeypatch):
    from fusion_core.cli import _review_stdout

    text = ("## Sidekick\n" + "x" * 220 + "\nBrief check: met - met item\n"
            + "```diff\n" + "diff line\n" * 250 + "```\n")
    monkeypatch.setattr(cli_module, "STDOUT_CHARS", 200)
    output = _review_stdout(text, pack_path="fusion/tasks/T1/review-1.md")
    assert len(output) <= 200
    assert "```diff" not in output and "Brief check: met -" not in output
    assert output.endswith("Full pack: fusion/tasks/T1/review-1.md")

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
    assert (proj.root / "fusion/tasks/T1/review-1.md").exists()
    calls = proj.calls()
    assert calls[0]["resume"] is False and calls[1]["resume"] is True
    assert "Full text of fusion/decisions.md" in calls[1]["prompt"]


def test_delegate_markdown_plan(proj):
    proj.script([{"text": "探索结论。"}, {"report": report(summary="完成", status="done")}])
    p = cli(proj, "explore", "-", input_text="任务原话")
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    md = "# 加模块\n\n## 目标\n加 app/new.py\n\n## scope\n- app/**\n"
    p = cli(proj, "delegate", "-", input_text=md)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    state = proj.state()
    expected = {"goal": "加模块", "brief": "## 目标\n加 app/new.py", "scope": ["app/**"]}
    from fusion_core import aq

    assert state["tasks"]["T1"]["plan"] == aq.parse_plan(json.dumps(expected, ensure_ascii=False))
    prompt = (proj.root / "fusion/runs/r2/prompt.txt").read_text(encoding="utf-8")
    assert "## Goal\n加模块" in prompt
    assert "加 app/new.py" in prompt


def test_codex_stdin_is_prompt_file_for_explore_and_resume(proj):
    proj.script([{"text": "探索完成"}, {"report": report(summary="完成")}])
    p = cli(proj, "explore", "-", input_text="管道任务文字")
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    plan = {"goal": "实现", "brief": "## 目标\n完成任务", "scope": ["app/**"]}
    p = cli(proj, "delegate", "-", input_text=json.dumps(plan, ensure_ascii=False))
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")

    calls = proj.calls()
    assert len(calls) == 2 and calls[0]["resume"] is False and calls[1]["resume"] is True
    for run_id, call in zip(("r1", "r2"), calls):
        prompt_file = proj.root / "fusion" / "runs" / run_id / "prompt.txt"
        assert call["stdin_is_file"] is True
        assert call["prompt"] == prompt_file.read_bytes().decode("utf-8")
        assert call["args"][-1] == "-"


def test_plan_validation_and_regex_expect(proj):
    for bad, expected in [
        ({"brief": "正文"}, "goal must be a non-empty single line of text"),
        (
            {"goal": "x", "brief": "正文", "checks": [{"run": "echo"}, {"run": ""}]},
            "checks[1].run",
        ),
        ({"goal": "x", "brief": "正文", "extra": True}, "unexpected: extra"),
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
    assert p.returncode == 2 and "3 revision rounds" in p.stderr.decode("utf-8", "replace")
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
    assert p.returncode == 1 and "Violations were found" in p.stderr.decode("utf-8")


def test_review_pack_sections_scope_and_stdout(proj):
    proj.script([{
        "write": {"app/new.py": "VALUE = 2\n", "outside.txt": "bad\n"},
        "report": report(status="done", choices=[{"what": "value 2", "why": "matches the existing value"}]),
    }])
    p = cli(proj, "delegate", "-", input_text=json.dumps(
        {"goal": "add module", "brief": "change code", "scope": ["app/**"]}
    ))
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    text = (proj.root / "fusion/tasks/T1/review-1.md").read_text(encoding="utf-8")
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert headings == ["## Checks", "## Engine scan", "## Sidekick", "## Changes"]
    assert "outside.txt" in text and "Out of scope: outside.txt" in text
    assert "Choice: value 2 (why: matches the existing value)" in text
    stdout = p.stdout.decode("utf-8")
    assert "fusion/tasks/T1/review-1.md" in stdout
    assert "## Checks" in stdout and "## Sidekick" in stdout
    assert "```diff" in stdout and stdout.count("Next:") == 1
    assert "Diff omitted" not in text and "workstation path" not in text
    assert "Auto-fix attempts" not in text

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
    text = (proj.root / "fusion/tasks/T1/review-1.md").read_text(encoding="utf-8")
    assert "## Violations" not in text
    assert "```diff" not in text and "app/new.py" in text
    assert "Diff omitted (" in text and "git diff " in text
    assert "workstation path" not in text and "Auto-fix attempts" not in text


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
    assert "A run was already in progress; this input was not used." in p.stdout.decode("utf-8")
    assert len(proj.calls()) == 1
    artifact = (proj.root / "fusion" / "tasks" / out["task"] / "explore.md").read_text(
        encoding="utf-8"
    )
    assert "第一次原话" in artifact and "不应使用的新输入" not in artifact


def test_on_restores_config_and_decision_defaults(proj):
    p = cli(proj, "on", "--test", "python -m unittest", "--lint", "ruff check .")
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    assert "Fusion is already enabled" in p.stdout.decode("utf-8")
    cfg = json.loads((proj.root / "fusion" / "config.json").read_text(encoding="utf-8"))
    assert cfg["test"] == "python -m unittest" and cfg["lint"] == "ruff check ."
    decisions = (proj.root / "fusion" / "decisions.md").read_text(encoding="utf-8")
    assert decisions.splitlines() == [
        "# Design decisions",
        "> lead edits this file directly. The engine includes the full text in every task handoff. Record only decisions that apply to every task.",
    ]


def test_preflight_has_original_check_names(proj):
    p = cli(proj, "preflight")
    assert p.returncode == 0
    preflight = json.loads(p.stdout)
    assert {row["check"] for row in preflight["checks"]} >= {
        "git",
        "Codex",
        "Station directory is outside the temp directory",
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
    review = (proj.root / "fusion/tasks/T1/review-1.md").read_text(encoding="utf-8")
    assert "FAIL (exit 1)" in review


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
    review = (proj.root / "fusion/tasks/T1/review-1.md").read_text(encoding="utf-8")
    assert "- tests/new_test.py +1 -0 (out of scope)" in review
    assert "files changed" not in review


def test_explore_prompt_is_plain_text_without_report_rules(proj):
    from fusion_core.prompts import explore_prompt

    prompt = explore_prompt("Q1: entry?", "# Decisions")
    assert "FIXED_RULES" not in prompt
    assert "final report" not in prompt
    for phrase in (
        "Do not modify any files",
        "quote no more than 15 source lines",
        "Q1~Q3",
        "conventions and pitfalls",
        "150 lines or fewer",
        "Do not write an implementation plan",
        "## Draft (mechanical only)",
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
    assert "Status: blocked" in review and "Summary: 需要 lead 回答" in review
    assert review.rstrip().endswith(f"Next: {CMD} revise - (answer the sidekick's questions)")


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
        f"Merge conflict; returned to review. Use {CMD} revise to have the assistant resolve it on the latest base branch"
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
        f"Lead working tree has uncommitted changes; fast-forward would conflict. Commit or discard them, then run {CMD} accept"
        in accepted.stderr.decode("utf-8")
    )


def test_task_prompt_carries_v4_work_rules_and_project_commands():
    from fusion_core.prompts import changes_prompt, fix_prompt, task_prompt

    task = {"plan": {"goal": "加 truncate", "brief": "## 决定\n- 放在 textkit/truncate.py",
                     "checks": [{"run": "python -m unittest", "expect": 0}], "scope": []}}
    prompt = task_prompt(task, "# Decisions", None, ["python -m pytest -q", None])
    for phrase in (
        "Verify the test count",  # Run tests and verify the count.
        "existing behavior",  # Preserve existing behavior when changing code.
        "You may choose",
        "blocking=true",
        "choices: decisions you made that were not specified",
        "`python -m pytest -q`",  # The project test command is included in the prompt.
        "放在 textkit/truncate.py",
        "# Decisions",
    ):
        assert phrase in prompt, phrase
    # When resuming the same session, repeat only the short rules, not the full workflow.
    for follow_up in (fix_prompt("失败输出", "# D"), changes_prompt("改一下", "# D")):
        assert "Verify the test count" not in follow_up
        assert "Return only a JSON report" in follow_up
