#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""codex-dispatch.ps1 的测试:用 tests/fake_codex 代替真的 Codex,不联网、不耗额度。只在 Windows 上运行。

    python tests/test_dispatch.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_fusion import GOOD_BRIEF, SKILL, make_project, run  # noqa: E402

FAKE = SKILL / "tests" / "fake_codex"


class DispatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lpf-dispatch-"))
        # 路径带空格:Windows PowerShell 5.1 传参的坑多出在这里(CraftTax 试点 2026-10-28)
        self.root = self.tmp / "my proj"
        make_project(self.root)
        for c in (["init", "-q", "-b", "main"], ["config", "user.name", "test"], ["config", "user.email", "t@example.invalid"]):
            run(["git"] + c, self.root)
        (self.root / "tasks" / "T5.md").write_text(GOOD_BRIEF, encoding="utf-8")
        run(["git", "add", "-A"], self.root)
        run(["git", "commit", "-q", "-m", "init"], self.root)
        self.state = self.tmp / "calls.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def dispatch(self, *args, scenario="partial", ok=True):
        env = {"PATH": str(FAKE) + os.pathsep + os.environ["PATH"], "FAKE_STATE": str(self.state),
               "FAKE_SCENARIO": scenario, "CLAUDE_TEST_SECRET": "x"}
        return run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(self.root / "tools" / "codex-dispatch.ps1")] + list(args), self.root, ok=ok, env=env)

    def calls(self):
        return json.loads(self.state.read_text(encoding="utf-8"))

    def ledger(self):
        p = self.root / "ledger.jsonl"
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

    def test_supervisor_continues_until_evidence_then_commits(self):
        r = self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", "-Worktree")
        c = self.calls()
        self.assertEqual(len(c), 2, r.stdout)
        self.assertEqual(c[1]["args"][:3], ["exec", "resume", "fake-thread"])
        self.assertIn("继续:阶段 2 还没有证据", c[1]["args"][-1])
        self.assertNotIn("--add-dir", c[0]["args"], "边界交接没有信箱,不用给沙箱加可写目录")
        self.assertTrue(c[0]["cwd"].endswith("my proj-T5"))
        self.assertEqual(c[0]["claudeEnv"], [], "Claude 的环境变量要在启动 Codex 前去掉")
        self.assertIn("没有证据的阶段:无", r.stdout)
        rows = self.ledger()
        self.assertEqual([x["run"] for x in rows], [1, 2])
        self.assertEqual(rows[0]["module"], "后端 · 锻造")
        self.assertEqual(rows[1]["tokensIn"], 200)
        wt = self.tmp / "my proj-T5"
        report = (wt / "dispatch-logs" / "evidence" / "T5" / "report.md").read_text(encoding="utf-8-sig")
        self.assertIn("## 假设\n- 超时按 5 秒", report)
        self.assertIn("## 接口修改请求\n- 无", report)
        # 助手不提交;脚本在任务分支上提交,追溯信息写好
        self.assertEqual(run(["git", "status", "--porcelain"], wt).stdout, "")
        body = run(["git", "log", "-1", "--format=%B"], wt).stdout
        for line in ("Task: T5", "Agent: Codex", "Model: gpt-6.1-sol", "Effort: default", "Session: fake-thread"):
            self.assertIn(line, body)

    def test_supervisor_asks_for_missing_report(self):
        self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", "-Worktree", scenario="noreport")
        c = self.calls()
        self.assertEqual(len(c), 2)
        self.assertIn("补最终报告", c[1]["args"][-1])

    def test_env_note_path_and_contract(self):
        ps1 = self.root / "tools" / "codex-dispatch.ps1"
        b = ps1.read_bytes().replace('$NeedCommands = @("git", "python")'.encode(), '$NeedCommands = @("git", "nosuchcmd")'.encode())
        ps1.write_bytes(b)
        self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", "-Worktree", scenario="stop")
        c = self.calls()[0]
        self.assertTrue(c["args"][-1].startswith("本机没有这些命令:nosuchcmd。"), c["args"][-1][:40])
        self.assertEqual(Path(c["path0"]), FAKE, "Codex 自己的目录(含 rg)要排在 PATH 最前")
        # -Contract:决定先写进主目录简报的"已定",再带进工作目录
        self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", "-Resume", "fake-thread", "-Message", '颜色用 "铁灰"', "-Contract",
                      scenario="stop")
        self.assertIn('颜色用 "铁灰"', (self.root / "tasks" / "T5.md").read_text(encoding="utf-8"))
        self.assertIn('颜色用 "铁灰"', (self.tmp / "my proj-T5" / "tasks" / "T5.md").read_text(encoding="utf-8"))
        self.assertTrue(self.calls()[-1]["args"][-1].endswith("已写进简报的「已定」)"))

    def test_stop_is_not_continued(self):
        r = self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", "-Worktree", scenario="stop")
        self.assertEqual(len(self.calls()), 1)
        self.assertIn("停止原因:产品决定", r.stdout)

    def test_bad_brief_is_refused(self):
        (self.root / "tasks" / "T5.md").write_text(GOOD_BRIEF.replace("## 停止条件", "## 别的"), encoding="utf-8")
        r = self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", ok=False)
        self.assertFalse(self.state.exists())
        self.assertIn("停止条件", r.stdout + r.stderr)

    def test_message_quotes_survive(self):
        self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", "-Resume", "abc", "-Message", '把 "a b" 改成 c', "-NoSupervise",
                      scenario="stop")
        self.assertEqual(self.calls()[0]["args"][-1], '把 "a b" 改成 c')

    def set_test_command(self, cmd):
        ps1 = self.root / "tools" / "codex-dispatch.ps1"
        text = ps1.read_bytes().decode("utf-8")
        ps1.write_bytes(re.sub(r'\$TestCommand = "[^"]*"', '$TestCommand = "%s"' % cmd, text).encode("utf-8"))
        run(["git", "commit", "-q", "-am", "测试命令:%s" % cmd], self.root)

    def test_review_merge_and_cleanup(self):
        self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", "-Worktree")
        wt = self.tmp / "my proj-T5"
        (self.root / "new-on-main.txt").write_text("x", encoding="utf-8")
        run(["git", "add", "-A"], self.root)
        run(["git", "commit", "-q", "-m", "main 前进"], self.root)
        r = self.dispatch("-Task", "T5", "-Model", "other", "-Review", scenario="review")
        self.assertTrue((wt / "new-on-main.txt").exists(), "交审前要把 main 合并进任务分支")
        self.assertIn("read-only", self.calls()[-1]["args"])
        self.assertIn("report.md", self.calls()[-1]["args"][-1])
        self.assertIn("审查报告", r.stdout)
        self.assertIn("没合并", self.dispatch("-Task", "T5", "-Cleanup", ok=False).stderr)
        # 合并:测试命令、审查结论、主目录干净,缺一样都不合并
        self.assertIn("TestCommand", self.dispatch("-Task", "T5", "-Merge", ok=False).stderr)
        self.set_test_command("git nosuchcmd")
        run([sys.executable, "tools/progress.py", "add-task", "铁砧", "--milestone", "M1", "--id", "T5"], self.root)
        self.assertIn("审查结果是 none", self.dispatch("-Task", "T5", "-Merge", ok=False).stderr)
        run([sys.executable, "tools/ledger.py", "review", "--task", "T5", "--result", "pass", "--findings", "0"], self.root)
        (self.root / "draft.txt").write_text("x", encoding="utf-8")
        self.assertIn("draft.txt", self.dispatch("-Task", "T5", "-Merge", ok=False).stderr)
        (self.root / "draft.txt").unlink()
        r = self.dispatch("-Task", "T5", "-Merge", ok=False)
        self.assertIn("测试失败", r.stderr)
        self.assertNotIn("task/T5", run(["git", "branch", "--merged", "main"], self.root).stdout, "测试失败时 main 不变")
        self.set_test_command("git --version")
        self.dispatch("-Task", "T5", "-Merge")
        self.assertTrue((self.root / "src" / "feature.txt").exists())
        test_txt = (self.root / "dispatch-logs" / "evidence" / "T5" / "merge" / "test.txt").read_text(encoding="utf-8-sig")
        self.assertIn("退出码:0", test_txt)
        self.assertIn("git version", test_txt)
        prog = json.loads((self.root / "progress.json").read_text(encoding="utf-8"))
        self.assertEqual([t["status"] for t in prog["tasks"] if t["id"] == "T5"], ["done"])
        self.dispatch("-Task", "T5", "-Cleanup")
        self.assertFalse(wt.exists())
        self.assertTrue((self.root / "dispatch-logs" / "evidence" / "T5" / "1" / "run.txt").exists())
        self.assertTrue((self.root / "dispatch-logs" / "evidence" / "T5" / "report.md").exists())

if __name__ == "__main__":
    unittest.main(verbosity=1)
