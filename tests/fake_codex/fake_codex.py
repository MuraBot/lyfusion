# 假的 codex 命令行,只给 tests/test_dispatch.py 用。按 FAKE_SCENARIO 模拟助手的行为,不联网。
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
state = Path(os.environ["FAKE_STATE"])
calls = json.loads(state.read_text(encoding="utf-8")) if state.exists() else []
calls.append({"args": args, "cwd": os.getcwd(), "path0": os.environ["PATH"].split(os.pathsep)[0],
              "claudeEnv": [k for k in os.environ if k.upper().startswith(("CLAUDE", "ANTHROPIC"))],
              "temp": os.environ.get("TEMP", "")})
state.write_text(json.dumps(calls, ensure_ascii=False), encoding="utf-8")
n = len(calls)
out = args[args.index("-o") + 1]
scenario = os.environ.get("FAKE_SCENARIO", "partial")


def evidence(phase):
    ev = Path("dispatch-logs/evidence/T5/%d" % phase)
    ev.mkdir(parents=True, exist_ok=True)
    (ev / "run.txt").write_text("命令:x\n退出码:0\n", encoding="utf-8")


final = {"status": "完成", "last_phase": 0, "stop_reason": "", "summary": "假的", "assumptions": ["超时按 5 秒"],
         "questions": [x for x in os.environ.get("FAKE_QUESTIONS", "").split(",") if x],
         "responses": [x for x in os.environ.get("FAKE_RESPONSES", "").split(",") if x],
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
elif scenario == "explore":
    final = "src/a.py:1-3 片段:def hit(): ..."
elif scenario == "lintfix":
    # 第 1 次做完两个阶段;lint 不通过后被续用,才补上 lint-ok.txt
    Path("src").mkdir(exist_ok=True)
    Path("src/feature.txt").write_text("功能\n", encoding="utf-8")
    evidence(1)
    evidence(2)
    final["last_phase"] = 2
    if "没通过" in args[-1]:
        Path("lint-ok.txt").write_text("ok", encoding="utf-8")
elif scenario == "branch":
    # HEX T9:助手照简报的"分支"一行自己建了分支
    import subprocess
    subprocess.run(["git", "switch", "-q", "-c", "task/T5"], check=True)
    Path("src").mkdir(exist_ok=True)
    Path("src/feature.txt").write_text("功能\n", encoding="utf-8")
    evidence(1)
    evidence(2)
    final["last_phase"] = 2
elif scenario == "sneaky":
    # HEX T4、T12:改弱了原有测试的断言,验收时用了关掉证书检查的参数
    Path("src/test/FooTest.java").write_text("class FooTest {\n  void a() { assertTrue(x > 0); }\n}\n", encoding="utf-8")
    Path("src/feature.txt").write_text("功能\n", encoding="utf-8")
    evidence(1)
    evidence(2)
    final["last_phase"] = 2
    # 改完又删掉的临时探针:diff 里看不到,事件流里有
    probe = os.path.join(os.getcwd(), "tmp", "Probe.java")
    print(json.dumps({"type": "item.completed", "item": {"type": "file_change", "changes": [{"path": probe, "kind": "delete"}]}}))
    print(json.dumps({"type": "item.completed", "item": {"type": "command_execution",
                                                         "command": "gradlew -Dnet.minecraftforge.gradle.check.certs=false test"}}))
elif scenario == "stop":
    evidence(1)
    final.update(status="停止", last_phase=1, stop_reason="产品决定:颜色")
print(json.dumps({"type": "thread.started", "thread_id": "fake-thread"}))
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 100 * n, "cached_input_tokens": 10, "output_tokens": 5}}))
Path(out).write_text(final if isinstance(final, str) else json.dumps(final, ensure_ascii=False), encoding="utf-8")
if os.environ.get("FAKE_LINGER"):
    # 像 Codex 启动时后台拉插件市场的 git:继承了输出管道,比 Codex 本身活得久
    import subprocess
    sys.stdout.flush()
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"], stdout=sys.stdout, stderr=sys.stderr, close_fds=False)
