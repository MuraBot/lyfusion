"""Blocking command line interface for the four-field Fusion workflow."""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import sys
import time
from pathlib import Path

from . import SCHEMA, VERSION, aq, store, views
from . import config as config_mod
from .commands import Ctx, cmd_accept, cmd_cancel, cmd_delegate, cmd_explore, cmd_revise
from .state import active_task, replay
from .supervisor import Supervisor
from .util import CMD, FormatTooNew, FusionError, clean_env, git

USAGE = views.lead_guide()


def _lead_usage_data(raw: dict) -> dict:
    """Pick individually valid fields from Claude Code's usage() response."""
    data = {}
    context = raw.get("context")
    if isinstance(context, dict):
        for source, target, integer_only in (
            ("tokens", "tokens", True), ("window", "window", True),
            ("percent", "percent", False),
        ):
            value = context.get(source)
            valid = isinstance(value, int) and not isinstance(value, bool) if integer_only else (
                isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value)
            )
            if valid:
                data[target] = value
    limits = raw.get("rateLimits")
    if isinstance(limits, list):
        for kind, prefix in (("five_hour", "five_hour"), ("seven_day", "seven_day")):
            limit = next((item for item in limits if isinstance(item, dict) and item.get("kind") == kind), None)
            if limit:
                percent = limit.get("percentUsed")
                if isinstance(percent, (int, float)) and not isinstance(percent, bool) and math.isfinite(percent):
                    data[prefix] = percent
                resets = limit.get("resetsAt")
                if isinstance(resets, str):
                    data[f"{prefix}_resets"] = resets
    cost = raw.get("cost")
    if isinstance(cost, dict):
        usd = cost.get("usd")
        if isinstance(usd, (int, float)) and not isinstance(usd, bool) and math.isfinite(usd):
            data["cost_usd"] = usd
    started = raw.get("startedAt")
    if isinstance(started, (int, float)) and not isinstance(started, bool) and math.isfinite(started):
        data["started_at"] = started
    return data


def _root(args):
    return config_mod.project_root(args.project)


def _setup_project(root: Path, test=None, lint=None, *, enabled: bool = True) -> None:
    config_mod.init(root, test, lint)
    conn = store.connect(root)
    conn.close()
    cfg = config_mod.load(root)
    cfg["local"]["enabled"] = enabled
    config_mod.save_local(root, cfg["local"])
    decisions = root / "fusion" / "decisions.md"
    if not decisions.exists():
        decisions.write_text(
            "# 设计决定\n> lead 直接编辑这个文件。每次派工,引擎把全文带给助手。只写所有任务都要守的决定。\n",
            encoding="utf-8",
        )


def _input(args):
    return aq.read_input(args.source, sys.stdin)


def _wait(root: Path, task_id: str, *, explore: bool = False) -> dict:
    """Wait without a fixed timeout; only durable terminal failure signals stop it."""
    sup = Supervisor(root, poll=0.2)
    try:
        initial = sup.state()["tasks"].get(task_id)
        if initial is None:
            raise FusionError(f"任务 {task_id} 不存在")
        signal_count = len(initial.get("signals", []))
        while True:
            if store.take_lease(sup.conn, sup.holder):
                sup.tick()
            state = sup.state()
            task = state["tasks"].get(task_id)
            if task is None:
                raise FusionError(f"任务 {task_id} 不存在")
            new_signals = task.get("signals", [])[signal_count:]
            signal_count = len(task.get("signals", []))
            for signal in new_signals:
                if signal["kind"] == "revise_dropped":
                    raise FusionError(
                        f"修改意见没有生效:{signal['detail']},请运行 {CMD} status 看清状态后再 revise",
                        code=2,
                    )
            if explore and task["state"] in ("explored", "blocked"):
                return state
            if not explore and task["state"] in (
                "in_review",
                "blocked",
                "accepted",
                "cancelled",
            ):
                return state
            for signal in new_signals:
                if signal["kind"] == "stalled":
                    raise FusionError(
                        f"{signal['detail']}\n请再运行同一条命令继续等,或运行 {CMD} cancel --task {task_id}",
                        code=2,
                    )
                if signal["kind"] == "watch":
                    run = state.get("runs", {}).get(signal.get("run")) or {}
                    if run.get("kind") == "changes":
                        continue_text = f"用同样的修改意见再运行一次 {CMD} revise -"
                    elif run.get("kind") == "explore":
                        continue_text = f"继续等: {CMD} explore -"
                    else:
                        continue_text = f"继续等: {CMD} delegate -"
                    raise FusionError(
                        f"{signal['detail']}\n{continue_text}\n"
                        f"改方向: {CMD} revise - <<'EOF'\n修改意见\nEOF\n"
                        "(停下这一轮,同一会话里按意见接着做,算一轮修改)\n"
                        f"放弃: {CMD} cancel --task {task_id}",
                        code=2,
                    )
            time.sleep(0.2)
    finally:
        try:
            store.release_lease(sup.conn, sup.holder)
        except sqlite3.Error:
            pass
        sup.conn.close()


def _existing_run(root: Path, kinds: tuple[str, ...]):
    conn = store.connect(root)
    try:
        state = replay(store.read(conn))
    finally:
        conn.close()
    task = active_task(state)
    if task and task.get("active_run"):
        run = state["runs"].get(task["active_run"])
        if run and run["kind"] in kinds and run["status"] in ("requested", "started"):
            return task["id"], run["kind"] == "explore", run["kind"]
    return None


def _write_review(root, task, state, filename, round_no):
    text = aq.review_pack(root, task, state, round_no)
    path = root / "fusion" / "review.md"
    path.write_text(text, encoding="utf-8")
    aq.save_history(root, task["id"], filename, text)
    return path


def _write_explore(root, tid, state, original: str | None, continued: bool = False):
    task = state["tasks"][tid]
    run = next(
        (
            rid
            for rid in reversed(task["runs"])
            if state["runs"][rid]["kind"] == "explore"
        ),
        task["runs"][-1],
    )
    if original is None:
        original = (state["runs"][run].get("questions") or [""])[0]
    answer = state["explore_answers"].get(run, {}).get("answer", "")
    station = state["runs"][run].get("station")
    session = (state["stations"].get(station) or {}).get("thread") or "(未绑定)"
    artifact = f"任务编号:{tid}\n助手会话编号:{session}\n\n# 探索结果\n\n## lead 的原文\n{original.rstrip()}\n\n## 助手回答\n{answer.rstrip()}\n"
    path = root / "fusion" / "explore.md"
    path.write_text(artifact, encoding="utf-8")
    aq.save_history(root, tid, "explore.md", artifact)
    print(
        f"结果: fusion/explore.md\n任务: {tid}\n会话: {session}\n探索包: {len(artifact.splitlines())} 行"
    )
    if continued:
        print("已有运行在进行,接着等它;这次的输入没有用")
    print(f"下一步: {CMD} delegate -(计划用 Markdown,heredoc 传)")


def _do_explore(args, root):
    existing = _existing_run(root, ("explore", "implement", "changes", "fix", "report"))
    if existing:
        tid, is_explore, _kind = existing
        state = _wait(root, tid, explore=is_explore)
        if not is_explore:
            task = state["tasks"][tid]
            round_no = task["change_rounds"] + 1
            path = _write_review(root, task, state, f"review-{round_no}.md", round_no)
            chk = (state["candidates"].get(task.get("latest")) or {}).get(
                "checks"
            ) or {}
            print(
                f"结果: {path.relative_to(root).as_posix()}\n检查与问题已写入审查包。\n已有运行在进行,接着等它;这次的输入没有用\n{aq.next_step_text(task, chk)}"
            )
            return
        text = None
    else:
        text = _input(args)
        ctx = Ctx(root)
        try:
            out = cmd_explore(ctx, text)
        finally:
            ctx.close()
        tid = out["task"]
        state = _wait(root, tid, explore=True)
    _write_explore(root, tid, state, text, continued=bool(existing))


def _do_delegate(args, root):
    existing = _existing_run(root, ("explore", "implement", "changes", "fix", "report"))
    if existing:
        tid, is_explore, _kind = existing
        state = _wait(root, tid, explore=is_explore)
        if is_explore:
            _write_explore(root, tid, state, None, continued=True)
            return
    else:
        plan = aq.parse_plan(_input(args))
        ctx = Ctx(root)
        try:
            out = cmd_delegate(ctx, plan, args.task)
        finally:
            ctx.close()
        tid = out["task"]
        if out.get("decisions_note"):
            print(out["decisions_note"])
        state = _wait(root, tid)
    task = state["tasks"][tid]
    path = _write_review(
        root,
        task,
        state,
        f"review-{task['change_rounds'] + 1}.md",
        task["change_rounds"] + 1,
    )
    chk = (state["candidates"].get(task.get("latest")) or {}).get("checks") or {}
    results = chk.get("results", [])
    passed = sum(bool(r.get("passed")) for r in results)
    violations = len(chk.get("violations", []))
    questions = len((task.get("latest_report") or {}).get("questions", []))
    files = len(chk.get("changed", []))
    lines = [
        f"结果: {path.relative_to(root).as_posix()}",
        f"检查: {passed}/{len(results)} 通过",
        f"违规: {violations} 条",
        f"问题: {questions} 条;改动文件: {files} 个",
    ]
    if existing:
        lines.append("已有运行在进行,接着等它;这次的输入没有用")
    lines.append(aq.next_step_text(task, chk))
    print("\n".join(lines))


def _do_revise(args, root):
    existing = _existing_run(root, ("explore", "implement", "changes", "fix", "report"))
    if existing:
        tid, is_explore, kind = existing
        if is_explore:
            raise FusionError("探索还在运行,请等探索结束后再 revise")
        if kind not in ("implement", "changes", "fix"):
            raise FusionError(f"{kind} 运行中不能 revise,请等它结束")
        ctx = Ctx(root)
        try:
            text = _input(args)
            out = cmd_revise(ctx, tid, text)
        finally:
            ctx.close()
        tid = out["task"]
        if out.get("decisions_note"):
            print(out["decisions_note"])
        state = _wait(root, tid)
    else:
        text = _input(args)
        ctx = Ctx(root)
        try:
            out = cmd_revise(ctx, args.task, text)
        finally:
            ctx.close()
        tid = out["task"]
        if out.get("decisions_note"):
            print(out["decisions_note"])
        state = _wait(root, tid)
    task = state["tasks"][tid]
    round_no = task["change_rounds"] + 1
    path = _write_review(root, task, state, f"review-{round_no}.md", round_no)
    chk = (state["candidates"].get(task.get("latest")) or {}).get("checks") or {}
    results = chk.get("results", [])
    report = task.get("latest_report") or {}
    lines = [
        f"结果: {path.relative_to(root).as_posix()}",
        f"检查: {sum(bool(r.get('passed')) for r in results)}/{len(results)} 通过",
        f"违规: {len(chk.get('violations', []))} 条",
        f"问题: {len(report.get('questions', []))} 条;改动文件: {len(chk.get('changed', []))} 个",
    ]
    if existing and out.get("continue_wait"):
        lines.append("修改意见和正在做的这一轮相同,接着等它")
    lines.append(aq.next_step_text(task, chk))
    print("\n".join(lines))


def _do_accept(args, root):
    ctx = Ctx(root)
    try:
        out = cmd_accept(ctx, args.task, args.waive)
    finally:
        ctx.close()
    if out.get("commit"):
        print(
            f"提交: {out['commit']}\n快进分支: {config_mod.load(root)['base_branch']}\n下一步: {CMD} status"
        )
        return
    state = _wait(root, out["task"])
    task = state["tasks"][out["task"]]
    if task["state"] != "accepted":
        detail = (task.get("integration") or {}).get("detail", task["state"])
        if "未提交" in detail:
            message = f"lead 工作目录有没提交的改动,快进会冲突:先提交或撤销,再运行 {CMD} accept"
        elif "冲突" in detail:
            message = (
                f"合并冲突,已退回审查:用 {CMD} revise 让助手在最新的主分支上解决"
            )
        else:
            message = f"集成失败:{detail}"
        raise FusionError(message, code=2)
    print(
        f"提交: {task['accepted_commit']}\n快进分支: {config_mod.load(root)['base_branch']}\n下一步: {CMD} status"
    )


def _preflight(root: Path) -> dict:
    from . import codex, gitops
    from .util import run

    rows = []

    def add(name, ok, detail):
        rows.append({"check": name, "ok": ok, "detail": detail})

    version_details = []
    format_ok = True
    for name in ("config.json", "local.json"):
        path = root / "fusion" / name
        if not path.exists():
            version_details.append(f"{path.as_posix()}: 没有,按 1")
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8") or "{}")
            version = raw.get("schema_version", 1)
            label = str(version) if "schema_version" in raw else "没有,按 1"
            if not isinstance(version, int) or isinstance(version, bool) or version <= 0:
                format_ok = False
                label += "(损坏)"
            elif version > SCHEMA:
                format_ok = False
                label += "(需要升级插件)"
        except (json.JSONDecodeError, UnicodeDecodeError):
            label = "损坏"
            format_ok = False
        version_details.append(f"{path.as_posix()}: {label}")
    db_path = root / "fusion" / "fusion.db"
    if db_path.exists():
        try:
            readonly = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
            db_version = readonly.execute("PRAGMA user_version").fetchone()[0]
            row_versions = readonly.execute("SELECT MAX(v) FROM events").fetchone()[0]
            readonly.close()
            version_details.append(f"{db_path.as_posix()}: {db_version if db_version else '没有,按 1'}")
            if db_version > SCHEMA or (row_versions is not None and row_versions > SCHEMA):
                format_ok = False
                if db_version <= SCHEMA and row_versions is not None and row_versions > SCHEMA:
                    version_details[-1] += f"(事件版本 {row_versions},需要升级插件)"
                elif db_version > SCHEMA:
                    version_details[-1] += "(需要升级插件)"
        except sqlite3.Error:
            version_details.append(f"{db_path.as_posix()}: 损坏")
            format_ok = False
    else:
        version_details.append(f"{db_path.as_posix()}: 没有,按 1")
    add("状态格式", format_ok, "; ".join(version_details))

    add("git", True, git("--version", cwd=root))
    add("Python", sys.version_info >= (3, 10), sys.version.split()[0])
    fusion = config_mod.is_fusion_project(root)
    add(
        "Fusion 已打开",
        fusion,
        str(root / "fusion") if fusion else "运行 /fusion on",
    )
    try:
        cfg = (
            config_mod.load(root)
            if fusion
            else {**config_mod.DEFAULT_CONFIG, "local": dict(config_mod.DEFAULT_LOCAL), "base_branch": None}
        )
    except FormatTooNew:
        cfg = {
            **config_mod.DEFAULT_CONFIG,
            "local": dict(config_mod.DEFAULT_LOCAL),
            "base_branch": git("rev-parse", "--abbrev-ref", "HEAD", cwd=root, check=False)[1].strip() or None,
        }
    env = clean_env(cfg["local"].get("env"))
    clean = config_mod.effective_settings(cfg)["clean"]
    codex_command = None
    try:
        codex_command = codex.find_codex(cfg)
        version = codex.version(cfg, root)
        add("Codex", version is not None, version or "无法读取版本")
    except (FusionError, OSError) as exc:
        add("Codex", False, str(exc))
    if codex_command:
        sandbox_args = ["sandbox"]
        sandbox_settings = codex.user_sandbox_settings() if clean else {}
        windows_sandbox = sandbox_settings.get("windows.sandbox")
        if windows_sandbox is not None:
            sandbox_args += ["-c", f"windows.sandbox={json.dumps(windows_sandbox)}"]
        sandbox_args += ["-c", 'sandbox_mode="read-only"', "--", "git", "rev-parse", "--show-toplevel"]
        try:
            sandbox_result = run(codex_command + sandbox_args, cwd=str(root), timeout=30, env=env)
            sandbox_output = sandbox_result["output"].strip()
            sandbox_line = sandbox_output.splitlines()[-1] if sandbox_output else "(无输出)"
            sandbox_ok = sandbox_result["exit"] == 0 and bool(sandbox_output)
            add("沙箱里能跑命令", sandbox_ok, sandbox_line)
        except OSError as exc:
            add("沙箱里能跑命令", False, str(exc).splitlines()[-1])
        missing = []
        try:
            exec_help = run(codex_command + ["exec", "--help"], cwd=str(root), timeout=30, env=env)
            resume_help = run(codex_command + ["exec", "resume", "--help"], cwd=str(root), timeout=30, env=env)
            features = run(codex_command + ["features", "list"], cwd=str(root), timeout=30, env=env)
            for label, result in (("exec --help", exec_help), ("exec resume --help", resume_help)):
                if result["exit"] != 0:
                    missing.append(f"{label} 执行失败(exit={result['exit']})")
                for flag in ("--ignore-user-config", "--disable"):
                    if flag not in result["output"]:
                        missing.append(f"{label} 缺少 {flag}")
            if features["exit"] != 0:
                missing.append(f"features list 执行失败(exit={features['exit']})")
            for feature in ("apps", "plugins"):
                if not re.search(rf"(?m)^\s*{feature}(?:\s|$)", features["output"]):
                    missing.append(f"features list 缺少 {feature}")
            detail = "; ".join(missing) if missing else "exec、exec resume 参数和 apps/plugins feature 均可用"
            if not clean:
                detail += "(项目没开干净模式,仅供参考)"
            add("干净模式参数", not missing or not clean, detail)
        except OSError as exc:
            detail = f"调用 Codex 失败:{exc}"
            add("干净模式参数", not clean, detail + ("(项目没开干净模式,仅供参考)" if not clean else ""))
    else:
        detail = "找不到 Codex,无法检查参数"
        if not clean:
            detail += "(项目没开干净模式,仅供参考)"
        add("干净模式参数", not clean, detail)
    if fusion:
        for warning in config_mod.configuration_warnings(cfg):
            add("配置警告", True, warning)
    worktree = gitops.station_dir(root)
    add("工位目录不在临时目录", not gitops.in_temp(worktree), str(worktree))
    add(
        "工位目录",
        not worktree.exists() or (worktree / ".git").exists(),
        "还没建"
        if not worktree.exists()
        else (
            "是 git worktree"
            if (worktree / ".git").exists()
            else "已存在但不是 worktree"
        ),
    )
    if fusion:
        add(
            "主分支",
            git(
                "rev-parse", "--verify", "-q", cfg["base_branch"], cwd=root, check=False
            )[0]
            == 0,
            cfg["base_branch"],
        )
        add(
            "测试命令",
            bool(cfg.get("test")),
            cfg.get("test") or "没配置:fusion/config.json 的 test",
        )
        dirty = git("status", "--porcelain", cwd=root)
        add(
            "lead 工作目录干净",
            not dirty,
            "干净" if not dirty else "有未提交的改动(验收快进时可能冲突)",
        )
    return {"ok": all(row["ok"] for row in rows), "checks": rows}


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        prog="fusion-core", description=f"lyfusion 引擎 {VERSION}"
    )
    parser.add_argument(
        "--project", help="项目目录(默认:CLAUDE_PROJECT_DIR 或当前目录)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, help_text in (
        ("explore", "探索原话 Markdown 或 -"),
        ("delegate", "计划用 Markdown 或 JSON,或 -"),
        ("revise", "修改意见或 -"),
    ):
        p = sub.add_parser(name)
        p.add_argument("source", help=help_text)
        p.add_argument("--task")
    p = sub.add_parser("accept")
    p.add_argument("--task")
    p.add_argument("--waive")
    p = sub.add_parser("cancel")
    p.add_argument("--task")
    sub.add_parser("status")
    p = sub.add_parser("on")
    p.add_argument("--test")
    p.add_argument("--lint")
    sub.add_parser("off")
    sub.add_parser("preflight")
    p = sub.add_parser("config")
    p.add_argument("action", choices=["get", "set", "model", "effort", "fast", "compact", "panel", "enabled"])
    p.add_argument("json", nargs="?")
    p = sub.add_parser("ledger")
    p.add_argument("--task")
    p = sub.add_parser("lead-usage")
    p.add_argument("source")
    p.add_argument("--task")
    p.add_argument("--at", required=True)
    p = sub.add_parser("hook")
    p.add_argument("event", choices=["session-start"])
    args = parser.parse_args(argv)
    try:
        if args.cmd == "hook":
            from .hooks import main as hook_main

            return hook_main(args.event)
        root = _root(args)
        if args.cmd == "explore":
            _do_explore(args, root)
        elif args.cmd == "delegate":
            _do_delegate(args, root)
        elif args.cmd == "revise":
            _do_revise(args, root)
        elif args.cmd == "accept":
            _do_accept(args, root)
        elif args.cmd == "cancel":
            ctx = Ctx(root)
            try:
                out = cmd_cancel(ctx, args.task, "lead 取消")
                print(f"已取消: {out['task']}\n下一步: {CMD} status")
            finally:
                ctx.close()
        elif args.cmd == "status":
            ctx = Ctx(root)
            try:
                print(views.status(root, ctx.cfg, ctx.state()))
            finally:
                ctx.close()
        elif args.cmd in ("on", "off"):
            if args.cmd == "on":
                _setup_project(root, args.test, args.lint)
                print(
                    f"Fusion 已在 {root} 打开。配置在 fusion/config.json,开关和助手模型在 fusion/local.json。"
                )
                print(USAGE)
            elif not config_mod.is_fusion_project(root):
                print("这个项目没有打开过 Fusion。")
            else:
                cfg = config_mod.load(root)
                cfg["local"]["enabled"] = False
                config_mod.save_local(root, cfg["local"])
                print("Fusion 已关闭(数据都还在,on 可以再打开)。")
        elif args.cmd == "config":
            if args.action == "panel" and not config_mod.is_fusion_project(root):
                print(json.dumps({"schema_version": SCHEMA, "project": False}, ensure_ascii=False))
                return 0
            if args.action == "enabled":
                if args.json not in ("on", "off"):
                    raise FusionError("config enabled 只能是 on 或 off")
                if not config_mod.is_fusion_project(root):
                    raise FusionError("这个项目没有打开过 Fusion。先运行 /fusion 打开")
                _setup_project(root, enabled=args.json == "on")
                print("Fusion 已打开" if args.json == "on" else "Fusion 已关闭")
                return 0
            cfg = config_mod.load(root)
            if args.action == "panel":
                local = cfg["local"]
                sidekick = local.get("sidekick", {})
                model = sidekick.get("model", config_mod.DEFAULT_LOCAL["sidekick"]["model"])
                model_settings = sidekick.get("models", {})
                models = list(config_mod.KNOWN_MODELS)
                if isinstance(model_settings, dict):
                    models.extend(name for name in model_settings if isinstance(name, str))
                models.append(model)
                models = list(dict.fromkeys(models))
                current = config_mod.current_model_settings(sidekick)
                compact_choices = config_mod.compact_choices(model, current["compact"])
                effective = config_mod.effective_settings(cfg)
                panel = {
                    "schema_version": SCHEMA,
                    "project": True,
                    "enabled": bool(local.get("enabled", False)),
                    "model": model,
                    "models": models,
                    "effort": current["effort"],
                    "efforts": config_mod.model_efforts(model),
                    "fast": current["fast"],
                    "fast_models": [name for name in models if config_mod.supports_fast(name)],
                    "model_names": {name: config_mod.MODEL_INFO[name]["name"] for name in models
                                    if name in config_mod.MODEL_INFO},
                    "compact": current["compact"],
                    "compacts": compact_choices,
                    "context_ratio": effective["context_ratio"],
                    "switch_at": effective["switch_at"],
                    "warnings": config_mod.configuration_warnings(cfg),
                }
                print(json.dumps(panel, ensure_ascii=False, separators=(",", ":")))
            elif args.action == "get":
                cfg["effective"] = config_mod.effective_settings(cfg)
                print(json.dumps(cfg, ensure_ascii=False, indent=2))
            elif args.action == "set":
                change = json.loads(args.json or "{}")
                local_change = change.get("local", {})
                project_change = change.get("config", {})
                if not isinstance(local_change, dict) or not isinstance(project_change, dict):
                    raise FusionError("config set 的 local 和 config 必须是对象")
                if "context_ratio" in project_change:
                    ratio = project_change["context_ratio"]
                    if (isinstance(ratio, bool) or not isinstance(ratio, (int, float))
                            or (isinstance(ratio, float) and not math.isfinite(ratio))
                            or not 0 < ratio < 1):
                        raise FusionError("context_ratio 只能是有限数,且大于 0、小于 1")
                if "clean" in project_change and not isinstance(project_change["clean"], bool):
                    raise FusionError("clean 只能是布尔值 true 或 false")
                if local_change:
                    local = cfg["local"]
                    for key, value in local_change.items():
                        if isinstance(value, dict) and isinstance(local.get(key), dict):
                            local[key].update(value)
                        else:
                            local[key] = value
                    config_mod.save_local(root, local)
                if project_change:
                    data = json.loads((root / "fusion" / "config.json").read_text(encoding="utf-8"))
                    data.update(project_change)
                    config_mod.save_project(root, data)
                print(json.dumps(config_mod.load(root), ensure_ascii=False, indent=2))
            else:
                value = args.json
                if not value:
                    raise FusionError(f"config {args.action} 需要一个值")
                sidekick = cfg["local"]["sidekick"]
                if args.action == "model":
                    sidekick["model"] = value
                    config_mod.save_local(root, cfg["local"])
                elif args.action == "compact":
                    try:
                        compact = int(value)
                    except ValueError as exc:
                        raise FusionError("compact 只能是正整数") from exc
                    if compact <= 0:
                        raise FusionError("compact 只能是正整数")
                    model = sidekick["model"]
                    limit = config_mod.max_compact(model)
                    if limit is not None and compact > limit:
                        raise FusionError(f"上下文上限不能超过 {model} 的 {limit}")
                    settings = sidekick.setdefault("models", {}).setdefault(model, {})
                    settings["compact"] = compact
                    config_mod.save_local(root, cfg["local"])
                else:
                    model = sidekick["model"]
                    settings = sidekick.setdefault("models", {}).setdefault(model, {})
                    if args.action == "effort":
                        choices = config_mod.model_efforts(model)
                        if value not in choices:
                            joined = "、".join(choices[:-1]) + " 或 " + choices[-1]
                            raise FusionError(f"effort 只能是 {joined}({model})")
                        settings["effort"] = value
                    else:
                        if value not in ("on", "off"):
                            raise FusionError("fast 只能是 on 或 off")
                        if value == "on" and not config_mod.supports_fast(model):
                            raise FusionError(f"{model} 不支持 Fast Mode")
                        settings["fast"] = value == "on"
                    config_mod.save_local(root, cfg["local"])
                print(json.dumps(config_mod.load(root), ensure_ascii=False, indent=2))
        elif args.cmd == "preflight":
            print(json.dumps(_preflight(root), ensure_ascii=False))
        elif args.cmd == "ledger":
            ctx = Ctx(root)
            try:
                print(views.ledger(ctx.state(), args.task))
            finally:
                ctx.close()
        elif args.cmd == "lead-usage":
            if args.at not in ("explore", "accept"):
                raise FusionError("lead-usage --at 只能是 explore 或 accept")
            if args.source != "-":
                raise FusionError("lead-usage 的输入必须是 - (标准输入)")
            try:
                raw_usage = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise FusionError("lead-usage 的输入不是合法 JSON") from exc
            if not isinstance(raw_usage, dict):
                raise FusionError("lead-usage 输入必须是 JSON 对象")
            ctx = Ctx(root)
            try:
                task_id = None
                if args.at == "accept":
                    state = ctx.state()
                    if args.task:
                        task = state["tasks"].get(args.task)
                    else:
                        task = next((item for item in reversed(list(state["tasks"].values()))
                                     if item["state"] in ("in_review", "integrating")), None)
                    if task is None:
                        raise FusionError("找不到要记录 lead 用量的任务", code=2)
                    task_id = task["id"]
                elif args.task:
                    task_id = args.task
                data = _lead_usage_data(raw_usage)
                data["at"] = args.at
                with store.transaction(ctx.conn):
                    store.append(ctx.conn, [{"type": "lead_usage", "task": task_id, "data": data}], ctx.actor)
                label = task_id or args.at
                print(f"已记录 {label} 的 lead 用量")
            finally:
                ctx.close()
        return 0
    except FusionError as exc:
        print(str(exc), file=sys.stderr)
        return getattr(exc, "code", 1)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"输入格式错误:{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
