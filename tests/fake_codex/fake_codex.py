# 假的 codex 命令行,只给 tests/test_dispatch.py 用。按 FAKE_SCENARIO 模拟助手的行为,不联网。
import json
import os
import subprocess
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


def report(phase):
    ev = Path("dispatch-logs/evidence/T5/%d" % phase)
    ev.mkdir(parents=True, exist_ok=True)
    (ev / "run.txt").write_text("命令:x\n退出码:0\n", encoding="utf-8")
    subprocess.run([sys.executable, "tools/mail.py", "send", "T5", "report", "--phase", str(phase), "--summary", "好",
                    "--evidence", ev.as_posix(), "--decisions", "无", "--problems", "无", "--downstream", "无"], check=True)


final = {"status": "完成", "last_phase": 0, "stop_reason": "", "summary": "假的"}
if scenario == "partial":
    # 第 1 次只做阶段 1 就说完成(漏了阶段 2 的回报),第 2 次补上
    Path("src").mkdir(exist_ok=True)
    Path("src/feature.txt").write_text("阶段 %d\n" % n, encoding="utf-8")
    report(n)
    final["last_phase"] = n
elif scenario == "stop":
    report(1)
    final.update(status="停止", last_phase=1, stop_reason="产品决定")
elif scenario == "review":
    final = None
print(json.dumps({"type": "thread.started", "thread_id": "fake-thread"}))
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 100 * n, "cached_input_tokens": 10, "output_tokens": 5}}))
Path(out).write_text(json.dumps(final, ensure_ascii=False) if final else "## 审查报告\n无问题", encoding="utf-8")
