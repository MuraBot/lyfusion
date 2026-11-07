"""Subprocess coverage for the public aq CLI and its artifacts."""
from __future__ import annotations

import json
import subprocess
import sys

from conftest import CORE, report


def cli(proj, *args, input_text=None):
    return subprocess.run([sys.executable, str(CORE / "fusion-core.py"), "--project", str(proj.root), *args],
                          input=None if input_text is None else input_text.encode("utf-8"),
                          capture_output=True, timeout=180)


def test_explore_stdin_utf8_writes_artifacts(proj):
    proj.script([{"text": "代码在 app/greet.py。"}])
    raw = "任务原话：修改问候。\nQ1：入口在哪？\n".encode("utf-8-sig")
    p = subprocess.run([sys.executable, str(CORE / "fusion-core.py"), "--project", str(proj.root), "explore", "-"],
                       input=raw, capture_output=True, timeout=180)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    artifact = (proj.root / "fusion" / "explore.md").read_text(encoding="utf-8")
    assert "任务原话：修改问候。" in artifact and "代码在 app/greet.py。" in artifact
    assert (proj.root / "fusion/tasks/explore/explore.md").exists()


def test_delegate_four_field_plan_and_resumes_explore(proj):
    proj.script([{"text": "探索结论。"},
                 {"write": {"app/new.py": "VALUE = 1\n"}, "report": report(summary="完成", status="done") }])
    p = cli(proj, "explore", "-", input_text="任务原话\nQ1：查入口")
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    plan = {"goal": "加模块", "brief": "## 目标\n加 app/new.py", "scope": ["app/**"]}
    p = cli(proj, "delegate", "-", input_text=json.dumps(plan, ensure_ascii=False))
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    assert (proj.root / "fusion/review.md").exists()
    calls = proj.calls()
    assert calls[0]["resume"] is False and calls[1]["resume"] is True
    assert "跨任务设计决定" in calls[1]["prompt"]
    assert (proj.root / "fusion/decisions.md").read_text(encoding="utf-8")


def test_plan_validation_and_regex_expect(proj):
    for bad, expected in [
        ({"brief": "正文"}, "goal 要是非空的一行文字"),
        ({"goal": "x", "brief": "正文", "checks": [{"run": "echo"}, {"run": ""}]}, "checks[1].run"),
        ({"goal": "x", "brief": "正文", "extra": True}, "只允许字段"),
    ]:
        p = cli(proj, "delegate", "-", input_text=json.dumps(bad))
        assert p.returncode == 1 and expected in p.stderr.decode("utf-8")
    assert not (proj.root / "fusion.db").exists() or proj.state()["next_task"] == 1


def test_revise_reuses_session_and_fourth_round_stops(proj):
    steps = [{"write": {"app/new.py": f"VALUE = {i}\n"}, "report": report(status="done")} for i in range(5)]
    proj.script(steps)
    p = cli(proj, "delegate", "-", input_text=json.dumps({"goal": "加模块", "brief": "改代码", "scope": ["app/**"]}))
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    for i in range(3):
        p = cli(proj, "revise", "-", input_text=f"第 {i + 1} 轮修改")
        assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    p = cli(proj, "revise", "-", input_text="第 4 轮")
    assert p.returncode == 2 and "3 轮" in p.stderr.decode("utf-8", "replace")
    assert "review-4.md" in {p.name for p in (proj.root / "fusion/tasks/T1").iterdir()}
    assert all(call["resume"] for call in proj.calls()[1:])


def test_accept_squashes_and_fast_forwards(proj):
    proj.script([{"write": {"app/new.py": "VALUE = 2\n"}, "report": report(status="done")}])
    p = cli(proj, "delegate", "-", input_text=json.dumps({"goal": "加模块", "brief": "改代码", "scope": ["app/**"]}))
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    p = cli(proj, "accept")
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    task_log = proj.git("log", "--format=%B", "--grep", "Task: T1", "main")
    assert "Candidate:" in task_log
    assert len(proj.git("log", "--format=%H", "--grep", "Task: T1", "main").split()) == 1


def test_accept_refuses_forbidden_command_without_waive(proj):
    proj.script([{"write": {"app/new.py": "VALUE = 2\n"}, "commands": [{"command": "git commit -m bad"}],
                 "report": report(status="done")}])
    p = cli(proj, "delegate", "-", input_text=json.dumps({"goal": "加模块", "brief": "改代码", "scope": ["app/**"]}))
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    p = cli(proj, "accept")
    assert p.returncode == 1 and "违规" in p.stderr.decode("utf-8")


def test_review_has_four_sections_and_scope_marking(proj):
    proj.script([{"write": {"app/new.py": "VALUE = 2\n", "outside.txt": "bad\n"},
                 "report": report(status="done", choices=[{"what": "value 2"}])}])
    p = cli(proj, "delegate", "-", input_text=json.dumps({"goal": "加模块", "brief": "改代码", "scope": ["app/**"]}))
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    text = (proj.root / "fusion/review.md").read_text(encoding="utf-8")
    headings = [line for line in text.splitlines() if line.startswith("# ")]
    assert headings == ["# 检查", "# 助手的问题和自定的选择", "# 改动"]
    assert "outside.txt" in text and "范围外" in text


def test_review_omits_violation_section_and_large_diff(proj):
    huge = "".join(f"LINE_{i} = {i}\n" for i in range(450))
    proj.script([{"write": {"app/new.py": huge}, "report": report(status="done")}])
    p = cli(proj, "delegate", "-", input_text=json.dumps({"goal": "加模块", "brief": "改代码", "scope": ["app/**"]}))
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    text = (proj.root / "fusion/review.md").read_text(encoding="utf-8")
    assert "# 违规" not in text and "```diff" not in text and "app/new.py" in text
