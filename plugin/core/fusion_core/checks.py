"""Candidate checks and source-only forbidden-operation scanning."""
from __future__ import annotations

import re
from pathlib import Path

from . import gitops
from .util import any_match, clean_env, redact_file, run

ENV_ERROR = re.compile(r"(?i)certificate verify failed|CERTIFICATE_VERIFY_FAILED|unable to get local issuer|"
                       r"SSL: |ECONNRESET|ETIMEDOUT|ECONNREFUSED|Could not resolve host|"
                       r"Temporary failure in name resolution|getaddrinfo|Connection timed out")
BUILTIN_RULES = [
    (r"(?i)GIT_SSL_NO_VERIFY|http\.sslVerify\s*=?\s*false|sslVerify\s+false", "关闭了 git 的证书检查", "cmd diff"),
    (r"(?i)NODE_TLS_REJECT_UNAUTHORIZED\s*=?\s*['\"]?0", "关闭了 Node 的证书检查", "cmd diff"),
    (r"(?i)strict-ssl\s*[= ]\s*false", "关闭了 npm 的证书检查", "cmd diff"),
    (r"(?i)--trusted-host\b", "pip 跳过证书检查", "cmd"),
    (r"(?i)\bcurl\b[^\n]*\s(-k|--insecure)\b", "curl 跳过证书检查", "cmd"),
    (r"(?i)\bverify\s*=\s*False\b", "代码里关闭了证书检查", "cmd diff"),
    (r"(?i)rejectUnauthorized\s*:\s*false", "代码里关闭了证书检查", "diff"),
    (r"(?i)--no-verify\b", "跳过了 git 钩子", "cmd"),
    (r"\bgit\s+(push|commit|rebase|merge|switch|checkout\s+-b|branch\s+-[dD]|reset\s+--hard)\b",
     "助手执行了 git 写操作", "cmd"),
]


def _expected(expect) -> dict:
    if isinstance(expect, dict):
        return expect
    if isinstance(expect, int):
        return {"exit": expect}
    if isinstance(expect, str):
        return {"exit": 0, "regex": expect}
    return {"exit": 0}


def _expect_ok(res: dict, expect=None) -> bool:
    expect = _expected(expect)
    if res["exit"] != expect.get("exit", 0):
        return False
    out = res["output"]
    if expect.get("contains") and expect["contains"] not in out:
        return False
    if expect.get("regex") and not re.search(expect["regex"], out):
        return False
    if expect.get("passed_min") is not None:
        match = re.search(r"(\d+) passed", out)
        if not match or int(match[1]) < int(expect["passed_min"]):
            return False
    return True


def run_one(name: str, cmd: str, cwd: Path, cfg: dict, log: Path, expect=None) -> dict:
    env = clean_env(cfg["local"].get("env"))
    result = run(cmd, cwd=str(cwd), timeout=cfg.get("check_timeout", 900), env=env,
                 shell=True, out_file=log)
    retried = False
    if not _expect_ok(result, expect) and ENV_ERROR.search(result["output"]):
        retried = True
        result = run(cmd, cwd=str(cwd), timeout=cfg.get("check_timeout", 900), env=env,
                     shell=True, out_file=log)
    redact_file(log)
    passed = _expect_ok(result, expect)
    return {"name": name, "cmd": cmd, "exit": result["exit"], "passed": passed,
            "seconds": result["seconds"], "retried": retried,
            "env_error": not passed and bool(ENV_ERROR.search(result["output"])),
            "log": str(log), "tail": "\n".join(result["output"].splitlines()[-40:])}


def scan_forbidden(cfg: dict, commands: list[dict], added: list[tuple[str, str]]) -> list[dict]:
    rules = [(re.compile(pattern), reason, where) for pattern, reason, where in BUILTIN_RULES]
    rules += [(re.compile(rule["pattern"]), rule.get("why", "项目禁止的操作"), rule.get("where", "cmd diff"))
              for rule in cfg.get("forbidden") or []]
    hits = []
    for command in commands:
        source = command.get("command") or ""
        for pattern, reason, where in rules:
            if "cmd" in where and pattern.search(source):
                hits.append({"kind": "forbidden", "why": reason, "where": "命令", "detail": source[:300]})
    for path, line in added:
        for pattern, reason, where in rules:
            if "diff" in where and pattern.search(line):
                hits.append({"kind": "forbidden", "why": reason, "where": path, "detail": line.strip()[:300]})
    return hits


def plan_checks(cfg: dict, plan: dict) -> list[tuple[int, dict]]:
    """计划里的检查,去掉和项目测试、lint 完全相同(期望退出码 0)的那些:同一条命令不跑两遍、不列两行。"""
    project = {(cfg.get(k) or "").strip() for k in ("test", "lint")} - {""}
    out = []
    for i, check in enumerate(plan.get("checks") or [], 1):
        if check["run"].strip() in project and check.get("expect", 0) in (0, None):
            continue
        out.append((i, check))
    return out


def pipeline(root: Path, cfg: dict, state: dict, task: dict, candidate: dict, worktree: Path,
             run_dir: Path, commands: list[dict]) -> dict:
    logs = run_dir / "checks"
    results, violations = [], []
    base, commit = task["base"], candidate["commit"]
    changed = gitops.changed_files(worktree, base, commit)
    paths = [item["path"] for item in changed]
    if cfg.get("test"):
        results.append(run_one("测试", cfg["test"], worktree, cfg, logs / "test.log"))
    if cfg.get("lint"):
        results.append(run_one("lint", cfg["lint"], worktree, cfg, logs / "lint.log"))
    for i, check in plan_checks(cfg, task["plan"]):
        results.append(run_one(f"检查 {i}", check["run"], worktree, cfg, logs / f"check-{i}.log", check.get("expect", 0)))

    tests_changed = [item for item in changed if any_match(item["old"] or item["path"], cfg.get("tests_glob"))
                     and item["status"] in ("M", "D", "R")]
    if tests_changed and cfg.get("test"):
        restored = gitops.restore_old_tests(worktree, base, tests_changed)
        try:
            old = run_one("旧测试跑新代码", cfg["test"], worktree, cfg, logs / "old-tests.log")
        finally:
            gitops.clean(worktree)
        old["restored"] = restored
        results.append(old)

    scope = task["plan"].get("scope") or []
    out_of_scope = [path for path in paths if scope and not any_match(path, scope)
                    and not any_match(path, cfg.get("tests_glob"))]
    added = gitops.added_lines(worktree, base, commit)
    violations.extend(scan_forbidden(cfg, commands, added))
    hard = [result for result in results if result["name"] != "旧测试跑新代码"]
    passed = all(result["passed"] for result in hard)
    only_env = not passed and all(result["passed"] or result["env_error"] for result in hard)
    failures = "\n\n".join(
        f"### {r['name']}:`{r['cmd']}`(退出码 {r['exit']})\n{r['tail']}"
        for r in hard if not r["passed"] and not r["env_error"])
    return {"cand": candidate["cand"], "commit": commit, "passed": passed, "only_env": only_env,
            "results": results, "violations": violations, "changed": paths,
            "tests_changed": [item["path"] for item in tests_changed], "out_of_scope": out_of_scope,
            "failures": failures, "check_hash": candidate.get("check_hash")}
