"""T2: model-scoped Codex settings and retained configuration behavior."""
from __future__ import annotations

import json

import pytest
from fusion_core import cli, config, views
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
    command("model", "gpt-6-astra")
    command("fast", "on")
    command("model", "haiku-5.5")
    before = (proj.root / "fusion" / "local.json").read_bytes()
    assert main(["--project", str(proj.root), "config", "fast", "on"]) == 1
    assert "haiku-5.5 does not support Fast Mode" in capsys.readouterr().err
    assert (proj.root / "fusion" / "local.json").read_bytes() == before
    changed = json.loads(before)
    assert changed["sidekick"]["models"]["gpt-6-luna"] == {"effort": "low", "fast": True}
    assert changed["sidekick"]["models"]["gpt-6-astra"] == {"fast": True}
    switched = command("model", "gpt-6-luna")
    assert config.current_model_settings(switched["local"]["sidekick"]) == {
        "effort": "low", "fast": True, "compact": config.DEFAULT_COMPACT,
    }


def test_unregistered_model_uses_codex_defaults_and_status_reports_current_model(proj):
    local = config.load(proj.root)["local"]
    local["sidekick"]["model"] = "haiku-5.5"
    local["sidekick"]["models"]["haiku-5.5"] = {"fast": True}
    config.save_local(proj.root, local)
    cfg = config.load(proj.root)
    args = build_args(cfg, {"model": "haiku-5.5", "worktree": str(proj.station)}, proj.root / "run", "workspace-write", None, True)
    assert "model_reasoning_effort=high" not in args
    assert not any("service_tier" in arg for arg in args)
    shown = views.status(proj.root, cfg, {"tasks": {}})
    assert "Assistant: haiku-5.5 · effort default · fast unsupported · compact 400000" in shown
    assert "· compact 400000" in shown
    assert "Codex environment: clean (does not read ~/.codex/config.toml; apps and plugins disabled)(set in fusion/config.json)" in shown
    assert "Station rotation: context exceeds 240000(compact limit 400000 × 60%)" in shown


def test_config_get_set_and_station_rotation_behavior_remain(proj, capsys):
    assert main(["--project", str(proj.root), "config", "set", '{"local":{"enabled":false}}']) == 0
    capsys.readouterr()
    assert config.load(proj.root)["local"]["enabled"] is False
    assert main(["--project", str(proj.root), "config", "get"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["local"]["enabled"] is False
    assert got["effective"] == {
        "model": "gpt-6-luna", "effort": "high", "fast": False,
        "compact": 400000, "clean": True, "context_ratio": 0.6, "switch_at": 240000,
    }

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


def test_default_clean_codex_args_for_new_and_resumed_sessions(proj):
    local_path = proj.root / "fusion" / "local.json"
    local = json.loads(local_path.read_text(encoding="utf-8"))
    local["clean"] = False
    local_path.write_text(json.dumps(local), encoding="utf-8")
    cfg = config.load(proj.root)
    assert cfg["clean"] is True
    assert "clean" not in cfg["local"]
    assert json.loads(local_path.read_text(encoding="utf-8"))["clean"] is False

    common = (cfg, {"model": "gpt-6-luna", "worktree": str(proj.station)},
              proj.root / "run", "workspace-write")
    fresh = build_args(*common, resume_thread=None, schema=True)
    resumed = build_args(*common, resume_thread="thread-1", schema=True)
    for args in (fresh, resumed):
        assert "--ignore-user-config" in args
        assert args[args.index("--disable") + 1] == "apps"
        second_disable = args.index("--disable", args.index("--disable") + 1)
        assert args[second_disable + 1] == "plugins"
        assert "model_auto_compact_token_limit=400000" in args
        assert args[-1] == "-"
    assert resumed[-2] == "thread-1"


def test_compact_is_model_scoped_and_passed_as_integer_override(proj, capsys):
    def command(*args):
        assert main(["--project", str(proj.root), "config", *args]) == 0
        return json.loads(capsys.readouterr().out)

    luna = command("compact", "300000")
    assert luna["local"]["sidekick"]["models"]["gpt-6-luna"]["compact"] == 300000
    cfg = {"local": luna["local"]}
    station = {"model": "gpt-6-luna", "worktree": str(proj.station)}
    args = build_args(cfg, station, proj.root / "run", "workspace-write", None, True)
    assert "model_auto_compact_token_limit=300000" in args

    command("model", "haiku-5.5")
    unknown = config.load(proj.root)
    args = build_args(unknown, {"model": "haiku-5.5", "worktree": str(proj.station)},
                      proj.root / "run", "workspace-write", None, True)
    assert "model_auto_compact_token_limit=400000" in args
    command("model", "gpt-6-luna")
    returned = config.load(proj.root)
    args = build_args(returned, {"model": "gpt-6-luna", "worktree": str(proj.station)},
                      proj.root / "run", "workspace-write", None, True)
    assert "model_auto_compact_token_limit=300000" in args


def test_clean_off_is_applied_on_resume_without_changing_thread(proj, capsys):
    setup_task(proj)
    proj.script([GOOD, GOOD])
    from fusion_core.commands import cmd_delegate, cmd_revise

    proj.do(cmd_delegate, plan_farewell(), "T1")
    proj.drain()
    thread = proj.state()["stations"]["main#1"]["thread"]
    assert thread
    assert main(["--project", str(proj.root), "config", "set", '{"config":{"clean":false}}']) == 0
    capsys.readouterr()
    cfg = config.load(proj.root)
    fresh = build_args(cfg, {"model": "gpt-6-luna", "worktree": str(proj.station)},
                       proj.root / "fresh", "workspace-write", None, True)
    assert not any(flag in fresh for flag in ("--ignore-user-config", "apps", "plugins"))
    assert "model_auto_compact_token_limit=400000" in fresh
    proj.do(cmd_revise, "T1", "再做一轮")
    proj.drain()
    second = proj.calls()[1]
    assert second["resume"] and second["thread"] == thread
    assert not any(flag in second["args"] for flag in ("--ignore-user-config", "apps", "plugins"))
    assert "model_auto_compact_token_limit=400000" in second["args"]


@pytest.mark.parametrize(("section", "key", "value"), [
    ("config", "context_ratio", 0),
    ("config", "context_ratio", 1),
    ("config", "context_ratio", 1.5),
    ("config", "context_ratio", "abc"),
    ("config", "context_ratio", True),
    ("config", "clean", "maybe"),
])
def test_invalid_project_settings_leave_all_config_files_unchanged(
    proj, capsys, section, key, value
):
    local_path = proj.root / "fusion" / "local.json"
    config_path = proj.root / "fusion" / "config.json"
    before = (local_path.read_bytes(), config_path.read_bytes())
    change = json.dumps({"local": {"enabled": True}, section: {key: value}})
    assert main(["--project", str(proj.root), "config", "set", change]) == 1
    error = capsys.readouterr().err
    assert key in error
    assert (local_path.read_bytes(), config_path.read_bytes()) == before


def test_ratio_and_legacy_context_limit_behavior(proj, capsys):
    config_path = proj.root / "fusion" / "config.json"
    local_path = proj.root / "fusion" / "local.json"
    original_local = local_path.read_bytes()
    old_config = json.loads(config_path.read_text(encoding="utf-8"))
    old_config["context_limit"] = 1
    config_path.write_text(json.dumps(old_config), encoding="utf-8")
    assert "context_limit" not in config.DEFAULT_CONFIG
    legacy = config.load(proj.root)
    assert config.effective_settings(legacy)["switch_at"] == 240000

    assert main(["--project", str(proj.root), "config", "set", '{"config":{"context_ratio":0.5}}']) == 0
    capsys.readouterr()
    updated = config.load(proj.root)
    assert config.effective_settings(updated)["switch_at"] == 200000
    assert json.loads(config_path.read_text(encoding="utf-8"))["context_limit"] == 1
    assert local_path.read_bytes() == original_local


def test_invalid_compact_and_ratio_fall_back_and_warn(proj):
    config_path = proj.root / "fusion" / "config.json"
    local_path = proj.root / "fusion" / "local.json"
    project = json.loads(config_path.read_text(encoding="utf-8"))
    project["context_ratio"] = True
    config_path.write_text(json.dumps(project), encoding="utf-8")
    local = json.loads(local_path.read_text(encoding="utf-8"))
    local["sidekick"]["models"]["gpt-6-luna"]["compact"] = 0
    local_path.write_text(json.dumps(local), encoding="utf-8")

    cfg = config.load(proj.root)
    shown = views.status(proj.root, cfg, {"tasks": {}})
    ratio_warning = "fusion/config.json has an invalid context_ratio; using 0.6"
    compact_warning = "fusion/local.json has an invalid sidekick.models.gpt-6-luna.compact; using 400000"
    assert ratio_warning in shown and compact_warning in shown
    assert "Station rotation: context exceeds 240000(compact limit 400000 × 60%)" in shown

    checks = cli._preflight(proj.root)["checks"]
    warnings = [row["detail"] for row in checks if row["check"] == "Configuration warning"]
    assert ratio_warning in warnings and compact_warning in warnings


def test_preflight_codex_clean_flags_available(proj):
    result = cli._preflight(proj.root)
    rows = {row["check"]: row for row in result["checks"]}
    sandbox_check = "Sandbox command execution"
    assert rows["Codex"]["ok"] and "codex fake-1.0" in rows["Codex"]["detail"]
    assert rows["Clean mode options"]["ok"]
    assert rows[sandbox_check]["ok"]
    assert str(proj.root).replace("\\", "/").lower() in rows[sandbox_check]["detail"].replace("\\", "/").lower()


def test_preflight_detects_command_rejected_inside_sandbox(proj):
    local = config.load(proj.root)["local"]
    local["env"]["FAKE_CODEX_SANDBOX_FAIL"] = "1"
    config.save_local(proj.root, local)
    result = cli._preflight(proj.root)
    row = next(row for row in result["checks"] if row["check"] == "Sandbox command execution")
    assert not row["ok"]
    assert row["detail"] == "rejected: blocked by policy"


def test_preflight_detects_missing_resume_flag(proj):
    local = config.load(proj.root)["local"]
    local["env"]["FAKE_CODEX_RESUME_HELP_MISSING"] = "--ignore-user-config"
    config.save_local(proj.root, local)
    result = cli._preflight(proj.root)
    row = next(row for row in result["checks"] if row["check"] == "Clean mode options")
    assert not row["ok"]
    assert "exec resume --help missing --ignore-user-config" in row["detail"]


def test_preflight_requires_exact_apps_feature_name(proj):
    local = config.load(proj.root)["local"]
    local["env"]["FAKE_CODEX_FEATURES"] = "apps_mcp_path_override\nplugins"
    config.save_local(proj.root, local)
    result = cli._preflight(proj.root)
    row = next(row for row in result["checks"] if row["check"] == "Clean mode options")
    assert not row["ok"]
    assert "features list missing apps" in row["detail"]


def test_preflight_failure_is_advisory_when_clean_mode_is_off(proj):
    local = config.load(proj.root)["local"]
    local["env"]["FAKE_CODEX_RESUME_HELP_MISSING"] = "--ignore-user-config"
    config.save_local(proj.root, local)
    project_path = proj.root / "fusion" / "config.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project["clean"] = False
    project_path.write_text(json.dumps(project), encoding="utf-8")
    result = cli._preflight(proj.root)
    row = next(row for row in result["checks"] if row["check"] == "Clean mode options")
    assert row["ok"]
    assert "clean mode is off for this project; informational only" in row["detail"]


def test_station_rotation_threshold_uses_model_compact(proj):
    cfg = config.load(proj.root)
    station = {"name": "main#1", "line": "main", "status": "idle", "ctx_est": 601,
               "model": "gpt-6-luna", "files": [], "tasks": []}

    def state():
        return {"runs": {}, "stations": {"main#1": dict(station)}, "station_seq": {"main": 1},
                "tasks": {"T1": {"runs": [], "plan": {"scope": []}}}}

    cfg["local"]["sidekick"]["models"]["gpt-6-luna"]["compact"] = 1000
    rotated, events, _ = proj.sup._station_for(state(), cfg, {"runs": [], "plan": {"scope": []}})
    assert rotated["name"] == "main#2"
    retired = next(event for event in events if event["type"] == "station_retired")
    assert retired["data"]["reason"] == "Current context is about 601 tokens, above the station rotation threshold 600 (compact limit 1000 × 60%)"

    cfg["local"]["sidekick"]["models"]["gpt-6-luna"]["compact"] = 2000
    kept, events, _ = proj.sup._station_for(state(), cfg, {"runs": [], "plan": {"scope": []}})
    assert kept["name"] == "main#1"
    assert not any(event["type"] == "station_retired" for event in events)


def test_station_reuses_worktree_when_new_scope_is_in_a_different_area(proj):
    cfg = config.load(proj.root)
    station = {"name": "main#1", "line": "main", "status": "idle", "ctx_est": 0,
               "model": cfg["local"]["sidekick"]["model"], "files": ["old/feature.py"], "tasks": []}
    state = {"stations": {"main#1": station}, "station_seq": {"main": 1},
             "runs": {}, "tasks": {}, "usage": {}}
    task = {"runs": [], "plan": {"scope": ["new/feature.py"]}}
    selected, events, _ = proj.sup._station_for(state, cfg, task)
    assert selected["name"] == "main#1"
    assert not any(event["type"] == "station_retired" for event in events)


def test_model_capabilities_and_effort_validation(proj, capsys):
    assert config.model_efforts("gpt-6-luna") == ["low", "medium", "high", "xhigh", "max"]
    assert config.model_efforts("gpt-6-astra")[-1] == "ultra"
    assert config.model_efforts("unknown") == config.DEFAULT_EFFORTS
    assert not config.supports_fast("unknown") and config.max_compact("unknown") is None
    assert config.current_model_settings({"model": "unknown", "models": {"unknown": {"fast": True}}})["fast"] is False

    for model, effort, expected in (("gpt-6-luna", "max", 0), ("gpt-6-luna", "ultra", 1),
                                    ("gpt-6-astra", "ultra", 0), ("unknown", "max", 1)):
        assert main(["--project", str(proj.root), "config", "model", model]) == 0
        capsys.readouterr()
        result = main(["--project", str(proj.root), "config", "effort", effort])
        assert result == expected
        capsys.readouterr()

    local = config.load(proj.root)["local"]
    local["sidekick"]["models"].setdefault("unknown", {})["fast"] = True
    config.save_local(proj.root, local)
    args = build_args(config.load(proj.root), {"model": "unknown", "worktree": str(proj.station)},
                      proj.root / "run", "workspace-write", None, True)
    assert not any("service_tier" in arg for arg in args)


def test_compact_model_upper_bound(proj, capsys):
    assert main(["--project", str(proj.root), "config", "compact", "900000"]) == 1
    assert "Context limit cannot exceed 872000 for gpt-6-luna" in capsys.readouterr().err
    assert main(["--project", str(proj.root), "config", "compact", "1"]) == 0
    capsys.readouterr()
    assert main(["--project", str(proj.root), "config", "model", "unknown"]) == 0
    capsys.readouterr()
    assert main(["--project", str(proj.root), "config", "compact", "900000"]) == 0


def test_clean_mode_preserves_only_user_sandbox_settings(proj, monkeypatch):
    codex_home = proj.base / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    path = codex_home / "config.toml"
    path.write_text('model = "ignored"\napproval_policy = "never"\n[windows]\nsandbox = "elevated"\n[sandbox_workspace_write]\nnetwork_access = false\n',
                    encoding="utf-8")
    cfg = config.load(proj.root)
    station = {"model": "gpt-6-luna", "worktree": str(proj.station)}

    fresh = build_args(cfg, station, proj.root / "run", "workspace-write", None, True)
    resumed = build_args(cfg, station, proj.root / "run", "workspace-write", "thread-1", True)
    for args in (fresh, resumed):
        window_settings = [args[i + 1] for i, flag in enumerate(args[:-1])
                           if flag == "-c" and args[i + 1].startswith("windows.sandbox=")]
        assert window_settings == ['windows.sandbox="elevated"']
        assert args.count("sandbox_workspace_write.network_access=false") == 1
        assert not any("ignored" in arg or "approval_policy" in arg or "never" == arg for arg in args)

    monkeypatch.setenv("CODEX_HOME", "")
    user_home = proj.base / "user-home"
    fallback_home = user_home / ".codex"
    fallback_home.mkdir(parents=True)
    (fallback_home / "config.toml").write_bytes(path.read_bytes())
    monkeypatch.setattr("fusion_core.codex.Path.home", lambda: user_home)
    empty_codex_home = build_args(cfg, station, proj.root / "run", "workspace-write", None, True)
    assert 'windows.sandbox="elevated"' in empty_codex_home
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    cfg["network"] = True
    project_network = build_args(cfg, station, proj.root / "run", "workspace-write", None, True)
    assert project_network.count("sandbox_workspace_write.network_access=true") == 1
    path.write_text('[sandbox_workspace_write]\nnetwork_access = true\n', encoding="utf-8")
    user_network = build_args({**cfg, "network": False}, station, proj.root / "run", "workspace-write", None, True)
    assert user_network.count("sandbox_workspace_write.network_access=true") == 1
    both_network = build_args(cfg, station, proj.root / "run", "workspace-write", None, True)
    assert both_network.count("sandbox_workspace_write.network_access=true") == 1
    other_sandbox = build_args(cfg, station, proj.root / "run", "read-only", None, True)
    assert other_sandbox.count("sandbox_workspace_write.network_access=true") == 1

    path.write_text('[windows]\nsandbox = 3\n[sandbox_workspace_write]\nnetwork_access = "yes"\n', encoding="utf-8")
    malformed_values = build_args({**cfg, "network": False}, station, proj.root / "run", "workspace-write", None, True)
    assert not any("windows.sandbox=" in arg or "sandbox_workspace_write.network_access=" in arg for arg in malformed_values)
    path.write_text("not = [valid", encoding="utf-8")
    broken_args = build_args({**cfg, "network": False}, station, proj.root / "run", "workspace-write", None, True)
    assert not any("windows.sandbox=" in arg for arg in broken_args)
    path.unlink()
    missing_args = build_args({**cfg, "network": False}, station, proj.root / "run", "workspace-write", None, True)
    assert not any("windows.sandbox=" in arg for arg in missing_args)
    path.write_text('[windows]\nsandbox = "elevated"\n', encoding="utf-8")
    clean_off = build_args({**cfg, "clean": False}, station, proj.root / "run", "workspace-write", None, True)
    assert clean_off.count("sandbox_workspace_write.network_access=true") == 1
    assert not any("windows.sandbox=" in arg for arg in clean_off)
