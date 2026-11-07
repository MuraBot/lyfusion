"""lead 的工具表:MCP 和命令行共用。说明文字要短,参数说明写在 schema 里。"""
from __future__ import annotations

from . import commands as C

_STR = {"type": "string"}
_STRS = {"type": "array", "items": {"type": "string"}}
_TASK = {"type": "string", "description": "任务编号,例如 T3"}

PLAN_SCHEMA = {
    "type": "object",
    "description": "任务单",
    "properties": {
        "goal": {"type": "string", "description": "目标;用户能感知的写成「体验:……」"},
        "direct": {"type": "boolean", "description": "true = lead 自己做(只写 goal 也行)"},
        "decisions": {"type": "array", "items": _STR, "description": "引用的决定,例如 D3 或 D3@2"},
        "bounds": {"type": "object", "description": "三组边界,派工时必须写(可以是空列表)",
                   "properties": {"must": _STRS, "free": _STRS, "escalate": _STRS}},
        "items": {"type": "array", "description": "工作项", "items": {"type": "object", "properties": {
            "id": {"type": "string", "description": "W1、W2……"},
            "type": {"type": "string", "enum": ["judgment", "mechanical", "verify", "explore"]},
            "title": _STR,
            "owner": {"type": "string", "enum": ["lead", "sidekick"],
                      "description": "默认:judgment 归 lead,其他归 sidekick"},
            "files": {"type": "array", "items": _STR, "description": "文件范围(glob)"},
            "decisions": _STRS,
            "checks": {"type": "array", "items": _STR, "description": "对应的验收检查编号"},
            "follows": {"type": "string", "description": "照哪个 lead 的 judgment 工作项做(样例)"},
            "perceivable": {"type": "boolean"},
            "notes": _STR}}},
        "checks": {"type": "array", "description": "验收检查", "items": {"type": "object", "properties": {
            "id": {"type": "string", "description": "C1、C2……"},
            "kind": {"type": "string", "enum": ["command", "manual"]},
            "run": {"type": "string", "description": "command:要跑的命令"},
            "expect": {"type": "object", "description": "command 的期望:exit、contains、regex、passed_min",
                       "properties": {"exit": {"type": "integer"}, "contains": _STR, "regex": _STR,
                                      "passed_min": {"type": "integer"}}},
            "look": {"type": "string", "description": "manual:看什么"},
            "pass": {"type": "string", "description": "manual:怎样算通过"},
            "signer": {"type": "string", "enum": ["lead", "user"]}}}},
        "tests_may_change": {"type": "array", "items": {"type": "object", "properties": {
            "glob": _STR, "decision": _STR}}, "description": "允许助手改的测试,每条引用一条决定"},
        "fixes": {"type": "string", "description": "修的是哪个已验收任务的漏检"},
        "notes": _STR,
    },
    "required": ["goal"],
}

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "op": {"type": "string", "enum": ["add", "revise", "supersede"], "description": "默认 add"},
        "id": {"type": "string", "description": "revise / supersede 时的决定编号"},
        "category": {"type": "string", "enum": ["experience", "interface", "rule", "constraint"]},
        "content": _STR, "reason": _STR,
        "scope": {"type": "array", "items": _STR, "description": "影响的文件(glob)"},
        "source": {"type": "string", "description": "来源,例如用户的原话"},
        "examples": _STRS, "counterexamples": _STRS, "rejected": {"type": "array", "items": _STR,
                                                                   "description": "否决过的方案"},
        "check": {"type": "object", "description": "检查命令:每个候选都会跑",
                  "properties": {"run": _STR, "expect": {"type": "object"}}},
        "by": {"type": "string", "description": "supersede:新的决定编号"},
    },
}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    out = {"type": "object", "properties": props}
    if required:
        out["required"] = required
    return out


TOOLS = [
    {"name": "fusion_status", "desc": "看 Fusion 的状态:任务、工位、待答问题、信号。target 可以是任务编号或运行编号。",
     "schema": _obj({"target": {"type": "string", "description": "可选:T3 或 r5"}}),
     "fn": lambda ctx, a: C.cmd_status(ctx, a.get("target"))},
    {"name": "fusion_intent", "desc": "新增、修改或取代一条意图决定(体验、接口、规则、约束)。",
     "schema": DECISION_SCHEMA, "fn": lambda ctx, a: C.cmd_intent(ctx, a)},
    {"name": "fusion_plan", "desc": "建任务或改任务单(planned、in_review 时可改版)。direct 任务只写 goal。",
     "schema": _obj({"plan": PLAN_SCHEMA, "task": {"type": "string", "description": "改已有任务时写编号"}},
                    ["plan"]),
     "fn": lambda ctx, a: C.cmd_plan(ctx, a["plan"], a.get("task"))},
    {"name": "fusion_explore", "desc": "派一次只读探索(1~3 个问题),答案以通知送达。",
     "schema": _obj({"questions": _STRS, "task": _TASK}, ["questions"]),
     "fn": lambda ctx, a: C.cmd_explore(ctx, a["questions"], a.get("task"))},
    {"name": "fusion_delegate", "desc": "把工作项派给助手。有 follows 的工作项要在 exemplar 里给样例的提交。",
     "schema": _obj({"task": _TASK, "items": {"type": "array", "items": _STR, "description": "默认:全部待做的助手工作项"},
                     "exemplar": {"type": "object", "description": "{\"W1\": \"提交\"}"},
                     "notes": {"type": "string", "description": "这次派工的补充说明"}}, ["task"]),
     "fn": lambda ctx, a: C.cmd_delegate(ctx, a["task"], a.get("items") or [], a.get("exemplar"), a.get("notes"))},
    {"name": "fusion_answer", "desc": "回答助手的问题。非阻塞问题要写 agree;值得长期记住的用 promote 升格为决定。",
     "schema": _obj({"question": {"type": "string", "description": "问题编号,例如 Q4"}, "answer": _STR,
                     "agree": {"type": "boolean", "description": "非阻塞问题:是否同意助手已经选的做法"},
                     "promote": {"type": "object", "description": "升格为决定:category、content、reason",
                                 "properties": {"category": _STR, "content": _STR, "reason": _STR,
                                                "scope": _STRS}}}, ["question", "answer"]),
     "fn": lambda ctx, a: C.cmd_answer(ctx, a["question"], a["answer"], a.get("promote"), a.get("agree"))},
    {"name": "fusion_review", "desc": "取最新候选的交接视图。tier 1 摘要;2(默认)加决定债和关键文件 diff;3 完整 diff 和日志。",
     "schema": _obj({"task": _TASK, "tier": {"type": "integer", "enum": [1, 2, 3]}}, ["task"]),
     "fn": lambda ctx, a: C.cmd_review(ctx, a["task"], a.get("tier") or 2)},
    {"name": "fusion_request_changes", "desc": "提修改意见(每条写 text 和 expect),可以驳回助手自定的选择。最多 3 轮。",
     "schema": _obj({"task": _TASK,
                     "comments": {"type": "array", "items": _obj({"text": _STR, "expect": {
                         "type": "string", "description": "期望的结果"}, "ref": {
                         "type": "string", "description": "可选:相关的决定或文件"}}, ["text", "expect"])},
                     "overrule": {"type": "array", "items": _obj({"eid": {
                         "type": "string", "description": "决定债编号,例如 T3.E2"}, "note": _STR}, ["eid"])}},
                    ["task"]),
     "fn": lambda ctx, a: C.cmd_request_changes(ctx, a["task"], a.get("comments") or [], a.get("overrule") or [])},
    {"name": "fusion_accept", "desc": "验收候选:处理剩下的决定债(ratify / promote)、签人工检查。引擎合并并快进 main。",
     "schema": _obj({"task": _TASK, "candidate": {"type": "string", "description": "例如 T3.c2;默认最新"},
                     "ratify": {"type": "array", "items": _STR, "description": "认可的决定债编号"},
                     "promote": {"type": "array", "items": _obj({"eid": _STR, "category": _STR, "content": _STR,
                                                                 "reason": _STR}, ["eid"]),
                                 "description": "升格为决定的决定债"},
                     "manual": {"type": "array", "items": _obj({"check": _STR, "verdict": {
                         "type": "string", "enum": ["pass", "fail"]}, "by": {
                         "type": "string", "enum": ["lead", "user-via-lead"]}, "note": _STR}, ["check"]),
                                "description": "人工检查签字"},
                     "note": _STR,
                     "waive": {"type": "string", "description": "放行环境错误或违规的理由(违规要写用户原话)"}},
                    ["task"]),
     "fn": lambda ctx, a: C.cmd_accept(ctx, a["task"], a.get("candidate"), a.get("ratify"), a.get("promote"),
                                       a.get("manual"), a.get("note"), a.get("waive"))},
    {"name": "fusion_reject", "desc": "退回任务:删任务分支,证据留在 fusion/runs/。",
     "schema": _obj({"task": _TASK, "reason": _STR}, ["task", "reason"]),
     "fn": lambda ctx, a: C.cmd_reject(ctx, a["task"], a["reason"])},
    {"name": "fusion_cancel", "desc": "取消任务:停止助手,丢掉没提交的改动。",
     "schema": _obj({"task": _TASK, "reason": _STR}, ["task"]),
     "fn": lambda ctx, a: C.cmd_cancel(ctx, a["task"], a.get("reason"))},
    {"name": "fusion_takeover", "desc": "接管:停止助手,工作项改由 lead 做;bring 为 true 时把半成品搬到你的工作目录(不提交)。",
     "schema": _obj({"task": _TASK, "bring": {"type": "boolean"}, "reason": _STR}, ["task", "reason"]),
     "fn": lambda ctx, a: C.cmd_takeover(ctx, a["task"], a.get("bring", True), a["reason"])},
]

BY_NAME = {t["name"]: t for t in TOOLS}
CLI_NAMES = {t["name"][len("fusion_"):].replace("_", "-"): t for t in TOOLS}
