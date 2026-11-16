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
    # claude.ai 鎵樼鐨勬彃浠朵笉鑳藉甫椤跺眰 bin/;lead 鐢ㄤ娇鐢ㄨ鏄庨噷鐨勫畬鏁村懡浠よ繍琛屽紩鎿?
    from fusion_core.util import CMD
    from fusion_core.views import lead_guide

    assert not (PLUGIN / "bin").exists()
    assert (CORE / "fusion-core.py").exists() and CMD.endswith('/core/fusion-core.py"')
    guide = lead_guide()
    for sub in ("explore -", "delegate -", "revise -", "accept", "wait", "cancel"):
        assert f"{CMD} {sub}" in guide, sub
    assert "fusion-core " not in guide.replace(CMD, "")
    # /fusion 鏄彧缁欑敤鎴锋墜鍔ㄨ繍琛岀殑鎶€鑳?瑁稿悕 /fusion 鑳界敤,鎻忚堪涓嶈繘 Claude 鐨勪笂涓嬫枃
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
    assert len(LEAD_GUIDE.splitlines()) <= 24


def test_minor_fix_guide_fits_every_handoff_mode():
    from fusion_core.config import DEFAULT_CONFIG, DEFAULT_LOCAL
    from fusion_core.views import lead_guide

    assert '--minor-fix "one sentence"' in LEAD_GUIDE
    for mode in ("clear", "write", "off"):
        cfg = {**DEFAULT_CONFIG, "local": {**DEFAULT_LOCAL, "handoff_mode": mode}}
        guide = lead_guide(cfg)
        assert len(guide.splitlines()) <= 24


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
    assert VERSION == "5.0.0-rc.1.1"
    meta = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert meta["version"] == VERSION


def test_fusion_command_exposes_only_settings():
    command = (PLUGIN / "skills/fusion/SKILL.md").read_text(encoding="utf-8")
    for removed in ("guide", "fusion_*", "ToolSearch"):
        assert removed not in command
    for retained in ("status", "on", "off", "model", "effort", "fast", "test"):
        assert retained in command
