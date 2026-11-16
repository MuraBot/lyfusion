"""Project configuration: `fusion/config.json` (tracked) and `fusion/local.json` (untracked)."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path, PureWindowsPath

from . import SCHEMA
from .util import FormatTooNew, FusionError, git

DEFAULT_COMPACT = 400000
DEFAULT_CONTEXT_RATIO = 0.6
HANDOFF_MODES = ["clear", "write", "off"]
# Built-in fallback capabilities from Lily's Codex 0.167 model cache, relayed on 2026-11-14.
MODEL_INFO = {
    "gpt-6.1-sol": {"name": "GPT-6.1-Sol", "efforts": ["low", "medium", "high", "xhigh", "max", "ultra"],
                    "fast": True, "max_compact": 872000},
    "gpt-6-luna": {"name": "GPT-6-Luna", "efforts": ["low", "medium", "high", "xhigh", "max"],
                   "fast": True, "max_compact": 872000},
}
# Lily's sidekick whitelist (rc.5): only these models can be the sidekick; Codex's model cache still supplies their
# names, efforts, Fast Mode and context sizes. A stored model outside it runs as DEFAULT_MODEL.
SIDEKICK_MODELS = ("gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna")
DEFAULT_MODEL = "gpt-6-luna"
# Per-model effort floors with the recommended effort: GPT-6-Luna below high is too weak to work as a sidekick.
EFFORT_POLICY = {"gpt-6-luna": {"min": "high", "recommended": "high"}}
DEFAULT_EFFORTS = ["low", "medium", "high", "xhigh"]
COMPACT_CHOICES = [262144, 400000, 600000, 800000]
_MODEL_CACHE_STATE = None


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def _models_from_state(ordered: list[dict], warning: str | None) -> list[str]:
    """The whitelisted models Codex lists, in its priority order; the built-in ones when its cache is unreadable."""
    if warning is not None:
        return [model for model in SIDEKICK_MODELS if model in MODEL_INFO]
    return [entry["slug"] for entry in sorted(
        ordered,
        key=lambda entry: (entry.get("priority") if isinstance(entry.get("priority"), int)
                           and not isinstance(entry.get("priority"), bool) else 0),
    ) if entry.get("visibility") == "list" and entry["slug"] in SIDEKICK_MODELS]


def _model_cache() -> tuple[dict[str, dict], list[dict], str | None]:
    """Read Codex's model cache once per path and modification time."""
    global _MODEL_CACHE_STATE
    path = codex_home() / "models_cache.json"
    try:
        mtime = path.stat().st_mtime_ns
    except OSError as exc:
        mtime = None
        reason = "file not found" if isinstance(exc, FileNotFoundError) else str(exc)
    else:
        reason = None
    state = _MODEL_CACHE_STATE
    if state is not None and state[0] == path and state[1] == mtime:
        return state[2], state[3], state[4]

    entries: dict[str, dict] = {}
    ordered: list[dict] = []
    if reason is None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            reason = str(exc)
        else:
            if not isinstance(data, dict):
                reason = "top-level value is not an object"
            elif not isinstance(data.get("models"), list):
                reason = "models is not a list"
            else:
                for entry in data["models"]:
                    if not isinstance(entry, dict) or not isinstance(entry.get("slug"), str):
                        continue
                    if entry["slug"] not in entries:
                        entries[entry["slug"]] = entry
                        ordered.append(entry)
                if not entries:
                    reason = "models has no entry with a string slug"

    warning = (
        f"Could not read Codex model cache ({path.as_posix()}): {reason}. "
        "Using the built-in model table."
        if reason is not None else None
    )
    if reason is not None:
        entries, ordered = {}, []
    _MODEL_CACHE_STATE = (path, mtime, entries, ordered, warning)
    return entries, ordered, warning


def known_models() -> list[str]:
    _, ordered, warning = _model_cache()
    return _models_from_state(ordered, warning)


def model_info(model: str) -> dict:
    """Resolve each capability from Codex's cache, then the built-in defaults."""
    entries, _, _ = _model_cache()
    built_in = MODEL_INFO.get(model, {})
    entry = entries.get(model, {})
    name = entry.get("display_name")
    levels = entry.get("supported_reasoning_levels")
    efforts = ([level.get("effort") for level in levels
                if isinstance(level, dict) and isinstance(level.get("effort"), str)]
               if isinstance(levels, list) else None)
    tiers = entry.get("additional_speed_tiers")
    max_compact = entry.get("max_context_window")
    return {
        "name": name if isinstance(name, str) else built_in.get("name", model),
        "efforts": efforts if efforts else built_in.get("efforts", DEFAULT_EFFORTS),
        "fast": ("fast" in tiers if isinstance(tiers, list) and all(isinstance(x, str) for x in tiers)
                 else built_in.get("fast", False)),
        "max_compact": (max_compact if isinstance(max_compact, int) and not isinstance(max_compact, bool)
                        and max_compact > 0 else built_in.get("max_compact")),
    }

DEFAULT_CONFIG = {
    "base_branch": None,          # Default: the branch of the lead worktree at init.
    "test": None,                 # Project test command, e.g. "python -m pytest -q".
    "lint": None,                 # Optional lint command.
    "tests_glob": ["tests/**", "test/**", "**/test_*.py", "**/*_test.py", "**/*.test.js", "**/*.spec.js"],
    "forbidden": [],              # Additional forbidden rules: {"pattern": regex, "why": reason}.
    "station_copy": [],           # Untracked files to copy when creating a worktree.
    "network": False,             # Whether the assistant sandbox can access the network.
    "clean": True,                # Whether Codex ignores user configuration and disables apps and plugins.
    "check_timeout": 900,         # Timeout for each check command (seconds).
    "stall_minutes": 20,          # Time without a new event before it counts as stalled.
    "auto_continue": 2,
    "wait_minutes": 9,           # Maximum wait before returning while a command runs (minutes); 0 = wait indefinitely. Claude Code foreground Bash runs for at most 10 minutes.
    "small_read_lines": 80,        # Maximum output lines for a single read command before it counts as fragmented reading.
    "context_ratio": DEFAULT_CONTEXT_RATIO,  # Must be below 1; switch worktrees before automatic compaction to preserve one-time work rules.
    "handoff_dir": "fusion/handoffs",
    "max_fix_attempts": 2,        # Number of assistant fix attempts after checks fail.
    "max_change_rounds": 3,       # Maximum revision rounds per task; ask the user before exceeding it.
    "runs_keep_days": 30,
    "runs_keep_count": 200,
    "commit_identity": None,      # {"name": ..., "email": ...}; use the repository Git configuration by default.
}

DEFAULT_LOCAL = {
    "enabled": False,
    "handoff_mode": "write",
    "handoff_tokens": 200000,
    "sidekick": {"model": DEFAULT_MODEL, "models": {DEFAULT_MODEL: {"effort": "high", "fast": False}}},
    "env": {},                    # Additional environment variables for the assistant and check commands.
    "codex": None,                # Codex command as a list; found automatically by default.
}

GITIGNORE = "fusion.db\nfusion.db-*\nlocal.json\nruns/\nhandoffs/\ntasks/\n"


def project_root(start: str | os.PathLike | None = None) -> Path:
    start = Path(start or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    code, out, _ = git("rev-parse", "--show-toplevel", cwd=start, check=False)
    if code != 0:
        raise FusionError(f"{start} is not in a Git repository. lyfusion requires Git.")
    return Path(out.strip())


def fusion_dir(root: Path) -> Path:
    return root / "fusion"


def is_fusion_project(root: Path) -> bool:
    return (fusion_dir(root) / "config.json").exists()


def _read(path: Path, default: dict) -> dict:
    data = json.loads(json.dumps(default))
    if path.exists():
        user = json.loads(path.read_text(encoding="utf-8") or "{}")
        version = user.get("schema_version", 1)
        if not isinstance(version, int) or isinstance(version, bool) or version <= 0:
            raise FusionError(f"{path.as_posix()} has an invalid schema_version; it must be a positive integer")
        if version > SCHEMA:
            raise FormatTooNew(path.as_posix(), version)
        for k, v in user.items():
            if k == "schema_version":
                continue
            if isinstance(v, dict) and isinstance(data.get(k), dict):
                data[k].update(v)
            else:
                data[k] = v
    return data


def save_project(root: Path, data: dict) -> None:
    path = fusion_dir(root) / "config.json"
    saved = dict(data)
    saved["schema_version"] = SCHEMA
    path.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load(root: Path) -> dict:
    cfg = _read(fusion_dir(root) / "config.json", DEFAULT_CONFIG)
    cfg["local"] = _read(fusion_dir(root) / "local.json", DEFAULT_LOCAL)
    cfg["local"].pop("clean", None)
    _normalize_sidekick(cfg["local"].setdefault("sidekick", {}))
    if not cfg.get("base_branch"):
        cfg["base_branch"] = git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
    return cfg


def _normalize_sidekick(sidekick: dict) -> None:
    """Migrate the legacy flat effort/fast values into the current model entry."""
    model = sidekick.setdefault("model", DEFAULT_LOCAL["sidekick"]["model"])
    models = sidekick.get("models")
    if not isinstance(models, dict):
        models = {}
    if "effort" in sidekick or "fast" in sidekick:
        legacy = models.setdefault(model, {})
        if "effort" in sidekick:
            legacy["effort"] = sidekick["effort"]
        if "fast" in sidekick:
            legacy["fast"] = sidekick["fast"]
        sidekick.pop("effort", None)
        sidekick.pop("fast", None)
    sidekick["models"] = models
    if model not in SIDEKICK_MODELS:
        # Stored before the whitelist, or by hand: the sidekick runs as the default model
        sidekick["model"] = DEFAULT_MODEL


def current_model_settings(sidekick: dict) -> dict:
    model = sidekick.get("model", DEFAULT_LOCAL["sidekick"]["model"])
    settings = sidekick.get("models", {}).get(model, {})
    if not isinstance(settings, dict):
        settings = {}
    compact = settings.get("compact", DEFAULT_COMPACT)
    if not _valid_compact(compact):
        compact = DEFAULT_COMPACT
    effort = settings.get("effort")
    if model in EFFORT_POLICY and effort not in model_efforts(model):
        # Unset, or below the floor (stored before the policy): the sidekick runs at the recommended effort
        effort = recommended_effort(model) or model_efforts(model)[0]
    return {
        "effort": effort,
        "fast": bool(settings.get("fast", False)) and supports_fast(model),
        "compact": compact,
    }


def model_efforts(model: str) -> list[str]:
    efforts = model_info(model)["efforts"]
    floor = EFFORT_POLICY.get(model, {}).get("min")
    return efforts[efforts.index(floor):] if floor in efforts else efforts


def recommended_effort(model: str) -> str | None:
    effort = EFFORT_POLICY.get(model, {}).get("recommended")
    return effort if effort in model_efforts(model) else None


def supports_fast(model: str) -> bool:
    return bool(model_info(model)["fast"])


def max_compact(model: str) -> int | None:
    return model_info(model)["max_compact"]


def compact_choices(model: str, current: int) -> list[int]:
    limit = max_compact(model)
    choices = [value for value in COMPACT_CHOICES if limit is None or value <= limit]
    if limit is None or current <= limit:
        choices.append(current)
    return sorted(set(choices))


def context_ratio(cfg: dict) -> float:
    ratio = cfg.get("context_ratio", DEFAULT_CONTEXT_RATIO)
    if not _valid_ratio(ratio):
        return DEFAULT_CONTEXT_RATIO
    return float(ratio)


def effective_settings(cfg: dict) -> dict:
    local = cfg.get("local", {})
    sidekick = local.get("sidekick", {})
    model = sidekick.get("model", DEFAULT_LOCAL["sidekick"]["model"])
    settings = current_model_settings(sidekick)
    ratio = context_ratio(cfg)
    clean = cfg.get("clean", True)
    if not isinstance(clean, bool):
        clean = True
    return {
        "model": model,
        "effort": settings["effort"],
        "fast": settings["fast"],
        "compact": settings["compact"],
        "clean": clean,
        "context_ratio": ratio,
        "switch_at": int(settings["compact"] * ratio),
    }


def handoff_settings(cfg: dict) -> dict:
    """Return validated handoff settings, falling back to defaults for stored values."""
    local = cfg.get("local", {})
    mode = local.get("handoff_mode", DEFAULT_LOCAL["handoff_mode"])
    if mode not in HANDOFF_MODES:
        mode = DEFAULT_LOCAL["handoff_mode"]
    tokens = local.get("handoff_tokens", DEFAULT_LOCAL["handoff_tokens"])
    if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens <= 0:
        tokens = DEFAULT_LOCAL["handoff_tokens"]
    handoff_dir = cfg.get("handoff_dir", DEFAULT_CONFIG["handoff_dir"])
    if not isinstance(handoff_dir, str) or not handoff_dir.strip():
        handoff_dir = DEFAULT_CONFIG["handoff_dir"]
    else:
        handoff_dir = handoff_dir.replace("\\", "/").strip()
        parts = handoff_dir.split("/")
        if (not handoff_dir or handoff_dir.startswith("/") or ".." in parts
                or Path(handoff_dir).is_absolute() or PureWindowsPath(handoff_dir).is_absolute()):
            handoff_dir = DEFAULT_CONFIG["handoff_dir"]
    return {"mode": mode, "tokens": tokens, "dir": handoff_dir}


def _valid_compact(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _valid_ratio(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and (not isinstance(value, float) or math.isfinite(value))
        and 0 < value < 1
    )


def configuration_warnings(cfg: dict) -> list[str]:
    warnings = []
    cache_warning = _model_cache()[2]
    if cache_warning is not None:
        warnings.append(cache_warning)
    ratio = cfg.get("context_ratio", DEFAULT_CONTEXT_RATIO)
    if not _valid_ratio(ratio):
        warnings.append(
            f"fusion/config.json has an invalid context_ratio; using {DEFAULT_CONTEXT_RATIO}"
        )
    sidekick = cfg.get("local", {}).get("sidekick", {})
    models = sidekick.get("models", {})
    if isinstance(models, dict):
        for model, model_settings in models.items():
            if (isinstance(model_settings, dict) and "compact" in model_settings
                    and not _valid_compact(model_settings["compact"])):
                warnings.append(
                    f"fusion/local.json has an invalid sidekick.models.{model}.compact; using {DEFAULT_COMPACT}"
                )
    return warnings


def save_local(root: Path, local: dict) -> None:
    path = fusion_dir(root) / "local.json"
    local = dict(local)
    local.pop("clean", None)
    local["schema_version"] = SCHEMA
    path.write_text(json.dumps(local, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_hash(cfg: dict) -> str:
    """Return a configuration fingerprint; if it changes, prior check evidence is invalid."""
    import hashlib
    keys = ("test", "lint", "tests_glob", "forbidden", "network")
    blob = json.dumps({k: cfg.get(k) for k in keys}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def init(root: Path, test: str | None = None, lint: str | None = None) -> dict:
    fd = fusion_dir(root)
    fd.mkdir(exist_ok=True)
    cfg_path = fd / "config.json"
    if not cfg_path.exists():
        cfg = {k: v for k, v in DEFAULT_CONFIG.items() if k in ("test", "lint", "station_copy", "network")}
        cfg["base_branch"] = git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
        cfg["test"], cfg["lint"] = test, lint
        save_project(root, cfg)
    if not (fd / "local.json").exists():
        local = json.loads(json.dumps(DEFAULT_LOCAL))
        local["enabled"] = True
        save_local(root, local)
    elif test is not None or lint is not None:
        cfg = load(root)
        if test is not None:
            cfg["test"] = test
        if lint is not None:
            cfg["lint"] = lint
        save_project(root, {k: v for k, v in cfg.items() if k != "local"})
    (fd / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    return load(root)
