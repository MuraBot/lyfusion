"""Validation for the public four-field plan and five-field Codex report."""
from __future__ import annotations

import re

from .util import FusionError

PLAN_FIELDS = ("goal", "brief", "checks", "scope")
REPORT_FIELDS = ("status", "summary", "questions", "choices", "problems")


def plan(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise FusionError("计划要是 JSON 对象")
    unknown = sorted(set(raw) - set(PLAN_FIELDS))
    if unknown:
        raise FusionError(f"计划只允许字段: {', '.join(PLAN_FIELDS)};不允许: {', '.join(unknown)}")
    goal = raw.get("goal")
    if not isinstance(goal, str) or not goal.strip() or "\n" in goal.strip() or "\r" in goal.strip():
        raise FusionError("goal 要是非空的一行文字")
    brief = raw.get("brief")
    if not isinstance(brief, str) or not brief.strip():
        raise FusionError("brief 要是非空字符串")
    checks, scope = raw.get("checks", []), raw.get("scope", [])
    if not isinstance(checks, list):
        raise FusionError("checks 要是列表")
    if not isinstance(scope, list) or any(not isinstance(g, str) or not g for g in scope):
        raise FusionError("scope 要是 glob 字符串列表")
    clean_checks = []
    for index, check in enumerate(checks, 1):
        if not isinstance(check, dict) or set(check) - {"run", "expect"}:
            raise FusionError(f"checks[{index - 1}] 只允许 run 和 expect")
        if not isinstance(check.get("run"), str) or not check["run"].strip():
            raise FusionError(f"checks[{index - 1}].run 要是非空字符串")
        expect = check.get("expect", 0)
        if isinstance(expect, bool) or not isinstance(expect, (int, str)):
            raise FusionError(f"checks[{index - 1}].expect 要是整数或正则字符串")
        if isinstance(expect, str):
            try:
                re.compile(expect)
            except re.error as exc:
                raise FusionError(f"checks[{index - 1}].expect 正则无效:{exc}") from exc
        clean_checks.append({"run": check["run"], "expect": expect})
    return {"goal": goal.strip(), "brief": brief, "checks": clean_checks, "scope": scope}


def report(raw) -> tuple[dict, list[str]]:
    problems = []
    if not isinstance(raw, dict):
        msg = "报告不是 JSON 对象"
        return {"status": "blocked", "summary": "", "questions": [], "choices": [], "problems": [msg]}, [msg]
    out = {key: raw.get(key) for key in REPORT_FIELDS}
    if out["status"] not in ("done", "blocked"):
        problems.append("status 要是 done 或 blocked")
        out["status"] = "done"
    if not isinstance(out["summary"], str) or not out["summary"].strip():
        problems.append("缺少 summary")
        out["summary"] = ""
    for key in ("questions", "choices", "problems"):
        if out[key] is None:
            problems.append(f"缺少 {key}")
            out[key] = []
        elif not isinstance(out[key], list):
            problems.append(f"{key} 要是列表")
            out[key] = []
    for question in out["questions"]:
        if not isinstance(question, dict) or not question.get("text"):
            problems.append("questions 里每条要有 text")
    return out, problems
