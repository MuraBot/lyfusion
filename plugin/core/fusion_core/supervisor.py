"""监督者:根据事件做真正的动作(启动 Codex、提交候选、跑检查、合并、清理),再把结果写成事件。

命令只写"想要什么"(例如 run_requested),监督者负责"去做"。这样命令很快、可以重复调用;
动作做到一半崩溃了,下次启动时按状态对账接着做。
"""
from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path

from . import aq, checks, codex, config as config_mod, gitops, prompts, store, validate
from .state import TERMINAL, current_station, replay
from .util import FusionError, git, globs_overlap, kill_tree, now, pid_alive, redact_file


def _same_area(files: list[str], globs: list[str]) -> bool:
    """工位做过的文件和新任务的范围是不是同一块地方:文件范围重叠,或者有共同的目录。"""
    if globs_overlap(files, globs):
        return True

    def dirs(paths):
        out = set()
        for p in paths:
            fixed = p.replace("\\", "/").split("*")[0]
            d = fixed.rsplit("/", 1)[0] if "/" in fixed else ""
            out.add(d)
        return out
    a, b = dirs(files), dirs(globs)
    return any(x == y or (x and y and (x.startswith(y + "/") or y.startswith(x + "/"))) for x in a for y in b)


class Supervisor:
    def __init__(self, root: Path, poll: float = 2.0):
        self.root = Path(root)
        self.poll = poll
        self.conn = store.connect(self.root)
        self.holder = store.holder_id()
        self._stop = threading.Event()
        self._stall_flagged: set[str] = set()
        self._last_error: str | None = None

    # ---------- 基础 ----------
    def cfg(self) -> dict:
        return config_mod.load(self.root)

    def state(self) -> dict:
        return replay(store.read(self.conn))

    def emit(self, events: list[dict]) -> None:
        if events:
            with store.transaction(self.conn):
                store.append(self.conn, events, "engine")

    def run_dir(self, rid: str) -> Path:
        return self.root / "fusion" / "runs" / rid

    @property
    def wt(self) -> Path:
        return gitops.station_dir(self.root)

    # ---------- 循环 ----------
    def prune_runs(self) -> int:
        """runs/ 保留最近 runs_keep_count 次,或 runs_keep_days 天内的运行;只删已经结束的运行。"""
        import shutil
        cfg, s = self.cfg(), self.state()
        keep_n, keep_days = cfg.get("runs_keep_count", 200), cfg.get("runs_keep_days", 30)
        ended = sorted((r for r in s["runs"].values() if r["status"] == "ended" and r.get("dir")),
                       key=lambda r: int(r["id"][1:]))
        old = ended[:-keep_n] if keep_n else ended
        cutoff = time.time() - keep_days * 86400
        n = 0
        for r in old:
            d = Path(r["dir"])
            if d.exists() and d.parent == self.root / "fusion" / "runs" and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                n += 1
        return n

    def serve_forever(self) -> None:
        try:
            self.prune_runs()
        except Exception as e:
            self._log_error(e)
        while not self._stop.is_set():
            try:
                if store.take_lease(self.conn, self.holder):
                    while self.tick() and not self._stop.is_set():
                        pass
            except Exception as e:  # 监督者不能死;记下错误,下一轮再试
                self._log_error(e)
            self._stop.wait(self.poll)
        try:
            store.release_lease(self.conn, self.holder)
        except Exception:
            pass

    def stop(self) -> None:
        self._stop.set()

    def _log_error(self, e: Exception) -> None:
        msg = f"{type(e).__name__}: {e}"
        path = self.root / "fusion" / "runs" / "supervisor-errors.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{now()} {msg}\n{traceback.format_exc()}\n")
        if msg != self._last_error:
            self._last_error = msg
            try:
                self.emit([{"type": "engine_error", "data": {"error": msg[:800], "log": str(path)}}])
            except Exception:
                pass

    def tick(self) -> int:
        """做一件能做的事,返回 1;没事可做返回 0。"""
        s = self.state()
        cfg = self.cfg()
        for t in s["tasks"].values():
            if t.get("takeover") and not t.get("takeover_done"):
                self.do_takeover(s, cfg, t)
                return 1
            if t["state"] in ("rejected", "cancelled") and not t.get("cleaned"):
                self.cleanup(s, cfg, t)
                return 1
        for run in s["runs"].values():
            if run["status"] == "started" and self.poll_run(s, cfg, run):
                return 1
        for run in s["runs"].values():
            if run["status"] == "requested":
                t = s["tasks"].get(run["task"] or "")
                if t and (t["state"] in TERMINAL or t.get("takeover")):
                    self.emit([{"type": "run_ended", "task": t["id"],
                                "data": {"run": run["id"], "result": "cancelled"}}])
                elif self._station_busy(s) and run["kind"] != "explore":
                    continue
                else:
                    self.start_run(s, cfg, run)
                return 1
        for t in s["tasks"].values():
            cand = s["candidates"].get(t["latest"] or "")
            if t["state"] == "checking" and cand and not cand.get("checks"):
                self.check_candidate(s, cfg, t, cand, None)
                return 1
            if t["state"] == "in_review" and cand and cand.get("checks"):
                chk = cand["checks"]
                if chk.get("plan_version") != t["version"] or chk.get("check_hash") != config_mod.check_hash(cfg):
                    self.check_candidate(s, cfg, t, cand, None, recheck=True)
                    return 1
            if t["state"] == "integrating":
                self.integrate(s, cfg, t)
                return 1
        return 0

    def drain(self, limit: int = 400, wait: float = 0.1) -> None:
        """测试和基准用:一直做到没有事可做、也没有在跑的运行。"""
        for _ in range(limit):
            n = self.tick()
            s = self.state()
            busy = any(r["status"] in ("requested", "started") for r in s["runs"].values())
            if n == 0 and not busy:
                return
            if n == 0:
                time.sleep(wait)
        raise FusionError("drain 超过次数上限")

    @staticmethod
    def _station_busy(s) -> bool:
        return any(r["status"] == "started" and r.get("station") for r in s["runs"].values())

    # ---------- 工位 ----------
    def _new_station(self, s, cfg, pred: str | None) -> tuple[dict, dict]:
        sk = cfg["local"]["sidekick"]
        n = s["station_seq"].get("main", 0) + 1
        st = {"name": f"main#{n}", "line": "main", "worktree": str(self.wt), "model": sk["model"],
              "effort": sk.get("effort"), "fast": bool(sk.get("fast")), "predecessor": pred,
              "thread": None, "status": "idle", "tasks": [], "files": [], "ctx_est": 0, "briefed": False}
        ev = {"type": "station_created", "data": {"station": {k: st[k] for k in (
            "name", "line", "worktree", "model", "effort", "fast", "predecessor")}}}
        return st, ev

    def _station_for(self, s, cfg, task) -> tuple[dict, list[dict], str | None]:
        """找到或换一个工位。返回 (工位, 要写的事件, 交接摘要)。"""
        events, handoff, pred = [], None, None
        sk = cfg["local"]["sidekick"]
        st = current_station(s, "main")
        first_run_of_task = not any(s["runs"][r]["status"] != "requested" and s["runs"][r]["kind"] != "explore"
                                    for r in task["runs"])
        if st and first_run_of_task:
            limit = cfg.get("context_limit", 400000) * cfg.get("context_ratio", 0.6)
            globs = [g for it in task["items"].values() if it.get("owner") == "sidekick" for g in it.get("files") or []]
            reason = None
            if st.get("model") != sk["model"]:
                reason = f"换了助手模型({st.get('model')} → {sk['model']})"
            elif st.get("ctx_est", 0) > limit:
                reason = (f"当前上下文约 {st['ctx_est']} token,超过上限 {cfg.get('context_limit', 400000)} 的 "
                          f"{int(cfg.get('context_ratio', 0.6) * 100)}%")
            elif st["files"] and globs and not _same_area(st["files"], globs):
                reason = "新任务的文件范围和这个工位做过的文件不在同一个目录(换了主题)"
            if reason:
                events.append({"type": "station_retired", "data": {"station": st["name"], "reason": reason}})
                handoff = prompts.handoff_summary(s, st)
                pred, st = st["name"], None
        if st is None:
            if pred is None and s["stations"]:
                last = list(s["stations"].values())[-1]
                pred = last["name"]
                handoff = handoff or prompts.handoff_summary(s, last)
            st, ev = self._new_station(s, cfg, pred)
            events.append(ev)
        return st, events, handoff

    # ---------- 启动运行 ----------
    def start_run(self, s, cfg, run) -> None:
        if gitops.in_temp(self.wt):
            raise FusionError("项目在系统临时目录里:Codex 的沙箱在那里挡不住目录外的写入。请把项目放到别处。")
        if run["kind"] == "explore":
            return self._start_explore(s, cfg, run)
        task = s["tasks"][run["task"]]
        rid, rdir = run["id"], self.run_dir(run["id"])
        st, events, handoff = self._station_for(s, cfg, task)
        wt = gitops.ensure_station(self.root, cfg)
        branch = f"fusion/{task['id']}"
        fresh = run["kind"] == "implement" and not task["branch"]
        base = gitops.prepare_branch(wt, branch, cfg["base_branch"], fresh)
        if not fresh and task["base"]:
            base = task["base"]
        need_brief = not st.get("briefed")
        kind = run["kind"]
        if kind == "implement":
            prompt = prompts.task_prompt(s, cfg, task, run["items"], handoff, need_brief)
            if run.get("message"):
                prompt += "\n\n## lead 这次派工的说明\n" + str(run["message"])
        else:
            if kind == "fix":
                body = prompts.fix_prompt(run["message"] or "", aq.decisions_text(self.root))
            elif kind == "changes":
                m = run["message"] or {}
                body = prompts.changes_prompt(m.get("comments", []), m.get("overruled", []),
                                              aq.decisions_text(self.root))
            elif kind == "answer":
                body = prompts.answer_prompt(run["message"] or [])
            elif kind == "report":
                body = ("## 你上一次的最终回复不是合格的 JSON 报告\n" + str(run.get("message") or "")
                        + "\n不要再改代码。" + prompts.REPORT_REMINDER)
            else:
                raise FusionError(f"未知的运行类型 {kind}")
            prompt = body
            if need_brief:  # 新工位接手进行中的任务:先给完整任务单
                prompt = prompts.task_prompt(s, cfg, task, run["items"], handoff, True) + "\n\n" + body
        pid = codex.launch(cfg, st, rdir, prompt, "workspace-write", st.get("thread"))
        events.append({"type": "run_started", "task": task["id"],
                       "data": {"run": rid, "station": st["name"], "pid": pid, "dir": str(rdir), "base": base,
                                "branch": branch, "briefed": need_brief, "resumed": bool(st.get("thread"))}})
        self.emit(events)

    def _start_explore(self, s, cfg, run) -> None:
        task = s["tasks"].get(run["task"] or "")
        rid, rdir = run["id"], self.run_dir(run["id"])
        prompt = prompts.explore_prompt(run["questions"], task, aq.decisions_text(self.root))
        st = current_station(s, "main")
        events = []
        if st is None or not self._station_busy(s):
            if st is None:
                st, ev = self._new_station(s, cfg, None)
                events.append(ev)
            gitops.ensure_station(self.root, cfg)
            pid = codex.launch(cfg, st, rdir, prompt, "read-only", st.get("thread"), schema=False)
            events.append({"type": "run_started", "task": run["task"], "data": {
                "run": rid, "station": st["name"], "pid": pid, "dir": str(rdir), "resumed": bool(st.get("thread"))}})
        else:
            sk = cfg["local"]["sidekick"]
            temp = {"name": None, "worktree": str(self.root), "model": sk["model"], "effort": sk.get("effort"),
                    "fast": sk.get("fast")}
            pid = codex.launch(cfg, temp, rdir, prompt, "read-only", None, schema=False, ephemeral=True)
            events.append({"type": "run_started", "task": run["task"],
                           "data": {"run": rid, "station": None, "pid": pid, "dir": str(rdir), "ephemeral": True}})
        self.emit(events)

    # ---------- 运行结束 ----------
    def poll_run(self, s, cfg, run) -> bool:
        rdir = Path(run["dir"])
        evs = codex.read_events(rdir)
        st = s["stations"].get(run.get("station") or "")
        tid = codex.thread_id(evs)
        if st and tid and st.get("thread") != tid and st["status"] != "retired":
            self.emit([{"type": "thread_bound", "data": {"station": st["name"], "thread": tid}}])
            return True
        if pid_alive(run["pid"]):
            ev_path = rdir / "events.jsonl"
            last = ev_path.stat().st_mtime if ev_path.exists() else time.time()
            idle = time.time() - last
            if idle > cfg.get("stall_minutes", 20) * 60 and run["id"] not in self._stall_flagged:
                self._stall_flagged.add(run["id"])
                if run["task"]:
                    self.emit([{"type": "signal", "task": run["task"], "data": {
                        "kind": "stalled", "detail": f"{run['id']} 已经 {int(idle // 60)} 分钟没有新事件。"
                                                     f"可以继续等,或者 cancel / takeover"}}])
                    return True
            return False
        self.finish_run(s, cfg, run, evs)
        return True

    def finish_run(self, s, cfg, run, evs) -> None:
        rdir = Path(run["dir"])
        for name in ("events.jsonl", "last.txt", "stderr.log"):
            redact_file(rdir / name)
        summ = codex.summarize(evs)
        text = codex.last_message(rdir)
        tid = run["task"]
        task = s["tasks"].get(tid or "")
        events = []
        st = s["stations"].get(run.get("station") or "")
        resume_failed = bool(st and run.get("resumed") and not codex.thread_id(evs) and not text)
        if resume_failed:
            # 续用失败(会话找不到等):这个工位作废,下次换新工位并带交接摘要
            events.append({"type": "station_retired", "data": {"station": st["name"], "reason": "续用失败"}})
            if tid:
                events.append({"type": "signal", "task": tid, "data": {
                    "kind": "stalled", "detail": f"工位 {st['name']} 续用失败,下次会换新工位。日志:{rdir / 'stderr.log'}"}})
        if run["kind"] == "explore":
            events.append({"type": "explore_answered", "task": tid, "data": {
                "run": run["id"], "answer": text or f"(探索没有返回内容,看 {rdir / 'stderr.log'})"}})
            events.append({"type": "run_ended", "task": tid, "data": {
                "run": run["id"], "result": "ok" if text else "failed", "usage": summ["usage"],
                "ctx_est": summ["ctx_est"]}})
            self.emit(events)
            return
        if task is None or task["state"] in TERMINAL or task.get("takeover"):
            events.append({"type": "run_ended", "task": tid,
                           "data": {"run": run["id"], "result": "cancelled", "usage": summ["usage"]}})
            self.emit(events)
            return
        raw = codex.parse_report(text)
        wt = self.wt
        if raw is None and text and run["kind"] != "report" and not resume_failed:
            # 有回复但不是 JSON 报告:续用一次让助手补报告(不算修复次数)
            rid = f"r{s['next_run']}"
            events.append({"type": "run_ended", "task": tid, "data": {
                "run": run["id"], "result": "no_report", "usage": summ["usage"], "ctx_est": summ["ctx_est"],
                "commands": summ["commands"][-200:]}})
            events.append({"type": "run_requested", "task": tid, "data": {
                "run": rid, "kind": "report", "items": run["items"], "message": "最终回复解析不出 JSON 报告"}})
            self.emit(events)
            return
        rep, problems = validate.report(raw) if raw is not None else (None, ["没有收到 JSON 报告"])
        blocking = [q for q in (rep or {}).get("questions", []) if isinstance(q, dict) and q.get("blocking")]
        result = "failed" if rep is None else ("blocked" if blocking or rep.get("status") == "blocked" else "ok")
        files = [f["path"] for f in gitops.changed_files(wt, task["base"], "HEAD")] if task["base"] else []
        if gitops.worktree_dirty(wt):
            files += [line[3:] for line in git("status", "--porcelain", "--untracked-files=all", cwd=wt).splitlines()]
        qn = s["next_question"]
        for q in (rep or {}).get("questions", []):
            if not isinstance(q, dict) or not q.get("text"):
                continue
            qid = f"Q{qn}"
            qn += 1
            events.append({"type": "question_asked", "task": tid, "data": {
                "qid": qid, "run": run["id"], "text": q["text"], "blocking": bool(q.get("blocking")),
                "options": q.get("options") or [], "recommendation": q.get("recommendation"),
                "proceeded_with": q.get("proceeded_with")}})
        events.append({"type": "run_ended", "task": tid, "data": {
            "run": run["id"], "result": result, "usage": summ["usage"], "ctx_est": summ["ctx_est"],
            "files": sorted(set(files)), "report": rep, "problems": problems, "commands": summ["commands"][-200:]}})
        if result == "blocked":
            events.append({"type": "signal", "task": tid,
                           "data": {"kind": "blocked", "detail": ";".join(q["text"] for q in blocking)}})
            self.emit(events)
            return
        if result == "failed" and not resume_failed:
            events.append({"type": "signal", "task": tid, "data": {
                "kind": "stalled", "detail": f"{run['id']} 没有交回有效的报告({';'.join(problems)})。日志在 {rdir}"}})
        cand = None
        if gitops.worktree_dirty(wt):
            n = len(task["candidates"]) + 1
            cid = f"{tid}.c{n}"
            msg = (f"fusion: {cid}\n\nTask: {tid}\nRun: {run['id']}\nPlan-Version: {task['version']}\n"
                   f"Station: {run.get('station')}\n")
            commit = gitops.commit_all(wt, msg, cfg.get("commit_identity"))
            if commit:
                cand = {"cand": cid, "commit": commit, "base": task["base"], "run": run["id"],
                        "plan_version": task["version"],
                        "check_hash": config_mod.check_hash(cfg)}
                events.append({"type": "candidate_created", "task": tid, "data": cand})
        if cand is None and result == "ok":
            events.append({"type": "no_changes", "task": tid, "data": {"run": run["id"]}})
            if run["kind"] == "fix":
                events.append({"type": "signal", "task": tid, "data": {
                    "kind": "check_failed", "cand": task["latest"],
                    "detail": f"助手的修复运行 {run['id']} 没有改动任何文件,检查仍然失败"}})
        self.emit(events)
        if cand:
            s2 = self.state()
            self.check_candidate(s2, cfg, s2["tasks"][tid], s2["candidates"][cand["cand"]], summ["commands"],
                                 report=rep, auto_fix=(result == "ok"))

    # ---------- 检查 ----------
    def _task_commands(self, s, task) -> list[dict]:
        out = []
        for rid in task["runs"]:
            r = s["runs"][rid]
            if r.get("status") == "ended" and r["kind"] != "explore" and r.get("dir"):
                out += codex.summarize(codex.read_events(Path(r["dir"])))["commands"]
        return out

    def check_candidate(self, s, cfg, task, cand, commands, recheck=False, report=None, auto_fix=True) -> None:
        wt = self.wt
        if git("rev-parse", "HEAD", cwd=wt) != cand["commit"]:
            # 工位已经不在这个候选上(例如有人手动动过工位目录):不在别的代码上出证据
            self.emit([{"type": "check_ran", "task": task["id"], "data": {
                "cand": cand["cand"], "commit": cand["commit"], "passed": False, "only_env": False, "results": [],
                "violations": [], "changed": [], "tests_changed": [], "out_of_scope": [], "perceivable": [],
                "suspicious": [], "urls": [], "failures": "工位目录不在这个候选提交上,检查没有运行",
                "plan_version": task["version"], "check_hash": config_mod.check_hash(cfg), "recheck": recheck,
                "not_run": True}}])
            return
        if commands is None:
            commands = self._task_commands(s, task)
        data = checks.pipeline(self.root, cfg, s, task, cand, wt, self.run_dir(cand["run"]), commands)
        data["plan_version"], data["check_hash"], data["recheck"] = task["version"], config_mod.check_hash(cfg), recheck
        events = [{"type": "check_ran", "task": task["id"], "data": data}]
        if not recheck:
            if data["violations"]:
                events.append({"type": "signal", "task": task["id"], "data": {
                    "kind": "violation", "cand": cand["cand"],
                    "detail": ";".join(f"{v['why']}({v['where']})" for v in data["violations"])}})
            if data["perceivable"]:
                rep = report or (s["runs"][cand["run"]].get("report") or {})
                silent = not rep.get("choices")
                events.append({"type": "signal", "task": task["id"], "data": {
                    "kind": "perceivable_touched", "cand": cand["cand"],
                    "detail": "改了用户能感知的文件:" + ", ".join(data["perceivable"][:12])
                              + (";报告里没有任何自定的选择,请重点看" if silent else "")}})
        if not data["passed"] and not data["only_env"] and not recheck:
            if auto_fix and task["fix_attempts"] < cfg.get("max_fix_attempts", 2):
                rid = f"r{self.state()['next_run']}"
                items = [i for i, it in task["items"].items() if it["status"] == "delegated"]
                events.append({"type": "run_requested", "task": task["id"], "data": {
                    "run": rid, "kind": "fix", "items": items, "message": data["failures"]}})
            else:
                why = (f"助手修了 {task['fix_attempts']} 次,检查仍然失败" if auto_fix
                       else "这次运行没有正常结束,候选的检查没通过")
                events.append({"type": "signal", "task": task["id"], "data": {
                    "kind": "check_failed", "cand": cand["cand"], "detail": why}})
        self.emit(events)

    # ---------- 验收和集成 ----------
    def integrate(self, s, cfg, task) -> None:
        tid = task["id"]
        rdir = self.root / "fusion" / "runs" / f"{tid}-accept"
        if task["direct"]:
            res = checks.direct_checks(self.root, cfg, s, task, rdir)
            events = [{"type": "integration_ran", "task": tid, "data": {
                "ok": res["passed"], "results": res["results"],
                "detail": "检查全部通过" if res["passed"] else "检查没有全部通过:" + "、".join(
                    r["name"] for r in res["results"] if not r["passed"])}}]
            if res["passed"]:
                events.append({"type": "accepted", "task": tid,
                               "data": {"cand": None, "commit": git("rev-parse", "HEAD", cwd=self.root)}})
            self.emit(events)
            return
        wt = self.wt
        cand = s["candidates"][task["accept_cand"]]
        ident = cfg.get("commit_identity")
        base_branch = cfg["base_branch"]
        if git("rev-parse", "HEAD", cwd=wt) != cand["commit"]:
            self.emit([{"type": "integration_ran", "task": tid, "data": {
                "ok": False, "detail": f"工位目录不在候选 {cand['cand']} 上,请重新审查最新候选"}}])
            return
        ok, msg = gitops.merge_base_into(wt, base_branch, ident)
        if not ok:
            self.emit([{"type": "integration_ran", "task": tid, "data": {
                "ok": False, "conflicts": msg,
                "detail": f"合并 {base_branch} 时有冲突:{msg}。可以提「解决冲突」的修改意见,或者接管"}}])
            return
        results = []
        if cfg.get("test"):
            results.append(checks.run_one("集成:测试", cfg["test"], wt, cfg, rdir / "test.log"))
        if cfg.get("lint"):
            results.append(checks.run_one("集成:lint", cfg["lint"], wt, cfg, rdir / "lint.log"))
        for c in task["plan"].get("checks", []):
            if c["kind"] == "command":
                results.append(checks.run_one(f"集成:{c['id']}", c["run"], wt, cfg, rdir / f"{c['id']}.log",
                                              c.get("expect")))
        failed = [r for r in results if not r["passed"]]
        if failed and not (task.get("waive") and all(r["env_error"] for r in failed)):
            git("reset", "--hard", "-q", cand["commit"], cwd=wt)  # 撤回这次合并,工位回到候选
            self.emit([{"type": "integration_ran", "task": tid, "data": {
                "ok": False, "results": results,
                "detail": f"合并 {base_branch} 之后检查没通过:" + "、".join(r["name"] for r in failed)}}])
            return
        goal = task["plan"]["goal"].splitlines()[0][:72]
        message = (f"{goal}\n\nTask: {tid}\nCandidate: {cand['cand']}\n"
                   f"Runs: {', '.join(task['runs'])}\nVia: lyfusion v5\n")
        squashed = gitops.squash_onto(wt, base_branch, message, ident)
        ok, msg = gitops.fast_forward(self.root, base_branch, squashed)
        if not ok:
            git("reset", "--hard", "-q", cand["commit"], cwd=wt)
            self.emit([{"type": "integration_ran", "task": tid, "data": {"ok": False, "detail": msg,
                                                                         "results": results}}])
            return
        self.emit([{"type": "integration_ran", "task": tid, "data": {"ok": True, "commit": squashed,
                                                                     "results": results, "detail": msg}},
                   {"type": "accepted", "task": tid, "data": {"cand": cand["cand"], "commit": squashed}}])
        gitops.detach_station(wt, base_branch)
        gitops.delete_branch(self.root, f"fusion/{tid}")

    # ---------- 退回、取消、接管 ----------
    def _stop_active(self, s, task) -> list[dict]:
        events = []
        for rid in task["runs"]:
            r = s["runs"][rid]
            if r["status"] in ("started", "requested"):
                if r["status"] == "started":
                    kill_tree(r.get("pid"))
                events.append({"type": "run_ended", "task": task["id"], "data": {"run": rid, "result": "cancelled"}})
        return events

    def cleanup(self, s, cfg, task) -> None:
        events = self._stop_active(s, task)
        wt = self.wt
        branch = task.get("branch") or f"fusion/{task['id']}"
        exists = git("rev-parse", "--verify", "-q", f"refs/heads/{branch}", cwd=self.root, check=False)[0] == 0
        if exists and task["base"]:
            out = self.root / "fusion" / "runs" / f"{task['id']}-{task['state']}.diff"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(git("diff", task["base"], branch, cwd=self.root), encoding="utf-8")
        if (wt / ".git").exists():
            gitops.detach_station(wt, cfg["base_branch"])
        if exists:
            gitops.delete_branch(self.root, branch)
        events.append({"type": "cleaned", "task": task["id"], "data": {}})
        self.emit(events)

    def do_takeover(self, s, cfg, task) -> None:
        events = self._stop_active(s, task)
        d = task["takeover"]
        wt = self.wt
        copied, conflicts = [], []
        has_station = (wt / ".git").exists()
        if has_station and d.get("branch") and gitops.current_branch(wt) == d["branch"]:
            tip = gitops.commit_all(wt, f"fusion: {task['id']} 接管前的半成品", cfg.get("commit_identity")) \
                or git("rev-parse", "HEAD", cwd=wt)
            if d.get("bring") and task["base"]:
                copied, conflicts = gitops.bring_changes(self.root, wt, task["base"], tip)
            out = self.root / "fusion" / "runs" / f"{task['id']}-takeover.diff"
            out.parent.mkdir(parents=True, exist_ok=True)
            if task["base"]:
                out.write_text(git("diff", task["base"], tip, cwd=wt), encoding="utf-8")
        if has_station:
            gitops.detach_station(wt, cfg["base_branch"])
        if d.get("branch"):
            gitops.delete_branch(self.root, d["branch"])
        events.append({"type": "takeover_done", "task": task["id"], "data": {"copied": copied,
                                                                             "conflicts": conflicts}})
        self.emit(events)
