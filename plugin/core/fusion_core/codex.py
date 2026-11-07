"""启动和解析 Codex 运行。会话编号来自 `thread.started` 事件,由引擎记住,lead 碰不到。"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .config import current_model_settings
from .util import IS_WIN, FusionError, clean_env, spawn_detached

SCHEMA = Path(__file__).with_name("report_schema.json")


def find_codex(cfg: dict) -> list[str]:
    custom = cfg["local"].get("codex")
    if custom:
        return list(custom) if isinstance(custom, list) else [custom]
    found = shutil.which("codex")
    if found:
        return [found]
    if IS_WIN:
        p = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "(Get-AppxPackage OpenAI.Codex -ErrorAction SilentlyContinue).InstallLocation"],
                           check=False, capture_output=True, text=True)
        loc = p.stdout.strip()
        if loc:
            exe = Path(loc) / "app" / "resources" / "codex.exe"
            if exe.exists():
                return [str(exe)]
    raise FusionError("找不到 Codex 命令行。请安装 Codex,或在 fusion/local.json 里设置 \"codex\"。")


def build_args(cfg: dict, station: dict, run_dir: Path, sandbox: str, resume_thread: str | None,
               schema: bool, ephemeral: bool = False) -> list[str]:
    sk = cfg["local"]["sidekick"]
    model = station.get("model") or sk["model"]
    settings = current_model_settings(sk) if model == sk.get("model") else sk.get("models", {}).get(model, {})
    effort = settings.get("effort")
    common = ["--json", "-o", str(run_dir / "last.txt")]
    conf = []
    if effort:
        conf += ["-c", f"model_reasoning_effort={effort}"]
    if settings.get("fast", False):
        conf += ["-c", 'service_tier="fast"']
    if sandbox == "workspace-write" and cfg.get("network"):
        conf += ["-c", "sandbox_workspace_write.network_access=true"]
    if schema:
        common += ["--output-schema", str(SCHEMA)]
    if ephemeral:
        common += ["--ephemeral"]
    if resume_thread:
        # S1:resume 没有 -s/-C;沙箱用 -c sandbox_mode,工作目录用子进程的 cwd
        return ["exec", "resume", *common, "-m", model, *conf, "-c", f'sandbox_mode="{sandbox}"',
                "--skip-git-repo-check", resume_thread, "-"]
    return ["exec", *common, "-m", model, *conf, "-s", sandbox, "--skip-git-repo-check",
            "-C", str(station["worktree"]), "-"]


def launch(cfg: dict, station: dict, run_dir: Path, prompt: str, sandbox: str, resume_thread: str | None,
           schema: bool = True, ephemeral: bool = False) -> int:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    args = build_args(cfg, station, run_dir, sandbox, resume_thread, schema, ephemeral)
    (run_dir / "args.json").write_text(json.dumps(args, ensure_ascii=False, indent=1), encoding="utf-8")
    cmd = find_codex(cfg) + args
    env = clean_env(cfg["local"].get("env"))
    return spawn_detached(cmd, cwd=str(station["worktree"]), env=env, stdin_path=run_dir / "prompt.txt",
                          stdout_path=run_dir / "events.jsonl", stderr_path=run_dir / "stderr.log")


def read_events(run_dir: Path) -> list[dict]:
    path = run_dir / "events.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # 半行:进程还在写
    return out


def thread_id(events: list[dict]) -> str | None:
    for e in events:
        if e.get("type") == "thread.started":
            return e.get("thread_id")
    return None


def summarize(events: list[dict]) -> dict:
    """用量、命令、上下文估算。turn.completed 的 usage 是整轮合计,上下文只能估。"""
    usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "requests": 0}
    commands, messages, last_turn_input = [], 0, 0
    for e in events:
        t = e.get("type")
        if t == "turn.completed" and e.get("usage"):
            u = e["usage"]
            usage["input"] += u.get("input_tokens", 0)
            usage["output"] += u.get("output_tokens", 0) + u.get("reasoning_output_tokens", 0)
            usage["cache_read"] += u.get("cached_input_tokens", 0)
            usage["cache_write"] += u.get("cache_write_input_tokens", 0)
            last_turn_input = u.get("input_tokens", 0)
        elif t == "item.completed":
            item = e.get("item") or {}
            if item.get("type") == "command_execution":
                commands.append({"command": item.get("command"), "exit": item.get("exit_code")})
            elif item.get("type") in ("agent_message", "reasoning"):
                messages += 1
    reqs = max(1, len(commands) + messages)
    usage["requests"] = reqs
    return {"usage": usage, "commands": commands, "ctx_est": int(last_turn_input / reqs) if last_turn_input else 0,
            "failed": any(e.get("type") in ("turn.failed", "error") for e in events)}


def last_message(run_dir: Path) -> str | None:
    p = run_dir / "last.txt"
    if p.exists():
        text = p.read_text(encoding="utf-8", errors="replace").strip()
        return text or None
    return None


def parse_report(text: str | None):
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):]
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end < 0:
        return None
    try:
        return json.loads(t[start:end + 1])
    except json.JSONDecodeError:
        return None
