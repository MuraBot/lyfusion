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


def test_usage_matches_design_and_is_short():
    source = DESIGN.read_text(encoding="utf-8")
    section = source.split("```text\n", 1)[1].split("\n```", 1)[0]
    assert LEAD_GUIDE == section
    assert len(LEAD_GUIDE.splitlines()) <= 20


def test_cli_public_command_set_and_version():
    p = subprocess.run([sys.executable, str(CORE / "fusion-core.py"), "--help"], check=False, capture_output=True)
    assert p.returncode == 0
    output = p.stdout.decode("utf-8")
    names = {"explore", "delegate", "revise", "accept", "status", "cancel", "on", "off", "config", "preflight", "ledger"}
    match = re.search(r"^\s+\{([^}]+)\}", output, re.MULTILINE)
    assert match
    found = set(match.group(1).split(","))
    found.discard("hook")  # Plugin-internal SessionStart bridge.
    assert found == names
    assert VERSION == "5.0.0-aq.1"
    meta = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert meta["version"] == VERSION


def test_fusion_command_exposes_only_settings():
    command = (PLUGIN / "commands/fusion.md").read_text(encoding="utf-8")
    for removed in ("guide", "fusion_*", "ToolSearch"):
        assert removed not in command
    for retained in ("status", "on", "off", "model", "effort", "fast", "test"):
        assert retained in command
