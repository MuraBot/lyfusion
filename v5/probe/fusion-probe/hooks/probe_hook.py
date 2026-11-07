"""记录钩子输入(不记 transcript_path 以外的路径内容),输出可识别的注入文字。"""
import json, os, sys, time, pathlib

_proj = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
if "probe-project" not in _proj.replace("\\", "/"):
    sys.exit(0)  # 只在测试项目里生效

event = sys.argv[1]
data = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
proj = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())
logdir = proj / ".probe"; logdir.mkdir(exist_ok=True)
keep = {k: data.get(k) for k in ("session_id", "cwd", "source", "hook_event_name", "tool_name", "model", "permission_mode")}
if event == "PreToolUse":
    keep["file_path"] = (data.get("tool_input") or {}).get("file_path")
with open(logdir / "hooks.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": time.strftime("%H:%M:%S"), "event": event, **keep}, ensure_ascii=False) + "\n")

if event == "SessionStart":
    ctx = f"PROBE-SESSIONSTART source={data.get('source')}"
elif event == "UserPromptSubmit":
    ctx = "PROBE-PROMPT"
else:
    ctx = f"PROBE-EDIT file={keep.get('file_path')}"
print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": ctx}}, ensure_ascii=False))
