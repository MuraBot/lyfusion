"""Pure run statistics derived only from Codex events.jsonl events."""
from __future__ import annotations

import re
import shlex
import time

from .util import timestamp

_READ = re.compile(
    r"get-content|sed\s+-n|"
    r"select-object(?=.*(?:-first|-skip|-last))",
    re.IGNORECASE,
)
_READ_COMMAND = re.compile(
    r"(?:^|[;|]|&&|\()\s*(?:gc|cat|type|head|tail)\b(?=\s|$)|"
    r"(?:^|[;|]|&&|\()\s*sed\s+-n\b(?=\s|$)",
    re.IGNORECASE,
)
_SHELL = re.compile(
    r'^\s*"?[^"\n]*powershell(?:\.exe)?"?\s+-command\s+', re.IGNORECASE
)


def _unwrap(command: str) -> str:
    command = _SHELL.sub("", command).strip()
    if len(command) >= 2 and command[0] == command[-1] and command[0] in "\'\"":
        command = command[1:-1]
    return command


def summarize(events: list[dict], config: dict | None = None) -> dict:
    """Count commands, small reads and repeats; retain concise recent command lines."""
    config = config or {}
    max_lines = config.get("small_read_lines", 80)
    test_commands = [config.get("test"), config.get("lint")]
    seen: set[str] = set()
    commands = small_reads = repeats = 0
    recent = []
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item") or {}
        if item.get("type") != "command_execution":
            continue
        commands += 1
        command = str(item.get("command") or "")
        lowered = command.lower()
        output = str(item.get("aggregated_output") or "")
        output_lines = len(output.splitlines())
        is_check = any(word in lowered for word in ("pytest", "ruff")) or any(
            text and str(text).lower() in lowered for text in test_commands
        )
        is_git_inspection = bool(re.match(r"\s*git\s+(?:status|diff)\b", _unwrap(command), re.IGNORECASE))
        repeated = False
        if not is_check and not is_git_inspection:
            repeated = command in seen
            repeats += int(repeated)
            seen.add(command)
        small = bool(_READ.search(command) or _READ_COMMAND.search(command)) and not is_check and output_lines <= max_lines
        small_reads += int(small)
        summary = _unwrap(command).replace("\r", " ").replace("\n", " ")
        summary = re.sub(r"\s+", " ", summary)[:140]
        tags = ("[碎读]" if small else "") + ("[重复]" if repeated else "")
        recent.append(
            f"{tags}{summary}(退出码 {item.get('exit_code')},输出 {output_lines} 行)"
        )
    return {"commands": commands, "small_reads": small_reads, "repeats": repeats, "recent": recent[-8:]}


_TEST_RUNNERS = ("pytest", "python -m pytest", "npm test", "vitest", "jest")
_LINTERS = ("ruff", "eslint", "flake8", "mypy", "tsc")


def _normal(command: str) -> str:
    return " ".join(command.split())


def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(_unwrap(command), posix=False)
    except ValueError:
        return _unwrap(command).split()


def _classify(command: str, config: dict) -> str:
    normalized = _normal(command)
    project_test = _normal(str(config.get("test") or ""))
    project_lint = _normal(str(config.get("lint") or ""))
    if project_test and normalized == project_test:
        return "full_tests"
    if project_lint and normalized == project_lint:
        return "lint"
    lowered = normalized.lower()
    if any(re.search(rf"(?<![\w.-]){re.escape(runner)}(?![\w.-])", lowered) for runner in _LINTERS):
        return "lint"
    tokens = _tokens(command)
    low_tokens = [token.lower() for token in tokens]
    runner = next((candidate for candidate in _TEST_RUNNERS if candidate in lowered), None)
    if runner:
        has_selector = any(token == "-k" or "::" in token or
                           token.endswith((".py", ".js", ".ts", ".jsx", ".tsx"))
                           for token in low_tokens)
        if has_selector:
            return "partial_tests"
        return "full_tests"
    return "other_cmds"


def _command_durations(events: list[dict], config: dict) -> dict[str, float]:
    starts: dict[str, float] = {}
    totals = {"full_tests": 0.0, "partial_tests": 0.0, "lint": 0.0, "other_cmds": 0.0}
    for event in events:
        item = event.get("item") or {}
        if item.get("type") != "command_execution":
            continue
        item_id = item.get("id")
        if not item_id:
            continue
        stamp = event.get("_fusion_read_at")
        if not isinstance(stamp, (int, float)):
            continue
        if event.get("type") == "item.started":
            starts[str(item_id)] = float(stamp)
        elif event.get("type") == "item.completed":
            started = starts.pop(str(item_id), None)
            if started is None:
                continue
            kind = _classify(str(item.get("command") or ""), config)
            totals[kind] += max(0.0, float(stamp) - started)
    return totals


def metrics(events: list[dict], started: str | None, codex_version: str | None,
            config: dict | None = None, *, ended_at: float | None = None) -> dict:
    """Return durable run metrics from events and the run's timestamps."""
    config = config or {}
    start = timestamp(started)
    end = ended_at if ended_at is not None else time.time()
    duration = max(0.0, end - start) if start else 0.0
    durations = _command_durations(events, config)
    command_total = sum(durations.values())
    durations["thinking"] = max(0.0, duration - command_total)
    fields = {f"{name}_seconds": round(seconds, 1)
              for name, seconds in (("full_tests", durations["full_tests"]),
                                    ("partial_tests", durations["partial_tests"]),
                                    ("lint", durations["lint"]),
                                    ("other_cmds", durations["other_cmds"]),
                                    ("thinking", durations["thinking"]))}
    return {"duration": round(duration, 1), "runstats": summarize(events, config),
            "codex_version": codex_version, **fields}
