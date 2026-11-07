"""生成 `fusion/intent.md`:给人和助手读,进 git。末尾附 JSON,事件库丢了时能恢复当前决定。"""
from __future__ import annotations

import json
import re
from pathlib import Path

CAT = {"experience": "体验", "interface": "接口", "rule": "规则", "constraint": "约束"}
MARK = "lyfusion-intent-data"


def render(state: dict) -> str:
    decs = sorted(state["decisions"].values(), key=lambda d: int(d["id"][1:]))
    active = [d for d in decs if d["status"] == "active"]
    old = [d for d in decs if d["status"] != "active"]
    lines = ["# 意图记录", "",
             "> 由 lyfusion 生成,不要手改。要改决定,请让 lead 用 intent 工具。",
             f"> 有效决定 {len(active)} 条,已取代 {len(old)} 条。", ""]
    for d in active:
        lines += _one(d)
    if old:
        lines += ["## 已取代", ""]
        for d in old:
            lines.append(f"- {d['id']}@{d['version']}:{_short(d.get('content'))}"
                         + (f"(由 {d['superseded_by']} 取代)" if d.get("superseded_by") else ""))
        lines.append("")
    data = {"decisions": decs}
    lines += [f"<!-- {MARK}", json.dumps(data, ensure_ascii=False), "-->", ""]
    return "\n".join(lines)


def _short(text, n=60):
    text = (text or "").replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def _one(d: dict) -> list[str]:
    out = [f"## {d['id']}@{d['version']} · {CAT.get(d.get('category'), d.get('category'))}", "", d.get("content", ""), ""]
    if d.get("reason"):
        out.append(f"- 理由:{d['reason']}")
    if d.get("scope"):
        out.append("- 影响:" + "、".join(f"`{x}`" for x in d["scope"]))
    if d.get("source"):
        out.append(f"- 来源:{d['source']}")
    for key, label in (("examples", "样例"), ("counterexamples", "反例"), ("rejected", "否决过的方案")):
        for x in d.get(key) or []:
            out.append(f"- {label}:{x}")
    if d.get("check"):
        out.append(f"- 检查:`{d['check']['run']}`")
    out.append("")
    return out


def write(root: Path, state: dict) -> bool:
    """写 intent.md,内容有变化时返回 True。"""
    path = root / "fusion" / "intent.md"
    text = render(state)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def recover(root: Path) -> list[dict]:
    """从 intent.md 读回决定(事件库丢失时用)。"""
    path = root / "fusion" / "intent.md"
    if not path.exists():
        return []
    m = re.search(rf"<!-- {MARK}\n(.*?)\n-->", path.read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1))["decisions"] if m else []


def for_prompt(state: dict, refs: list[str]) -> str:
    """派工时附给助手的决定全文。"""
    out = []
    for ref in refs:
        did = ref.split("@")[0]
        d = state["decisions"].get(did)
        if not d:
            continue
        out += _one(d)
    return "\n".join(out).strip()
