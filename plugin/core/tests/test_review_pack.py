from __future__ import annotations

import subprocess

from fusion_core import aq, validate
from fusion_core.util import CMD


def make_pack(proj, changes, *, scope=None, report=None, checks=None):
    base = proj.git("rev-parse", "HEAD")
    if not changes:
        changes = {"app/review-marker.txt": "review marker\n"}
    for path, text in changes.items():
        if text is None:
            (proj.root / path).unlink()
        else:
            proj.write(path, text)
    proj.commit("review candidate")
    commit = proj.git("rev-parse", "HEAD")
    task_report = {"status": "done", "summary": "Completed", "questions": [], "choices": [], "problems": []}
    if report:
        task_report.update(report)
    task = {
        "id": "T1", "state": "in_review", "latest": "T1.c1", "runs": ["r1"],
        "signals": [], "fix_attempts": 0, "change_rounds": 0,
        "plan": {"goal": "Review changes", "scope": scope or []},
        "latest_report": task_report,
    }
    candidate = {"commit": commit, "base": base, "run": "r1", "checks": checks or {"passed": True, "results": [], "violations": []}}
    state = {"candidates": {"T1.c1": candidate}, "runs": {"r1": {"dir": None}}, "stations": {}}
    return task, state, aq.review_pack(proj.root, task, state, 1)


def test_brief_check_deviations_lead_and_invalid_checks_are_lenient(proj):
    report, problems = validate.report({
        "status": "done", "summary": "Completed", "questions": [], "choices": [], "problems": [],
        "brief_check": [{"item": "Keep API stable", "status": "differs", "where": "app/api.py:2", "why": "Needed a parameter."}],
    })
    assert not problems
    _task, _state, pack = make_pack(proj, {"app/api.py": "VALUE = 1\n"}, report=report)
    assert pack.index("## Differs from brief") < pack.index("## Checks")
    assert "differs: Keep API stable (app/api.py:2): Needed a parameter." in pack

    legacy, problems = validate.report({
        "status": "done", "summary": "Completed", "questions": [], "choices": [], "problems": [],
    })
    malformed, malformed_problems = validate.report({
        "status": "done", "summary": "Completed", "questions": [], "choices": [], "problems": [],
        "brief_check": [{"item": "bad", "status": "unknown", "where": 3, "why": "bad"}],
    })
    assert not problems and not malformed_problems
    assert legacy["status"] == malformed["status"] == "done"
    assert legacy["brief_check"] is malformed["brief_check"] is None
    _, _, missing_pack = make_pack(proj, {}, report=legacy)
    assert "Brief check: not provided" in missing_pack
    assert "## Differs from brief" not in missing_pack


def test_old_tests_run_is_never_listed_as_a_check(proj):
    _, _, pack = make_pack(proj, {"app/change.py": "VALUE = 1\n"}, checks={
        "passed": True,
        "results": [{"name": "Old tests on new code", "cmd": "pytest", "exit": 0,
                     "passed": True, "restored": True}],
        "violations": [],
    })
    checks = pack.split("## Checks\n", 1)[1].split("\n## ", 1)[0]
    assert "Old tests on new code" not in checks
    assert "pytest" not in checks


def test_engine_scan_reports_public_signatures_markers_and_scope(proj):
    proj.write("app/api.py", "def foo(a):\n    return a\n\ndef _bar(a):\n    return a\n")
    proj.write("app/private.py", "def _bar(a):\n    return a\n")
    proj.commit("baseline functions")
    _task, _state, pack = make_pack(proj, {
        "app/api.py": "def foo(a, b):\n    return a + b\n\ndef _bar(a, b):\n    return a + b\n",
        "app/private.py": "def _bar(a, b):\n    return a + b\n",
        "app/new.py": "# TODO: review\nVALUE = 1\n",
        "outside.txt": "outside\n",
    }, scope=["app/**"], checks={"passed": True, "results": [], "violations": [], "out_of_scope": ["outside.txt"]})
    assert "## Engine scan" in pack
    assert "foo: def foo(a):" in pack and "def foo(a, b):" in pack
    assert chr(0x2192) in pack
    engine_scan = pack.split("## Engine scan\n", 1)[1].split("\n## Sidekick", 1)[0]
    assert "_bar" not in engine_scan
    assert "Marker: app/new.py: # TODO: review" in pack
    assert "Out of scope: outside.txt" in pack


def test_engine_scan_ignores_body_only_signature_text_and_keeps_parameter_changes(proj):
    proj.write("app/api.py", "def update_stock(self, tool_id, quantity):\n    return quantity\n\n"
               "def load_stock(stock_id):\n    return stock_id\n")
    proj.commit("baseline signature")
    _, _, pack = make_pack(proj, {
        "app/api.py": "def update_stock(self, tool_id, quantity):\n    return quantity + 1\n\n"
                      "def load_stock(stock_id, location=None):\n    return stock_id\n",
    })
    assert "update_stock:" not in pack
    assert "load_stock: def load_stock(stock_id):" in pack
    assert "def load_stock(stock_id, location=None):" in pack


def test_mechanical_folding_and_function_context_diff(proj):
    proj.write("app/spacing.py", "  # spacing\nVALUE = 1\n")
    proj.write("app/logic.py", "def compute():\n    marker = 'far context'\n    first = 1\n    second = 2\n    third = 3\n    fourth = 4\n    target = 5\n    return target\n")
    proj.commit("baseline files")
    _, _, pack = make_pack(proj, {
        "app/spacing.py": "# spacing\nVALUE = 1\n",
        "app/logic.py": "def compute():\n    marker = 'far context'\n    first = 1\n    second = 2\n    third = 3\n    fourth = 4\n    target = 6\n    return target\n",
    }, scope=["app/**"])
    assert "app/spacing.py +1 -1 (whitespace only)" in pack
    diff = pack.split("```diff\n", 1)[1].split("\n```", 1)[0]
    assert "spacing.py" not in diff
    assert "far context" in diff


def test_review_diff_limit_and_stdout_full_pack_location(proj):
    from fusion_core.cli import _review_stdout

    _, _, small = make_pack(proj, {"app/small.py": "VALUE = 1\n"})
    assert "```diff" in small and "Diff omitted" not in small
    huge = "".join(f"VALUE_{index} = {index}\n" for index in range(700))
    task, _, large = make_pack(proj, {
        "app/z-large.py": huge,
        "app/a-small.py": "VALUE = 1\n",
    })
    assert "app/a-small.py" in large and "```diff" in large
    assert "Not attached: app/z-large.py (+700 -0)" in large
    assert "Diff of files not attached: git -C " in large
    assert "Diff omitted" not in large
    text = ("## Sidekick\n" + "x" * 20500 + "\n```diff\ndiff --git a/first.py b/first.py\nx\n```\n"
            + "```diff\ndiff --git a/last.py b/last.py\n" + "x\n" * 50 + "```\n")
    output = _review_stdout(text, limit=len(text) - 30,
                            pack_path=f"fusion/tasks/{task['id']}/review-1.md")
    assert len(output) <= len(text) - 30
    assert "```diff\ndiff --git a/first.py b/first.py" in output
    assert "```diff\ndiff --git a/last.py b/last.py" not in output
    assert "Not printed: last.py (full pack: fusion/tasks/T1/review-1.md)" in output


def test_diff_blocks_follow_modified_added_document_order_and_copyable_command(proj, tmp_path):
    proj.write("app/b_mod.py", "VALUE = 1\n")
    proj.write("app/c_mod.py", "VALUE = 1\n")
    proj.commit("review baseline")
    long_added = "".join(f"VALUE_{i} = '{'x' * 180}'\n" for i in range(500))
    _, _, pack = make_pack(proj, {
        "app/b_mod.py": "VALUE = 2\n",
        "app/c_mod.py": "VALUE = 2\n",
        "app/a_new.py": long_added,
        "README.md": "# Updated\n",
    })
    b = pack.index("diff --git a/app/b_mod.py")
    c = pack.index("diff --git a/app/c_mod.py")
    readme = pack.index("diff --git a/README.md")
    assert b < c < readme
    assert "Not attached: app/a_new.py" in pack
    command = next(line.split(": ", 1)[1] for line in pack.splitlines()
                   if line.startswith("Diff of files not attached:"))
    other = tmp_path / "different-working-directory"
    other.mkdir()
    result = subprocess.run(command, check=False, shell=True, cwd=other, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "diff --git a/app/a_new.py" in result.stdout
    assert "diff --git a/app/b_mod.py" not in result.stdout
    assert "diff --git a/app/c_mod.py" not in result.stdout
    assert "diff --git a/README.md" not in result.stdout


def test_plain_diffs_attach_before_optional_function_context_expansion(proj):
    original = "def compute():\n" + "".join(f"    value_{i} = '{'x' * 100}'\n" for i in range(150))
    changed = original.replace("value_75 =", "value_75 = 1 +", 1)
    for path in ("app/one.py", "app/two.py", "app/three.py"):
        proj.write(path, original)
    proj.commit("large functions baseline")
    _, _, pack = make_pack(proj, {path: changed for path in (
        "app/one.py", "app/two.py", "app/three.py")})
    assert all(f"diff --git a/{path}" in pack for path in ("app/one.py", "app/two.py", "app/three.py"))
    assert "Not attached:" not in pack


def test_char_budget_skips_large_plain_diffs_without_stdout_fallback(proj):
    from fusion_core import util
    from fusion_core.cli import _review_stdout

    long_line = "VALUE = '" + "x" * 3500 + "'\n"
    _, _, pack = make_pack(proj, {
        f"app/long_{index}.py": long_line.replace("VALUE", f"VALUE_{index}") for index in range(10)
    })
    assert len(pack) <= util.STDOUT_CHARS
    output = _review_stdout(pack, pack_path="fusion/tasks/T1/review-1.md")
    assert "Not printed:" not in output
    command = next(line for line in pack.splitlines() if line.startswith("Diff of files not attached:"))
    assert "app/long_" in command


def test_unattached_path_with_space_is_quoted_in_copyable_command(proj, tmp_path):
    _, _, pack = make_pack(proj, {
        "app/with space.py": "VALUE = 1\n" + "".join(f"VALUE_{i} = {i}\n" for i in range(700))
    })
    command = next(line.split(": ", 1)[1] for line in pack.splitlines()
                   if line.startswith("Diff of files not attached:"))
    assert '"app/with space.py"' in command
    other = tmp_path / "space-command-cwd"
    other.mkdir()
    result = subprocess.run(command, check=False, shell=True, cwd=other, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "diff --git a/app/with space.py b/app/with space.py" in result.stdout


def test_import_only_and_renamed_files_are_folded(proj):
    proj.write("app/imports.py", "import os\n")
    proj.write("app/oldname.py", "def keep():\n    return 'same content'\n")
    proj.commit("baseline mechanical files")
    _, _, pack = make_pack(proj, {
        "app/imports.py": "import sys\n",
        "app/oldname.py": None,
        "app/newname.py": "def keep():\n    return 'same content'\n",
    }, scope=["app/**"])
    assert "app/imports.py +1 -1 (imports only)" in pack
    assert "app/newname.py +0 -0 (renamed from app/oldname.py (100% similar))" in pack
    assert "```diff" not in pack


def test_struggle_signals_and_round_limit_next_step(proj):
    cfg = {"max_change_rounds": 3}
    failed = {"name": "Plan check 1", "cmd": "python check.py", "passed": False, "restored": None}
    task = {"id": "T1", "state": "in_review", "candidates": ["T1.c1", "T1.c2"],
            "signals": [{"kind": "blocked"}, {"kind": "blocked"}], "change_rounds": 3,
            "latest_report": {}}
    state = {"candidates": {
        "T1.c1": {"cand": "T1.c1", "checks": {"results": [failed]}},
        "T1.c2": {"cand": "T1.c2", "checks": {"results": [failed]}},
    }}
    signals = aq.struggle_signals(task, state, cfg)
    assert signals == [
        "the same check failed on T1.c1 and T1.c2: Plan check 1 (python check.py)",
        "the sidekick stopped 2 times",
        "revision rounds reached the limit (3/3)",
    ]
    text = aq.next_step_text(task, {"results": [failed]}, state, cfg)
    assert text.startswith("Next: ask the user whether to allow more revision rounds")
    assert "revision rounds reached the limit (3/3)" in text
    assert f"run {CMD} takeover" in text
    green = {**task, "signals": [], "candidates": ["T1.c2"]}
    assert aq.next_step_text(green, {"results": []}, state, cfg) == f"Next: {CMD} accept (revision rounds are used up)"


def test_no_struggle_keeps_the_existing_next_step(proj):
    task = {"id": "T1", "state": "in_review", "signals": [], "change_rounds": 0,
            "latest_report": {}}
    assert aq.next_step_text(task, {"results": []}, {"candidates": {}}, {"max_change_rounds": 3}) == (
        f"Next: {CMD} accept (or {CMD} revise - to request changes)"
    )
