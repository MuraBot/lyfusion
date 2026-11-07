"""把 lyfusion/plugin 打成 zip(文件在 zip 根目录),给 Claude 桌面应用的"管理插件"上传。

    python v5/build_plugin.py

不打包:测试、测试工作目录、__pycache__。
"""
import json
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent / "plugin"
SKIP_DIRS = {"__pycache__", "tests", "_work", ".pytest_cache"}


def main():
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
