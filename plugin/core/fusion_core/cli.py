"""Blocking command line interface for the four-field Fusion workflow."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

from . import VERSION, aq, store, views
from . import config as config_mod
from .commands import Ctx, cmd_accept, cmd_cancel, cmd_delegate, cmd_explore, cmd_revise
from .state import active_task
from .supervisor import Supervisor
from .util import FusionError, git

USAGE = views.LEAD_GUIDE


def _root(args):
    return config_mod.project_root(args.project)


def _input(args):
    return aq.read_input(args.source, sys.stdin)


def _wait(root: Path, task_id: str, *, explore: bool = False) -> dict:
    """Wait without a fixed timeout; only durable terminal failure signals stop it."""
    sup = Supervisor(root, poll=0.2)
    try:
        while True:
            if store.take_lease(sup.conn, sup.holder):
                sup.tick()
            state = sup.state()
            task = state["tasks"].get(task_id)
            if task is None:
                raise FusionError(f"任务 {task_id} 不存在")
            if explore and task["state"] in ("explored", "blocked"):
                return state
            if not explore and task["state"] in ("in_review", "blocked", "accepted", "cancelled"):
                if task["state"] == "in_review" and task.get("signals"):
                    latest = task["signals"][-1]
                    if latest["kind"] in ("stalled", "check_failed"):
                        raise FusionError(f"{latest['detail']}\n请再运行同一条命令继续等,或运行 fusion-core cancel --task {task_id}", code=2)
                return state
            if task.get("signals"):
                latest = task["signals"][-1]
                if latest["kind"] in ("stalled", "check_failed"):
                    raise FusionError(f"{latest['detail']}\n请再运行同一条命令继续等,或运行 fusion-core cancel --task {task_id}", code=2)
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
        state = __import__("fusion_core.state", fromlist=["replay"]).replay(store.read(conn))
    finally:
        conn.close()
    task = active_task(state)
    if task and task.get("active_run"):
        run = state["runs"].get(task["active_run"])
        if run and run["kind"] in kinds and run["status"] in ("requested", "started"):
            print("已有运行在进行,接着等它;这次的输入没有用")
            return task["id"], run["kind"] == "explore"
    return None


def _write_review(root, task, state, filename, round_no):
    text = aq.review_pack(root, task, state, round_no)
    path = root / "fusion" / "review.md"
    path.write_text(text, encoding="utf-8")
    aq.save_history(root, task["id"], filename, text)
    return path


def _write_explore(root, tid, state, original):
    task = state["tasks"][tid]
    run = next((rid for rid in reversed(task["runs"]) if state["runs"][rid]["kind"] == "explore"), task["runs"][-1])
    if original == "(本次输入未使用;接续已有运行)":
        original = (state["runs"][run].get("questions") or [""])[0]
    answer = state["explore_answers"].get(run, {}).get("answer", "")
    station = state["runs"][run].get("station")
    session = (state["stations"].get(station) or {}).get("thread") or "(未绑定)"
    artifact = f"任务编号:{tid}\n助手会话编号:{session}\n\n# 探索结果\n\n## 任务原话\n{original.rstrip()}\n\n## 助手回答\n{answer.rstrip()}\n"
    path = root / "fusion" / "tasks" / tid / "explore.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact, encoding="utf-8")
    print(f"结果: {path.relative_to(root).as_posix()}\n任务: {tid}\n会话: {session}\n探索包: {len(artifact.splitlines())} 行\n下一步: fusion-core delegate")


def _do_explore(args, root):
    existing = _existing_run(root, ("explore", "implement", "changes", "fix", "report"))
    if existing:
        tid, is_explore = existing
        state = _wait(root, tid, explore=is_explore)
        text = "(本次输入未使用;接续已有运行)"
    else:
        text = _input(args)
        ctx = Ctx(root)
        try:
            out = cmd_explore(ctx, text)
        finally:
            ctx.close()
        tid = out["task"]
        state = _wait(root, tid, explore=True)
    _write_explore(root, tid, state, text)


def _do_delegate(args, root):
    existing = _existing_run(root, ("explore", "implement", "changes", "fix", "report"))
    if existing:
        tid, is_explore = existing
        state = _wait(root, tid, explore=is_explore)
        if is_explore:
            _write_explore(root, tid, state, "(本次输入未使用;接续已有运行)")
            return
    else:
        plan = aq.parse_plan(_input(args))
        ctx = Ctx(root)
        try:
            out = cmd_delegate(ctx, plan, args.task)
        finally:
            ctx.close()
        tid = out["task"]
        state = _wait(root, tid)
    task = state["tasks"][tid]
    path = _write_review(root, task, state, f"review-{task['change_rounds'] + 1}.md", task["change_rounds"] + 1)
    chk = (state["candidates"].get(task.get("latest")) or {}).get("checks") or {}
    results = chk.get("results", [])
    passed = sum(bool(r.get("passed")) for r in results)
    violations = len(chk.get("violations", []))
    questions = len((task.get("latest_report") or {}).get("questions", []))
    files = len(chk.get("changed", []))
    print(f"结果: {path.relative_to(root).as_posix()}\n检查: {passed}/{len(results)} 通过\n违规: {violations} 条\n问题: {questions} 条;改动文件: {files} 个\n下一步: fusion-core revise --task {tid} 或 accept --task {tid}")


def _do_revise(args, root):
    existing = _existing_run(root, ("explore", "implement", "changes", "fix", "report"))
    if existing:
        tid, is_explore = existing
        state = _wait(root, tid, explore=is_explore)
        if is_explore:
            _write_explore(root, tid, state, "(本次输入未使用;接续已有运行)")
            return
    else:
        text = _input(args)
        ctx = Ctx(root)
        try:
            out = cmd_revise(ctx, args.task, text)
        finally:
            ctx.close()
        tid = out["task"]
        state = _wait(root, tid)
    task = state["tasks"][tid]
    round_no = task["change_rounds"] + 1
    path = _write_review(root, task, state, f"review-{round_no}.md", round_no)
    chk = (state["candidates"].get(task.get("latest")) or {}).get("checks") or {}
    results = chk.get("results", [])
    report = task.get("latest_report") or {}
    print(f"结果: {path.relative_to(root).as_posix()}\n检查: {sum(bool(r.get('passed')) for r in results)}/{len(results)} 通过\n违规: {len(chk.get('violations', []))} 条\n问题: {len(report.get('questions', []))} 条;改动文件: {len(chk.get('changed', []))} 个\n下一步: fusion-core revise --task {tid} 或 accept --task {tid}")


def _do_accept(args, root):
    ctx = Ctx(root)
    try:
        out = cmd_accept(ctx, args.task, args.waive)
    finally:
        ctx.close()
    if out.get("commit"):
        print(f"提交: {out['commit']}\n快进分支: {config_mod.load(root)['base_branch']}\n下一步: fusion-core status")
        return
    state = _wait(root, out["task"])
    task = state["tasks"][out["task"]]
    if task["state"] != "accepted":
        raise FusionError(f"集成失败:{(task.get('integration') or {}).get('detail', task['state'])}\n再运行同一条命令继续等,或 fusion-core cancel --task {task['id']}", code=2)
    print(f"提交: {task['accepted_commit']}\n快进分支: {config_mod.load(root)['base_branch']}\n下一步: fusion-core status")


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="fusion-core", description=f"lyfusion 引擎 {VERSION}")
    parser.add_argument("--project", help="项目目录(默认:CLAUDE_PROJECT_DIR 或当前目录)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, help_text in (("explore", "探索原话 Markdown 或 -"), ("delegate", "四字段计划 JSON 或 -"), ("revise", "修改意见或 -")):
        p = sub.add_parser(name); p.add_argument("source", help=help_text); p.add_argument("--task")
    p = sub.add_parser("accept"); p.add_argument("--task"); p.add_argument("--waive")
    p = sub.add_parser("cancel"); p.add_argument("--task")
    sub.add_parser("status"); p = sub.add_parser("on"); p.add_argument("--test"); p.add_argument("--lint")
    sub.add_parser("off"); sub.add_parser("preflight")
    p = sub.add_parser("config"); p.add_argument("action", choices=["get", "set"]); p.add_argument("json", nargs="?")
    p = sub.add_parser("ledger"); p.add_argument("--task")
    p = sub.add_parser("hook"); p.add_argument("event", choices=["session-start"])
    args = parser.parse_args(argv)
    try:
        if args.cmd == "hook":
            from .hooks import main as hook_main
            return hook_main(args.event)
        root = _root(args)
        if args.cmd == "explore": _do_explore(args, root)
        elif args.cmd == "delegate": _do_delegate(args, root)
        elif args.cmd == "revise": _do_revise(args, root)
        elif args.cmd == "accept": _do_accept(args, root)
        elif args.cmd == "cancel":
            ctx = Ctx(root)
            try:
                out = cmd_cancel(ctx, args.task, "lead 取消")
                print(f"已取消: {out['task']}\n下一步: fusion-core status")
            finally: ctx.close()
        elif args.cmd == "status":
            ctx = Ctx(root)
            try: print(views.status(root, ctx.cfg, ctx.state()))
            finally: ctx.close()
        elif args.cmd in ("on", "off"):
            if args.cmd == "on":
                config_mod.init(root, args.test, args.lint)
                cfg = config_mod.load(root); cfg["local"]["enabled"] = True; config_mod.save_local(root, cfg["local"])
                decisions = root / "fusion" / "decisions.md"
                if not decisions.exists():
                    decisions.write_text("# 设计决定\n> lead 直接编辑这个文件。每次派工,引擎把全文带给助手。只写所有任务都要守的决定。\n", encoding="utf-8")
                print(f"Fusion 已在 {root} 打开。配置在 fusion/config.json,开关和助手模型在 fusion/local.json。")
                print(USAGE)
            elif not config_mod.is_fusion_project(root): print("这个项目没有打开过 Fusion。")
            else:
                cfg = config_mod.load(root); cfg["local"]["enabled"] = False; config_mod.save_local(root, cfg["local"])
                print("Fusion 已关闭(数据都还在,on 可以再打开)。")
        elif args.cmd == "config":
            cfg = config_mod.load(root)
            if args.action == "get": print(json.dumps(cfg, ensure_ascii=False, indent=2))
            else:
                change = json.loads(args.json or "{}")
                if "local" in change:
                    local = cfg["local"]
                    for key, value in change["local"].items():
                        if isinstance(value, dict) and isinstance(local.get(key), dict): local[key].update(value)
                        else: local[key] = value
                    config_mod.save_local(root, local)
                if "config" in change:
                    path = root / "fusion" / "config.json"; data = json.loads(path.read_text(encoding="utf-8")); data.update(change["config"])
                    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(json.dumps(config_mod.load(root), ensure_ascii=False, indent=2))
        elif args.cmd == "preflight":
            from . import codex, gitops
            from .util import run
            fusion = config_mod.is_fusion_project(root); cfg = config_mod.load(root) if fusion else {"local": config_mod.DEFAULT_LOCAL}
            rows = [{"check": "git", "ok": True, "detail": git("--version", cwd=root)},
                    {"check": "Fusion", "ok": fusion, "detail": str(root / "fusion") if fusion else "运行 fusion-core on"},
                    {"check": "工位目录", "ok": not gitops.in_temp(gitops.station_dir(root)), "detail": str(gitops.station_dir(root))}]
            try:
                res = run(codex.find_codex(cfg) + ["--version"], cwd=str(root), timeout=60)
                rows.append({"check": "Codex", "ok": res["exit"] == 0, "detail": res["output"].strip()[:200]})
            except FusionError as exc: rows.append({"check": "Codex", "ok": False, "detail": str(exc)})
            print(json.dumps({"ok": all(r["ok"] for r in rows), "checks": rows}, ensure_ascii=False))
        elif args.cmd == "ledger":
            ctx = Ctx(root)
            try: print(views.ledger(ctx.state(), args.task))
            finally: ctx.close()
        return 0
    except FusionError as exc:
        print(str(exc), file=sys.stderr)
        return getattr(exc, "code", 1)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"输入格式错误:{exc}", file=sys.stderr); return 1


if __name__ == "__main__":
    raise SystemExit(main())
