"""项目配置:`fusion/config.json`(进 git)和 `fusion/local.json`(不进 git)。"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

from .util import FusionError, git

DEFAULT_COMPACT = 400000
DEFAULT_CONTEXT_RATIO = 0.6

DEFAULT_CONFIG = {
    "base_branch": None,          # 默认:init 时 lead 工作目录所在的分支
    "test": None,                 # 项目测试命令,例如 "python -m pytest -q"
    "lint": None,                 # lint 命令,可以没有
    "tests_glob": ["tests/**", "test/**", "**/test_*.py", "**/*_test.py", "**/*.test.js", "**/*.spec.js"],
    "forbidden": [],              # 额外的禁止规则:{"pattern": 正则, "why": 原因}
    "station_copy": [],           # 建工位目录时要复制的未跟踪文件
    "network": False,             # 助手的沙箱能否联网
    "clean": True,                # Codex 是否不读用户配置并禁用 apps、plugins
    "check_timeout": 900,         # 单条检查命令的超时(秒)
    "stall_minutes": 20,          # 多久没有新事件算"长时间无进展"
    "context_ratio": DEFAULT_CONTEXT_RATIO,  # 必须小于 1,在自动压缩前换工位,避免压缩丢掉只发送一次的工作规则
    "max_fix_attempts": 2,        # 检查失败后让助手修的次数
    "max_change_rounds": 3,       # 同一个任务修改意见的轮数上限,超过要先问用户
    "runs_keep_days": 30,
    "runs_keep_count": 200,
    "commit_identity": None,      # {"name": ..., "email": ...};默认用仓库自己的 git 配置
}

DEFAULT_LOCAL = {
    "enabled": False,
    "sidekick": {"model": "gpt-6-luna", "models": {"gpt-6-luna": {"effort": "high", "fast": False}}},
    "env": {},                    # 给助手和检查命令的额外环境变量
    "codex": None,                # Codex 命令,列表;默认自动查找
}

GITIGNORE = "fusion.db\nfusion.db-*\nlocal.json\nruns/\nhandoffs/\nexplore.md\nreview.md\ntasks/\n"


def project_root(start: str | os.PathLike | None = None) -> Path:
    start = Path(start or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    code, out, _ = git("rev-parse", "--show-toplevel", cwd=start, check=False)
    if code != 0:
        raise FusionError(f"{start} 不在 git 仓库里。lyfusion 需要 git。")
    return Path(out.strip())


def fusion_dir(root: Path) -> Path:
    return root / "fusion"


def is_fusion_project(root: Path) -> bool:
    return (fusion_dir(root) / "config.json").exists()


def _read(path: Path, default: dict) -> dict:
    data = json.loads(json.dumps(default))
    if path.exists():
        user = json.loads(path.read_text(encoding="utf-8") or "{}")
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(data.get(k), dict):
                data[k].update(v)
            else:
                data[k] = v
    return data


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


def current_model_settings(sidekick: dict) -> dict:
    model = sidekick.get("model", DEFAULT_LOCAL["sidekick"]["model"])
    settings = sidekick.get("models", {}).get(model, {})
    if not isinstance(settings, dict):
        settings = {}
    compact = settings.get("compact", DEFAULT_COMPACT)
    if not _valid_compact(compact):
        compact = DEFAULT_COMPACT
    return {
        "effort": settings.get("effort"),
        "fast": bool(settings.get("fast", False)),
        "compact": compact,
    }


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
    ratio = cfg.get("context_ratio", DEFAULT_CONTEXT_RATIO)
    if not _valid_ratio(ratio):
        warnings.append(
            f"fusion/config.json 的 context_ratio 无效,按 {DEFAULT_CONTEXT_RATIO} 计算"
        )
    sidekick = cfg.get("local", {}).get("sidekick", {})
    models = sidekick.get("models", {})
    if isinstance(models, dict):
        for model, model_settings in models.items():
            if (isinstance(model_settings, dict) and "compact" in model_settings
                    and not _valid_compact(model_settings["compact"])):
                warnings.append(
                    f"fusion/local.json 的 sidekick.models.{model}.compact 无效,按 {DEFAULT_COMPACT} 计算"
                )
    return warnings


def save_local(root: Path, local: dict) -> None:
    path = fusion_dir(root) / "local.json"
    local = dict(local)
    local.pop("clean", None)
    path.write_text(json.dumps(local, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_hash(cfg: dict) -> str:
    """检查配置的指纹:变了,旧的检查证据就失效。"""
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
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
        cfg_path.write_text(json.dumps({k: v for k, v in cfg.items() if k != "local"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (fd / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    return load(root)
