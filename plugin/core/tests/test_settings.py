"""T2: model-scoped Codex settings and retained configuration behavior."""
from __future__ import annotations

import json

from fusion_core import config, views
from fusion_core.cli import main
from fusion_core.codex import build_args
from test_flow import GOOD, plan_farewell, setup_task


def test_legacy_flat_settings_migrate_to_current_model(proj):
    local = config.load(proj.root)["local"]
    local["sidekick"] = {"model": "gpt-6-luna", "effort": "medium", "fast": True}
    config.save_local(proj.root, local)

    loaded = config.load(proj.root)["local"]["sidekick"]
    assert loaded == {"model": "gpt-6-luna", "models": {"gpt-6-luna": {"effort": "medium", "fast": True}}}
    assert "effort" not in loaded and "fast" not in loaded


def test_effort_and_fast_are_isolated_by_model(proj, capsys):
    def command(*args):
        assert main(["--project", str(proj.root), "config", *args]) == 0
        return json.loads(capsys.readouterr().out)

    command("effort", "low")
    command("fast", "on")
    command("model", "haiku-5.5")
    changed = command("fast", "on")
    assert changed["local"]["sidekick"]["models"]["gpt-6-luna"] == {"effort": "low", "fast": True}
    assert changed["local"]["sidekick"]["models"]["haiku-5.5"] == {"fast": True}
    switched = command("model", "gpt-6-luna")
    assert config.current_model_settings(switched["local"]["sidekick"]) == {"effort": "low", "fast": True}
    assert json.loads(capsys.readouterr().out or "{}") == {}


def test_unregistered_model_uses_codex_defaults_and_status_reports_current_model(proj):
    local = config.load(proj.root)["local"]
    local["sidekick"]["model"] = "haiku-5.5"
    config.save_local(proj.root, local)
    cfg = config.load(proj.root)
    args = build_args(cfg, {"model": "haiku-5.5", "worktree": str(proj.station)}, proj.root / "run", "workspace-write", None, True)
    assert "model_reasoning_effort=high" not in args
    assert not any("service_tier" in arg for arg in args)
    shown = views.status(proj.root, cfg, {"tasks": {}})
    assert "助手: haiku-5.5 · effort 默认 · fast off" in shown


def test_config_get_set_and_station_rotation_behavior_remain(proj, capsys):
    assert main(["--project", str(proj.root), "config", "set", '{"local":{"enabled":false}}']) == 0
    capsys.readouterr()
    assert config.load(proj.root)["local"]["enabled"] is False
    assert main(["--project", str(proj.root), "config", "get"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["local"]["enabled"] is False

    setup_task(proj)
    proj.script([GOOD, GOOD])
    proj.do(__import__("fusion_core.commands", fromlist=["cmd_delegate"]).cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    first = proj.state()["stations"]["main#1"]
    assert {"model", "worktree", "thread", "status"}.issubset(first)
    assert "effort" not in first and "fast" not in first
    local = config.load(proj.root)["local"]
    local["sidekick"]["model"] = "gpt-6-astra"
    config.save_local(proj.root, local)
    assert config.load(proj.root)["local"]["sidekick"]["model"] == "gpt-6-astra"


def test_fast_change_keeps_resume_thread_and_applies_fast_to_next_run(proj):
    setup_task(proj)
    proj.script([GOOD, GOOD])
    from fusion_core.commands import cmd_delegate, cmd_revise
    proj.do(cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    thread = proj.state()["stations"]["main#1"]["thread"]
    local = config.load(proj.root)["local"]
    local["sidekick"].setdefault("models", {}).setdefault("gpt-6-luna", {})["fast"] = True
    config.save_local(proj.root, local)
    proj.do(cmd_revise, "T1", "再做一轮")
    proj.drain()
    second = proj.calls()[1]
    assert second["resume"] and second["thread"] == thread
    assert 'service_tier="fast"' in second["args"]
