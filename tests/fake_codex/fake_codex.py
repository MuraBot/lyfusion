# 假的 codex 命令行,只给 tests/test_dispatch.py 用。按 FAKE_SCENARIO 模拟助手的行为,不联网。
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
state = Path(os.environ["FAKE_STATE"])
calls = json.loads(state.read_text(encoding="utf-8")) if state.exists() else []
calls.append({"args": args, "cwd": os.getcwd(), "path0": os.environ["PATH"].split(os.pathsep)[0],
              "claudeEnv": [k for k in os.environ if k.upper().startswith(("CLAUDE", "ANTHROPIC"))]})
state.write_text(json.dumps(calls, ensure_ascii=False), encoding="utf-8")
n = len(calls)
out = args[args.index("-o") + 1]
scenario = os.environ.get("FAKE_SCENARIO", "partial")


def evidence(phase):
    ev = Path("dispatch-logs/evidence/T5/%d" % phase)
    ev.mkdir(parents=True, exist_ok=True)
    (ev / "run.txt").write_text("命令:x\n退出码:0\n", encoding="utf-8")


final = {"status": "完成", "last_phase": 0, "stop_reason": "", "summary": "假的", "assumptions": ["超时按 5 秒"],
         "interface_requests": [], "downstream": [], "problems": []}
if scenario == "partial":
    # 第 1 次只做阶段 1 就说完成(阶段 2 没有证据),第 2 次补上
    Path("src").mkdir(exist_ok=True)
    Path("src/feature.txt").write_text("阶段 %d\n" % n, encoding="utf-8")
    evidence(n)
    final["last_phase"] = n
elif scenario == "noreport":
    # 阶段都做完了,第 1 次却没写最终报告
    evidence(1)
    evidence(2)
    final = "做完了" if n == 1 else dict(final, last_phase=2)
elif scenario == "stop":
    evidence(1)
    final.update(status="停止", last_phase=1, stop_reason="产品决定:颜色")
elif scenario == "review":
    final = "## 审查报告\n无问题"
print(json.dumps({"type": "thread.started", "thread_id": "fake-thread"}))
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 100 * n, "cached_input_tokens": 10, "output_tokens": 5}}))
Path(out).write_text(final if isinstance(final, str) else json.dumps(final, ensure_ascii=False), encoding="utf-8")
if os.environ.get("FAKE_LINGER"):
    # 像 Codex 启动时后台拉插件市场的 git:继承了输出管道,比 Codex 本身活得久
    import subprocess
    sys.stdout.flush()
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"], stdout=sys.stdout, stderr=sys.stderr, close_fds=False)
