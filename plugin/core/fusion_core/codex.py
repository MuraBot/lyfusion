"""Start and parse Codex runs. The engine stores session IDs from `thread.started` events; the lead cannot access them."""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from .config import codex_home, current_model_settings
from .util import IS_WIN, FusionError, clean_env, run, spawn_detached

SCHEMA = Path(__file__).with_name("report_schema.json")


def user_sandbox_settings() -> dict:
    """Read only the two user sandbox settings required by clean mode."""
    try:
        import tomllib
    except ImportError:
        return {}
    config_home = codex_home()
    try:
        with (config_home / "config.toml").open("rb") as stream:
            config = tomllib.load(stream)
    except (OSError, ValueError, TypeError):
        return {}
    result = {}
    windows = config.get("windows")
    if isinstance(windows, dict) and isinstance(windows.get("sandbox"), str):
        result["windows.sandbox"] = windows["sandbox"]
    workspace_write = config.get("sandbox_workspace_write")
    if isinstance(workspace_write, dict) and isinstance(workspace_write.get("network_access"), bool):
        result["sandbox_workspace_write.network_access"] = workspace_write["network_access"]
    return result


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
    raise FusionError("Codex CLI not found. Install Codex or set \"codex\" in fusion/local.json.")


def version(cfg: dict, cwd: str | Path) -> str | None:
    """Return Codex's version using the same cleaned environment as launch/preflight."""
    try:
        result = run(find_codex(cfg) + ["--version"], cwd=str(cwd), timeout=10,
                     env=clean_env(cfg["local"].get("env")))
    except (FusionError, OSError, subprocess.SubprocessError):
        return None
    return result["output"].strip()[:200] if result["exit"] == 0 else None


def build_args(cfg: dict, station: dict, run_dir: Path, sandbox: str, resume_thread: str | None,
               schema: bool, ephemeral: bool = False) -> list[str]:
    sk = cfg["local"]["sidekick"]
    model = station.get("model") or sk["model"]
    settings = current_model_settings(sk) if model == sk.get("model") else current_model_settings({**sk, "model": model})
    effort = settings.get("effort")
    common = ["--json", "-o", str(run_dir / "last.txt")]
    conf = []
    conf += ["-c", f"model_auto_compact_token_limit={settings['compact']}"]
    if effort:
        conf += ["-c", f"model_reasoning_effort={effort}"]
    if settings.get("fast", False):
        conf += ["-c", 'service_tier="fast"']
    clean = cfg.get("clean", True)
    if not isinstance(clean, bool):
        clean = True
    user_settings = user_sandbox_settings() if clean else {}
    if clean:
        windows_sandbox = user_settings.get("windows.sandbox")
        if windows_sandbox is not None:
            conf += ["-c", f"windows.sandbox={json.dumps(windows_sandbox)}"]
    project_network_access = sandbox == "workspace-write" and bool(cfg.get("network"))
    if project_network_access or "sandbox_workspace_write.network_access" in user_settings:
        network_access = project_network_access or user_settings["sandbox_workspace_write.network_access"]
        conf += ["-c", f"sandbox_workspace_write.network_access={'true' if network_access else 'false'}"]
    if schema:
        common += ["--output-schema", str(SCHEMA)]
    if ephemeral:
        common += ["--ephemeral"]
    environment = ["--ignore-user-config", "--disable", "apps", "--disable", "plugins"] if clean else []
    if resume_thread:
        # S1: resume has no -s/-C; pass sandbox_mode with -c and set the worktree as the subprocess cwd.
        return ["exec", "resume", *environment, *common, "-m", model, *conf, "-c", f'sandbox_mode="{sandbox}"',
                "--skip-git-repo-check", resume_thread, "-"]
    return ["exec", *environment, *common, "-m", model, *conf, "-s", sandbox, "--skip-git-repo-check",
            "-C", str(station["worktree"]), "-"]


def launch(cfg: dict, station: dict, run_dir: Path, prompt: str, sandbox: str, resume_thread: str | None,
           schema: bool = True, ephemeral: bool = False) -> int:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    args = build_args(cfg, station, run_dir, sandbox, resume_thread, schema, ephemeral)
    cmd = find_codex(cfg) + args
    (run_dir / "args.json").write_text(json.dumps(cmd, ensure_ascii=False, indent=1), encoding="utf-8")
    engine_env = {"FUSION_SANDBOX": "1"}
    if sandbox == "workspace-write":
        temp_dir = Path(station["worktree"]) / ".fusion-tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        gitignore = temp_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n", encoding="utf-8")
        temp_path = str(temp_dir)
        engine_env.update({"TEMP": temp_path, "TMP": temp_path, "TMPDIR": temp_path})
    env = clean_env({**engine_env, **(cfg["local"].get("env") or {})})
    return spawn_detached(cmd, cwd=str(station["worktree"]), env=env, stdin_path=run_dir / "prompt.txt",
                          stdout_path=run_dir / "events.jsonl", stderr_path=run_dir / "stderr.log")


def read_events(run_dir: Path) -> list[dict]:
    path = run_dir / "events.jsonl"
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # A partial line may still be written by the process.
    stamp_path = run_dir / "event-stamps.jsonl"
    stamps = []
    if stamp_path.exists():
        with stamp_path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    stamps.append(float(line.strip()))
                except ValueError:
                    continue
    if len(stamps) > len(out):
        stamps = stamps[:len(out)]
    if len(stamps) < len(out):
        with stamp_path.open("a", encoding="utf-8") as stream:
            for _ in range(len(out) - len(stamps)):
                stamp = time.time()
                stamps.append(stamp)
                stream.write(f"{stamp:.6f}\n")
    for event, stamp in zip(out, stamps):
        event["_fusion_read_at"] = stamp
    return out

def thread_id(events: list[dict]) -> str | None:
    for e in events:
        if e.get("type") == "thread.started":
            return e.get("thread_id")
    return None


def summarize(events: list[dict]) -> dict:
    """Usage, commands, and context estimates. turn.completed usage covers the whole turn, so context can only be estimated."""
    usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "requests": 0}
    commands, messages, last_turn_input = [], 0, 0
    for e in events:
        t = e.get("type")
        if t == "turn.completed" and e.get("usage"):
            u = e["usage"]
            usage["input"] = u.get("input_tokens", 0)
            usage["output"] = u.get("output_tokens", 0) + u.get("reasoning_output_tokens", 0)
            usage["cache_read"] = u.get("cached_input_tokens", 0)
            usage["cache_write"] = u.get("cache_write_input_tokens", 0)
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
