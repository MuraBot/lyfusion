"""假 Codex:按剧本输出事件、改文件、写最终回复。只给测试用。

剧本是 JSON 列表,每次被调用取下一步(计数器存在剧本旁边)。一步可以有:
  write: {路径: 内容}       在工作目录里写文件
  delete: [路径]
  commands: [{"command": "...", "exit": 0}]
  report: {...}             最终回复(JSON 报告);或 text: "..." 原样输出
  sleep: 秒
  resume_fails: true        续用时假装找不到会话(不输出 thread.started、不写最终回复)
  input_tokens / output_tokens
"""
import json
import os
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path


def main():
    args = sys.argv[1:]
    if args == ["--version"]:
        print(os.environ.get("FAKE_CODEX_VERSION", "codex fake-1.0"))
        return
    if args in (["exec", "--help"], ["exec", "resume", "--help"]):
        mode = "EXEC" if args == ["exec", "--help"] else "RESUME"
        missing = set(os.environ.get(f"FAKE_CODEX_{mode}_HELP_MISSING", "").split(","))
        flags = [flag for flag in ("--ignore-user-config", "--disable") if flag not in missing]
        print("Options:\n" + "\n".join(flags))
        return
    if args and args[0] == "sandbox":
        if os.environ.get("FAKE_CODEX_SANDBOX_FAIL"):
            print("rejected: blocked by policy", file=sys.stderr)
            raise SystemExit(1)
        separator = args.index("--")
        command = args[separator + 1:]
        raise SystemExit(subprocess.run(command, check=False).returncode)
    if args == ["features", "list"]:
        print(os.environ.get("FAKE_CODEX_FEATURES", "apps\nplugins"))
        return
    script = Path(os.environ["FAKE_CODEX_SCRIPT"])
    log = script.with_suffix(".calls.jsonl")
    counter = script.with_suffix(".n")
    n = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(n + 1))
    steps = json.loads(script.read_text(encoding="utf-8"))
    step = steps[n] if n < len(steps) else {"report": _report("没有更多剧本")}
    stdin_is_file = stat.S_ISREG(os.fstat(0).st_mode)
    prompt = sys.stdin.buffer.read().decode("utf-8")
    resume = len(args) > 1 and args[0] == "exec" and args[1] == "resume"
    thread = None
    if resume:
        thread = args[-2]
    out = args[args.index("-o") + 1] if "-o" in args else None
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"n": n, "args": args, "cwd": os.getcwd(), "prompt": prompt, "resume": resume,
                            "thread": thread, "stdin_is_file": stdin_is_file}, ensure_ascii=False) + "\n")

    def emit(obj):
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    if resume and step.get("resume_fails"):
        sys.stderr.write("Error: thread not found\n")
        sys.exit(1)
    emit({"type": "thread.started", "thread_id": thread or str(uuid.uuid4())})
    emit({"type": "turn.started"})
    if step.get("sleep"):
        time.sleep(step["sleep"])
    for path, content in (step.get("write") or {}).items():
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    for path in step.get("delete") or []:
        Path(path).unlink(missing_ok=True)
    for i, c in enumerate(step.get("commands") or []):
        command_item = {"id": f"c{i}", "type": "command_execution", "command": c["command"]}
        emit({"type": "item.started", "item": command_item})
        emit({"type": "item.completed", "item": {**command_item, "exit_code": c.get("exit", 0),
                                                 "aggregated_output": c.get("output", "")}})
    text = step.get("text")
    if text is None:
        text = json.dumps(step.get("report") or _report("做完了"), ensure_ascii=False)
    emit({"type": "item.completed", "item": {"id": "m", "type": "agent_message", "text": text}})
    emit({"type": "turn.completed", "usage": {"input_tokens": step.get("input_tokens", 1000),
                                              "cached_input_tokens": 800, "cache_write_input_tokens": 0,
                                              "output_tokens": step.get("output_tokens", 100),
                                              "reasoning_output_tokens": 20}})
    if out:
        Path(out).write_text(text, encoding="utf-8")


def _report(summary, **kw):
    r = {"status": "done", "summary": summary, "choices": [], "questions": [], "problems": []}
    r.update(kw)
    return r


if __name__ == "__main__":
    main()
