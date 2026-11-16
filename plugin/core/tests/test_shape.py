"""Distribution and lead-facing shape checks for v5.0.0-aq."""
from __future__ import annotations

import json
import re
import subprocess
import sys

from conftest import CORE
from fusion_core import VERSION
from fusion_core.views import LEAD_GUIDE

PLUGIN = CORE.parent
DESIGN = PLUGIN.parent / "design" / "v5.0.0-aq.md"


def test_removed_public_surfaces_are_absent():
    for rel in (".mcp.json", "monitors/monitors.json", "core/fusion_core/tools.py",
                "core/fusion_core/mcp.py", "core/fusion_core/intent.py"):
        assert not (PLUGIN / rel).exists(), rel
    hook = json.loads((PLUGIN / "hooks/hooks.json").read_text(encoding="utf-8"))
    assert list(hook["hooks"]) == ["SessionStart"]


def test_no_bin_dir_and_guide_has_full_command():
    # claude.ai 托管的插件不能带顶层 bin/;lead 用使用说明里的完整命令运行引擎
    from fusion_core.util import CMD
    from fusion_core.views import lead_guide

    assert not (PLUGIN / "bin").exists()
    assert (CORE / "fusion-core.py").exists() and CMD.endswith('/core/fusion-core.py"')
    guide = lead_guide()
    for sub in ("explore -", "delegate -", "revise -", "accept", "wait", "status", "cancel"):
        assert f"{CMD} {sub}" in guide, sub
    assert "fusion-core " not in guide.replace(CMD, "")
    # /fusion 是只给用户手动运行的技能:裸名 /fusion 能用,描述不进 Claude 的上下文
    assert not (PLUGIN / "commands").exists()
    skill = (PLUGIN / "skills/fusion/SKILL.md").read_text(encoding="utf-8")
    front = skill.split("---")[1].splitlines()
    assert "name: fusion" in front and "disable-model-invocation: true" in front
    assert '${CLAUDE_PLUGIN_ROOT}/core/fusion-core.py' in skill and "$ARGUMENTS" in skill
    meta = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert meta["name"] == "lyfusion-plugin"


def test_usage_matches_design_and_is_short():
    source = DESIGN.read_text(encoding="utf-8")
    section = source.split("```text\n", 1)[1].split("\n```", 1)[0]
    assert LEAD_GUIDE == section
    assert len(LEAD_GUIDE.splitlines()) <= 20


def test_cli_public_command_set_and_version():
    p = subprocess.run([sys.executable, str(CORE / "fusion-core.py"), "--help"], check=False, capture_output=True)
    assert p.returncode == 0
    output = p.stdout.decode("utf-8")
    names = {"explore", "delegate", "revise", "accept", "wait", "status", "cancel", "on", "off", "config", "preflight", "ledger", "lead-usage"}
    match = re.search(r"^\s+\{([^}]+)\}", output, re.MULTILINE)
    assert match
    found = set(match.group(1).split(","))
    found.discard("hook")  # Plugin-internal SessionStart bridge.
    assert found == names
    assert VERSION == "5.0.0-rc.1"
    meta = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert meta["version"] == VERSION


def test_fusion_command_exposes_only_settings():
    command = (PLUGIN / "skills/fusion/SKILL.md").read_text(encoding="utf-8")
    for removed in ("guide", "fusion_*", "ToolSearch"):
        assert removed not in command
    for retained in ("status", "on", "off", "model", "effort", "fast", "test"):
        assert retained in command
