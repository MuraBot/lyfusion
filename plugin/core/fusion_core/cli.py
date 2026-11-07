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
from .state import active_task, replay
from .supervisor import Supervisor
from .util import CMD, FusionError, git

USAGE = views.lead_guide()


def _root(args):
    return config_mod.project_root(args.project)


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
            if explore and task["state"] in ("explored", "blocked"):
                return state
            if not explore and task["state"] in (
                "in_review",
                "blocked",
                "accepted",
                "cancelled",
            ):
                return state
            new_signals = task.get("signals", [])[signal_count:]
            signal_count = len(task.get("signals", []))
            for signal in new_signals:
                if signal["kind"] == "stalled":
                    raise FusionError(
                        f"{signal['detail']}\n请再运行同一条命令继续等,或运行 {CMD} cancel --task {task_id}",
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
    print(f"下一步: {CMD} delegate -(计划 JSON 用 heredoc 传)")


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
        tid, is_explore, _kind = existing
        state = _wait(root, tid, explore=is_explore)
        if is_explore:
            _write_explore(root, tid, state, None, continued=True)
            return
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
    if existing:
        lines.append("已有运行在进行,接着等它;这次的输入没有用")
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

    add("git", True, git("--version", cwd=root))
    add("Python", sys.version_info >= (3, 10), sys.version.split()[0])
    fusion = config_mod.is_fusion_project(root)
    add(
        "Fusion 已打开",
        fusion,
        str(root / "fusion") if fusion else "运行 /fusion on",
    )
    cfg = (
        config_mod.load(root)
        if fusion
        else {"local": dict(config_mod.DEFAULT_LOCAL), "base_branch": None}
    )
    try:
        command = codex.find_codex(cfg)
        result = run(command + ["--version"], cwd=str(root), timeout=60)
        add("Codex", result["exit"] == 0, result["output"].strip()[:200])
    except FusionError as exc:
        add("Codex", False, str(exc))
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
        ("delegate", "四字段计划 JSON 或 -"),
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
    p.add_argument("action", choices=["get", "set", "model", "effort", "fast"])
    p.add_argument("json", nargs="?")
    p = sub.add_parser("ledger")
    p.add_argument("--task")
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
                config_mod.init(root, args.test, args.lint)
                cfg = config_mod.load(root)
                cfg["local"]["enabled"] = True
                config_mod.save_local(root, cfg["local"])
                decisions = root / "fusion" / "decisions.md"
                if not decisions.exists():
                    decisions.write_text(
                        "# 设计决定\n> lead 直接编辑这个文件。每次派工,引擎把全文带给助手。只写所有任务都要守的决定。\n",
                        encoding="utf-8",
                    )
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
            cfg = config_mod.load(root)
            if args.action == "get":
                print(json.dumps(cfg, ensure_ascii=False, indent=2))
            elif args.action == "set":
                change = json.loads(args.json or "{}")
                if "local" in change:
                    local = cfg["local"]
                    for key, value in change["local"].items():
                        if isinstance(value, dict) and isinstance(local.get(key), dict):
                            local[key].update(value)
                        else:
                            local[key] = value
                    config_mod.save_local(root, local)
                if "config" in change:
                    path = root / "fusion" / "config.json"
                    data = json.loads(path.read_text(encoding="utf-8"))
                    data.update(change["config"])
                    path.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                print(json.dumps(config_mod.load(root), ensure_ascii=False, indent=2))
            else:
                value = args.json
                if not value:
                    raise FusionError(f"config {args.action} 需要一个值")
                sidekick = cfg["local"]["sidekick"]
                if args.action == "model":
                    sidekick["model"] = value
                else:
                    model = sidekick["model"]
                    settings = sidekick.setdefault("models", {}).setdefault(model, {})
                    if args.action == "effort":
                        if value not in ("low", "medium", "high", "xhigh"):
                            raise FusionError("effort 只能是 low、medium、high 或 xhigh")
                        settings["effort"] = value
                    else:
                        if value not in ("on", "off"):
                            raise FusionError("fast 只能是 on 或 off")
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
        return 0
    except FusionError as exc:
        print(str(exc), file=sys.stderr)
        return getattr(exc, "code", 1)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"输入格式错误:{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
