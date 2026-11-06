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
import time
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

    def dispatch(self, *args, scenario="partial", ok=True, linger=False, responses="", questions=""):
        env = {"PATH": str(FAKE) + os.pathsep + os.environ["PATH"], "FAKE_STATE": str(self.state),
               "FAKE_SCENARIO": scenario, "CLAUDE_TEST_SECRET": "x", "FAKE_LINGER": "1" if linger else "",
               "FAKE_RESPONSES": responses, "FAKE_QUESTIONS": questions}
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
        # 续用时 Codex 报会话累计用量(100 → 200),台账记差值
        self.assertEqual((rows[1]["tokensIn"], rows[1]["cum"]["tokensIn"]), (100, 200))
        self.assertIn("token 用量(会话累计):输入 200", r.stdout)
        wt = self.tmp / "my proj-T5"
        report = (wt / "dispatch-logs" / "evidence" / "T5" / "report.md").read_text(encoding="utf-8-sig")
        self.assertIn("## 假设\n- 超时按 5 秒", report)
        self.assertIn("## 接口修改请求\n- 无", report)
        # 助手不提交;脚本在任务分支上提交,追溯信息写好
        self.assertEqual(run(["git", "status", "--porcelain"], wt).stdout, "")
        body = run(["git", "log", "-1", "--format=%B"], wt).stdout
        for line in ("Task: T5", "Agent: Codex", "Model: gpt-6.1-sol", "Effort: high", "Session: fake-thread"):
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
        self.assertIn("已写进简报的「已定」)", self.calls()[-1]["args"][-1])

    def test_stop_is_not_continued(self):
        r = self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", "-Worktree", scenario="stop")
        self.assertEqual(len(self.calls()), 1)
        self.assertIn("停止原因:产品决定", r.stdout)

    def test_lingering_child_does_not_block(self):
        # 小熊对比实验(2026-11-02):Codex 退出后,派工脚本和调用它的工具都等后台的 git 关掉输出管道,挂住 7~34 分钟
        t = time.time()
        r = self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", scenario="stop", linger=True)
        self.assertLess(time.time() - t, 12)
        self.assertIn("停止原因:产品决定", r.stdout)

    def test_bad_brief_is_refused(self):
        (self.root / "tasks" / "T5.md").write_text(GOOD_BRIEF.replace("## 停止条件", "## 别的"), encoding="utf-8")
        r = self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", ok=False)
        self.assertFalse(self.state.exists())
        self.assertIn("停止条件", r.stdout + r.stderr)

    def test_message_quotes_survive(self):
        self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", "-Resume", "abc", "-Message", '把 "a b" 改成 c', "-NoSupervise",
                      scenario="stop")
        self.assertTrue(self.calls()[0]["args"][-1].startswith('把 "a b" 改成 c'))
        self.assertIn("T5 的完整最终报告", self.calls()[0]["args"][-1], "续用后的报告会覆盖前面的,要求写完整(fusion-bench C2-H2)")

    def set_test_command(self, cmd, name="TestCommand"):
        ps1 = self.root / "tools" / "codex-dispatch.ps1"
        text = ps1.read_bytes().decode("utf-8")
        ps1.write_bytes(re.sub(r'\$%s = "[^"]*"' % name, '$%s = "%s"' % (name, cmd), text).encode("utf-8"))
        run(["git", "commit", "-q", "-am", "%s:%s" % (name, cmd)], self.root)

    def progress(self, task="T5"):
        prog = json.loads((self.root / "progress.json").read_text(encoding="utf-8"))
        return [t for t in prog["tasks"] if t["id"] == task]

    def test_explore_is_read_only_and_writes_pack(self):
        models = self.root / "prompts" / "models"
        models.mkdir(parents=True, exist_ok=True)
        (models / "gpt-6-luna.md").write_text("# gpt-6-luna\n\n## 备注\n- 列出要保留的原有行为\n\n## 待观察\n- 还没定的\n",
                                              encoding="utf-8")
        ask = self.root / "tasks" / "T5-ask.md"
        ask.write_text("任务原话:敲铁砧\n", encoding="utf-8")
        r = self.dispatch("-Task", "T5", "-Model", "gpt-6-luna", "-Explore", "-AskFile", str(ask), scenario="explore")
        c = self.calls()
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]["args"][c[0]["args"].index("-s") + 1], "read-only")
        self.assertNotIn("--output-schema", c[0]["args"])
        self.assertIn(str(ask), c[0]["args"][-1])
        pack = (self.root / "dispatch-logs" / "evidence" / "T5" / "explore.md").read_text(encoding="utf-8-sig")
        self.assertIn("src/a.py:1-3", pack)
        self.assertIn("- 列出要保留的原有行为", pack)
        self.assertNotIn("还没定的", pack, "待观察的不带上")
        self.assertIn("探索包:", r.stdout)
        self.assertEqual(self.ledger()[0]["role"], "探索")

    def test_root_mode_gates_bundle_accept(self):
        # v4(2026-11-03):助手直接在主目录改,脚本跑测试和 lint,不过就让助手修,打交接包;lead 用 -Accept 一步验收
        (self.root / "lintcheck.py").write_text("import os, sys\nprint('lint')\nsys.exit(0 if os.path.exists('lint-ok.txt') else 1)\n",
                                                encoding="utf-8")
        run(["git", "add", "-A"], self.root)
        run(["git", "commit", "-q", "-m", "lint 脚本"], self.root)
        self.set_test_command("git --version")
        self.set_test_command("python lintcheck.py", "LintCommand")
        (self.root / "draft.txt").write_text("x", encoding="utf-8")
        self.assertIn("draft.txt", self.dispatch("-Task", "T5", "-Model", "gpt-6-luna", ok=False).stderr)
        (self.root / "draft.txt").unlink()
        r = self.dispatch("-Task", "T5", "-Model", "gpt-6-luna", scenario="lintfix")
        c = self.calls()
        self.assertEqual(len(c), 2, r.stdout)
        self.assertIn("python lintcheck.py", c[1]["args"][-1])
        self.assertTrue(c[0]["temp"].startswith(str(self.root)), "临时目录要在工作目录里")
        self.assertEqual(Path(c[0]["cwd"]), self.root)
        self.assertEqual([t["status"] for t in self.progress()], ["doing"], "派工时登记任务")
        self.assertEqual(self.progress()[0]["title"], "铁砧敲击")
        ev = self.root / "dispatch-logs" / "evidence" / "T5"
        bundle = (ev / "bundle.md").read_text(encoding="utf-8-sig")
        for s in ("## 验收命令", "lint:python lintcheck.py · 退出码 0", "src/feature.txt", "## 关键改动", "## 最终报告", "-Accept"):
            self.assertIn(s, bundle)
        self.assertNotIn("lintcheck.py\n", bundle.split("## 关键改动")[1], "起点之前的提交不算")
        body = run(["git", "log", "-1", "--format=%B"], self.root).stdout
        self.assertIn("Agent: Codex", body)
        left = run(["git", "status", "--porcelain"], self.root).stdout
        self.assertIn("progress.json", left, "台账和进度不进助手的提交")
        self.assertNotIn("src/", left)
        # 修改请求编号:报告没回应完就不验收
        req = self.tmp / "req.md"
        req.write_text('R1 改名 "a b"\nR2 补测试\n', encoding="utf-8")
        self.dispatch("-Task", "T5", "-Model", "gpt-6-luna", "-Resume", "fake-thread", "-MessageFile", str(req), "-NoSupervise",
                      scenario="lintfix", responses="T5-R1:改了")
        self.assertIn('R1 改名 "a b"', self.calls()[-1]["args"][-1])
        self.assertIn("-Session", self.dispatch("-Task", "T5", "-Accept", ok=False).stderr)
        self.assertIn("R2", self.dispatch("-Task", "T5", "-Accept", "-Session", "s1", ok=False).stderr)
        self.dispatch("-Task", "T5", "-Model", "gpt-6-luna", "-Resume", "fake-thread", "-MessageFile", str(req), "-NoSupervise",
                      scenario="lintfix", responses="T5-R1:改了,T5-R2:补了")
        self.dispatch("-Task", "T5", "-Accept", "-Session", "s1", "-Note", "看了交接包")
        self.assertEqual([(t["status"], t["review"]) for t in self.progress()], [("done", "pass")])
        self.assertEqual(run(["git", "status", "--porcelain"], self.root).stdout, "")
        body = run(["git", "log", "-1", "--format=%B"], self.root).stdout
        for line in ("Agent: Claude Code", "Session: s1", "Task: T5"):
            self.assertIn(line, body)

    def test_sidekick_branch_is_undone(self):
        # HEX T9(2026-11-05):助手自己建了分支。脚本切回原分支、删掉它,改动照常提交在原分支上
        r = self.dispatch("-Task", "T5", "-Model", "gpt-6-luna", "-NoSupervise", scenario="branch")
        self.assertIn("不要建分支", self.calls()[0]["args"][-1])
        self.assertIn("已切回 main", r.stdout + r.stderr)
        self.assertEqual(run(["git", "rev-parse", "--abbrev-ref", "HEAD"], self.root).stdout.strip(), "main")
        self.assertNotIn("task/T5", run(["git", "branch"], self.root).stdout)
        self.assertIn("src/feature.txt", run(["git", "show", "--stat", "HEAD"], self.root).stdout)

    def test_new_task_resume_sends_start_prompt(self):
        # HEX M1~M2:lead 续用会话派新任务,开工提示、模型备注、主目录检查都被跳过了。续用不带消息 = 开始做任务
        (self.root / "draft.txt").write_text("x", encoding="utf-8")
        self.assertIn("draft.txt", self.dispatch("-Task", "T5", "-Model", "gpt-6-luna", "-Resume", "explore-thread", ok=False).stderr)
        (self.root / "draft.txt").unlink()
        self.dispatch("-Task", "T5", "-Model", "gpt-6-luna", "-Resume", "explore-thread", "-NoSupervise")
        c = self.calls()[-1]
        self.assertEqual(c["args"][:3], ["exec", "resume", "explore-thread"])
        self.assertIn("这是新任务 T5", c["args"][-1])
        self.assertIn("改造现有代码", c["args"][-1], "带上模型备注")
        self.assertIn("model_reasoning_effort=high", c["args"], "默认推理强度 high(Lily 2026-11-06)")
        self.assertNotIn("service_tier=fast", c["args"], "速度档默认是标准")
        # 速度档(v4.2.1):填了 fast 才传给 Codex,台账记下
        self.set_test_command("fast", "ServiceTier")
        self.dispatch("-Task", "T5", "-Model", "gpt-6-luna", "-Resume", "explore-thread", "-NoSupervise")
        self.assertIn("service_tier=fast", self.calls()[-1]["args"])
        self.assertEqual(self.ledger()[-1]["tier"], "fast")
        self.set_test_command("slow", "ServiceTier")
        r = self.dispatch("-Task", "T5", "-Model", "gpt-6-luna", "-Resume", "explore-thread", "-NoSupervise")
        self.assertIn("不支持速度档 slow", r.stdout + r.stderr)
        # 正文里顺带提到的"T7 的 R3"不是修改请求(HEX T8、T11 被记成了修改请求)
        msg = self.tmp / "msg.md"
        msg.write_text("照 T7 的 R3 写卡片\n", encoding="utf-8")
        self.dispatch("-Task", "T5", "-Model", "gpt-6-luna", "-Resume", "fake-thread", "-MessageFile", str(msg), "-NoSupervise")
        self.assertFalse((self.root / "dispatch-logs" / "evidence" / "T5" / "requests-latest.md").exists())

    def test_env_failure_is_not_given_to_sidekick(self):
        # HEX T12:证书错误被当成代码问题交给助手修,助手关掉了证书检查
        (self.root / "envfail.py").write_text('print("Failed to validate certificate for host")\nraise SystemExit(1)\n', encoding="utf-8")
        run(["git", "add", "-A"], self.root)
        run(["git", "commit", "-q", "-m", "envfail"], self.root)
        self.set_test_command("python envfail.py")
        self.dispatch("-Task", "T5", "-Model", "gpt-6-luna", scenario="lintfix")
        self.assertEqual(len(self.calls()), 1, "环境错误不让助手修")
        bundle = (self.root / "dispatch-logs" / "evidence" / "T5" / "bundle.md").read_text(encoding="utf-8-sig")
        self.assertIn("环境错误", bundle)

    def test_bundle_flags_weakened_tests_and_forbidden(self):
        t = self.root / "src" / "test" / "FooTest.java"
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text("class FooTest {\n  void a() { assertEquals(2.0, x); }\n}\n", encoding="utf-8")
        run(["git", "add", "-A"], self.root)
        run(["git", "commit", "-q", "-m", "原有测试"], self.root)
        self.dispatch("-Task", "T5", "-Model", "gpt-6-luna", scenario="sneaky")
        bundle = (self.root / "dispatch-logs" / "evidence" / "T5" / "bundle.md").read_text(encoding="utf-8-sig")
        self.assertIn("原有测试里删掉的断言", bundle)
        self.assertIn("assertEquals(2.0, x)", bundle)
        self.assertNotIn("### src/test/FooTest.java", bundle, "Java 的测试不算关键改动")
        self.assertIn("## 禁止的操作", bundle)
        self.assertIn("forbidden.txt", self.dispatch("-Task", "T5", "-Accept", "-Session", "s1", ok=False).stderr)

    def test_questions_session_and_scope(self):
        # HEX:助手问的分支问题没人答;-Session 填成助手的;临时探针越出可写范围;探索比实现早 4 小时
        brief = GOOD_BRIEF.replace("- 可写范围:src/\n", "- 可写范围:`src/feature.txt`、`src/test/`\n")
        (self.root / "tasks" / "T5.md").write_text(brief, encoding="utf-8")
        t = self.root / "src" / "test" / "FooTest.java"
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text("class FooTest {}\n", encoding="utf-8")
        ev = self.root / "dispatch-logs" / "evidence" / "T5"
        ev.mkdir(parents=True, exist_ok=True)
        (ev / "explore.md").write_text("# 探索包\n", encoding="utf-8")
        os.utime(ev / "explore.md", (time.time() - 3600, time.time() - 3600))
        run(["git", "add", "-A"], self.root)
        run(["git", "commit", "-q", "-m", "探索之后的代码"], self.root)
        self.dispatch("-Task", "T5", "-Model", "gpt-6-luna", scenario="sneaky", questions="要不要切到 task/T5 分支")
        self.assertIn("探索之后代码又有", self.calls()[0]["args"][-1])
        bundle = (ev / "bundle.md").read_text(encoding="utf-8-sig")
        self.assertTrue(bundle.split("## 验收命令")[0].count("要不要切到 task/T5 分支"), "要 lead 回答的问题放在交接包最前面")
        for s in ("## 要 lead 回答的问题", "## 可写范围之外改过的文件", "tmp/Probe.java", "探索包可能过时"):
            self.assertIn(s, bundle)
        (ev / "forbidden.txt").unlink()
        self.assertIn("助手的会话编号", self.dispatch("-Task", "T5", "-Accept", "-Session", "fake-thread", ok=False).stderr)
        self.assertIn("要 lead 回答", self.dispatch("-Task", "T5", "-Accept", "-Session", "s1", "-Note", "看了交接包", ok=False).stderr)
        self.dispatch("-Task", "T5", "-Accept", "-Session", "s1", "-Note", "答:不切分支,在 main 上改")
        self.assertEqual([t["status"] for t in self.progress()], ["done"])

    def test_rollback_keeps_ledger(self):
        self.dispatch("-Task", "T5", "-Model", "gpt-6-luna", "-NoSupervise")
        self.assertTrue((self.root / "src" / "feature.txt").exists())
        self.dispatch("-Task", "T5", "-Rollback", "-Session", "s1")
        self.assertFalse((self.root / "src" / "feature.txt").exists())
        self.assertEqual(len(self.ledger()), 1, "台账不退")
        self.assertEqual([t["status"] for t in self.progress()], ["todo"])
        self.assertEqual(run(["git", "status", "--porcelain"], self.root).stdout, "")

    def test_merge_and_cleanup(self):
        self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", "-Worktree")
        wt = self.tmp / "my proj-T5"
        (self.root / "new-on-main.txt").write_text("x", encoding="utf-8")
        run(["git", "add", "-A"], self.root)
        run(["git", "commit", "-q", "-m", "main 前进"], self.root)
        self.assertIn("没合并", self.dispatch("-Task", "T5", "-Cleanup", ok=False).stderr)
        # 合并:测试命令、审查结论、主目录干净,缺一样都不合并
        self.assertIn("TestCommand", self.dispatch("-Task", "T5", "-Merge", ok=False).stderr)
        self.set_test_command("git nosuchcmd")
        # 派工时脚本代 lead 登记任务、改进度
        self.dispatch("-Task", "T5", "-Model", "gpt-6.1-sol", "-Resume", "fake-thread", "-Message", "继续", "-NoSupervise",
                      scenario="stop")
        prog = json.loads((self.root / "progress.json").read_text(encoding="utf-8"))
        self.assertEqual([t["status"] for t in prog["tasks"] if t["id"] == "T5"], ["doing"])
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
        self.assertTrue((wt / "new-on-main.txt").exists(), "合并前要把 main 合并进任务分支")
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
