"""Compact assistant prompts for the four-field task interface."""

from __future__ import annotations

import re
from pathlib import Path


def model_notes(root, model: str) -> dict[str, str]:
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        return {"sidekick": "", "lead": ""}
    result = {"sidekick": [], "lead": []}
    paths = (Path(__file__).parent / "prompts" / "models" / f"{model}.md",
             Path(root) / "fusion" / "models" / f"{model}.md")
    for path in paths:
        if not path.is_file():
            continue
        section = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() == "## For the assistant":
                section = "sidekick"
            elif line.strip() == "## For the lead":
                section = "lead"
            elif line.startswith("## "):
                section = None
            elif section and line.strip():
                result[section].append(line)
    return {key: "\n".join(value) for key, value in result.items()}

REPORT_REMINDER = "Return only the final JSON report with status, summary, questions, choices, problems and brief_check; status is done or blocked."
CONTINUE_PROMPT = ("You reported blocked but listed no blocking question. If nothing blocks you, continue and finish the brief. "
                   "If something does block you, report blocked again with a question marked blocking that says what you need from the lead.")

def continue_prompt() -> str:
    return CONTINUE_PROMPT + "\n" + REPORT_REMINDER

# When continuing the same session (auto-fix, revision, or report retry), repeat only these short rules.
# The full workflow is in WORK_RULES and is sent once with the task.
FIXED_RULES = """Fixed rules:
- Complete the task in one go.
- Read whole files or large sections; one command may read several files. Do not reread only a few dozen lines at a time or repeat a command, except rerunning tests and lint after code changes.
- Mid-task, run only relevant tests (one file or one test), using the project's test options. Run the full test suite and lint once at the end.
- Return only a JSON report (status/summary/questions/choices/problems)."""

FORBIDDEN = [
    'Work only in the current station directory. Do not commit, push, or switch branches; the engine handles commits.',
    'Do not weaken or delete existing tests to make them pass, and do not change check commands. Rerun environment errors as-is; do not disable certificate checks or bypass checks or hooks (--no-verify).',
    'Do not call Claude or read ~/.claude/, Claude folders under AppData, or Codex auth.json. Do not accept agreements for the user or download unrelated files.',
]

FIXED_RULES += "\n\nDo not:\n" + "\n".join(f"- {item}" for item in FORBIDDEN)

# The complete workflow sent with every task brief.
WORK_RULES = """You are lyfusion's assistant. The lead handles design and decisions; implement the task brief below. Do not communicate with the lead during the task. Return only code changes and the final report.

## Workflow
1. Complete the brief from start to finish, moving to the next step as soon as one is done. Stop only when all work is complete or a stop condition below applies.
2. Write tests, implement the code, and run tests yourself. Before finishing, run both the project's test and lint commands and all check commands. Verify the test count: some frameworks return 0 after skipping an entire test batch, so an unexpected count is a failure. Compilation without execution is not a test.
   Read whole files or large sections; one command may read several files. Do not read only a few dozen lines at a time or repeat a command, except rerunning tests and lint after code changes.
3. Preserve existing behavior (error text, handling of null and blank lines, numbering, and output format) unless the brief asks to change it.
   Do not format the whole project or untouched files (ruff format, black, etc.). Change only what the task needs. Fix lint findings; do not bypass them with noqa.
4. Follow the brief's decisions and prohibitions. If they conflict with evidence, do not change direction; explain the conflict and evidence in problems.
5. You may choose internal structure, names, and test cases the brief leaves open; check framework source for constants and defaults. Create files implied by the brief's goal.
6. After you finish, the engine reruns tests, lint, and checks. If any fail, it will return the output for you to fix.

## When uncertain
- If a wrong guess has low cost, proceed with your recommendation and record it in questions (blocking=false), including your choice and alternatives.
- If a wrong guess has high cost (changing a public interface or data format, deleting user data, conflicting with the brief or decisions.md, or requiring new permissions or downloads), do independent work first, then stop with status=blocked and a blocking=true question.
- For environment or network errors, rerun as-is, increase the timeout, and reuse the cache. Do not disable certificate checks or skip hooks (--no-verify).

## Final report (JSON)
Include only information that cannot be seen in the repository; the lead can inspect the diff and engine check results.
- summary: one or two sentences describing what you completed.
- questions: questions for the lead, with options and your recommendation.
- choices: decisions you made that were not specified and may matter to users or other modules. Explain what you chose and why, including alternatives you did not choose. Use an empty list if there are none.
- problems: unfinished work, known problems, and any existing tests changed with the reason.

## Do not
""" + "\n".join(f"- {item}" for item in FORBIDDEN) + """

## Brief conventions
- The brief gives constraints, edge cases, done criteria, behaviour that must not change and exact test assertions. Follow its decisions; treat anything marked as a guess as a suggestion: with contrary evidence you may deviate, record it in choices with a reason.
- Before the final report, reread the brief and your work item's git diff item by item, then fill brief_check with one entry per decision, constraint and done criterion. Use met, differs (and explain why), or not_done; where must be file:line or empty.
- If the brief gives stop conditions, stop when one is met (status blocked).

## Test instructions
- Mid-task, run only relevant tests (one file or one test), using the project's options such as parallelism. Run the full suite and lint once at the end.
- The sandbox may be unable to terminate other processes or write to the system temp directory. If a test fails for either reason, explain the sandbox limitation in problems; the engine will rerun checks outside the sandbox. Do not put temporary directories (such as pytest's --basetemp) in a location that will be committed from the station."""

def _checks(plan: dict) -> str:
    return (
        "\n".join(
            f"- `{item['run']}` (expected exit {item.get('expect', 0)})"
            for item in plan.get("checks", [])
        )
        or "- (none)"
    )


def task_prompt(
    task: dict, decisions: str, handoff: str | None = None, project_cmds: list[str] | None = None,
    model_note: str = "", model: str = "",
) -> str:
    plan = task["plan"]
    parts = [WORK_RULES]
    if model_note:
        parts.append(f"## Notes for assistant {model}\n{model_note}")
    if handoff:
        parts.append("## Previous station handoff summary\n" + handoff)
    cmds = [c for c in project_cmds or [] if c]
    parts += [
        f"## Goal\n{plan['goal']}",
        f"## Brief\n{plan['brief']}",
        "## Project tests and lint\n" + ("\n".join(f"- `{c}`" for c in cmds) or "- (not configured)"),
        "## Check commands and expected results\n" + _checks(plan),
        "## File scope\n"
        + ("\n".join(f"- {g}" for g in plan.get("scope", [])) or "- (unspecified)"),
        "## Full text of fusion/decisions.md\n" + decisions,
    ]
    return "\n\n".join(parts)


def fix_prompt(failures: str, decisions: str, model_note: str = "") -> str:
    return (
        "## Check failures\n"
        + failures
        + "\n\n## Full text of fusion/decisions.md\n"
        + decisions
        + "\n\n"
        + FIXED_RULES
        + "\n"
        + REPORT_REMINDER
        + (f"\n\n{model_note}" if model_note else "")
    )


def changes_prompt(text: str, decisions: str, model_note: str = "") -> str:
    return (
        "## Lead revision request (verbatim)\n"
        + text
        + "\n\n## Full text of fusion/decisions.md\n"
        + decisions
        + "\n\n"
        + FIXED_RULES
        + "\n"
        + REPORT_REMINDER
        + (f"\n\n{model_note}" if model_note else "")
    )


def minor_fix_prompt(text: str, files: list[str]) -> str:
    allowed = "\n".join(f"- {path}" for path in files) or "- (no files)"
    return (
        "Make exactly this fix: " + text + "\n"
        "Change only these files:\n" + allowed + "\n"
        "Change at most 20 lines total (added plus deleted). Do not refactor or make any other edits.\n"
        "Then finish with the usual report.\n"
        + REPORT_REMINDER
    )


def report_prompt(previous_error: str, decisions: str) -> str:
    return (
        "Before returning the report, reread the brief and the work item's git diff item by item. Fill `brief_check` with one entry per decision, constraint and done criterion, using `met`, `differs` (explain why), or `not_done`; `where` must be `file:line` or empty.\n"
        "## Return the final report\nThe previous run did not return a valid report. Do not change the code again.\n"
        + previous_error
        + "\n\n## Full text of fusion/decisions.md\n"
        + decisions
        + "\n\n"
        + FIXED_RULES
        + "\n"
        + REPORT_REMINDER
    )


def explore_prompt(original: str, decisions: str) -> str:
    return (
        "This is read-only code exploration. Do not modify any files. Keep the entire answer, including the draft, to 150 lines or fewer. Do not write an implementation plan.\n"
        "1. Restate the lead's task and goal, then list uncertainties.\n"
        "2. Find relevant code excerpts in order of importance. For each, give `file:start-end`, explain why it matters, and quote no more than 15 source lines.\n"
        "3. Answer the lead's numbered questions (Q1~Q3; answer those present and omit this section if there are none), referring to the excerpts above. If the repository cannot answer one, check framework source or official documentation and name the source.\n"
        "4. List existing conventions and pitfalls.\n"
        "Read whole files or large sections; one command may read several files. Do not repeat the same command (except rerunning tests and lint after code changes).\n"
        "Safety: do not read `~/.claude/`, Claude folders under AppData, or Codex auth.json; do not call Claude.\n"
        "Finish with `## Draft (mechanical only)` and exactly three lists: files involved (path — one line describing what is there), suggested check commands, and verbatim signatures of functions likely to change. The draft contains no approach or recommended implementation. Keep this section within the 150-line total.\n"
        "## Lead's task (verbatim)\n"
        + original
        + "\n\n## fusion/decisions.md (full text)\n"
        + decisions
    )

def handoff_summary(state: dict, old: dict) -> str:
    lines = [f"Previous station {old['name']} tasks: {', '.join(old['tasks']) or '(none)'}"]
    if old.get("files"):
        lines.append("Files changed: " + ", ".join(old["files"][:60]))
    for task_id in old["tasks"][-3:]:
        task = state["tasks"].get(task_id)
        if task:
            lines.append(
                f"- {task_id}({task['state']}):{(task.get('plan') or {}).get('goal', '')}"
            )
            for run_id in task["runs"][-1:]:
                report = state["runs"][run_id].get("report") or {}
                lines.extend(
                    f"  Known problem: {problem}" for problem in report.get("problems") or []
                )
    return "\n".join(lines)
