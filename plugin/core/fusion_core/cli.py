"""Command line interface for the blocking v5.0.0-aq workflow."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from . import VERSION, aq, config as config_mod, store, views
from .commands import Ctx, cmd_accept, cmd_cancel, cmd_delegate, cmd_explore, cmd_plan, cmd_request_changes
from .state import replay
from .supervisor import Supervisor
from .util import FusionError, git


USAGE = views.LEAD_GUIDE


def _root(args) -> Path:
    return config_mod.project_root(args.project)


def _input(args) -> str:
    return aq.read_input(args.source, sys.stdin)


def _wait(root: Path, *, run: str | None = None, task: str | None = None,
          predicate=None, timeout: int = 1200) -> dict:
    sup = Supervisor(root, poll=0.2)
    conn = store.connect(root)
    start = time.monotonic()
    try:
        while time.monotonic() - start < timeout:
            if store.take_lease(sup.conn, sup.holder):
                while sup.tick():
                    pass
            state = sup.state()
            if predicate and predicate(state):
                return state
            if run and state["runs"].get(run, {}).get("status") == "ended":
                return state
            if not run and not predicate:
                break
            time.sleep(0.2)
        raise FusionError("等待超时或没有取得结果;请运行 fusion-core status 查看,再重试对应命令", code=2)
    finally:
        try:
            store.release_lease(sup.conn, sup.holder)
        except Exception:
            pass
        conn.close()
        sup.conn.close()


def _task_arg(parser):
    parser.add_argument("--task")


def _active_task(state: dict, task: str | None) -> str:
    if task:
        if task not in state["tasks"]:
            raise FusionError(f"任务 {task} 不存在")
        return task
    active = [t for t in state["tasks"].values() if t["state"] not in ("accepted", "rejected", "cancelled")]
    if not active:
        raise FusionError("没有进行中的任务")
    return active[-1]["id"]


def _add_input(parser, help_text):
    parser.add_argument("source", help=help_text)
    _task_arg(parser)


def _preflight(root: Path) -> dict:
    from . import codex, gitops
    from .util import run
    rows = []
    def add(name, ok, detail):
        rows.append({"check": name, "ok": ok, "detail": detail})
    add("git", True, git("--version", cwd=root))
    add("Python", sys.version_info >= (3, 10), sys.version.split()[0])
    fusion = config_mod.is_fusion_project(root)
    add("Fusion 已打开", fusion, str(root / "fusion") if fusion else "运行 fusion-core init")
    cfg = config_mod.load(root) if fusion else {"local": dict(config_mod.DEFAULT_LOCAL), "base_branch": None}
    try:
        cmd = codex.find_codex(cfg)
        result = run(cmd + ["--version"], cwd=str(root), timeout=60)
        add("Codex", result["exit"] == 0, result["output"].strip()[:200])
    except FusionError as exc:
        add("Codex", False, str(exc))
    wt = gitops.station_dir(root)
    add("工位目录不在临时目录", not gitops.in_temp(wt), str(wt))
    add("工位目录", not wt.exists() or (wt / ".git").exists(),
        "还没建" if not wt.exists() else ("是 git worktree" if (wt / ".git").exists() else "已存在但不是 worktree"))
    if fusion:
        add("主分支", git("rev-parse", "--verify", "-q", cfg["base_branch"], cwd=root, check=False)[0] == 0,
            cfg["base_branch"])
        add("测试命令", bool(cfg.get("test")), cfg.get("test") or "没配置:fusion/config.json 的 test")
        dirty = git("status", "--porcelain", cwd=root)
        add("lead 工作目录干净", not dirty, "干净" if not dirty else "有未提交的改动(验收快进时可能冲突)")
    return {"ok": all(row["ok"] for row in rows), "checks": rows}


def _do_explore(args, root):
    text = _input(args)
    ctx = Ctx(root)
    try:
        state = ctx.state()
        task = args.task
        run = cmd_explore(ctx, [text], task)["run"]
    finally:
        ctx.close()
    state = _wait(root, run=run)
    answer = state["explore_answers"].get(run, {}).get("answer", "")
    artifact = f"# 探索 {run}\n\n## 任务原话和问题\n\n{text.rstrip()}\n\n## 助手回答\n\n{answer.rstrip()}\n"
    path = root / "fusion" / "explore.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(artifact, encoding="utf-8")
    tid = task or "explore"
    aq.save_history(root, tid, "explore.md", artifact)
    print(f"结果: fusion/explore.md\n{answer[:500]}\n下一步: fusion-core delegate")


def _do_delegate(args, root):
    plan = aq.parse_plan(_input(args))
    ctx = Ctx(root)
    try:
        state = ctx.state()
        aq.decisions_text(root)
        internal = aq.engine_plan(plan, ctx.cfg)
        internal["notes"] += "\n\n跨任务设计决定:\n" + aq.decisions_text(root)
        out = cmd_plan(ctx, internal, args.task)
        tid = out["task"]
        run = cmd_delegate(ctx, tid, []) ["run"]
    finally:
        ctx.close()
    state = _wait(root, task=tid, predicate=lambda s: s["tasks"][tid]["state"] in ("in_review", "blocked", "cancelled"))
    task = state["tasks"][tid]
    if task["state"] != "in_review":
        raise FusionError(f"{tid} 没有得到可审查结果(状态:{task['state']});查看 fusion/status", code=2)
    _write_review(root, task, state, "review-1.md", 1)
    print(f"结果: fusion/review.md\n{tid} 已完成检查,请查看审查包。\n下一步: fusion-core accept --task {tid}")


def _write_review(root, task, state, history, round_no):
    text = aq.review_pack(root, task, state)
    current = root / "fusion" / "review.md"
    current.parent.mkdir(exist_ok=True)
    current.write_text(text, encoding="utf-8")
    aq.save_history(root, task["id"], history, text)


def _do_revise(args, root):
    text = _input(args)
    ctx = Ctx(root)
    try:
        state = ctx.state()
        tid = _active_task(state, args.task)
        try:
            out = cmd_request_changes(ctx, tid, [{"text": text.strip(), "expect": "按修改意见完成"}])
        except FusionError as exc:
            if "先停下来问用户" in str(exc):
                exc.code = 2
            raise
        run = out["run"]
    finally:
        ctx.close()
    state = _wait(root, task=tid, predicate=lambda s: s["tasks"][tid]["state"] in ("in_review", "blocked", "cancelled"))
    task = state["tasks"][tid]
    if task["state"] != "in_review":
        raise FusionError(f"{tid} 没有得到新的审查结果(状态:{task['state']});查看 fusion/status", code=2)
    round_no = task["change_rounds"]
    _write_review(root, task, state, f"review-{round_no + 1}.md", round_no + 1)
    print(f"结果: fusion/review.md\n{tid} 第 {round_no} 轮修改已完成。\n下一步: fusion-core accept --task {tid}")


def _do_accept(args, root):
    ctx = Ctx(root)
    try:
        state = ctx.state()
        tid = _active_task(state, args.task)
        out = cmd_accept(ctx, tid, waive=args.waive)
    finally:
        ctx.close()
    state = _wait(root, task=tid, predicate=lambda s: s["tasks"][tid]["state"] in ("accepted", "in_review", "blocked"))
    task = state["tasks"][tid]
    if task["state"] != "accepted":
        raise FusionError(f"{tid} 集成未完成:{(task.get('integration') or {}).get('detail', task['state'])}", code=2)
    print(f"{tid} 已验收,提交 {task['accepted_commit']}\n下一步: fusion-core status")


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = argparse.ArgumentParser(prog="fusion-core", description=f"lyfusion 引擎 {VERSION}")
    parser.add_argument("--project", help="项目目录(默认:CLAUDE_PROJECT_DIR 或当前目录)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    _add_input(sub.add_parser("explore"), "任务原话与问题 Markdown 文件,或 - 读标准输入")
    _add_input(sub.add_parser("delegate"), "4 字段计划 JSON 文件,或 - 读标准输入")
    _add_input(sub.add_parser("revise"), "修改意见文件,或 - 读标准输入")
    p = sub.add_parser("accept"); _task_arg(p); p.add_argument("--waive")
    _task_arg(sub.add_parser("cancel"))
    sub.add_parser("status"); sub.add_parser("on"); sub.add_parser("off"); sub.add_parser("preflight")
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
            try: print(cmd_cancel(ctx, _active_task(ctx.state(), args.task), "lead 取消" )["text"])
            finally: ctx.close()
        elif args.cmd == "status":
            ctx = Ctx(root)
            try: print(views.status(root, ctx.cfg, ctx.state()))
            finally: ctx.close()
        elif args.cmd in ("on", "off"):
            if args.cmd == "on" and not config_mod.is_fusion_project(root):
                config_mod.init(root)
            if not config_mod.is_fusion_project(root):
                print("这个项目没有打开过 Fusion。")
            else:
                cfg = config_mod.load(root)
                cfg["local"]["enabled"] = args.cmd == "on"
                config_mod.save_local(root, cfg["local"])
                if args.cmd == "on":
                    aq.decisions_text(root)
                    print(USAGE)
                else:
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
            print(json.dumps(_preflight(root), ensure_ascii=False))
        elif args.cmd == "ledger":
            ctx = Ctx(root)
            try: print(views.ledger(ctx.state(), args.task))
            finally: ctx.close()
        return 0
    except FusionError as exc:
        print(str(exc), file=sys.stderr)
        return getattr(exc, "code", 1)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"输入格式错误:{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
