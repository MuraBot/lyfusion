import json

import pytest
from fusion_core import aq
from fusion_core.util import FusionError


def as_json(d):
    return aq.parse_plan(json.dumps(d, ensure_ascii=False))


def test_markdown_plan_equals_json_plan():
    md = "# 加一个功能\n\n## 目标\n做 X\n\n## scope\n- src/**\n- `tests/**`\n\n## checks\n- python -m pytest -q\n* `ruff check .`\n"
    assert aq.parse_plan(md) == as_json({"goal": "加一个功能", "brief": "## 目标\n做 X",
        "scope": ["src/**", "tests/**"],
        "checks": [{"run": "python -m pytest -q"}, {"run": "ruff check ."}]})


def test_markdown_without_reserved_sections_and_crlf():
    assert aq.parse_plan("﻿\r\n# 目标一句\r\n正文第一行\r\n\r\n正文第二行\r\n") == as_json({"goal": "目标一句", "brief": "正文第一行\n\n正文第二行"})


def test_reserved_section_in_middle_and_fence():
    md = "# g\n前文\n## SCOPE  \n- a/**\n## 已知的坑\n坑\n```text\n## checks\n- not a check\n```\n"
    assert aq.parse_plan(md) == as_json({"goal": "g", "brief": "前文\n## 已知的坑\n坑\n```text\n## checks\n- not a check\n```", "scope": ["a/**"]})


def test_json_still_first():
    assert aq.parse_plan('  \n{"goal": "g", "brief": "b"}') == as_json({"goal": "g", "brief": "b"})
    with pytest.raises(FusionError, match="计划不是合法的 JSON"):
        aq.parse_plan("{bad")


@pytest.mark.parametrize("md, words", [
    ("目标\n正文", '"# 一句话目标"'),
    ("## 小标题\n正文", '"# 一句话目标"'),
    ("# g\nb\n## scope\nsrc/**\n", "## scope"),
    ("# g\nb\n## checks\n- ``\n", "## checks"),
    ("# g\nb\n## scope\n- a\n## scope\n- b\n", "只能写一次"),
])
def test_markdown_errors(md, words):
    with pytest.raises(FusionError) as err:
        aq.parse_plan(md)
    assert words in str(err.value)


def test_markdown_empty_brief_is_rejected_by_validate():
    with pytest.raises(FusionError):
        aq.parse_plan("# g\n## scope\n- a\n")
