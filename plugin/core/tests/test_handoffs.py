from __future__ import annotations

import json

from fusion_core import cli, config, hooks, prompts, store, views


def _save_local(proj, **values):
    local = config.load(proj.root)["local"]
    local.update(values)
    config.save_local(proj.root, local)


def _save_project(proj, **values):
    cfg = config.load(proj.root)
    project = {key: value for key, value in cfg.items() if key != "local"}
    project.update(values)
    config.save_project(proj.root, project)


def test_guide_renders_handoff_modes_and_wait_setting(proj):
    cfg = config.load(proj.root)
    guide = views.lead_guide(cfg)
    assert "tell the user they can /clear" in guide
    assert "clear_session" not in guide
    assert "passed 200000 tokens" in guide
    assert len(guide.splitlines()) <= 24

    cfg["local"]["handoff_mode"] = "clear"
    clear_guide = views.lead_guide(cfg)
    assert "clear_session" in clear_guide
    assert "ask the user to run /clear" in clear_guide
    assert len(clear_guide.splitlines()) <= 24

    cfg["local"]["handoff_mode"] = "off"
    cfg["wait_minutes"] = 0.5
    off_guide = views.lead_guide(cfg)
    assert not any(line.startswith("Handoff:") for line in off_guide.splitlines())
    assert "after 0.5 minutes" in off_guide
    assert len(off_guide.splitlines()) <= 24
    for forbidden in ("fusion-core status", "ledger", "JSON"):
        assert forbidden not in guide


def test_invalid_stored_handoff_settings_fall_back_to_defaults(proj):
    cfg = config.load(proj.root)
    cfg["local"]["handoff_mode"] = "maybe"
    cfg["local"]["handoff_tokens"] = True
    cfg["handoff_dir"] = "../outside"
    assert config.handoff_settings(cfg) == {
        "mode": "write", "tokens": 200000, "dir": "fusion/handoffs",
    }


def test_handoff_config_actions_panel_and_status(proj, capsys):
    assert cli.main(["--project", str(proj.root), "config", "handoff", "clear"]) == 0
    capsys.readouterr()
    local = json.loads((proj.root / "fusion/local.json").read_text(encoding="utf-8"))
    assert local["handoff_mode"] == "clear"
    assert cli.main(["--project", str(proj.root), "config", "handoff-tokens", "210000"]) == 0
    capsys.readouterr()
    local = json.loads((proj.root / "fusion/local.json").read_text(encoding="utf-8"))
    assert local["handoff_tokens"] == 210000

    assert cli.main(["--project", str(proj.root), "config", "handoff", "maybe"]) != 0
    assert "clear, write, or off" in capsys.readouterr().err
    assert cli.main(["--project", str(proj.root), "config", "handoff-tokens", "0"]) != 0
    assert "positive integer" in capsys.readouterr().err

    assert cli.main(["--project", str(proj.root), "config", "panel"]) == 0
    panel = json.loads(capsys.readouterr().out)
    assert panel["handoff"] == {
        "mode": "clear", "tokens": 210000, "modes": ["clear", "write", "off"],
        "dir": "fusion/handoffs",
    }
    shown = views.status(proj.root, config.load(proj.root), {"tasks": {}})
    assert "Handoff: clear (at 210000 tokens) · fusion/handoffs" in shown


def test_session_start_points_to_latest_handoff_only_after_clear_or_compact(proj):
    directory = proj.root / "fusion/handoffs"
    directory.mkdir(parents=True)
    for name in ("2026-11-15-01.md", "2026-11-15-02.md", "README.md"):
        (directory / name).write_text("handoff", encoding="utf-8")

    clear = hooks.run("session-start", {"cwd": str(proj.root), "session_id": "s-clear", "source": "clear"})
    assert "Context was cleared: read the latest handoff first: fusion/handoffs/2026-11-15-02.md" in clear
    assert len(clear.splitlines()) <= 30
    compact = hooks.run("session-start", {"cwd": str(proj.root), "session_id": "s-compact", "source": "compact"})
    assert "Context was compacted: read the latest handoff first: fusion/handoffs/2026-11-15-02.md" in compact
    assert len(compact.splitlines()) <= 30
    for source in ("startup", "resume", "fusion-panel", None):
        text = hooks.run("session-start", {"cwd": str(proj.root), "source": source})
        assert "read the latest handoff first" not in text

    _save_local(proj, handoff_mode="off")
    text = hooks.run("session-start", {"cwd": str(proj.root), "source": "clear"})
    assert "read the latest handoff first" not in text


def test_session_start_ignores_empty_or_missing_handoff_directory(proj):
    _save_project(proj, handoff_dir="missing/handoffs")
    text = hooks.run("session-start", {"cwd": str(proj.root), "source": "clear"})
    assert "read the latest handoff first" not in text
    (proj.root / "missing/handoffs").mkdir(parents=True)
    text = hooks.run("session-start", {"cwd": str(proj.root), "source": "compact"})
    assert "read the latest handoff first" not in text


def test_accept_handoff_reminder_threshold_and_reset_sequence(proj, capsys):
    def snapshot(tokens):
        with store.transaction(proj.sup.conn):
            store.append(proj.sup.conn, [{
                "type": "lead_usage", "task": "T1",
                "data": {"at": "accept", "tokens": tokens},
            }], "test")
        cli._maybe_print_handoff_reminder(proj.root, "T1")
        return capsys.readouterr().out

    cli._maybe_print_handoff_reminder(proj.root, "T1")
    assert capsys.readouterr().out == ""
    assert snapshot(120000) == ""
    assert "Lead context: 210000 tokens" in snapshot(210000)
    assert snapshot(260000) == ""
    assert "Lead context: 365000 tokens" in snapshot(365000)
    assert snapshot(50000) == ""
    assert "Lead context: 205000 tokens" in snapshot(205000)


def test_explore_prompt_requires_mechanical_draft_within_limit():
    text = prompts.explore_prompt("task", "decisions")
    assert "## Draft (mechanical only)" in text
    assert "150 lines or fewer" in text
    assert "no approach or recommended implementation" in text
    assert "path — one line" in text
