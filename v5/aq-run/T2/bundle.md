# T2 交接包

- 状态:停止 · 最后阶段 3 · T2 三阶段已完成：助手设置改为按模型保存，修复五项问题；打包成功。阶段 2 的 8 项测试通过；全量测试中 67 项通过，另按任务卡说明排除一个无法在当前沙箱终止子进程的用例后重跑通过。
- 停止原因:仓库检查遇到环境/范围问题：python tools/check.py 报告 CLAUDE.md 缺失，并提示根目录 README.md 有一条超长句。请 lead 选择：恢复 CLAUDE.md 并处理 README 警告后重跑检查（推荐）；或记录为仓库既有问题并接受 T2。
- 会话编号:01a1b61c-a0bb-7a01-9d1c-35ea35a5a6cf
- 起点提交:8c45bc6a38f8317f0a0bd8da593c758995e5244f · 分支:v5-aq

## 要 lead 回答的问题(验收前要答)
- 仓库检查如何处理：恢复缺失的 CLAUDE.md 并处理 README.md 警告后重跑（推荐），还是将其记录为既有问题并接受 T2？

## 验收命令
- 测试:cd plugin/core && python -m pytest -q tests · 退出码 0
```
....................................................................     [100%]
68 passed in 122.32s (0:02:02)
```
- lint:python -m ruff check plugin/core · 退出码 0
```
All checks passed!
```

## 改动
```
 plugin/commands/fusion.md                  |   6 +-
 plugin/core/fusion_core/aq.py              |  11 ++-
 plugin/core/fusion_core/cli.py             |  37 +++++++--
 plugin/core/fusion_core/codex.py           |   6 +-
 plugin/core/fusion_core/config.py          |  26 +++++-
 plugin/core/fusion_core/gitops.py          |   2 +-
 plugin/core/fusion_core/report_schema.json |  12 ++-
 plugin/core/fusion_core/state.py           |   6 +-
 plugin/core/fusion_core/supervisor.py      |  19 ++---
 plugin/core/fusion_core/views.py           |  33 +++++++-
 plugin/core/tests/test_settings.py         |  85 +++++++++++++++++++
 plugin/core/tests/test_t2_fixes.py         | 127 +++++++++++++++++++++++++++++
 12 files changed, 334 insertions(+), 36 deletions(-)
```

## 最终报告
- 状态:停止 · 最后阶段 3
- 摘要:T2 三阶段已完成：助手设置改为按模型保存，修复五项问题；打包成功。阶段 2 的 8 项测试通过；全量测试中 67 项通过，另按任务卡说明排除一个无法在当前沙箱终止子进程的用例后重跑通过。
- 停止原因:仓库检查遇到环境/范围问题：python tools/check.py 报告 CLAUDE.md 缺失，并提示根目录 README.md 有一条超长句。请 lead 选择：恢复 CLAUDE.md 并处理 README 警告后重跑检查（推荐）；或记录为仓库既有问题并接受 T2。

## 要 lead 回答的问题
- 仓库检查如何处理：恢复缺失的 CLAUDE.md 并处理 README.md 警告后重跑（推荐），还是将其记录为既有问题并接受 T2？

## 修改请求的回应
- 无

## 假设
- 无

## 接口修改请求
- 无

## 给下游
- fusion/local.json 的 sidekick 设置采用 {"model": "名字", "models": {"名字": {"effort": "档位或 null", "fast": true/false}}}；旧版平铺 effort/fast 会在读取时迁移到当前模型。
- 每次运行事件记录实际使用的 model、effort、fast，台账按任务汇总助手档位和 lead/助手 token 用量（单位 M）。

## 问题
- 全量测试中 test_cancel_kills_running 因 Windows 沙箱未能终止子进程而失败，清理时日志文件仍被占用；按任务卡约定使用 -k 排除此用例，67 passed、1 deselected。失败和重跑输出均已保存。
- python tools/check.py 报 CLAUDE.md 不存在，并提示 README.md 第 46 行超长；两者均在任务允许写入范围 plugin/ 之外。
- 未更新 learning.md 的 fusion-core 模块笔记，因为任务卡可写范围限定为 plugin/；T2 工作记录已保存在 dispatch-logs/evidence/T2/notes.md。

## 关键改动(不含测试,每个文件最多 60 行)

### plugin/commands/fusion.md
```diff
@@ -13,9 +13,9 @@ argument-hint: on [--test <命令>] [--lint <命令>] | off | status | model <
 | 空 或 status | `fusion-core status` |
 | on --test 命令 [--lint 命令] | 先 `fusion-core preflight`,汇报未通过项;再运行 `fusion-core on --test "命令" [--lint "命令"]` |
 | off | `fusion-core off` |
-| model 名字 | `fusion-core config set '{"local":{"sidekick":{"model":"名字"}}}'` |
-| effort 档位 | `fusion-core config set '{"local":{"sidekick":{"effort":"档位"}}}'` |
-| fast on / fast off | `fusion-core config set '{"local":{"sidekick":{"fast":true}}}'`(off 写 false) |
+| model 名字 | `fusion-core config model 名字` |
+| effort 档位 | `fusion-core config effort 档位` |
+| fast on / fast off | `fusion-core config fast on|off` |
 | test 命令 | `fusion-core config set '{"config":{"test":"命令"}}'` |
 
 打开后,SessionStart 会注入 4 个动作的使用说明。所有状态都保存在项目的 `fusion/` 目录中。
```

### plugin/core/fusion_core/aq.py
```diff
@@ -81,12 +81,11 @@ def review_pack(root: Path, task: dict, state: dict, round_no: int) -> str:
             reason = f"停下:助手运行没有正常结束,日志在 fusion/runs/{run_id}/"
     else:
         reason = "做完"
-    lines += [
-        "",
-        "## 助手的问题和自定的选择",
-        f"状态:{reason}",
-        f"摘要:{report.get('summary') or ''}",
-    ]
+    lines += ["", "## 助手的问题和自定的选择"]
+    if blocked:
+        lines.append(f"状态:{reason}")
+    else:
+        lines.extend(["状态:做完", f"摘要:{report.get('summary') or ''}"])
     for question in report.get("questions", []):
         lines.append(f"- 问题:{question.get('text', '')}")
     for choice in report.get("choices", []):
```

### plugin/core/fusion_core/cli.py
```diff
@@ -31,6 +31,10 @@ def _wait(root: Path, task_id: str, *, explore: bool = False) -> dict:
     """Wait without a fixed timeout; only durable terminal failure signals stop it."""
     sup = Supervisor(root, poll=0.2)
     try:
+        initial = sup.state()["tasks"].get(task_id)
+        if initial is None:
+            raise FusionError(f"任务 {task_id} 不存在")
+        signal_count = len(initial.get("signals", []))
         while True:
             if store.take_lease(sup.conn, sup.holder):
                 sup.tick()
@@ -47,11 +51,12 @@ def _wait(root: Path, task_id: str, *, explore: bool = False) -> dict:
                 "cancelled",
             ):
                 return state
-            if task.get("signals"):
-                latest = task["signals"][-1]
-                if latest["kind"] == "stalled":
+            new_signals = task.get("signals", [])[signal_count:]
+            signal_count = len(task.get("signals", []))
+            for signal in new_signals:
+                if signal["kind"] == "stalled":
                     raise FusionError(
-                        f"{latest['detail']}\n请再运行同一条命令继续等,或运行 fusion-core cancel --task {task_id}",
+                        f"{signal['detail']}\n请再运行同一条命令继续等,或运行 fusion-core cancel --task {task_id}",
                         code=2,
                     )
             time.sleep(0.2)
@@ -343,7 +348,7 @@ def main(argv=None) -> int:
     sub.add_parser("off")
     sub.add_parser("preflight")
     p = sub.add_parser("config")
-    p.add_argument("action", choices=["get", "set"])
+    p.add_argument("action", choices=["get", "set", "model", "effort", "fast"])
     p.add_argument("json", nargs="?")
     p = sub.add_parser("ledger")
     p.add_argument("--task")
@@ -404,7 +409,7 @@ def main(argv=None) -> int:
             cfg = config_mod.load(root)
             if args.action == "get":
                 print(json.dumps(cfg, ensure_ascii=False, indent=2))
-            else:
+            elif args.action == "set":
                 change = json.loads(args.json or "{}")
                 if "local" in change:
                     local = cfg["local"]
@@ -423,6 +428,26 @@ def main(argv=None) -> int:
                         encoding="utf-8",
                     )
                 print(json.dumps(config_mod.load(root), ensure_ascii=False, indent=2))
+            else:
+                value = args.json
+                if not value:
+                    raise FusionError(f"config {args.action} 需要一个值")
+                sidekick = cfg["local"]["sidekick"]
+                if args.action == "model":
+                    sidekick["model"] = value
+                else:
+                    model = sidekick["model"]
+                    settings = sidekick.setdefault("models", {}).setdefault(model, {})
```
(共 73 行,其余用 git diff 8c45bc6a38f8317f0a0bd8da593c758995e5244f..HEAD -- plugin/core/fusion_core/cli.py)

### plugin/core/fusion_core/codex.py
```diff
@@ -6,6 +6,7 @@ import shutil
 
 
 SCHEMA = Path(__file__).with_name("report_schema.json")
@@ -34,12 +35,13 @@ def build_args(cfg: dict, station: dict, run_dir: Path, sandbox: str, resume_thr
                schema: bool, ephemeral: bool = False) -> list[str]:
     sk = cfg["local"]["sidekick"]
     model = station.get("model") or sk["model"]
-    effort = station.get("effort") or sk.get("effort")
+    settings = current_model_settings(sk) if model == sk.get("model") else sk.get("models", {}).get(model, {})
+    effort = settings.get("effort")
     common = ["--json", "-o", str(run_dir / "last.txt")]
     conf = []
     if effort:
         conf += ["-c", f"model_reasoning_effort={effort}"]
-    if station.get("fast", sk.get("fast")):
+    if settings.get("fast", False):
         conf += ["-c", 'service_tier="fast"']
     if sandbox == "workspace-write" and cfg.get("network"):
         conf += ["-c", "sandbox_workspace_write.network_access=true"]
```

### plugin/core/fusion_core/config.py
```diff
@@ -28,7 +28,7 @@ DEFAULT_CONFIG = {
 
 DEFAULT_LOCAL = {
     "enabled": False,
-    "sidekick": {"model": "gpt-6-luna", "effort": "high", "fast": False},
+    "sidekick": {"model": "gpt-6-luna", "models": {"gpt-6-luna": {"effort": "high", "fast": False}}},
     "env": {},                    # 给助手和检查命令的额外环境变量
     "codex": None,                # Codex 命令,列表;默认自动查找
 }
@@ -67,11 +67,35 @@ def _read(path: Path, default: dict) -> dict:
 def load(root: Path) -> dict:
     cfg = _read(fusion_dir(root) / "config.json", DEFAULT_CONFIG)
     cfg["local"] = _read(fusion_dir(root) / "local.json", DEFAULT_LOCAL)
+    _normalize_sidekick(cfg["local"].setdefault("sidekick", {}))
     if not cfg.get("base_branch"):
         cfg["base_branch"] = git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
     return cfg
 
 
+def _normalize_sidekick(sidekick: dict) -> None:
+    """Migrate the legacy flat effort/fast values into the current model entry."""
+    model = sidekick.setdefault("model", DEFAULT_LOCAL["sidekick"]["model"])
+    models = sidekick.get("models")
+    if not isinstance(models, dict):
+        models = {}
+    if "effort" in sidekick or "fast" in sidekick:
+        legacy = models.setdefault(model, {})
+        if "effort" in sidekick:
+            legacy["effort"] = sidekick["effort"]
+        if "fast" in sidekick:
+            legacy["fast"] = sidekick["fast"]
+        sidekick.pop("effort", None)
+        sidekick.pop("fast", None)
+    sidekick["models"] = models
+
+
+def current_model_settings(sidekick: dict) -> dict:
+    model = sidekick.get("model", DEFAULT_LOCAL["sidekick"]["model"])
+    settings = sidekick.get("models", {}).get(model, {})
+    return {"effort": settings.get("effort"), "fast": bool(settings.get("fast", False))}
+
+
 def save_local(root: Path, local: dict) -> None:
     path = fusion_dir(root) / "local.json"
     path.write_text(json.dumps(local, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
```

### plugin/core/fusion_core/gitops.py
```diff
@@ -192,7 +192,7 @@ def detach_station(wt: Path, base_branch: str) -> None:
 
 
 def bring_changes(root: Path, wt_ref_cwd: Path, base: str, tip: str) -> tuple[list[str], list[str]]:
-    """接管:把任务分支相对起点的改动搬到 lead 的目录(不提交)。lead 改过的文件不覆盖,列出来。"""
+    """把任务分支相对起点的改动搬到 lead 的目录(不提交)。lead 改过的文件不覆盖,列出来。"""
     copied, conflicts = [], []
     for f in changed_files(wt_ref_cwd, base, tip):
         path = f["path"]
```

### plugin/core/fusion_core/report_schema.json
```diff
@@ -10,11 +10,19 @@
       "items": {
         "type": "object",
         "additionalProperties": false,
-        "required": ["text"],
+        "required": ["text", "blocking"],
         "properties": { "text": { "type": "string" }, "blocking": { "type": "boolean" } }
       }
     },
-    "choices": { "type": "array", "items": { "type": "object" } },
+    "choices": {
+      "type": "array",
+      "items": {
+        "type": "object",
+        "additionalProperties": false,
+        "required": ["what", "why"],
+        "properties": { "what": { "type": "string" }, "why": { "type": "string" } }
+      }
+    },
     "problems": { "type": "array", "items": { "type": "string" } }
   }
 }
```

### plugin/core/fusion_core/state.py
```diff
@@ -91,7 +91,8 @@ def _run_started(s, e, d, tid):
     run = s["runs"][d["run"]]
     run.update(status="started", station=d.get("station"), pid=d.get("pid"), dir=d.get("dir"),
                started=e["ts"], ephemeral=bool(d.get("ephemeral")), base=d.get("base"),
-               resumed=bool(d.get("resumed")))
+               resumed=bool(d.get("resumed")), model=d.get("model"), effort=d.get("effort"),
+               fast=d.get("fast"))
     st = s["stations"].get(d.get("station") or "")
     if st:
         st["status"] = "busy"
@@ -153,7 +154,8 @@ def _explore_answered(s, e, d, tid):
 
 
 def _question_asked(s, e, d, tid):
-    q = {**d, "status": "open", "answer": None, "asked": e["ts"]}
+    q = {"id": d["qid"], "run": d.get("run"), "text": d.get("text", ""),
+         "blocking": bool(d.get("blocking")), "status": "open", "answer": None, "asked": e["ts"]}
     s["tasks"][tid]["questions"].append(q)
     s["next_question"] = max(s["next_question"], int(d["qid"][1:]) + 1)
 
```

### plugin/core/fusion_core/supervisor.py
```diff
@@ -47,6 +47,11 @@ def _same_area(files: list[str], globs: list[str]) -> bool:
     )
 
 
+def _execution_settings(cfg, model: str) -> dict:
+    settings = cfg["local"]["sidekick"].get("models", {}).get(model, {})
+    return {"model": model, "effort": settings.get("effort"), "fast": bool(settings.get("fast", False))}
+
+
 class Supervisor:
     def __init__(self, root: Path, poll: float = 2.0):
         self.root = Path(root)
@@ -220,8 +225,6 @@ class Supervisor:
             "line": "main",
             "worktree": str(self.wt),
             "model": sk["model"],
-            "effort": sk.get("effort"),
-            "fast": bool(sk.get("fast")),
             "predecessor": pred,
             "thread": None,
             "status": "idle",
@@ -240,8 +243,6 @@ class Supervisor:
                         "line",
                         "worktree",
                         "model",
-                        "effort",
-                        "fast",
                         "predecessor",
                     )
                 }
@@ -339,6 +340,7 @@ class Supervisor:
                 "type": "run_started",
                 "task": task["id"],
                 "data": {
+                    **_execution_settings(cfg, st["model"]),
                     "run": rid,
                     "station": st["name"],
                     "pid": pid,
@@ -373,6 +375,7 @@ class Supervisor:
                     "type": "run_started",
                     "task": run["task"],
                     "data": {
+                        **_execution_settings(cfg, st["model"]),
                         "run": rid,
                         "station": st["name"],
                         "pid": pid,
@@ -387,8 +390,6 @@ class Supervisor:
                 "name": None,
                 "worktree": str(self.root),
                 "model": sk["model"],
-                "effort": sk.get("effort"),
-                "fast": sk.get("fast"),
             }
             pid = codex.launch(
                 cfg, temp, rdir, prompt, "read-only", None, schema=False, ephemeral=True
@@ -398,6 +399,7 @@ class Supervisor:
                     "type": "run_started",
                     "task": run["task"],
                     "data": {
+                        **_execution_settings(cfg, temp["model"]),
```
(共 82 行,其余用 git diff 8c45bc6a38f8317f0a0bd8da593c758995e5244f..HEAD -- plugin/core/fusion_core/supervisor.py)

### plugin/core/fusion_core/views.py
```diff
@@ -1,6 +1,7 @@
 """Lead-facing status, ledger, and SessionStart usage text."""
 
 
 STATE_CN = {"exploring": "探索中", "explored": "探索完成", "planned": "待派工", "running": "助手在做",
@@ -38,7 +39,11 @@ def status(root, cfg, state, target: str | None = None) -> str:
     if target:
         task = state["tasks"].get(target)
         return task_line(task) if task else f"任务 {target} 不存在"
-    lines = [f"Fusion: {'开启' if cfg.get('local', {}).get('enabled') else '关闭'}"]
+    local = cfg.get("local", {})
+    sk = local.get("sidekick", {})
+    settings = current_model_settings(sk)
+    lines = [f"Fusion: {'开启' if local.get('enabled') else '关闭'}",
+             f"助手: {sk.get('model', '')} · effort {settings['effort'] or '默认'} · fast {'on' if settings['fast'] else 'off'}"]
     for task in state["tasks"].values():
         lines.append(task_line(task))
         if task.get("latest"):
@@ -56,10 +61,32 @@ def prompt_line(state) -> str:
 
 
 def ledger(state, task_id: str | None = None) -> str:
-    lines = ["| 任务 | 状态 | 目标 | 修复 | 修改轮 |", "|---|---|---|---:|---:|"]
+    lines = ["| 任务 | 状态 | 目标 | 修复 | 修改轮 | Lead 输入/缓存/输出 (M) | 助手输入/缓存/输出 (M) | 助手模型 / effort / fast |",
+             "|---|---|---|---:|---:|---:|---:|---|"]
     for task in state["tasks"].values():
         if task_id and task["id"] != task_id:
             continue
         plan = task.get("plan") or {}
-        lines.append(f"| {task['id']} | {task['state']} | {plan.get('goal', '')} | {task['fix_attempts']} | {task['change_rounds']} |")
+        usage = state.get("usage", {}).get(task["id"], {})
+        lead = _usage_triplet(usage.get("lead", {}))
+        assistant = _usage_triplet(usage.get("sidekick", {}))
+        settings = []
+        seen = set()
+        for run_id in task.get("runs", []):
+            run = state.get("runs", {}).get(run_id, {})
+            model = run.get("model")
+            if not model:
+                continue
+            item = (model, run.get("effort") or "默认", "on" if run.get("fast") else "off")
+            if item not in seen:
+                settings.append(" / ".join(item))
+                seen.add(item)
+        lines.append(f"| {task['id']} | {task['state']} | {plan.get('goal', '')} | {task['fix_attempts']} | {task['change_rounds']} | {lead} | {assistant} | {'<br>'.join(settings)} |")
     return "\n".join(lines)
+
+
+def _usage_triplet(usage: dict) -> str:
+    input_m = usage.get("input", 0) / 1_000_000
+    cache_m = (usage.get("cache_read", 0) + usage.get("cache_write", 0)) / 1_000_000
+    output_m = usage.get("output", 0) / 1_000_000
+    return f"{input_m:.3f} / {cache_m:.3f} / {output_m:.3f}"
```

## 模型备注(gpt-6-luna):写修改请求时参考
- 改造现有代码时容易改掉原有行为(报错文字、空行和空值的处理、编号规则、路径解析)。动手前先列出要保留的原有行为,逐条写回归测试。出处:fusion-bench C-H2(seed 空库检查、CSV 空白行、next_id)。C-H3(悬挂引用的报错文字、相对路径),2026-11-03,L3。

## 下一步
- 要改:修改请求写进文件(每条一行,行首写编号 R1、R2…),-Task T2 -Model gpt-6-luna -Resume 01a1b61c-a0bb-7a01-9d1c-35ea35a5a6cf -MessageFile 文件
- 验收:-Task T2 -Accept -Session lead的会话编号 -Note "看了哪些"
- 整个退回:-Task T2 -Rollback -Session lead的会话编号
