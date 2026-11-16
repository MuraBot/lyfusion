"""Repository-specific lint rules that are not covered by existing tools."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

RULE_P7 = "P7"
RULE_C1 = "C1"
RULE_T3 = "T3"
RULE_C4 = "C4"
P7_CHARS = {0xFEFF, 0x200B, 0x200C, 0x200D, 0x2060}
C4_PATTERN = re.compile(r"\?{3,}")
T3_CLOCK = re.compile(r"\$\.clock")
T3_CLAUDE_PATH = re.compile(r"(?:~[/\\]\.claude(?:[/\\]|$)|[/\\]\.claude[/\\])")


def _line_number(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def _hit(path: str, text: str, position: int, rule: str, message: str) -> str:
    return f"{path}:{_line_number(text, position)}: {rule} {message}"


def _regex_literal_starts(source: str, position: int) -> bool:
    previous = source[:position].rstrip()
    if not previous:
        return True
    return previous[-1] in "=(:,[!&|?{};>" or previous.endswith("return")


def _tracked_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
    )
    return [os.fsdecode(path) for path in result.stdout.split(b"\0") if path]


def _text_files(root: Path):
    for relative in _tracked_paths(root):
        path = root / relative
        try:
            raw = path.read_bytes()
            if b"\0" in raw:
                continue
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        yield relative.replace("\\", "/"), path, text


def _without_comments_and_strings(source: str) -> tuple[str, list[tuple[str, int]]]:
    """Mask comments and string bodies while preserving code offsets and line breaks."""
    output = list(source)
    literals = []
    quote = None
    quote_start = 0
    literal = []
    escaped = False
    regex_class = False
    state = "code"
    index = 0
    while index < len(source):
        char = source[index]
        following = source[index:index + 2]
        if state == "line":
            if char == "\n":
                state = "code"
            else:
                output[index] = " "
            index += 1
            continue
        if state == "block":
            if following == "*/":
                output[index] = output[index + 1] = " "
                index += 2
                state = "code"
            else:
                if char != "\n":
                    output[index] = " "
                index += 1
            continue
        if state == "regex":
            if char != "\n":
                output[index] = " "
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "[":
                regex_class = True
            elif char == "]":
                regex_class = False
            elif char == "/" and not regex_class:
                state = "code"
            index += 1
            continue
        if quote is not None:
            if char != "\n":
                output[index] = " "
            if escaped:
                literal.append(char)
                escaped = False
            elif char == "\\":
                literal.append(char)
                escaped = True
            elif char == quote:
                literals.append(("".join(literal), quote_start))
                quote = None
            else:
                literal.append(char)
            index += 1
            continue
        if following == "//":
            output[index] = output[index + 1] = " "
            index += 2
            state = "line"
        elif following == "/*":
            output[index] = output[index + 1] = " "
            index += 2
            state = "block"
        elif char == "/" and _regex_literal_starts(source, index):
            output[index] = " "
            index += 1
            regex_class = False
            escaped = False
            state = "regex"
        elif char in "\"'`":
            quote = char
            quote_start = index
            literal = []
            output[index] = " "
            index += 1
        else:
            index += 1
    if quote is not None:
        literals.append(("".join(literal), quote_start))
    return "".join(output), literals


def _c1_pattern(username: str) -> re.Pattern:
    prefix = r"(?:[A-Za-z]:|/[A-Za-z])[/\\]+Users[/\\]+"
    return re.compile(prefix + re.escape(username) + r"(?!\w)", re.IGNORECASE)


def _file_hits(relative: str, path: Path, text: str, username: str | None) -> list[str]:
    hits = []
    if path.suffix == ".py":
        for position, char in enumerate(text):
            codepoint = ord(char)
            if codepoint in P7_CHARS and not (codepoint == 0xFEFF and position == 0):
                hits.append(_hit(relative, text, position, RULE_P7,
                                 f"invisible character U+{codepoint:04X}; write it as an escape"))

    if username:
        pattern = _c1_pattern(username)
        for match in pattern.finditer(text):
            hits.append(_hit(relative, text, match.start(), RULE_C1,
                             r"real user directory; write C:\Users\<username>"))

    if relative.startswith("plugin/hooks/") and path.suffix in {".ts", ".tsx"}:
        code, literals = _without_comments_and_strings(text)
        t3_matches = [(match.start(), match) for match in T3_CLOCK.finditer(code)]
        t3_matches.extend((match.start(), match) for match in T3_CLAUDE_PATH.finditer(code))
        for literal, start in literals:
            if literal == ".claude":
                t3_matches.append((start, None))
            else:
                t3_matches.extend((start + match.start(), match)
                                  for match in T3_CLAUDE_PATH.finditer(literal))
        message = "mod must not use $.clock or read .claude paths (policy)"
        for position, _ in t3_matches:
            hits.append(_hit(relative, text, position, RULE_T3, message))

    for match in C4_PATTERN.finditer(text):
        hits.append(_hit(relative, text, match.start(), RULE_C4,
                         ("?" * 3) + " looks like lost encoding"))
    return hits


def find_hits(root: Path) -> list[str]:
    username = os.environ.get("USERNAME") or os.environ.get("USER")
    hits = []
    for relative, path, text in _text_files(root):
        hits.extend(_file_hits(relative, path, text, username))
    return hits


def main(root: Path | None = None) -> int:
    repo_root = root or Path(__file__).resolve().parents[1]
    hits = find_hits(Path(repo_root))
    for hit in hits:
        print(hit)
    if hits:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
