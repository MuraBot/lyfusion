"""Pure run statistics derived only from Codex events.jsonl events."""
from __future__ import annotations

import re
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


def metrics(events: list[dict], started: str | None, codex_version: str | None,
            config: dict | None = None, *, ended_at: float | None = None) -> dict:
    """Return durable run metrics from events and the run's timestamps."""
    start = timestamp(started)
    end = ended_at if ended_at is not None else time.time()
    duration = round(max(0, end - start), 1) if start else 0.0
    return {"duration": duration, "runstats": summarize(events, config),
            "codex_version": codex_version}
