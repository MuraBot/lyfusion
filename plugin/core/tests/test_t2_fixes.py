"""T2 regressions for report, wait, ledger, integration, and review output."""
from __future__ import annotations

import json

from fusion_core import cli, codex, gitops, views
from fusion_core.aq import review_pack
from fusion_core.commands import cmd_accept, cmd_delegate
from fusion_core.util import CMD
from test_flow import GOOD, plan_farewell


def test_report_schema_is_strict_for_every_object():
    schema = json.loads(codex.SCHEMA.read_text(encoding="utf-8"))

    def inspect(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert set(node.get("required", [])) == set(node.get("properties", {}))
            for value in node.values():
                inspect(value)
        elif isinstance(node, list):
            for value in node:
                inspect(value)

    inspect(schema)
    q = schema["properties"]["questions"]["items"]
    assert q["required"] == ["text", "blocking"]
    choice = schema["properties"]["choices"]["items"]
    assert choice["required"] == ["what", "why"]


def test_wait_ignores_stalled_signal_that_predates_this_wait(monkeypatch):
    old_signal = {"kind": "stalled", "detail": "old stalled"}
    running = {"tasks": {"T1": {"state": "running", "signals": [old_signal]}}}
    accepted = {"tasks": {"T1": {"state": "accepted", "signals": [old_signal]}}}

    class FakeSupervisor:
        def __init__(self, *_args, **_kwargs):
            self.holder = "test"
            self.conn = type("Conn", (), {"close": lambda _self: None})()
            self.states = iter([running, running, accepted])

        def state(self):
            return next(self.states)

        def tick(self):
            pass

    monkeypatch.setattr(cli, "Supervisor", FakeSupervisor)
    monkeypatch.setattr(cli.store, "take_lease", lambda *_: True)
    monkeypatch.setattr(cli.store, "release_lease", lambda *_: None)
    result = cli._wait(__import__("pathlib").Path("."), "T1")
    assert result["tasks"]["T1"]["state"] == "accepted"


def test_ledger_shows_usage_in_millions_and_each_run_model_settings():
    state = {
        "tasks": {"T1": {"id": "T1", "state": "in_review", "plan": {"goal": "task"},
                          "fix_attempts": 0, "change_rounds": 0, "runs": ["r1", "r2"]}},
        "runs": {"r1": {"model": "gpt-6-luna", "effort": "high", "fast": False},
                 "r2": {"model": "haiku-5.5", "effort": None, "fast": True}},
        "usage": {"T1": {"lead": {"input": 1_000_000, "cache_read": 200_000, "output": 300_000},
                          "sidekick": {"input": 2_000_000, "cache_read": 500_000, "cache_write": 100_000, "output": 400_000}}},
    }
    ledger = views.ledger(state, "T1")
    assert "1.000 / 0.200 / 0.300" in ledger
    assert "2.000 / 0.600 / 0.400" in ledger
    assert "gpt-6-luna / high / off" in ledger
    assert "haiku-5.5 / 默认 / on" in ledger


def test_run_event_records_model_effort_and_fast(proj):
    from test_flow import setup_task
    setup_task(proj)
    proj.script([GOOD])
    proj.do(cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    run = proj.state()["runs"]["r1"]
    assert run["model"] == "gpt-6-luna"
    assert run["effort"] == "high"
    assert run["fast"] is False


def test_question_asked_persists_only_text_and_blocking(proj):
    from test_flow import setup_task
    setup_task(proj)
    q = {"text": "Which option?", "blocking": True, "options": ["a"], "recommendation": "a"}
    proj.script([{"report": {**GOOD["report"], "questions": [q]}}])
    proj.do(cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    event = next(e for e in proj.events("question_asked") if e["task"] == "T1")
    assert set(event["data"]) == {"qid", "run", "text", "blocking"}
    assert proj.task()["questions"][0]["text"] == "Which option?"


def test_conflict_detail_recommends_revise_on_latest_base(proj, monkeypatch):
    from test_flow import setup_task
    setup_task(proj)
    proj.script([GOOD])
    proj.do(cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    monkeypatch.setattr(gitops, "merge_base_into", lambda *_args, **_kwargs: (False, "conflict"))
    proj.do(cmd_accept, "T1")
    proj.drain()
    detail = proj.task()["integration"]["detail"]
    assert f"用 {CMD} revise 让助手在最新的主分支上解决" in detail
    assert "接" + "管" not in detail and "take" + "over" not in detail


def test_blocked_review_has_one_status_line_and_no_duplicate_summary(proj):
    task = {"id": "T1", "plan": {"goal": "task"}, "state": "blocked", "latest": None,
            "latest_report": {"status": "blocked", "summary": "需要回答", "questions": [], "choices": [], "problems": []},
            "runs": ["r1"], "fix_attempts": 0}
    text = review_pack(proj.root, task, {"candidates": {}}, 1)
    section = text.split("## 助手的问题和自定的选择", 1)[1].split("## 改动", 1)[0]
    assert section.count("状态:") == 1
    assert "状态:停下:需要回答" in section
    assert "摘要:" not in section


def test_done_review_keeps_status_and_summary_lines(proj):
    task = {"id": "T1", "plan": {"goal": "task"}, "state": "in_review", "latest": None,
            "latest_report": {"status": "done", "summary": "完成", "questions": [], "choices": [], "problems": []},
            "runs": ["r1"], "fix_attempts": 0}
    text = review_pack(proj.root, task, {"candidates": {}}, 1)
    assert "状态:做完\n摘要:完成" in text
