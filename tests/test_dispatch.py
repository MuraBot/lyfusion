#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""codex-dispatch.ps1 的测试:用 tests/fake_codex 代替真的 Codex,不联网、不耗额度。只在 Windows 上运行。

    python tests/test_dispatch.py
"""
import json
import os
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

    def test_supervisor_asks_for_missing_report(self):
        r = self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", "-Worktree")
        c = self.calls()
        self.assertEqual(len(c), 2, r.stdout)
        self.assertEqual(c[1]["args"][:3], ["exec", "resume", "fake-thread"])
        self.assertIn("补回报", c[1]["args"][-1])
        roots = c[1]["args"][c[1]["args"].index("sandbox_workspace_write.writable_roots=['%s']" % (self.root / "mail")) - 1]
        self.assertEqual(roots, "-c", "resume 的 writable_roots 要是完整的一个参数")
        self.assertIn("--add-dir", c[0]["args"])
        self.assertTrue(c[0]["cwd"].endswith("my proj-T5"))
        self.assertEqual(c[0]["claudeEnv"], [], "Claude 的环境变量要在启动 Codex 前去掉")
        self.assertIn("已回报的阶段:1、2", r.stdout)
        rows = self.ledger()
        self.assertEqual([x["run"] for x in rows], [1, 2])
        self.assertEqual(rows[0]["module"], "后端 · 锻造")
        self.assertEqual(rows[1]["tokensIn"], 200)

    def test_env_note_path_meta_and_brief_copy(self):
        ps1 = self.root / "tools" / "codex-dispatch.ps1"
        b = ps1.read_bytes().replace('$NeedCommands = @("git", "python")'.encode(), '$NeedCommands = @("git", "nosuchcmd")'.encode())
        ps1.write_bytes(b)
        self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", "-Worktree", scenario="stop")
        c = self.calls()[0]
        self.assertTrue(c["args"][-1].startswith("本机没有这些命令:nosuchcmd。"), c["args"][-1][:40])
        self.assertEqual(Path(c["path0"]), FAKE, "Codex 自己的目录(含 rg)要排在 PATH 最前")
        meta = json.loads((self.root / "mail" / "T5.meta.json").read_text(encoding="utf-8-sig"))
        self.assertEqual((meta["session"], meta["finished"], meta["model"]), ("fake-thread", True, "gpt-6.1-sol"))
        brief = self.root / "tasks" / "T5.md"
        brief.write_text(brief.read_text(encoding="utf-8").replace("- 接口:I2", "- 接口:I2\n- 决定(T5-3):可以下载"), encoding="utf-8")
        self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", "-Resume", "fake-thread", "-Message", "继续", scenario="stop")
        self.assertIn("可以下载", (self.tmp / "my proj-T5" / "tasks" / "T5.md").read_text(encoding="utf-8"))

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

    def test_review_merges_main_then_cleanup(self):
        self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", "-Worktree")
        wt = self.tmp / "my proj-T5"
        (self.root / "new-on-main.txt").write_text("x", encoding="utf-8")
        run(["git", "add", "-A"], self.root)
        run(["git", "commit", "-q", "-m", "main 前进"], self.root)
        r = self.dispatch("-Task", "T5", "-Model", "other", "-Review", scenario="review")
        self.assertTrue((wt / "new-on-main.txt").exists(), "交审前要把 main 合并进任务分支")
        self.assertIn("read-only", self.calls()[-1]["args"])
        self.assertIn("审查报告", r.stdout)
        r = self.dispatch("-Task", "T5", "-Cleanup", ok=False)
        self.assertIn("没提交的改动", r.stdout + r.stderr)
        self.assertTrue((wt / "src" / "feature.txt").exists())
        run(["git", "add", "-A"], wt)
        run(["git", "commit", "-q", "-m", "lead 提交 T5"], wt)
        r = self.dispatch("-Task", "T5", "-Cleanup", ok=False)
        self.assertIn("没合并", r.stdout + r.stderr)
        run(["git", "merge", "-q", "--no-edit", "task/T5"], self.root)
        self.dispatch("-Task", "T5", "-Cleanup")
        self.assertFalse(wt.exists())
        self.assertTrue((self.root / "dispatch-logs" / "evidence" / "T5" / "1" / "run.txt").exists())


if __name__ == "__main__":
    unittest.main(verbosity=1)
