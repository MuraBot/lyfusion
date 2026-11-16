from __future__ import annotations

import io
import json
from types import SimpleNamespace

from fusion_core import cli, config, store, views


def test_panel_emits_only_panel_fields_and_current_settings(proj, capsys):
    local = config.load(proj.root)["local"]
    local["sidekick"]["models"]["gpt-6-luna"]["compact"] = 250000
    local["sidekick"]["models"]["custom-model"] = {"effort": "low"}
    config.save_local(proj.root, local)

    assert cli.main(["--project", str(proj.root), "config", "panel"]) == 0
    raw = capsys.readouterr().out
    assert len(raw.splitlines()) == 1
    panel = json.loads(raw)
    assert panel == {
        "schema_version": 2, "project": True, "enabled": True,
        "model": "gpt-6-luna", "models": ["gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra", "custom-model"],
        "effort": "high", "efforts": config.model_efforts("gpt-6-luna"), "fast": False,
        "fast_models": ["gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra"],
        "model_names": {"gpt-6.1-sol": "GPT-6.1-Sol", "gpt-6-luna": "GPT-6-Luna",
                        "gpt-6-astra": "GPT-6-Astra", "custom-model": "custom-model"},
        "compact": 250000, "compacts": [250000, 262144, 400000, 600000, 800000],
        "context_ratio": 0.6, "switch_at": 150000,
        "handoff": {"mode": "write", "tokens": 200000, "dir": "fusion/handoffs", "modes": ["clear", "write", "off"]},
        "warnings": [],
    }
    assert "env" not in panel and "codex" not in panel


def test_panel_reports_project_not_initialized(proj, capsys):
    (proj.root / "fusion" / "config.json").unlink()
    assert cli.main(["--project", str(proj.root), "config", "panel"]) == 0
    assert capsys.readouterr().out == '{"schema_version": 2, "project": false}\n'


def test_config_enabled_only_changes_switch_and_initializes_on_artifacts(proj, capsys):
    assert cli.main(["--project", str(proj.root), "config", "enabled", "off"]) == 0
    assert config.load(proj.root)["local"]["enabled"] is False
    assert (proj.root / "fusion" / "fusion.db").exists()
    assert (proj.root / "fusion" / "decisions.md").exists()
    assert capsys.readouterr().out == "Fusion disabled\n"

    assert cli.main(["--project", str(proj.root), "config", "enabled", "on"]) == 0
    assert config.load(proj.root)["local"]["enabled"] is True
    assert capsys.readouterr().out == "Fusion is enabled\n"
    assert cli.main(["--project", str(proj.root), "config", "enabled", "maybe"]) == 1


def _append_task(conn, task_id):
    with store.transaction(conn):
        store.append(conn, [{"type": "task_created", "task": task_id,
                             "data": {"plan": {"goal": task_id}, "state": "in_review"}}], "test")


def _lead_usage(proj, monkeypatch, capsys, payload, at, *args):
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(
        buffer=io.BytesIO(json.dumps(payload).encode("utf-8"))))
    return cli.main(["--project", str(proj.root), "lead-usage", "--at", at, *args, "-"])


def test_lead_usage_snapshots_pair_pre_and_post_create_explore_and_use_latest(proj, monkeypatch, capsys):
    session = 1763100000000
    assert _lead_usage(proj, monkeypatch, capsys,
                       {"startedAt": session, "cost": {"usd": 5.0}}, "explore") == 0
    capsys.readouterr()
    conn = store.connect(proj.root)
    try:
        _append_task(conn, "T1")
    finally:
        conn.close()
    for cost in (5.4, 5.6):
        assert _lead_usage(proj, monkeypatch, capsys,
                           {"startedAt": session, "cost": {"usd": cost}}, "explore") == 0
        capsys.readouterr()
    accepted = {
        "startedAt": session,
        "context": {"tokens": 150000, "window": 434000, "percent": 35},
        "rateLimits": [
            {"kind": "five_hour", "percentUsed": 84, "resetsAt": "later"},
            {"kind": "seven_day", "percentUsed": 12, "resetsAt": "next week"},
        ],
        "cost": {"usd": 6.0},
    }
    assert _lead_usage(proj, monkeypatch, capsys, accepted, "accept", "--task", "T1") == 0
    capsys.readouterr()
    accepted["cost"]["usd"] = 6.1
    assert _lead_usage(proj, monkeypatch, capsys, accepted, "accept", "--task", "T1") == 0
    capsys.readouterr()
    state = proj.state()
    explores = [event for event in state["lead_usage_events"] if event["data"]["at"] == "explore"]
    assert [event["task"] for event in explores] == [None, None, None]
    assert all("at" in event["data"] for event in state["lead_usage_events"])
    assert state["lead_usage"]["T1"]["data"]["cost_usd"] == 6.1
    rendered = views.ledger(state, "T1")
    assert "This task $0.50 · At acceptance Context 150k/434k · 5h 84% · 7d 12%" in rendered


def test_lead_usage_cross_session_has_no_guessed_cost_delta(proj, monkeypatch, capsys):
    assert _lead_usage(proj, monkeypatch, capsys,
                       {"startedAt": 1763100000000, "cost": {"usd": 8.0}}, "explore") == 0
    capsys.readouterr()
    conn = store.connect(proj.root)
    try:
        _append_task(conn, "T1")
    finally:
        conn.close()
    assert _lead_usage(proj, monkeypatch, capsys,
                       {"startedAt": 1763100000001, "cost": {"usd": 9.0}},
                       "accept", "--task", "T1") == 0
    capsys.readouterr()
    assert "This task -" in views.ledger(proj.state(), "T1")


def test_lead_usage_tool_call_delta_and_invalid_counts(proj, monkeypatch, capsys):
    session = 1763100000000
    assert _lead_usage(proj, monkeypatch, capsys,
                       {"startedAt": session, "toolCalls": 3, "requests": 2}, "explore") == 0
    capsys.readouterr()
    conn = store.connect(proj.root)
    try:
        _append_task(conn, "T1")
    finally:
        conn.close()
    accepted = {"startedAt": session, "toolCalls": 10, "requests": 5}
    assert _lead_usage(proj, monkeypatch, capsys, accepted, "accept", "--task", "T1") == 0
    capsys.readouterr()
    assert "7 / 3" in views.ledger(proj.state(), "T1")
    accepted.update(toolCalls=-1, requests=True)
    assert _lead_usage(proj, monkeypatch, capsys, accepted, "accept", "--task", "T1") == 0
    capsys.readouterr()
    assert "- / -" in views.ledger(proj.state(), "T1")


def test_lead_usage_default_task_and_invalid_input_leave_no_event(proj, monkeypatch, capsys):
    conn = store.connect(proj.root)
    try:
        _append_task(conn, "T1")
    finally:
        conn.close()
    assert _lead_usage(proj, monkeypatch, capsys, {"context": {"tokens": 1}}, "accept") == 0
    assert capsys.readouterr().out == "Recorded lead usage for T1\n"
    before = len(proj.events("lead_usage"))
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"[]")))
    assert cli.main(["--project", str(proj.root), "lead-usage", "--at", "accept", "-"]) == 1
    assert "JSON object" in capsys.readouterr().err
    assert len(proj.events("lead_usage")) == before


def test_lead_usage_requires_review_task_with_exit_two(proj, monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"{}")))
    assert cli.main(["--project", str(proj.root), "lead-usage", "--at", "accept", "-"]) == 2
    assert "No task found" in capsys.readouterr().err


def test_lead_usage_invalid_json_has_specific_error(proj, monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"{bad")))
    assert cli.main(["--project", str(proj.root), "lead-usage", "--at", "explore", "-"]) == 1
    assert capsys.readouterr().err.strip() == "lead-usage input is not valid JSON"


def test_lead_usage_rejects_unknown_at_value(proj, monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"{}")))
    assert cli.main(["--project", str(proj.root), "lead-usage", "--at", "revise", "-"]) == 1
    assert "must be explore or accept" in capsys.readouterr().err

