from __future__ import annotations

from fusion_core import aq, validate


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
    huge = "".join(f"VALUE_{index} = {index}\n" for index in range(450))
    task, _, large = make_pack(proj, {"app/large.py": huge})
    assert "```diff" not in large
    assert "Diff omitted (" in large
    assert "git diff " in large
    output = _review_stdout("## Sidekick\n" + "x" * 20500 + "\n```diff\nx\n```\n",
                            pack_path=f"fusion/tasks/{task['id']}/review-1.md")
    assert len(output) <= 20000
    assert output.endswith(f"Full pack: fusion/tasks/{task['id']}/review-1.md")
    assert "```diff" not in output


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
