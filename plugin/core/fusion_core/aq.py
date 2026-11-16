"""aq input parsing and task artifact formatting."""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import gitops, validate
from .util import CMD, FusionError, any_match, git


def read_input(value: str | None, stdin) -> str:
    if not value:
        raise FusionError("缺少输入文件或 - (标准输入)")
    if value == "-":
        return stdin.buffer.read().decode("utf-8-sig")
    return Path(value).read_bytes().decode("utf-8-sig")


def parse_plan(text: str) -> dict:
    if not text.lstrip("\ufeff \t\r\n").startswith("{"):
        return validate.plan(_markdown_plan(text))
    try:
        return validate.plan(json.loads(text))
    except json.JSONDecodeError as exc:
        raise FusionError(f"计划不是合法的 JSON:{exc}") from exc


def _markdown_plan(text: str) -> dict:
    """把 Markdown 计划转换成四字段计划。"""
    text = text.lstrip("\ufeff \t\r\n")
    lines = text.splitlines()
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first is None:
        raise FusionError('Markdown 计划第一行要是 "# 一句话目标";也可以用 JSON(第一个字符是 {)')
    goal_match = re.fullmatch(r"#\s+(.+?)\s*", lines[first])
    if not goal_match or not goal_match.group(1).strip():
        raise FusionError('Markdown 计划第一行要是 "# 一句话目标";也可以用 JSON(第一个字符是 {)')
    goal = goal_match.group(1).strip()

    reserved: dict[str, list[str]] = {}
    removed = {first}
    section: str | None = None
    fence: str | None = None
    heading = re.compile(r"^#{1,6}\s+")
    reserved_heading = re.compile(r"^## (scope|checks)\s*$", re.IGNORECASE)
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if fence:
            if section:
                removed.add(index)
            if stripped.startswith(fence):
                fence = None
            continue
        if stripped.startswith(("```", "~~~")):
            fence = stripped[:3]
            if section:
                removed.add(index)
            continue
        if heading.match(line):
            match = reserved_heading.fullmatch(line)
            if match:
                name = match.group(1).lower()
                if name in reserved:
                    raise FusionError(f"## {name} 一节只能写一次")
                reserved[name] = []
                section = name
                removed.add(index)
                continue
            section = None
        if section:
            removed.add(index)
            if not line.strip():
                continue
            item_match = re.fullmatch(r"\s*[-*]\s+(.+?)\s*", line)
            if not item_match:
                raise FusionError(f'## {section} 一节每行写 "- 项":{line}')
            item = item_match.group(1).strip()
            if len(item) >= 2 and item.startswith("`") and item.endswith("`"):
                item = item[1:-1].strip()
            if not item:
                raise FusionError(f'## {section} 一节每行写 "- 项":{line}')
            reserved[section].append(item)

    brief_lines = [line for index, line in enumerate(lines) if index not in removed]
    while brief_lines and not brief_lines[0].strip():
        brief_lines.pop(0)
    while brief_lines and not brief_lines[-1].strip():
        brief_lines.pop()
    plan = {"goal": goal, "brief": "\n".join(brief_lines)}
    if "scope" in reserved:
        plan["scope"] = reserved["scope"]
    if "checks" in reserved:
        plan["checks"] = [{"run": command} for command in reserved["checks"]]
    return plan


def decisions_text(root: Path) -> str:
    path = root / "fusion" / "decisions.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def save_history(root: Path, task: str, name: str, text: str) -> Path:
    folder = root / "fusion" / "tasks" / task
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def _is_test_path(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    name = parts[-1]
    return "tests" in parts or (name.startswith("test_") and name.endswith(".py")) or "_test." in name or ".test." in name


def _report_brief_check(report: dict) -> list[dict] | None:
    value = report.get("brief_check")
    if not isinstance(value, list):
        return None
    valid = []
    for item in value:
        if (not isinstance(item, dict) or set(item) != {"item", "status", "where", "why"}
                or not all(isinstance(item.get(key), str) for key in ("item", "status", "where", "why"))
                or item["status"] not in ("met", "differs", "not_done")):
            return None
        if item["where"] and not re.fullmatch(r".+:\d+", item["where"]):
            return None
        valid.append(item)
    return valid


def _diff(root: Path, base: str, commit: str, *args: str) -> str:
    if "--" in args:
        split = args.index("--")
        command = (*args[:split], base, commit, *args[split:])
    else:
        command = (*args, base, commit)
    return git("diff", *command, cwd=root)


def _changed_line_kinds(diff: str) -> list[str]:
    return [line[1:] for line in diff.splitlines()
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]


def _import_line(line: str) -> bool:
    return bool(re.match(
        r"^\s*(?:from\s+\S+\s+import\b|import\s+\S|export\s+.*\s+from\s+|"
        r"const\s+\w+\s*=\s*require\()", line
    ))


def _signature(line: str) -> tuple[str, str] | None:
    patterns = (
        r"^\s*(?:async\s+)?def\s+([A-Za-z]\w*)\s*\(.*$",
        r"^\s*export\s+(?:async\s+)?function\s+([A-Za-z]\w*)\s*\(.*$",
    )
    for pattern in patterns:
        match = re.match(pattern, line)
        if match and not match.group(1).startswith("_"):
            return match.group(1), line.strip()
    return None


def _engine_scan(root: Path, candidate: dict, check: dict, files: list[dict]) -> list[str]:
    hits = []
    for path in check.get("out_of_scope", []):
        hits.append(f"Out of scope: {path}")
    base, commit = candidate["base"], candidate["commit"]
    for item in files:
        path = item["path"]
        if _is_test_path(path):
            continue
        diff_paths = ("-M", "--", item["old"], path) if item["status"] == "R" else ("--", path)
        diff = _diff(root, base, commit, "--unified=0", *diff_paths)
        removed, added = {}, {}
        for line in diff.splitlines():
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                parsed = _signature(line[1:])
                if parsed:
                    (added if line[0] == "+" else removed).setdefault(parsed[0], []).append(parsed[1])
        for name in sorted(removed.keys() | added.keys()):
            old, new = removed.get(name, []), added.get(name, [])
            if old and new:
                for before, after in zip(old, new):
                    hits.append(f"{name}: {before} {chr(0x2192)} {after}")
                for line in old[len(new):]:
                    hits.append(f"removed: {name}: {line}")
                for line in new[len(old):]:
                    hits.append(f"added: {name}: {line}")
            elif old:
                hits.extend(f"removed: {name}: {line}" for line in old)
            else:
                hits.extend(f"added: {name}: {line}" for line in new)
    for path, line in gitops.added_lines(root, candidate["base"], candidate["commit"]):
        if re.search(r"\b(?:TODO|FIXME|XXX)\b", line):
            hits.append(f"Marker: {path}: {line.strip()}")
    return hits


def _rename_note(root: Path, base: str, commit: str, item: dict) -> str:
    if item["status"] != "R":
        return ""
    summary = _diff(root, base, commit, "--summary", "-M", "--", item["old"], item["path"])
    match = re.search(r"similarity index (\d+)%", summary) or re.search(r"\((\d+)%\)", summary)
    similarity = f"{match.group(1)}% similar" if match else "similarity unavailable"
    return f"(renamed from {item['old']} ({similarity}))"


def _file_facts(root: Path, candidate: dict, scope: list[str]) -> tuple[list[dict], list[str]]:
    base, commit = candidate["base"], candidate["commit"]
    files = gitops.changed_files(root, base, commit)
    facts, diff_files = [], []
    for item in files:
        path = item["path"]
        stat_paths = (item["old"], path) if item["status"] == "R" else (path,)
        stat = _diff(root, base, commit, "--numstat", "-M", "--", *stat_paths)
        stat_line = next((line for line in stat.splitlines() if "\t" in line), "0\t0\t" + path)
        added, deleted = stat_line.split("\t", 2)[:2]
        suffix = " (out of scope)" if scope and not any_match(path, scope) else ""
        fold = ""
        file_diff = _diff(root, base, commit, "--", path)
        if file_diff and not _diff(root, base, commit, "-w", "--", path):
            fold = "(whitespace only)"
        else:
            fold = _rename_note(root, base, commit, item)
            changed = _changed_line_kinds(_diff(root, base, commit, "--unified=0", "--", path))
            if changed and all(_import_line(line) for line in changed):
                fold = (fold + " " if fold else "") + "(imports only)"
        facts.append({"item": item, "path": path, "added": added, "deleted": deleted,
                      "suffix": suffix, "fold": fold})
        if not _is_test_path(path) and not fold:
            diff_files.append(path)
    return facts, diff_files


def _assertion_lines(root: Path, candidate: dict, files: list[dict]) -> list[str]:
    rows = []
    for item in files:
        path = item["path"]
        if not _is_test_path(path):
            continue
        diff = _diff(root, candidate["base"], candidate["commit"], "--unified=3", "--", path)
        source = git("show", f"{candidate['commit']}:{path}", cwd=root, check=False)
        if isinstance(source, tuple):
            source = source[1] if source[0] == 0 else ""
        source_lines = source.splitlines()
        current_test = "test_module"
        pending = []
        for line in diff.splitlines():
            if line.startswith("@@"):
                match = re.search(r"\+(\d+)(?:,\d+)?", line)
                line_no = int(match.group(1)) if match else 1
                context_match = re.search(r"(?:async\s+)?def\s+(test_\w+)\s*\(", line)
                if context_match:
                    current_test = context_match.group(1)
                else:
                    for source_line in source_lines[:max(0, line_no - 1)]:
                        func = re.match(r"\s*(?:async\s+)?def\s+(test_\w+)\s*\(", source_line)
                        if func:
                            current_test = func.group(1)
                continue
            if line.startswith(("+++", "---")):
                continue
            content = line[1:] if line[:1] in ("+", "-", " ") else ""
            func = re.match(r"\s*(?:async\s+)?def\s+(test_\w+)\s*\(", content)
            if func:
                current_test = func.group(1)
            if not line.startswith("+"):
                continue
            stripped = content.strip()
            if stripped.startswith(("assert", "with pytest.raises", "self.assert", "expect(")):
                pending.append((f"{path}::{current_test}", stripped))
        rows.extend(pending)
    lines = []
    for group in dict.fromkeys(group for group, _ in rows):
        lines.append(group)
        lines.extend(f"  {text}" for name, text in rows if name == group)
    if len(rows) > 60:
        kept = []
        remaining = 60
        for group in dict.fromkeys(group for group, _ in rows):
            group_rows = [(name, text) for name, text in rows if name == group]
            if remaining <= 0:
                break
            kept.append(group)
            take = group_rows[:remaining]
            kept.extend(f"  {text}" for _, text in take)
            remaining -= len(take)
        lines = kept + [f"{chr(0x2026)} {len(rows) - 60} more"]
    return lines


def review_pack(root: Path, task: dict, state: dict, round_no: int) -> str:
    latest_run = (task.get("runs") or [None])[-1]
    failed = next(
        (signal for signal in task.get("signals", [])
         if signal.get("kind") == "candidate_failed" and signal.get("run") == latest_run),
        None,
    )
    candidate = None if failed else state["candidates"].get(task.get("latest"))
    check = candidate.get("checks") or {} if candidate else {}
    report = task.get("latest_report") or {}
    brief_check = _report_brief_check(report)
    lines = [f"# {task['id']} Review (round {round_no})", f"Goal: {(task.get('plan') or {}).get('goal', '')}"]

    deviations = [item for item in brief_check or [] if item["status"] in ("differs", "not_done")]
    if deviations:
        lines.extend(["", "## Differs from brief"])
        for item in deviations:
            lines.append(f"- {item['status']}: {item['item']} ({item['where'] or 'location not provided'}): {item['why']}")

    lines.extend(["", "## Checks"])
    for result in check.get("results", []):
        if result.get("restored") is not None:
            continue
        status = "PASS" if result["passed"] else "FAIL"
        lines.append(f"- {result['name']}: `{result['cmd']}` {status} (exit {result['exit']})")
        if not result["passed"]:
            lines.extend(f"  {line}" for line in result.get("tail", "").splitlines()[-20:])
    if task.get("fix_attempts", 0) > 0:
        lines.append(f"- Auto-fix attempts: {task['fix_attempts']}")

    violations = check.get("violations", [])
    if violations:
        lines.extend(["", "## Violations"])
        lines.extend(f"- {item['why']} ({item['where']})" for item in violations)
        lines.append(f'Acceptance requires `{CMD} accept --waive "reason"`; for prohibited actions, quote the user\'s words.')

    facts, diff_files = _file_facts(root, candidate, (task.get("plan") or {}).get("scope") or []) if candidate else ([], [])
    scan = _engine_scan(root, candidate, check, [fact["item"] for fact in facts]) if candidate else []
    if scan:
        lines.extend(["", "## Engine scan", *[f"- {hit}" for hit in scan]])

    blocked = task.get("state") == "blocked" or report.get("status") == "blocked"
    lines.extend(["", "## Sidekick", f"Status: {'blocked' if blocked else 'done'}"])
    if report.get("summary"):
        lines.append(f"Summary: {report['summary']}")
    elif blocked:
        run_id = (task.get("runs") or ["unknown"])[-1]
        lines.append(f"Run did not finish cleanly; see fusion/runs/{run_id}/.")
    report_text = " ".join(str(value) for value in (report.get("summary", ""), *report.get("problems", []))).lower()
    mentions_test = any(marker in report_text for marker in ("test", "pytest"))
    mentions_failure = any(marker in report_text for marker in ("failed", "failure", "did not pass"))
    if check.get("passed") and mentions_test and mentions_failure:
        lines.append("The sidekick reported a test failure, but the engine checks passed; trust the engine checks.")
    for question in report.get("questions", []):
        lines.append(f"- {'[blocking] ' if question.get('blocking') else ''}Question: {question.get('text', '')}")
    for choice in report.get("choices", []):
        if isinstance(choice, dict):
            lines.append(f"- Choice: {choice.get('what', '')}" + (f" (why: {choice['why']})" if choice.get("why") else ""))
        else:
            lines.append(f"- Choice: {choice}")
    for problem in report.get("problems", []):
        lines.append(f"- Known issue: {problem}")
    if brief_check is None:
        lines.append("Brief check: not provided")
    else:
        met = [f"{item['item']} ({item['where']})" if item["where"] else item["item"]
               for item in brief_check if item["status"] == "met"]
        lines.append("Brief check: met - " + ("; ".join(met) if met else "no met items"))

    if facts and any(_is_test_path(fact["path"]) for fact in facts):
        lines.extend(["", "## Changed test expectations"])
        old_test = next((result for result in check.get("results", [])
                         if result.get("restored") is not None), None)
        if old_test and not old_test.get("passed"):
            run = state.get("runs", {}).get(candidate.get("run"), {})
            log = Path(run["dir"]) / "checks" / "old-tests.log" if run.get("dir") else None
            failed_names = []
            output_lines = old_test.get("tail", "").splitlines()
            if log and log.exists():
                output_lines = log.read_text(encoding="utf-8", errors="replace").splitlines() + output_lines
            if output_lines:
                for line in output_lines:
                    match = re.search(r"(?:FAILED|ERROR)\s+([^\s]+::[^\s]+)", line)
                    unittest_match = re.search(r"(?:FAIL|ERROR):\s+(\w+)\s+\(([^)]+)\)", line)
                    name = match.group(1) if match else None
                    if unittest_match:
                        test_name = unittest_match.group(1)
                        modules = unittest_match.group(2).split(".")
                        path = next((fact["path"] for fact in facts
                                     if Path(fact["path"]).stem in modules), None)
                        module = Path(path).stem if path else modules[-1]
                        name = f"{path}::{test_name}" if path else f"{module}::{test_name}"
                    if name and name not in failed_names:
                        failed_names.append(name)
            if failed_names:
                lines.extend(f"Old test failed on new code: {name}" for name in failed_names)
        assertions = _assertion_lines(root, candidate, [fact["item"] for fact in facts])
        lines.extend(assertions or ["No added or changed assertion lines found."])

    lines.extend(["", "## Changes"])
    if candidate:
        lines.append(f"Candidate: `{candidate['commit'][:10]}`; base: `{candidate['base'][:10]}`")
        for fact in facts:
            fold = f" {fact['fold']}" if fact["fold"] else ""
            lines.append(f"- {fact['path']} +{fact['added']} -{fact['deleted']}{fact['suffix']}{fold}")
        selected = ""
        omitted_count = 0
        if diff_files:
            selected = _diff(root, candidate["base"], candidate["commit"], "-W", "--", *diff_files)
            if len(selected.splitlines()) > 400:
                plain = _diff(root, candidate["base"], candidate["commit"], "--", *diff_files)
                if len(plain.splitlines()) <= 400:
                    selected = plain
                else:
                    omitted_count = len(plain.splitlines())
                    selected = ""
        if selected:
            lines.extend(["", "```diff", selected.rstrip(), "```"])
        elif omitted_count:
            lines.append(f"Diff omitted ({omitted_count} lines): git diff {candidate['base']} {candidate['commit']}")
    elif failed:
        lines.append(f"Candidate was not created: {failed.get('detail', '')}")
        lines.append(f"Next: {CMD} revise - (describe the fix) or {CMD} cancel")
        return "\n".join(lines) + "\n"
    else:
        lines.append("No code candidate.")
    lines.append(next_step_text(task, check))
    return "\n".join(lines) + "\n"


def next_step_text(task: dict, check: dict) -> str:
    report = task.get("latest_report") or {}
    if task.get("state") == "blocked" or report.get("status") == "blocked":
        return f"Next: {CMD} revise - (answer the sidekick's questions)"
    failed = any(not result.get("passed") and result.get("restored") is None
                 for result in check.get("results", []))
    if failed or check.get("violations"):
        return f"Next: {CMD} revise - (or, after review, {CMD} accept --waive \"reason\")"
    return f"Next: {CMD} accept (or {CMD} revise - to request changes)"
