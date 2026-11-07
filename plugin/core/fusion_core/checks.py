"""检查流水线:证据由程序产生,绑定某一个候选提交。"""
from __future__ import annotations

import re
from pathlib import Path

from . import gitops
from .util import any_match, clean_env, redact_file, run

ENV_ERROR = re.compile(r"(?i)certificate verify failed|CERTIFICATE_VERIFY_FAILED|unable to get local issuer|"
                       r"SSL: |ECONNRESET|ETIMEDOUT|ECONNREFUSED|Could not resolve host|"
                       r"Temporary failure in name resolution|getaddrinfo|Connection timed out")

# (正则, 原因, 用在哪:cmd=助手执行过的命令,diff=新增的代码行)
BUILTIN_RULES = [
    (r"(?i)GIT_SSL_NO_VERIFY|http\.sslVerify\s*=?\s*false|sslVerify\s+false", "关闭了 git 的证书检查", "cmd diff"),
    (r"(?i)NODE_TLS_REJECT_UNAUTHORIZED\s*=?\s*['\"]?0", "关闭了 Node 的证书检查", "cmd diff"),
    (r"(?i)strict-ssl\s*[= ]\s*false", "关闭了 npm 的证书检查", "cmd diff"),
    (r"(?i)--trusted-host\b", "pip 跳过证书检查", "cmd"),
    (r"(?i)\bcurl\b[^\n]*\s(-k|--insecure)\b", "curl 跳过证书检查", "cmd"),
    (r"(?i)\bverify\s*=\s*False\b", "代码里关闭了证书检查", "cmd diff"),
    (r"(?i)rejectUnauthorized\s*:\s*false", "代码里关闭了证书检查", "diff"),
    (r"(?i)--no-verify\b", "跳过了 git 钩子", "cmd"),
    (r"\bgit\s+(push|commit|rebase|merge|switch|checkout\s+-b|branch\s+-[dD]|reset\s+--hard)\b", "助手执行了 git 写操作", "cmd"),
]

SUSPICIOUS_FILES = ["package.json", "**/package.json", "*.lock", "**/*.lock", "pyproject.toml", "setup.cfg",
                    "requirements*.txt", "**/requirements*.txt", "build.gradle", "**/build.gradle", "*.gradle.kts",
                    "**/*.gradle.kts", "gradle.properties", ".github/**", ".gitlab-ci.yml", "Makefile", "fusion/**"]
URL = re.compile(r"https?://[^\s'\")]+")


def _expect_ok(res: dict, expect: dict | None) -> bool:
    expect = expect or {"exit": 0}
    if res["exit"] != expect.get("exit", 0):
        return False
    out = res["output"]
    if expect.get("contains") and expect["contains"] not in out:
        return False
    if expect.get("regex") and not re.search(expect["regex"], out):
        return False
    if expect.get("passed_min") is not None:
        m = re.search(r"(\d+) passed", out)
        if not m or int(m.group(1)) < int(expect["passed_min"]):
            return False
    return True


def run_one(name: str, cmd: str, cwd: Path, cfg: dict, log: Path, expect: dict | None = None) -> dict:
    env = clean_env(cfg["local"].get("env"))
    res = run(cmd, cwd=str(cwd), timeout=cfg.get("check_timeout", 900), env=env, shell=True, out_file=log)
    retried = False
    if not _expect_ok(res, expect) and ENV_ERROR.search(res["output"]):
        retried = True
        res = run(cmd, cwd=str(cwd), timeout=cfg.get("check_timeout", 900), env=env, shell=True, out_file=log)
    redact_file(log)
    passed = _expect_ok(res, expect)
    env_error = (not passed) and bool(ENV_ERROR.search(res["output"]))
    tail = "\n".join(res["output"].splitlines()[-40:])
    return {"name": name, "cmd": cmd, "exit": res["exit"], "passed": passed, "seconds": res["seconds"],
            "retried": retried, "env_error": env_error, "log": str(log), "tail": tail}


def scan_forbidden(cfg: dict, commands: list[dict], added: list[tuple[str, str]]) -> list[dict]:
    rules = [(re.compile(p), why, where) for p, why, where in BUILTIN_RULES]
    rules += [(re.compile(r["pattern"]), r.get("why", "项目禁止的操作"), r.get("where", "cmd diff"))
              for r in cfg.get("forbidden") or []]
    hits = []
    for c in commands:
        text = c.get("command") or ""
        for rx, why, where in rules:
            if "cmd" in where and rx.search(text):
                hits.append({"kind": "forbidden", "why": why, "where": "命令", "detail": text[:300]})
    for path, line in added:
        for rx, why, where in rules:
            if "diff" in where and rx.search(line):
                hits.append({"kind": "forbidden", "why": why, "where": path, "detail": line.strip()[:300]})
    return hits


def pipeline(root: Path, cfg: dict, state: dict, task: dict, cand: dict, wt: Path, run_dir: Path,
             commands: list[dict]) -> dict:
    """在工位目录里对候选跑全部检查,返回 check_ran 的数据。"""
    logs = run_dir / "checks"
    results, violations = [], []
    base, commit = task["base"], cand["commit"]
    changed = gitops.changed_files(wt, base, commit)
    paths = [f["path"] for f in changed]

    if cfg.get("test"):
        results.append(run_one("测试", cfg["test"], wt, cfg, logs / "test.log"))
    if cfg.get("lint"):
        results.append(run_one("lint", cfg["lint"], wt, cfg, logs / "lint.log"))

    lead_checks = {c for it in task["items"].values() if it.get("owner") == "lead" for c in it.get("checks") or []}
    for c in task["plan"].get("checks", []):
        if c["kind"] == "command" and c["id"] not in lead_checks:
            results.append(run_one(f"验收 {c['id']}", c["run"], wt, cfg, logs / f"{c['id']}.log", c.get("expect")))

    refs = set(task["plan"].get("decisions") or [])
    for it in task["items"].values():
        refs.update(it.get("decisions") or [])
    for ref in sorted(refs):
        dec = state["decisions"].get(ref.split("@")[0])
        if dec and dec.get("check") and dec["status"] == "active":
            results.append(run_one(f"决定 {dec['id']}", dec["check"]["run"], wt, cfg, logs / f"{dec['id']}.log",
                                   dec["check"].get("expect")))

    allowed = [t["glob"] for t in task["plan"].get("tests_may_change") or []]
    tests_changed = [f for f in changed if any_match(f["old"] or f["path"], cfg.get("tests_glob"))
                     and f["status"] in ("M", "D", "R")]
    guarded = [f for f in tests_changed if not any_match(f["old"] or f["path"], allowed)]
    if guarded and cfg.get("test"):
        restored = gitops.restore_old_tests(wt, base, guarded)
        try:
            old = run_one("旧测试跑新代码", cfg["test"], wt, cfg, logs / "old-tests.log")
        finally:
            gitops.clean(wt)
        old["restored"] = restored
        results.append(old)
        if not old["passed"] and not old["env_error"]:
            violations.append({"kind": "old_tests", "why": "派工前的测试在新代码上失败(测试可能被改弱了)",
                               "where": ", ".join(restored), "detail": old["tail"][-600:]})

    delegated = [it for it in task["items"].values() if it.get("owner") == "sidekick"]
    scope = [g for it in delegated for g in it.get("files") or []]
    out_of_scope = [p for p in paths if scope and not any_match(p, scope) and not any_match(p, cfg.get("tests_glob"))]
    judgment_files = [g for it in task["items"].values() if it.get("type") == "judgment" for g in it.get("files") or []]
    perceivable = [p for p in paths if any_match(p, cfg.get("perceivable")) or any_match(p, judgment_files)
                   or any(it.get("perceivable") and any_match(p, it.get("files")) for it in delegated)]

    added = gitops.added_lines(wt, base, commit)
    violations += scan_forbidden(cfg, commands, added)
    suspicious = [p for p in paths if any_match(p, SUSPICIOUS_FILES)]
    urls = sorted({u for _, line in added for u in URL.findall(line)})

    hard = [r for r in results if r["name"] != "旧测试跑新代码"]
    passed = all(r["passed"] for r in hard)
    only_env = (not passed) and all(r["passed"] or r["env_error"] for r in hard)
    failures = "\n\n".join(f"### {r['name']}:`{r['cmd']}`(退出码 {r['exit']})\n{r['tail']}"
                           for r in hard if not r["passed"] and not r["env_error"])
    return {"cand": cand["cand"], "commit": commit, "passed": passed, "only_env": only_env, "results": results,
            "violations": violations, "changed": paths, "tests_changed": [f["path"] for f in tests_changed],
            "out_of_scope": out_of_scope, "perceivable": perceivable, "suspicious": suspicious, "urls": urls,
            "failures": failures, "check_hash": cand.get("check_hash")}


def direct_checks(root: Path, cfg: dict, state: dict, task: dict, run_dir: Path) -> dict:
    """direct 任务:在 lead 的工作目录上跑测试、lint、验收检查,只记录。"""
    logs = run_dir / "checks"
    results = []
    if cfg.get("test"):
        results.append(run_one("测试", cfg["test"], root, cfg, logs / "test.log"))
    if cfg.get("lint"):
        results.append(run_one("lint", cfg["lint"], root, cfg, logs / "lint.log"))
    for c in task["plan"].get("checks", []):
        if c["kind"] == "command":
            results.append(run_one(f"验收 {c['id']}", c["run"], root, cfg, logs / f"{c['id']}.log", c.get("expect")))
    return {"passed": all(r["passed"] for r in results), "results": results}
