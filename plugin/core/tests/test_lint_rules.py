from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

from fusion_core import gitops
from fusion_core.checks import BUILTIN_RULES, scan_forbidden

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK_PATH = REPO_ROOT / "lint" / "check.py"
SPEC = importlib.util.spec_from_file_location("repo_lint_check", CHECK_PATH)
lint_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lint_check)


def make_repo(path: Path) -> Path:
    path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Lint test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "lint@example.invalid"], cwd=path, check=True)
    return path


def write_file(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def commit(root: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=root, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_p7_ignores_initial_bom_and_reports_zero_width_character(tmp_path, capsys):
    root = make_repo(tmp_path / "repo")
    write_file(root, "start.py", "\ufeffprint('safe')\n")
    commit(root, "initial")
    assert lint_check.main(root) == 0
    assert capsys.readouterr().out == ""

    write_file(root, "hidden.py", "value = '\u200b'\n")
    commit(root, "add invisible character")
    assert lint_check.main(root) == 1
    output = capsys.readouterr().out
    assert "hidden.py:1: P7 invisible character U+200B; write it as an escape" in output


def test_c1_matches_user_directory_forms_and_rejects_placeholders(tmp_path, monkeypatch, capsys):
    root = make_repo(tmp_path / "repo")
    monkeypatch.setenv("USERNAME", "alice")
    monkeypatch.delenv("USER", raising=False)
    first = "C:\\Users\\" + "alice" + "\\x\n"
    second = "c:/users/" + "ALICE" + "/x\n"
    placeholder = "C:\\Users\\<" + "username>\n"
    longer = "C:\\Users\\" + "alicex\n"
    write_file(root, "one.txt", first + placeholder)
    write_file(root, "two.txt", second + longer)
    commit(root, "user path cases")

    assert lint_check.main(root) == 1
    output = capsys.readouterr().out.splitlines()
    assert output == [
        r"one.txt:1: C1 real user directory; write C:\Users\<username>",
        r"two.txt:1: C1 real user directory; write C:\Users\<username>",
    ]

    write_file(root, "one.txt", placeholder)
    write_file(root, "two.txt", longer)
    commit(root, "remove user path cases")
    assert lint_check.main(root) == 0
    assert capsys.readouterr().out == ""


def test_c1_skips_when_no_username_environment_variable(tmp_path, monkeypatch, capsys):
    root = make_repo(tmp_path / "repo")
    monkeypatch.delenv("USERNAME", raising=False)
    monkeypatch.delenv("USER", raising=False)
    write_file(root, "path.txt", "C:\\Users\\alice\\x\n")
    commit(root, "user path")
    assert lint_check.main(root) == 0
    assert capsys.readouterr().out == ""


def test_t3_ignores_comments_and_url_strings_but_checks_code_and_paths(tmp_path, capsys):
    root = make_repo(tmp_path / "repo")
    write_file(root, "plugin/hooks/mod.ts", """// $.clock.after(1)
/*
 * $.clock.after(1)
 */
const url = 'http://x'
""")
    commit(root, "safe mod")
    assert lint_check.main(root) == 0
    assert capsys.readouterr().out == ""

    write_file(root, "plugin/hooks/mod.ts", "const timer = $.clock.after(1)\n")
    commit(root, "timer use")
    assert lint_check.main(root) == 1
    assert "plugin/hooks/mod.ts:1: T3 mod must not use $.clock or read .claude paths (policy)" in capsys.readouterr().out

    write_file(root, "plugin/hooks/mod.ts", "const path = '~/.claude/settings.json'\n")
    commit(root, "claude path")
    assert lint_check.main(root) == 1
    assert "plugin/hooks/mod.ts:1: T3 mod must not use $.clock or read .claude paths (policy)" in capsys.readouterr().out


def test_c4_reports_three_question_marks_but_allows_nullish_coalescing(tmp_path, capsys):
    root = make_repo(tmp_path / "repo")
    write_file(root, "notes.txt", "a " + "?" * 3 + " b\nx ?? y\n")
    commit(root, "question mark cases")
    assert lint_check.main(root) == 1
    assert capsys.readouterr().out.splitlines() == [
        ("notes.txt:1: C4 " + "?" * 3 + " looks like lost encoding")
    ]

    write_file(root, "notes.txt", "x ?? y\n")
    commit(root, "clean question marks")
    assert lint_check.main(root) == 0
    assert capsys.readouterr().out == ""


def test_c3_forbidden_rule_scans_only_added_lines(tmp_path):
    root = make_repo(tmp_path / "repo")
    legacy = "x = 1  # n" + "oqa" + "\n"
    write_file(root, "legacy.py", legacy)
    base = commit(root, "legacy bypass")

    write_file(root, "safe.py", "value = 1\n")
    safe_commit = commit(root, "unrelated change")
    config = json.loads((REPO_ROOT / "fusion" / "config.json").read_text(encoding="utf-8"))
    configured_lines = [
        ("fusion/config.json", line)
        for line in (REPO_ROOT / "fusion" / "config.json").read_text(encoding="utf-8").splitlines()
    ]
    assert scan_forbidden(config, [], configured_lines) == []
    unchanged_additions = gitops.added_lines(root, base, safe_commit)
    assert scan_forbidden(config, [], unchanged_additions) == []

    new_bypass = "x = 1  # n" + "oqa" + "\n"
    write_file(root, "new.py", new_bypass)
    new_commit = commit(root, "new bypass")
    additions = gitops.added_lines(root, safe_commit, new_commit)
    violations = scan_forbidden(config, [], additions)
    assert len(violations) == 1
    assert violations[0]["kind"] == "forbidden"
    assert violations[0]["why"] == "New comment that bypasses a check (lint C3)"


def test_builtin_rules_do_not_match_their_source_and_keep_examples():
    checks_path = REPO_ROOT / "plugin" / "core" / "fusion_core" / "checks.py"
    cfg = {"forbidden": []}
    source = [("plugin/core/fusion_core/checks.py", line)
              for line in checks_path.read_text(encoding="utf-8").splitlines()]
    assert scan_forbidden(cfg, [], source) == []

    examples = [
        ("git -c http.sslVerify=false clone x", None),
        ("NODE_TLS_REJECT_UNAUTHORIZED=0", None),
        ("npm config set strict-ssl false", None),
        ("pip install --trusted-host x y", None),
        ("curl -k https://x", None),
        (None, "requests.get(u, verify=False)"),
        (None, "{rejectUnauthorized: false}"),
        ("git commit --no-verify", None),
        ("git push", None),
    ]
    for (pattern, why, where), (command, diff) in zip(BUILTIN_RULES, examples, strict=True):
        hits = scan_forbidden(
            cfg,
            [{"command": command}] if command is not None else [],
            [("example.py", diff)] if diff is not None else [],
        )
        matching = [hit for hit in hits if hit["why"] == why]
        assert len(matching) == 1
        assert matching[0]["where"] == ("command" if command is not None else "example.py")
        assert ("cmd" if command is not None else "diff") in where
    assert scan_forbidden(cfg, [], [("example.py", "requests.get(u, verify=True)")]) == []
