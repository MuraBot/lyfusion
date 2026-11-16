"""v5.0.0-aq.2: H2 lead feedback tests (exploration required, decisions.md checkpoint, deduplicated review pack and worktree lines, no formatter)."""
from __future__ import annotations

import json

from conftest import report, sh
from fusion_core import checks
from fusion_core.commands import DECISIONS, commit_decisions
from fusion_core.prompts import WORK_RULES
from fusion_core.views import LEAD_GUIDE
from test_cli import cli


def test_plan_checks_skip_exact_project_commands():
    cfg = {"test": "python -m pytest -q", "lint": "ruff check ."}
    plan = {"checks": [{"run": "python -m pytest -q", "expect": 0},
                       {"run": "python -m pytest -q tests/test_x.py", "expect": 0},
                       {"run": "ruff check .", "expect": 1},
                       {"run": " ruff check . ", "expect": 0}]}
    kept = checks.plan_checks(cfg, plan)
    assert [i for i, _ in kept] == [2, 3]  # Keep original numbering; different expectations are not duplicates.


def test_commit_decisions_commits_only_that_file(proj):
    (proj.root / DECISIONS).parent.mkdir(exist_ok=True)
    (proj.root / DECISIONS).write_text("# Decisions\n- D1: use sqlite\n", encoding="utf-8")
    proj.write("notes.txt", "Lead draft; should not be committed\n")
    sh("git", "add", "notes.txt", cwd=proj.root)
    before = sh("git", "rev-list", "--count", "HEAD", cwd=proj.root)
    assert commit_decisions(proj.root) is None
    assert int(sh("git", "rev-list", "--count", "HEAD", cwd=proj.root)) == int(before) + 1
    files = sh("git", "show", "--name-only", "--format=", "HEAD", cwd=proj.root).split()
    assert files == [DECISIONS]
    assert "notes.txt" in sh("git", "diff", "--cached", "--name-only", cwd=proj.root)
    assert commit_decisions(proj.root) is None  # Do not commit when there are no changes.
    assert int(sh("git", "rev-list", "--count", "HEAD", cwd=proj.root)) == int(before) + 1


def test_review_lists_candidate_station_and_each_command_once(proj):
    proj.script([{"write": {"app/new.py": "VALUE = 2\n"}, "report": report()}])
    test_cmd = json.loads((proj.root / "fusion/config.json").read_text(encoding="utf-8"))["test"]
    p = cli(proj, "delegate", "-", input_text=json.dumps(
        {"goal": "Add module", "brief": "Change code", "checks": [{"run": test_cmd, "expect": 0}]}))
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    text = (proj.root / "fusion/tasks/T1/review-1.md").read_text(encoding="utf-8")
    assert text.count(f"`{test_cmd}`") == 1
    assert "Old tests on new code" not in text
    assert "workstation path" not in text
    assert "Diff omitted" not in text


def test_guide_and_rules_carry_lily_decisions():
    assert "Choose a tier after a quick look at the code" in LEAD_GUIDE
    assert "Start at step 2" in LEAD_GUIDE
    assert "exact test assertions" in LEAD_GUIDE
    assert "No run_in_background, Monitor, sleep or polling" in LEAD_GUIDE
    assert "timeout 600000" in LEAD_GUIDE
    assert "fusion-core wait" in LEAD_GUIDE
    assert "queued" in LEAD_GUIDE
    assert len(LEAD_GUIDE.splitlines()) <= 24
    assert "Brief conventions" in WORK_RULES
    assert "Do not format the whole project or untouched files" in WORK_RULES
