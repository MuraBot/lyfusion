from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fusion_core import cli, config, views
from fusion_core.cli import main


def cache_path() -> Path:
    return Path(os.environ["CODEX_HOME"]) / "models_cache.json"


def write_cache(models):
    cache_path().write_text(json.dumps({"models": models}), encoding="utf-8")
    config._MODEL_CACHE_STATE = None


def model_entry(slug, priority, **changes):
    entry = {
        "slug": slug,
        "display_name": slug,
        "visibility": "list",
        "priority": priority,
        "supported_reasoning_levels": [{"effort": "low"}],
        "additional_speed_tiers": ["fast"],
        "max_context_window": 872000,
    }
    entry.update(changes)
    return entry


def test_panel_uses_cache_priority_capabilities_and_visibility(proj, capsys):
    write_cache([
        model_entry("gpt-6.1-sol", 1, display_name="GPT-6.1-Sol",
                    supported_reasoning_levels=[{"effort": effort} for effort in
                                                ("low", "medium", "high", "xhigh", "max", "ultra")]),
        model_entry("gpt-6-luna", 6, display_name="GPT-6-Luna"),
        model_entry("gpt-reserve", 0, visibility="hide"),
    ])

    assert main(["--project", str(proj.root), "config", "panel"]) == 0
    panel = json.loads(capsys.readouterr().out)
    assert panel["models"][:2] == ["gpt-6.1-sol", "gpt-6-luna"]
    assert "gpt-6-astra" not in panel["models"]  # never offered as the sidekick (Lily, 2026-11-16)
    assert "gpt-reserve" not in panel["models"]
    assert panel["model_names"]["gpt-6.1-sol"] == "GPT-6.1-Sol"
    assert {"gpt-6.1-sol", "gpt-6-luna"}.issubset(panel["fast_models"])
    assert config.model_efforts("gpt-6.1-sol")[-1] == "ultra"


def test_config_validates_cache_efforts_and_speed_tiers(proj, capsys):
    write_cache([
        model_entry("gpt-6.1-sol", 1, display_name="GPT-6.1-Sol",
                    supported_reasoning_levels=[{"effort": value} for value in
                                                ("low", "medium", "high", "xhigh", "max", "ultra")]),
        model_entry("gpt-6-luna", 6, display_name="GPT-6-Luna"),
        model_entry("slow-model", 2, additional_speed_tiers=[]),
    ])
    assert main(["--project", str(proj.root), "config", "model", "gpt-6.1-sol"]) == 0
    capsys.readouterr()
    assert main(["--project", str(proj.root), "config", "effort", "ultra"]) == 0
    capsys.readouterr()
    assert main(["--project", str(proj.root), "config", "model", "gpt-6-luna"]) == 0
    capsys.readouterr()
    assert main(["--project", str(proj.root), "config", "effort", "ultra"]) != 0
    capsys.readouterr()
    assert main(["--project", str(proj.root), "config", "model", "slow-model"]) == 0
    capsys.readouterr()
    assert main(["--project", str(proj.root), "config", "fast", "on"]) != 0
    assert "Fast Mode" in capsys.readouterr().err


def test_compact_choices_respect_cached_max_context(proj):
    write_cache([model_entry("gpt-6.1-sol", 1, max_context_window=500000)])
    assert config.compact_choices("gpt-6.1-sol", 400000) == [262144, 400000]


@pytest.mark.parametrize("payload", [None, "not json", {"models": "x"}, {"models": [{"name": "no slug"}]}])
def test_unusable_cache_warns_and_falls_back_without_writing(proj, capsys, payload):
    path = cache_path()
    if payload is None:
        path.unlink()
    elif payload == "not json":
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    config._MODEL_CACHE_STATE = None
    home_before = {item.name for item in path.parent.iterdir()}
    fusion_before = {item.relative_to(proj.root).as_posix()
                     for item in (proj.root / "fusion").rglob("*")}

    assert main(["--project", str(proj.root), "config", "panel"]) == 0
    panel = json.loads(capsys.readouterr().out)
    warning = panel["warnings"]
    assert len(warning) == 1 and warning[0].startswith("Could not read Codex model cache")
    assert "gpt-6.1-sol" in panel["models"]
    status = views.status(proj.root, config.load(proj.root), {"tasks": {}})
    assert warning[0] in status
    checks = cli._preflight(proj.root)["checks"]
    assert warning[0] in [row["detail"] for row in checks if row["check"] == "Configuration warning"]
    assert {item.name for item in path.parent.iterdir()} == home_before
    assert {item.relative_to(proj.root).as_posix()
            for item in (proj.root / "fusion").rglob("*")} == fusion_before


def test_cache_is_read_once_per_mtime(proj, monkeypatch):
    cache = cache_path()
    config._MODEL_CACHE_STATE = None
    original = Path.read_text
    reads = []

    def counted_read(path, *args, **kwargs):
        if path == cache:
            reads.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counted_read)
    config.model_efforts("gpt-6-luna")
    config.supports_fast("gpt-6-luna")
    config.max_compact("gpt-6-luna")
    config.known_models()
    assert len(reads) == 1

    stat = cache.stat()
    cache.write_text(json.dumps({"models": [model_entry("changed", 1)]}), encoding="utf-8")
    os.utime(cache, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
    assert "changed" in config.known_models()
    assert len(reads) == 2


def test_wrongly_typed_capability_fields_fall_back_individually(proj):
    write_cache([model_entry(
        "gpt-6-luna", 1,
        display_name=3,
        supported_reasoning_levels="not a list",
        additional_speed_tiers="fast",
        max_context_window="872000",
    )])
    info = config.model_info("gpt-6-luna")
    assert info == config.MODEL_INFO["gpt-6-luna"]
