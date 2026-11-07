"""最小的 MCP stdio 服务器(Python 标准库),用来测 S2。"""
import json, os, subprocess, sys, time, pathlib

LOG_DIR = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()) / ".probe"
LOG_DIR.mkdir(exist_ok=True)
START = time.time()

def log(obj):
    with open(LOG_DIR / "server.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": round(time.time() - START, 1), **obj}, ensure_ascii=False) + "\n")

TOOLS = [
    {"name": "probe_info", "description": "Report the probe server's pid, cwd and environment facts.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "probe_spawn", "description": "Spawn a detached child that writes a heartbeat every 10 s for 10 minutes.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "probe_child", "description": "Report whether the spawned child is alive and its last heartbeat.",
     "inputSchema": {"type": "object", "properties": {}}},
]

CHILD = r'''
import sys, time
p = sys.argv[1]
for i in range(60):
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} beat {i}\n")
    time.sleep(10)
'''

def call(name):
    if name == "probe_info":
        return {"pid": os.getpid(), "cwd": os.getcwd(), "python": sys.version.split()[0],
                "CLAUDE_PROJECT_DIR": os.environ.get("CLAUDE_PROJECT_DIR"),
                "CLAUDE_PLUGIN_ROOT": os.environ.get("CLAUDE_PLUGIN_ROOT"),
                "uptime_s": round(time.time() - START, 1)}
    if name == "probe_spawn":
        beat = LOG_DIR / "child-heartbeat.txt"
        script = LOG_DIR / "child.py"
        script.write_text(CHILD, encoding="utf-8")
        out = open(LOG_DIR / "child.out", "w", encoding="utf-8")
        flags = 0
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_BREAKAWAY_FROM_JOB
        try:
            p = subprocess.Popen([sys.executable, str(script), str(beat)], stdin=subprocess.DEVNULL, stdout=out,
                                 stderr=subprocess.STDOUT, creationflags=flags, close_fds=True)
            breakaway = True
        except OSError as e:
            flags &= ~getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
            p = subprocess.Popen([sys.executable, str(script), str(beat)], stdin=subprocess.DEVNULL, stdout=out,
                                 stderr=subprocess.STDOUT, creationflags=flags, close_fds=True)
            breakaway = f"failed: {e}"
        (LOG_DIR / "child.pid").write_text(str(p.pid))
        log({"spawn": p.pid, "breakaway": breakaway})
        return {"child_pid": p.pid, "breakaway": breakaway}
    if name == "probe_child":
        beat = LOG_DIR / "child-heartbeat.txt"
        lines = beat.read_text(encoding="utf-8").splitlines() if beat.exists() else []
        return {"beats": len(lines), "last": lines[-1] if lines else None}
    raise KeyError(name)

def send(msg):
    sys.stdout.buffer.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()

log({"event": "start", "pid": os.getpid(), "cwd": os.getcwd()})
for raw in sys.stdin.buffer:
    line = raw.decode("utf-8").strip()
    if not line:
        continue
    req = json.loads(line)
    mid, method = req.get("id"), req.get("method")
    log({"method": method})
    if mid is None:
        continue  # 通知,不回
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": req.get("params", {}).get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}}, "serverInfo": {"name": "fusion-probe", "version": "0.0.1"}}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
    elif method == "tools/call":
        try:
            out = call(req["params"]["name"])
            send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}]}})
        except Exception as e:
            send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True}})
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": mid, "result": {}})
    else:
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}})
log({"event": "stdin closed"})
