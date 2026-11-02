#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则预算:规则文档的总行数不超过上限。skill 要越来越深,不是越来越大。

    python tests/test_budget.py
新加一条规则,要同时删掉或合并一条旧规则,或者把它变成程序能检查的东西。
提高上限要 Lily 同意(Lily 2026-10-28 定下这条做法)。
"""
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
LIMIT = 183  # 2026-10-28 定的总上限 620,2026-11-02 拆分时分给 LiEC 437、lyfusion 183。改这个数要 Lily 同意
RULE_DOCS = ["SKILL.md", "addon/prompts/*.md"]
# 代码不设上限,但 --show 要报出来:复杂度从文档挪进代码时,Lily 也看得见(CraftTax lead 2026-10-29)
CODE = ["addon/tools/*.py", "addon/tools/*.ps1", "tests/*.py", "tests/fake_codex/*.py"]


def count(pats=RULE_DOCS):
    rows = []
    for pat in pats:
        for p in sorted(SKILL.glob(pat)):
            rows.append((p.relative_to(SKILL).as_posix(), len(p.read_text(encoding="utf-8").splitlines())))
    return rows


class BudgetTest(unittest.TestCase):
    def test_rule_docs_within_budget(self):
        rows = count()
        total = sum(n for _, n in rows)
        detail = "\n".join("%5d  %s" % (n, f) for f, n in sorted(rows, key=lambda x: -x[1]))
        self.assertLessEqual(total, LIMIT, "规则文档共 %d 行,超过上限 %d。先删或合并旧规则:\n%s" % (total, LIMIT, detail))


if __name__ == "__main__":
    if "--show" in sys.argv:
        rows = count()
        for f, n in sorted(rows, key=lambda x: -x[1]):
            print("%5d  %s" % (n, f))
        print("%5d  合计(上限 %d)" % (sum(n for _, n in rows), LIMIT))
        print("%5d  代码:工具和测试(不设上限)" % sum(n for _, n in count(CODE)))
    else:
        unittest.main(verbosity=1)
