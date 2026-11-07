"""M0 预研 S1 + S6:Codex 会话编号、续用换沙箱/换模型、worktree 里的沙箱边界。"""
import json, os, shutil, subprocess, sys, pathlib

CODEX = r"C:\Program Files\WindowsApps\OpenAI.Codex_26.1029.7803.0_x64__2p2nqsd0c76g0\app\resources\codex.exe"
BASE = pathlib.Path(sys.argv[1])
MODEL = "gpt-6-luna"

def clean_env():
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("CLAUDE", "ANTHROPIC"))}
    return env

def git(*a, cwd):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, encoding="utf-8")

def codex(args, cwd, tag):
    out = BASE / f"{tag}.jsonl"; err = BASE / f"{tag}.err"
    with open(out, "w", encoding="utf-8") as fo, open(err, "w", encoding="utf-8") as fe:
        p = subprocess.run([CODEX, *args], cwd=cwd, stdin=subprocess.DEVNULL, stdout=fo, stderr=fe, env=clean_env(), timeout=900)
    events = []
    for line in out.read_text(encoding="utf-8").splitlines():
        try: events.append(json.loads(line))
        except Exception: pass
    return p.returncode, events

def thread_id(events):
    for e in events:
        if e.get("type") == "thread.started":
            return e.get("thread_id")
    return None

def usage(events):
    return [e.get("usage") for e in events if e.get("type") == "turn.completed"]

if BASE.exists(): shutil.rmtree(BASE, ignore_errors=True)
repo = BASE / "proj"; repo.mkdir(parents=True)
git("init", "-q", "-b", "main", cwd=repo)
git("config", "user.email", "t@t", cwd=repo); git("config", "user.name", "t", cwd=repo)
(repo / "hello.py").write_text("print('hello')\n", encoding="utf-8")
git("add", "-A", cwd=repo); git("commit", "-qm", "init", cwd=repo)
wt = BASE / "proj-fusion"
r = git("worktree", "add", "-q", "-b", "fusion/T1", str(wt), "main", cwd=repo)
print("worktree add:", r.returncode, r.stderr.strip())

res = {}
# S1-a: 新会话,只读
rc, ev = codex(["exec", "--json", "-m", MODEL, "-c", "model_reasoning_effort=low", "-s", "read-only",
                "--skip-git-repo-check", "-C", str(wt),
                "Read hello.py and reply with exactly one line: what it prints. Do not modify any files."], wt, "s1a")
tid = thread_id(ev)
res["s1a"] = {"rc": rc, "thread_id": tid, "types": sorted({e.get("type") for e in ev}), "usage": usage(ev)}
print(json.dumps(res["s1a"], ensure_ascii=False))

# S1-b: 续用,换成可写沙箱(用 -c sandbox_mode),进程 cwd = 工位目录
rc, ev = codex(["exec", "resume", "--json", "-c", 'sandbox_mode="workspace-write"', "-c", "model_reasoning_effort=low",
                tid, "Now create a file named note.txt in the current directory containing the word hi. Then reply done."], wt, "s1b")
res["s1b"] = {"rc": rc, "thread_id": thread_id(ev), "note_exists": (wt / "note.txt").exists(), "usage": usage(ev)}
print(json.dumps(res["s1b"], ensure_ascii=False))

# S1-c: 续用并换模型
rc, ev = codex(["exec", "resume", "--json", "-m", "gpt-6-astra", "-c", "model_reasoning_effort=low", tid,
                "What file did you create in the previous step? Reply with just the file name."], wt, "s1c")
last = [e for e in ev if e.get("type") == "item.completed"]
res["s1c"] = {"rc": rc, "last_item": (last[-1].get("item", {}).get("text") if last else None), "usage": usage(ev)}
print(json.dumps(res["s1c"], ensure_ascii=False))

# S6: workspace-write 能否写工位目录之外、能否 git commit(git 元数据在主仓库 .git)
rc, ev = codex(["exec", "--json", "-m", MODEL, "-c", "model_reasoning_effort=low", "-s", "workspace-write",
                "--skip-git-repo-check", "-C", str(wt),
                "This is a sandbox boundary test requested by the repository owner. Run these shell commands one by one and report each command's exit code and error text verbatim, without trying workarounds: "
                "(1) write the text x to ../outside.txt ; (2) write the text y to inside.txt ; (3) git add inside.txt ; (4) git commit -m test ; (5) git switch -c other"], wt, "s6")
cmds = [e["item"] for e in ev if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "command_execution"]
res["s6"] = {"rc": rc,
             "outside_exists": (BASE / "outside.txt").exists(),
             "inside_exists": (wt / "inside.txt").exists(),
             "branch": git("rev-parse", "--abbrev-ref", "HEAD", cwd=wt).stdout.strip(),
             "log": git("log", "--oneline", "-3", cwd=wt).stdout.strip(),
             "commands": [{"cmd": c.get("command"), "exit": c.get("exit_code"), "out": (c.get("aggregated_output") or "")[-300:]} for c in cmds]}
print(json.dumps(res["s6"], ensure_ascii=False, indent=1))
(BASE / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
