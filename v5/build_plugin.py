"""把 lyfusion/plugin 打成 zip(文件在 zip 根目录),给 Claude 桌面应用的"管理插件"上传。

    python v5/build_plugin.py --claude "<桌面端自带的 claude.exe>"
    (或者先设环境变量 LYFUSION_CLAUDE_EXE)

打包前先跑 `claude.exe plugin validate plugin`,没过就不打包(Lily 2026-11-14 定:"这个插件检查还挺重要的")。
rc.1 第一次上传时 mod 整个没加载,就是因为没跑这一步。
脚本不去 AppData 里找 claude.exe(工作区规则:脚本不读 AppData 里 Claude 的文件夹),路径由跑的人给:
桌面端自带的在 %LOCALAPPDATA%\\Claude-Data\\<…>\\claude-code\\<版本>\\<hash>\\claude.exe,用版本号最大的那个。

不打包:测试、测试工作目录、__pycache__。
"""
import argparse
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent / "plugin"
SKIP_DIRS = {"__pycache__", "tests", "_work", ".pytest_cache"}
CLAUDE_ENV = "LYFUSION_CLAUDE_EXE"


def validate(claude: str) -> None:
    try:
        result = subprocess.run(
            [claude, "plugin", "validate", str(PLUGIN)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        sys.exit(f"跑不了 plugin validate({claude}):{exc}。不打包")
    output = result.stdout + result.stderr
    if result.returncode != 0 or "Validation passed" not in output:
        print(output)
        sys.exit(f"plugin validate 没过(退出码 {result.returncode}),不打包")
    print("plugin validate:通过")


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # validate 的输出有 GBK 打不出的字符
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="跑 plugin validate,通过后把 plugin/ 打成 zip")
    parser.add_argument("--claude", default=os.environ.get(CLAUDE_ENV),
                        help=f"桌面端自带的 claude.exe;不给就读环境变量 {CLAUDE_ENV}")
    args = parser.parse_args(argv)
    if not args.claude:
        sys.exit(
            f"打包前要跑 plugin validate:用 --claude 或环境变量 {CLAUDE_ENV} 指定 claude.exe"
            "(桌面端自带的在 %LOCALAPPDATA%\\Claude-Data\\<…>\\claude-code\\<版本>\\<hash>\\claude.exe,用版本号最大的)"
        )
    validate(args.claude)

    meta = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    out = HERE / "dist" / f"{meta['name']}-{meta['version']}.zip"
    out.parent.mkdir(exist_ok=True)
    files = []
    for p in sorted(PLUGIN.rglob("*")):
        rel = p.relative_to(PLUGIN)
        if p.is_dir() or any(part in SKIP_DIRS for part in rel.parts):
            continue
        files.append((p, rel.as_posix()))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p, arc in files:
            z.write(p, arc)
    print(out)
    for _, arc in files:
        print("  ", arc)


if __name__ == "__main__":
    main()
