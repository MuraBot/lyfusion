"""MCP stdio 服务器:给 lead 提供 fusion_* 工具,同时在后台线程里监督助手。

- 项目没有打开 Fusion(没有 fusion/config.json)时,工具列表是空的,对别的项目零影响
- 打开 Fusion 之后(/fusion on),发 tools/list_changed 通知,工具出现
- 只用标准输入输出做 MCP 通道;日志写 fusion/runs/,不写标准输出
"""
from __future__ import annotations

import json
import sys
import threading
import traceback
from pathlib import Path

from . import VERSION, config as config_mod
from .commands import Ctx
from .supervisor import Supervisor
from .tools import BY_NAME, TOOLS
from .util import FusionError

PROTOCOL = "2025-06-18"


class Server:
    def __init__(self, root: Path | None, stdin=None, stdout=None, supervise: bool = True):
        self.root = root
        self.stdin = stdin or sys.stdin.buffer
        self.stdout = stdout or sys.stdout.buffer
        self.lock = threading.Lock()
        self.supervise = supervise
        self.sup: Supervisor | None = None
        self._enabled_seen = self.active()
        self._stop = threading.Event()

    # ----- 状态 -----
    def active(self) -> bool:
        return bool(self.root) and config_mod.is_fusion_project(self.root)

    def enabled(self) -> bool:
        return self.active() and bool(config_mod.load(self.root)["local"].get("enabled"))

    # ----- 输出 -----
    def send(self, msg: dict) -> None:
        data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        with self.lock:
            self.stdout.write(data)
            self.stdout.flush()

    def log(self, text: str) -> None:
        if self.active():
            p = self.root / "fusion" / "runs" / "mcp.log"
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write(text + "\n")

    # ----- 后台 -----
    def start_background(self) -> None:
        t = threading.Thread(target=self._watch, daemon=True)
        t.start()

    def _watch(self) -> None:
        while not self._stop.is_set():
            try:
                now_active = self.active()
                if now_active != self._enabled_seen:
                    self._enabled_seen = now_active
                    self.send({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})
                if self.supervise and now_active and self.sup is None:
                    self.sup = Supervisor(self.root)
                    threading.Thread(target=self.sup.serve_forever, daemon=True).start()
            except Exception:
                self.log(traceback.format_exc())
            self._stop.wait(3)

    # ----- 请求 -----
    def handle(self, req: dict) -> dict | None:
        method, rid = req.get("method"), req.get("id")
        if rid is None:  # 通知,不回
            return None
        try:
            if method == "initialize":
                ver = (req.get("params") or {}).get("protocolVersion") or PROTOCOL
                result = {"protocolVersion": ver, "capabilities": {"tools": {"listChanged": True}},
                          "serverInfo": {"name": "fusion", "version": VERSION}}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.list_tools()}
            elif method == "tools/call":
                p = req.get("params") or {}
                result = self.call(p.get("name"), p.get("arguments") or {})
            else:
                return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"未知方法 {method}"}}
        except Exception as e:
            self.log(traceback.format_exc())
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32603, "message": str(e)}}
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    def list_tools(self) -> list[dict]:
        if not self.active():
            return []
        return [{"name": t["name"], "description": t["desc"], "inputSchema": t["schema"]} for t in TOOLS]

    def call(self, name: str, args: dict) -> dict:
        tool = BY_NAME.get(name)
        if not tool:
            return _text(f"没有工具 {name}", True)
        if not self.active():
            return _text("这个项目没有打开 Fusion。用 /fusion on 打开。", True)
        if not self.enabled() and name != "fusion_status":
            return _text("Fusion 现在是关闭的(fusion/local.json 里 enabled=false)。用 /fusion on 打开。", True)
        ctx = Ctx(self.root)
        try:
            out = tool["fn"](ctx, args)
            return _text(out.get("text") if isinstance(out, dict) else str(out))
        except FusionError as e:
            return _text(str(e), True)
        except KeyError as e:
            return _text(f"缺少参数 {e}", True)
        except Exception as e:
            self.log(traceback.format_exc())
            return _text(f"引擎出错:{type(e).__name__}: {e}(详情在 fusion/runs/mcp.log)", True)
        finally:
            ctx.close()

    def serve(self) -> None:
        self.start_background()
        for raw in self.stdin:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                self.send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON 解析失败"}})
                continue
            reqs = req if isinstance(req, list) else [req]
            for r in reqs:
                resp = self.handle(r)
                if resp is not None:
                    self.send(resp)
        self._stop.set()
        if self.sup:
            self.sup.stop()


def _text(text: str, error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text or ""}], "isError": error}


def main(root: Path | None) -> None:
    Server(root).serve()
