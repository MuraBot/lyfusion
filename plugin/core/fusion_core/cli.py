"""命令行:`fusion-core <命令> [JSON]`。参数是 JSON(命令行参数或标准输入),输出也是 JSON。"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from . import VERSION, codex, config as config_mod, gitops, store, views
from .commands import Ctx, cmd_usage
from .state import replay
from .tools import CLI_NAMES
from .util import FusionError, git, run


def _out(obj) -> None:
    sys.stdout.buffer.write((json.dumps(obj, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


def _args_json(text: str | None) -> dict:
    if text is None or text == "-":
        raw = sys.stdin.buffer.read().decode("utf-8") if not sys.stdin.isatty() else ""
    else:
        raw = text
    raw = raw.strip()
    return json.loads(raw) if raw else {}


def _root(args) -> Path:
    return config_mod.project_root(args.project)


def cmd_init(args) -> dict:
    root = _root(args)
    cfg = config_mod.init(root, args.test, args.lint)
    return {"ok": True, "root": str(root), "base_branch": cfg["base_branch"],
            "text": f"Fusion 已在 {root} 打开。配置在 fusion/config.json,开关和助手模型在 fusion/local.json。"}


def cmd_onoff(args, on: bool) -> dict:
    root = _root(args)
    if on and not config_mod.is_fusion_project(root):
        return cmd_init(args)
    if not config_mod.is_fusion_project(root):
        return {"ok": True, "text": "这个项目没有打开过 Fusion。"}
    local = config_mod.load(root)["local"]
    local["enabled"] = on
    config_mod.save_local(root, local)
    return {"ok": True, "text": "Fusion 已打开。" if on else "Fusion 已关闭(数据都还在,on 可以再打开)。"}


def cmd_config(args) -> dict:
    root = _root(args)
    cfg = config_mod.load(root)
    if args.action == "get":
        return cfg
    change = _args_json(args.json)
    if "local" in change:
        local = cfg["local"]
        for k, v in change["local"].items():
            if isinstance(v, dict) and isinstance(local.get(k), dict):
                local[k].update(v)
            else:
                local[k] = v
        config_mod.save_local(root, local)
    if "config" in change:
        path = root / "fusion" / "config.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(change["config"])
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return config_mod.load(root)


def _root_or_none(args) -> Path | None:
    hint = args.project
    if hint and not Path(hint).is_dir():  # 宿主没替换 ${CLAUDE_PROJECT_DIR} 时是字面值
        hint = None
    try:
        return config_mod.project_root(hint)
    except FusionError:
        return None


def cmd_wait(args) -> dict:
    """阻塞到有需要 lead 处理的事(或超时),打印通知后退出。给 lead 在 Bash 后台运行:结束时会话会被唤醒。

    MCP 服务器没在监督时(例如只用命令行),这里顺便监督。"""
    from .supervisor import Supervisor
    root = _root(args)
    ctx = Ctx(root)
    sup = Supervisor(root, poll=1.0)
    evs = store.read(ctx.conn)
    last = args.after if args.after is not None else (evs[-1]["seq"] if evs else 0)
    deadline = time.time() + args.timeout
    try:
        while True:
            if store.take_lease(sup.conn, sup.holder):
                try:
                    while sup.tick():
                        pass
                except Exception as e:
                    sup._log_error(e)
            new = [e for e in store.read(ctx.conn, last) if not args.task or e["task"] in (args.task, None)]
            s = ctx.state()
            if new:
                last = new[-1]["seq"]
                lines = views.notifications(s, new)
                if lines:
                    return {"ok": True, "notifications": lines, "status": views.prompt_line(s), "after": last}
            moving = any(r["status"] in ("requested", "started") and (not args.task or r["task"] == args.task)
                         for r in s["runs"].values()) or any(
                t["state"] in ("checking", "integrating") or (t.get("takeover") and not t.get("takeover_done"))
                for t in s["tasks"].values() if not args.task or t["id"] == args.task)
            if not moving:
                return {"ok": True, "notifications": [], "idle": True, "after": last,
                        "status": views.prompt_line(s) + "(没有在跑的运行,不用再等)"}
            if time.time() > deadline:
                return {"ok": True, "notifications": [], "timeout": True, "after": last,
                        "status": views.prompt_line(s) + f"(等了 {args.timeout} 秒,还在跑;可以再运行一次 wait)"}
            time.sleep(2)
    finally:
        try:
            store.release_lease(sup.conn, sup.holder)
        except Exception:
            pass
        ctx.close()


def cmd_events(args) -> int | dict:
    root = _root_or_none(args) if args.follow else _root(args)
    if args.export:
        conn = store.connect(root)
        n = store.export_jsonl(conn, Path(args.export))
        return {"ok": True, "events": n, "file": args.export}
    if not args.follow:
        conn = store.connect(root)
        return store.read(conn, args.after or 0)[-(args.limit or 50):]
    # --follow:给 monitor 用。没打开 Fusion 时安静地等,打开后开始输出通知
    conn, last = None, None
    while True:
        try:
            if conn is None:
                if root and config_mod.is_fusion_project(root) and config_mod.load(root)["local"].get("enabled"):
                    conn = store.connect(root)
                    evs = store.read(conn)
                    last = evs[-1]["seq"] if evs else 0
                else:
                    time.sleep(10)
                    continue
            new = store.read(conn, last)
            if new:
                last = new[-1]["seq"]
                s = replay(store.read(conn))
                for line in views.notifications(s, new):
                    sys.stdout.buffer.write((line + "\n").encode("utf-8"))
                sys.stdout.buffer.flush()
            time.sleep(args.interval)
        except KeyboardInterrupt:
            return 0
        except Exception as e:  # 库暂时锁住等:等一下再读
            sys.stderr.write(f"{type(e).__name__}: {e}\n")
            time.sleep(5)


def cmd_preflight(args) -> dict:
    root = _root(args)
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
        p = run(cmd + ["--version"], cwd=str(root), timeout=60)
        add("Codex", p["exit"] == 0, p["output"].strip()[:200])
    except FusionError as e:
        add("Codex", False, str(e))
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
    return {"ok": all(r["ok"] for r in rows), "checks": rows}


def cmd_tool(args, tool) -> dict:
    root = _root(args)
    ctx = Ctx(root, actor=args.actor)
    try:
        return tool["fn"](ctx, _args_json(args.json))
    finally:
        ctx.close()


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="fusion-core", description=f"lyfusion 引擎 {VERSION}")
    ap.add_argument("--project", help="项目目录(默认:CLAUDE_PROJECT_DIR 或当前目录)")
    ap.add_argument("--actor", default="lead")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--test")
    p.add_argument("--lint")
    for name in ("on", "off"):
        p = sub.add_parser(name)
        p.add_argument("--test")
        p.add_argument("--lint")
    sub.add_parser("serve")
    p = sub.add_parser("hook")
    p.add_argument("event", choices=["session-start", "prompt", "pre-edit"])
    p = sub.add_parser("events")
    p.add_argument("--follow", action="store_true")
    p.add_argument("--audience", default="lead")
    p.add_argument("--export")
    p.add_argument("--after", type=int)
    p.add_argument("--limit", type=int)
    p.add_argument("--interval", type=float, default=2.0)
    p = sub.add_parser("config")
    p.add_argument("action", choices=["get", "set"])
    p.add_argument("json", nargs="?")
    p = sub.add_parser("usage")
    p.add_argument("action", choices=["record"])
    p.add_argument("json", nargs="?")
    p = sub.add_parser("ledger")
    p.add_argument("--task")
    sub.add_parser("preflight")
    sub.add_parser("guide", help="打印 lead 的使用说明和当前状态(和新对话开始时注入的一样)")
    p = sub.add_parser("wait", help="等到有需要 lead 处理的事再退出(在 Bash 后台运行)")
    p.add_argument("--task")
    p.add_argument("--timeout", type=int, default=3000)
    p.add_argument("--after", type=int, help="从哪个事件之后算(默认:现在)")
    p = sub.add_parser("tick", help="调试:让监督者做完能做的事")
    p.add_argument("--wait", action="store_true", help="一直等到没有在跑的运行")
    for name in CLI_NAMES:
        p = sub.add_parser(name)
        p.add_argument("json", nargs="?")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "serve":
            from . import mcp
            try:
                root = config_mod.project_root(args.project)
            except FusionError:
                root = None
            mcp.main(root)
            return 0
        if args.cmd == "hook":
            from . import hooks
            return hooks.main(args.event)
        if args.cmd == "events":
            res = cmd_events(args)
            if isinstance(res, int):
                return res
            _out(res)
            return 0
        if args.cmd == "init":
            res = cmd_init(args)
        elif args.cmd in ("on", "off"):
            res = cmd_onoff(args, args.cmd == "on")
        elif args.cmd == "config":
            res = cmd_config(args)
        elif args.cmd == "usage":
            ctx = Ctx(_root(args))
            res = cmd_usage(ctx, _args_json(args.json))
        elif args.cmd == "ledger":
            ctx = Ctx(_root(args))
            res = {"text": views.ledger(ctx.state(), args.task)}
        elif args.cmd == "preflight":
            res = cmd_preflight(args)
        elif args.cmd == "wait":
            res = cmd_wait(args)
        elif args.cmd == "guide":
            ctx = Ctx(_root(args))
            res = {"text": views.session_context(ctx.root, ctx.cfg, ctx.state(), "manual")}
        elif args.cmd == "tick":
            from .supervisor import Supervisor
            sup = Supervisor(_root(args))
            if args.wait:
                sup.drain(limit=100000, wait=2.0)
            else:
                while sup.tick():
                    pass
            res = {"ok": True}
        else:
            res = cmd_tool(args, CLI_NAMES[args.cmd])
        _out(res)
        return 0
    except FusionError as e:
        _out({"ok": False, "error": str(e)})
        return 2
    except json.JSONDecodeError as e:
        _out({"ok": False, "error": f"参数不是合法的 JSON:{e}"})
        return 2
