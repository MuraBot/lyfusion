#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lyfusion addon/tools 的回归测试。用旁边 LiEC 的模板加上 addon/ 建项目,建 git 仓库,运行真实命令。

    python tests/test_fusion.py
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

    # ---------------- 提交钩子
    def commit(self, cwd, msg, ok=True):
        run(["git", "add", "-A"], cwd)
        return run(["git", "commit", "-q", "--allow-empty", "-m", msg], cwd, ok=ok)

    TRAIL = "\n\nTask: T5\nAgent: Codex\nModel: m\nEffort: low\nSession: s"

    def test_hook_main_needs_trailers(self):
        r = self.commit(self.root, "改了点东西", ok=False)
        self.assertIn("追溯信息", r.stderr)
        self.commit(self.root, "改了点东西" + self.TRAIL)

    def test_hook_task_branch_and_shared_ledger(self):
        wt = self.tmp / "proj-T5"
        run(["git", "worktree", "add", "-q", "-b", "task/T5", str(wt)], self.root)
        r = self.commit(wt, "改动" + self.TRAIL.replace("Task: T5", "Task: T6"), ok=False)
        self.assertIn("Task 却写了 T6", r.stderr)
        self.commit(wt, "改动" + self.TRAIL)  # 不再要求 Phase 和信箱回报(2026-11-02 边界交接)
        # 在工作目录里运行,写的也是主目录的台账:台账只有一份
        self.tool("ledger.py", "record", "--task", "T5", "--role", "助手", "--agent", "Codex", "--model", "m", cwd=wt)
        self.assertIn('"task": "T5"', (self.root / "ledger.jsonl").read_text(encoding="utf-8"))
        self.assertNotIn('"task"', (wt / "ledger.jsonl").read_text(encoding="utf-8"))

    # ---------------- ledger.py
    def add_tasks(self, *ids):
        self.tool("progress.py", "set-scale", "large")
        for t in ids:
            self.tool("progress.py", "add-task", "任务 " + t, "--milestone", "M1", "--id", t)

    def test_ledger_metrics_and_levels(self):
        L = lambda *a, ok=True: self.tool("ledger.py", *a, ok=ok)
        self.add_tasks("T5", "T6", "T7")
        for task, model in (("T5", "gpt-6.1-sol"), ("T6", "other-model"), ("T7", "other-model")):
            L("record", "--task", task, "--role", "助手", "--agent", "Codex", "--model", model, "--module", "后端",
              "--tokens-in", "1000", "--tokens-cached", "800")
        L("record", "--task", "预检", "--role", "预检", "--agent", "Codex", "--model", "x")
        L("review", "--task", "T5", "--result", "changes", "--findings", "3")
        L("review", "--task", "T5", "--result", "pass", "--findings", "0")
        self.assertEqual(json.loads((self.root / "progress.json").read_text(encoding="utf-8"))["tasks"][-3]["review"], "pass",
                         "台账记审查结论时,进度里的审查结果也要改")
        L("review", "--task", "T6", "--result", "pass", "--findings", "0")
        L("review", "--task", "T7", "--result", "pass", "--findings", "1")
        L("bug", "--task", "T5", "--count", "2", "--note", "敲不动")
        self.assertRegex(L("show").stdout, r"gpt-6.1-sol · 后端\s+1\s+0/1\s+2\s+3\s+2\s+1000\s+800\s+0")
        r = L("level").stdout
        self.assertIn("gpt-6.1-sol · 后端:建议 L3", r)
        self.assertIn("other-model · 后端:建议 L3", r, "连续 2 个模块第 1 次审查就通过,L2 升到 L3")
        L("bug", "--task", "T7", "--count", "2")
        self.assertIn("other-model · 后端:建议 L2", L("level").stdout, "试玩 bug 有 2 个,这个模块不算通过")
        L("flag", "--task", "T6", "--flag", "接手", ok=False)
        L("flag", "--task", "T6", "--flag", "接手", "--signal", "超预估")
        self.assertIn("other-model · 后端:建议 L2", L("level").stdout, "接手信号只有 1 次,不降级")
        L("flag", "--task", "T7", "--flag", "接手", "--signal", "测试修2次")
        self.assertIn("other-model · 后端:建议 L1", L("level").stdout)

    def test_ledger_lead_usage_and_review_refusal(self):
        L = lambda *a, ok=True: self.tool("ledger.py", *a, ok=ok)
        self.add_tasks("T5")
        # 同一个会话记了开始和结束两次读数,取差;新会话只记一次,从 0 算
        L("lead", "--milestone", "M3", "--session", "s1", "--tokens-in", "100", "--tokens-cached", "1000", "--tokens-out", "10",
          "--calls", "5")
        L("lead", "--milestone", "M3", "--session", "s1", "--tokens-in", "300", "--tokens-cached", "5000", "--tokens-out", "30",
          "--calls", "25")
        L("lead", "--milestone", "M3", "--session", "s2", "--tokens-in", "50", "--tokens-cached", "500", "--tokens-out", "5",
          "--calls", "3")
        self.assertIn("lead · M3:输入 250,缓存读取 4500,输出 25,调用 23 次", L("show").stdout)
        # Codex 续用会话报的是累计用量:同一会话记差值
        for n in ("1000", "1500"):
            L("record", "--task", "T5", "--role", "助手", "--agent", "Codex", "--model", "m", "--session", "th",
              "--tokens-in", n)
        rows = [json.loads(l) for l in (self.root / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual([r["tokensIn"] for r in rows if r["kind"] == "run"], [1000, 500])
        L("score", "--task", "T5", "--delivery", "4", "--work", "3", "--label", "lead + sol")
        L("score", "--task", "T5", "--delivery", "6", "--work", "3", ok=False)
        L("score", "--task", "T5", "--score", "4.5", "--note", "初版 6 分")
        L("score", "--task", "T5", "--score", "11", ok=False)
        L("score", "--task", "T5", "--work", "3", ok=False)
        # progress.py 拒绝时(lead 记 pass 没写理由),台账也不记
        L("review", "--task", "T5", "--result", "pass", "--findings", "0", "--by", "lead", ok=False)
        self.assertNotIn('"review"', (self.root / "ledger.jsonl").read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main(verbosity=1)
