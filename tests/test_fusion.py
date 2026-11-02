#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lyfusion addon/tools 的回归测试。用旁边 LiEC 的模板加上 addon/ 建项目,建 git 仓库,运行真实命令。

    python tests/test_tools.py
只使用 Python 标准库。需要 git。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
# lyfusion 建立在 LiEC 的项目上。默认 LiEC 在旁边的文件夹,可用环境变量 LIEC_HOME 指定
LIEC = Path(os.environ.get("LIEC_HOME", SKILL.parent / "LiEC"))


def make_project(dest):
    """LiEC 的模板 + lyfusion 的 addon/,和"安装到项目"的步骤一致。"""
    if not (LIEC / "template").is_dir():
        raise unittest.SkipTest("找不到 LiEC 的模板:%s。设置 LIEC_HOME" % LIEC)
    shutil.copytree(LIEC / "template", dest)
    shutil.copytree(SKILL / "addon", dest, dirs_exist_ok=True)
PY = sys.executable

GOOD_BRIEF = """# 任务 T5:铁砧敲击

- 所属里程碑:M1
- 级别:L3
- 助手与模型:Codex · gpt-6.1-sol
- 模块:后端 · 锻造
- 分支:task/T5

## 目标
玩家用锤子敲铁砧上的剑,剑的进度增加。

## 已定
- 接口:I2

## 猜测
- 无

## 未定
类怎么拆,由助手决定。

## 约束
- 可写范围:src/

## 阶段
1. 最薄路径 —— 成功:命令 `python -c "print(1)"` 期望 输出 1
2. 边界情况 —— 成功:现象:敲空铁砧没有反应

## 成功标准
- [ ] 敲击生效 —— 证据:命令 `python -c "print(1)"` 期望 输出 1

## 停止条件
- spec 里没有的产品决定

## 回报
"""


def run(args, cwd, ok=True, env=None, inp=None):
    e = dict(os.environ, PYTHONIOENCODING="utf-8")
    e.pop("LPF_MAIL_ROOT", None)
    if env:
        e.update(env)
    r = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", env=e, input=inp)
    if ok is True and r.returncode != 0:
        raise AssertionError("命令失败 %s\n%s\n%s" % (args, r.stdout, r.stderr))
    if ok is False and r.returncode == 0:
        raise AssertionError("命令应该失败 %s\n%s" % (args, r.stdout))
    return r


class FusionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lpf-test-"))
        self.root = self.tmp / "proj"
        make_project(self.root)
        for c in (["init", "-q", "-b", "main"], ["config", "user.name", "test"], ["config", "user.email", "t@example.invalid"],
                  ["config", "core.hooksPath", "tools/hooks"]):
            run(["git"] + c, self.root)
        run(["git", "add", "-A"], self.root)
        run(["git", "commit", "-q", "-m", "init", "--no-verify"], self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def tool(self, name, *args, cwd=None, ok=True):
        cwd = cwd or self.root
        return run([PY, str(Path(cwd) / "tools" / name)] + list(args), cwd, ok=ok)

    def write_brief(self, text=GOOD_BRIEF, task="T5"):
        (self.root / "tasks" / ("%s.md" % task)).write_text(text, encoding="utf-8")

    # ---------------- mail.py
    def test_mail_contract_reply_goes_into_brief(self):
        self.write_brief()
        self.tool("mail.py", "send", "T5", "question", "--kind", "不可撤回", "--text", "能下载吗?")
        self.tool("mail.py", "reply", "T5", "T5-1", "--text", "官方来源、校验 sha1 后可以下载", "--contract")
        text = (self.root / "tasks" / "T5.md").read_text(encoding="utf-8")
        decided = text.split("## 已定")[1].split("## 猜测")[0]
        self.assertIn("- 决定(T5-2,", decided)
        self.assertIn("校验 sha1", decided)
        self.tool("brief.py", "check", "T5")

    def test_mail_watch_follow_prints_lines(self):
        self.evidence(self.root)
        self.report(self.root)
        self.tool("mail.py", "send", "T5", "question", "--kind", "产品", "--text", "颜色?")
        r = self.tool("mail.py", "watch", "--follow", "--timeout", "1", ok=None)
        lines = [l for l in r.stdout.splitlines() if l.startswith("[")]
        self.assertEqual(len(lines), 2, r.stdout)
        self.assertIn("回报 · 阶段 1:做完了", lines[0])

    def test_mail_close(self):
        (self.root / "mail").mkdir()
        (self.root / "mail" / "T5.meta.json").write_text(json.dumps({"pid": os.getpid(), "finished": False}), encoding="utf-8")
        self.evidence(self.root)
        self.report(self.root)
        self.tool("progress.py", "add-next", "T5 做完后派 T6")
        r = self.tool("mail.py", "close", "T5", ok=False)
        self.assertIn("还在运行", r.stderr)
        r = self.tool("mail.py", "close", "T5", "--force")
        self.assertIn("remove-next", r.stdout)
        self.assertTrue((self.root / "dispatch-logs" / "evidence" / "T5" / "mailbox.md").exists())
        self.assertEqual([p.name for p in (self.root / "mail").iterdir()], [])

    def evidence(self, cwd, phase=1):
        d = Path(cwd) / "dispatch-logs" / "evidence" / "T5" / str(phase)
        d.mkdir(parents=True, exist_ok=True)
        (d / "test.txt").write_text("命令:x\n退出码:0\n", encoding="utf-8")
        return "dispatch-logs/evidence/T5/%d" % phase

    def report(self, cwd, phase=1, ok=True):
        return self.tool("mail.py", "send", "T5", "report", "--phase", str(phase), "--summary", "做完了",
                         "--evidence", "dispatch-logs/evidence/T5/%d" % phase, "--decisions", "无",
                         "--problems", "无", "--downstream", "无", cwd=cwd, ok=ok)

    def test_mail_report_needs_evidence_and_snapshots(self):
        r = self.report(self.root, ok=False)
        self.assertIn("证据不存在", r.stderr)
        self.evidence(self.root)
        (self.root / "src.txt").write_text("新文件\n", encoding="utf-8")
        self.report(self.root)
        snap = (self.root / "mail" / "T5" / "phase-1.patch").read_text(encoding="utf-8")
        self.assertIn("src.txt", snap)
        self.assertNotIn("dispatch-logs", snap)
        st = json.loads(self.tool("mail.py", "status", "T5", "--json").stdout)
        self.assertEqual(st["reportedPhases"], [1])

    def test_mail_question_wait_timeout_and_reply(self):
        r = self.tool("mail.py", "send", "T5", "question", "--kind", "可撤回", "--text", "用多大?", ok=False)
        self.assertIn("--assumption", r.stderr)
        self.tool("mail.py", "send", "T5", "question", "--kind", "可撤回", "--text", "用多大?", "--assumption", "用 1")
        r = self.tool("mail.py", "wait", "T5", "--reply-to", "T5-1", "--timeout", "0.5", ok=None)
        self.assertEqual(r.returncode, 2)
        self.assertIn("用 1", r.stdout)
        self.tool("mail.py", "reply", "T5", "T5-1", "--text", "用 2", "--in-brief")
        r = self.tool("mail.py", "wait", "T5", "--reply-to", "T5-1", "--timeout", "5")
        self.assertIn("用 2", r.stdout)

    def test_mail_objection_rules(self):
        r = self.tool("mail.py", "send", "T5", "objection", "--claim", "a", "--evidence", "b", "--cost", "c", ok=False)
        self.assertIn("--alternative", r.stderr)
        self.tool("mail.py", "send", "T5", "objection", "--claim", "a", "--evidence", "b", "--cost", "c", "--alternative", "d")
        r = self.tool("mail.py", "reply", "T5", "T5-1", "--text", "好", ok=False)
        self.assertIn("--verdict", r.stderr)
        self.tool("mail.py", "reply", "T5", "T5-1", "--text", "好", "--verdict", "接受")

    def test_mail_inbox_cursor_and_stop(self):
        self.tool("mail.py", "send", "T5", "guide", "--text", "注意命名")
        self.tool("mail.py", "send", "T5", "stop", "--text", "停一下")
        r = self.tool("mail.py", "inbox", "T5", "--as", "assistant")
        self.assertIn("注意命名", r.stdout)
        self.assertIn("做完当前步骤就停下", r.stdout)
        r = self.tool("mail.py", "inbox", "T5", "--as", "assistant")
        self.assertIn("没有新消息", r.stdout)

    def test_mail_text_from_file(self):
        f = self.root / "note.md"
        f.write_text('带 "引号" 的长文字', encoding="utf-8")
        self.tool("mail.py", "send", "T5", "guide", "--text", "@note.md")
        self.assertIn('带 \\"引号\\"', (self.root / "mail" / "T5.jsonl").read_text(encoding="utf-8"))

    def test_mail_shared_from_worktree_and_diff(self):
        wt = self.tmp / "proj-T5"
        run(["git", "worktree", "add", "-q", "-b", "task/T5", str(wt)], self.root)
        self.evidence(wt, 1)
        (wt / "a.txt").write_text("一\n", encoding="utf-8")
        self.report(wt, 1)
        self.evidence(wt, 2)
        (wt / "a.txt").write_text("一\n二\n", encoding="utf-8")
        self.report(wt, 2)
        self.assertTrue((self.root / "mail" / "T5.jsonl").exists())
        self.assertFalse((wt / "mail").exists())
        r = self.tool("mail.py", "diff", "T5", "--phase", "2")
        self.assertIn("+二", r.stdout.replace("+ ", "+"))
        r = self.tool("mail.py", "watch", "--timeout", "1")
        self.assertIn("回报", r.stdout)

    # ---------------- 提交钩子
    def commit(self, cwd, msg, ok=True):
        run(["git", "add", "-A"], cwd)
        return run(["git", "commit", "-q", "--allow-empty", "-m", msg], cwd, ok=ok)

    TRAIL = "\n\nTask: T5\nAgent: Codex\nModel: m\nEffort: low\nSession: s"

    def test_hook_main_needs_trailers(self):
        r = self.commit(self.root, "改了点东西", ok=False)
        self.assertIn("追溯信息", r.stderr)
        self.commit(self.root, "改了点东西" + self.TRAIL)

    def test_hook_task_branch_needs_phase_report(self):
        wt = self.tmp / "proj-T5"
        run(["git", "worktree", "add", "-q", "-b", "task/T5", str(wt)], self.root)
        r = self.commit(wt, "阶段 1" + self.TRAIL, ok=False)
        self.assertIn("Phase", r.stderr)
        r = self.commit(wt, "阶段 1" + self.TRAIL + "\nPhase: 1", ok=False)
        self.assertIn("没有 T5 阶段 1 的回报", r.stderr)
        self.evidence(wt, 1)
        self.report(wt, 1)
        self.commit(wt, "阶段 1" + self.TRAIL + "\nPhase: 1")
        (wt / "tasks" / "T5.md").write_text(GOOD_BRIEF, encoding="utf-8")
        r = self.commit(wt, "全部" + self.TRAIL + "\nPhase: 全部", ok=False)
        self.assertIn("阶段 2", r.stderr)
        self.evidence(wt, 2)
        self.report(wt, 2)
        self.commit(wt, "全部" + self.TRAIL + "\nPhase: 全部")

    def test_hook_stamps_trailers_from_meta(self):
        wt = self.tmp / "proj-T5"
        run(["git", "worktree", "add", "-q", "-b", "task/T5", str(wt)], self.root)
        (self.root / "mail").mkdir(exist_ok=True)
        meta = {"task": "T5", "agent": "Codex", "model": "gpt-6.1-sol", "effort": "high", "runId": "run-1", "session": "thread-9"}
        (self.root / "mail" / "T5.meta.json").write_text(json.dumps(meta), encoding="utf-8")
        self.evidence(wt, 1)
        self.report(wt, 1)
        self.commit(wt, "阶段 1\n\nPhase: 1")
        body = run(["git", "log", "-1", "--format=%B"], wt).stdout
        for line in ("Task: T5", "Agent: Codex", "Model: gpt-6.1-sol", "Effort: high", "Session: thread-9"):
            self.assertIn(line, body)

    # ---------------- ledger.py
    def test_ledger_metrics_and_levels(self):
        for task, model in (("T5", "gpt-6.1-sol"), ("T6", "other-model")):
            self.tool("ledger.py", "record", "--task", task, "--role", "助手", "--agent", "Codex", "--model", model,
                      "--module", "后端", "--tokens-in", "1000")
        self.tool("ledger.py", "record", "--task", "预检", "--role", "预检", "--agent", "Codex", "--model", "x")
        for ph, res in ((1, "ok"), (2, "guide"), (2, "ok")):
            self.tool("mail.py", "send", "T5", "review", "--phase", str(ph), "--result", res)
        for ph in (1, 2, 3):
            self.tool("mail.py", "send", "T6", "review", "--phase", str(ph), "--result", "ok")
        self.tool("mail.py", "send", "T5", "bug", "--text", "敲不动")
        r = self.tool("ledger.py", "show")
        self.assertRegex(r.stdout, r"gpt-6.1-sol · 后端\s+1\s+1/2\s+1\s+0\s+1")
        r = self.tool("ledger.py", "level")
        self.assertIn("gpt-6.1-sol · 后端:建议 L3", r.stdout)
        self.assertIn("other-model · 后端:建议 L3", r.stdout)
        # 任务收尾删了信箱,指标还要在(第 3 轮的回归)
        self.tool("mail.py", "send", "T5", "guide", "--text", "改一下")
        for t in ("T5", "T6"):
            self.tool("mail.py", "close", t)
        self.assertFalse((self.root / "mail" / "T5.jsonl").exists())
        r = self.tool("ledger.py", "show")
        self.assertRegex(r.stdout, r"gpt-6.1-sol · 后端\s+1\s+1/2\s+1\s+0\s+1\s+-\s+1000\s+1")
        self.assertIn("other-model · 后端:建议 L3", self.tool("ledger.py", "level").stdout)
        self.tool("ledger.py", "flag", "--task", "T6", "--flag", "接手", ok=False)
        self.tool("ledger.py", "flag", "--task", "T6", "--flag", "接手", "--signal", "超预估")
        self.assertIn("other-model · 后端:建议 L2", self.tool("ledger.py", "level").stdout)

    # ---------------- progress.py 与信箱
    def test_done_closes_mailbox_in_multi(self):
        P = lambda *a, ok=True: self.tool("progress.py", *a, ok=ok)
        P("set-scale", "small")
        P("set-collab", "multi")
        P("add-task", "铁砧", "--milestone", "M1")
        tid = json.loads((self.root / "progress.json").read_text(encoding="utf-8"))["tasks"][-1]["id"]
        self.tool("mail.py", "send", tid, "guide", "--text", "好")
        r = P("set-status", tid, "done")
        self.assertIn("信箱原文已存到", r.stdout)
        self.assertFalse((self.root / "mail" / ("%s.jsonl" % tid)).exists())


if __name__ == "__main__":
    unittest.main(verbosity=1)
