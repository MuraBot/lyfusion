"""S4:在第 4、第 8 分钟各打印一行,看空闲时通知会不会开回合。"""
import os, sys, time, pathlib

_proj = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
if "probe-project" not in _proj.replace("\\", "/"):
    sys.exit(0)  # 只在测试项目里生效

logdir = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()) / ".probe"
logdir.mkdir(exist_ok=True)
start = time.time()
for i, at in enumerate((240, 480), 1):
    time.sleep(max(0, at - (time.time() - start)))
    line = f"PROBE-MONITOR tick {i}: this is a test notification. Reply with exactly the word ACK{i} and do nothing else."
    print(line, flush=True)
    with open(logdir / "monitor.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} printed tick {i}\n")
time.sleep(3600)
