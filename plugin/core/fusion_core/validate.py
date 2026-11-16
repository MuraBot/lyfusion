"""Validation for the public four-field plan and five-field Codex report."""
from __future__ import annotations

import re

from .util import FusionError

PLAN_FIELDS = ("goal", "brief", "checks", "scope")
REPORT_FIELDS = ("status", "summary", "questions", "choices", "problems", "brief_check")


def plan(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise FusionError("Plan must be a JSON object")
    unknown = sorted(set(raw) - set(PLAN_FIELDS))
    if unknown:
        raise FusionError(f"Plan allows only these fields: {', '.join(PLAN_FIELDS)}; unexpected: {', '.join(unknown)}")
    goal = raw.get("goal")
    if not isinstance(goal, str) or not goal.strip() or "\n" in goal.strip() or "\r" in goal.strip():
        raise FusionError("goal must be a non-empty single line of text")
    brief = raw.get("brief")
    if not isinstance(brief, str) or not brief.strip():
        raise FusionError("brief must be a non-empty string")
    checks, scope = raw.get("checks", []), raw.get("scope", [])
    if not isinstance(checks, list):
        raise FusionError("checks must be a list")
    if not isinstance(scope, list) or any(not isinstance(g, str) or not g for g in scope):
        raise FusionError("scope must be a list of glob strings")
    clean_checks = []
    for index, check in enumerate(checks, 1):
        if not isinstance(check, dict) or set(check) - {"run", "expect"}:
            raise FusionError(f"checks[{index - 1}] allows only run and expect")
        if not isinstance(check.get("run"), str) or not check["run"].strip():
            raise FusionError(f"checks[{index - 1}].run must be a non-empty string")
        expect = check.get("expect", 0)
        if isinstance(expect, bool) or not isinstance(expect, (int, str)):
            raise FusionError(f"checks[{index - 1}].expect must be an integer or regex string")
        if isinstance(expect, str):
            try:
                re.compile(expect)
            except re.error as exc:
                raise FusionError(f"checks[{index - 1}].expect has an invalid regex:{exc}") from exc
        clean_checks.append({"run": check["run"], "expect": expect})
    return {"goal": goal.strip(), "brief": brief, "checks": clean_checks, "scope": scope}


def report(raw) -> tuple[dict, list[str]]:
    problems = []
    if not isinstance(raw, dict):
        msg = "Report must be a JSON object"
        return {"status": "blocked", "summary": "", "questions": [], "choices": [],
                "problems": [msg], "brief_check": None}, [msg]
    out = {key: raw.get(key) for key in REPORT_FIELDS}
    if out["status"] not in ("done", "blocked"):
        problems.append("status must be done or blocked")
        out["status"] = "done"
    if not isinstance(out["summary"], str) or not out["summary"].strip():
        problems.append("missing summary")
        out["summary"] = ""
    for key in ("questions", "choices", "problems"):
        if out[key] is None:
            problems.append(f"missing {key}")
            out[key] = []
        elif not isinstance(out[key], list):
            problems.append(f"{key} must be a list")
            out[key] = []
    for question in out["questions"]:
        if not isinstance(question, dict) or not question.get("text"):
            problems.append("each question must have text")
    brief_check = raw.get("brief_check")
    if isinstance(brief_check, list) and all(
        isinstance(item, dict)
        and set(item) == {"item", "status", "where", "why"}
        and isinstance(item["item"], str)
        and item["status"] in ("met", "differs", "not_done")
        and isinstance(item["where"], str)
        and (item["where"] == "" or re.fullmatch(r".+:\d+", item["where"]))
        and isinstance(item["why"], str)
        for item in brief_check
    ):
        out["brief_check"] = brief_check
    else:
        out["brief_check"] = None
    return out, problems
