from __future__ import annotations

import json
import subprocess
import sys

from conftest import CORE
from fusion_core.state import empty, replay
from fusion_core.supervisor import _estimate_ctx
from fusion_core.util import run


def usage(input_tokens: int) -> dict:
    return {"input": input_tokens, "output": input_tokens // 10,
            "cache_read": input_tokens // 2, "cache_write": input_tokens // 20,
            "requests": 1}


def usage_events(values: list[tuple[str, int]], thread: str = "thread-a") -> list[dict]:
    events = [
        {"seq": 1, "ts": "t1", "type": "task_created", "task": "T1", "data": {"plan": {}}},
        {"seq": 2, "ts": "t2", "type": "station_created", "data": {
            "station": {"name": "main#1", "line": "main"}}},
    ]
    seq = 3
    bound_thread = thread
    for index, (run_id, input_tokens) in enumerate(values):
        events.extend([
            {"seq": seq, "ts": f"t{seq}", "type": "run_requested", "task": "T1",
             "data": {"run": run_id, "kind": "delegate"}},
            {"seq": seq + 1, "ts": f"t{seq + 1}", "type": "run_started", "task": "T1",
             "data": {"run": run_id, "station": "main#1"}},
            {"seq": seq + 2, "ts": f"t{seq + 2}", "type": "thread_bound",
             "data": {"station": "main#1", "thread": bound_thread}},
            {"seq": seq + 3, "ts": f"t{seq + 3}", "type": "run_ended", "task": "T1",
             "data": {"run": run_id, "result": "ok", "usage": usage(input_tokens)}},
        ])
        seq += 4
        if index + 1 < len(values):
            events.append({"seq": seq, "ts": f"t{seq}", "type": "thread_bound",
                           "data": {"station": "main#1", "thread": bound_thread}})
            seq += 1
    return events


def test_usage_replay_counts_cumulative_thread_usage_as_delta():
    state = replay(usage_events([("r1", 1_000_000), ("r2", 1_500_000)]), empty())
    assert state["usage"]["T1"]["sidekick"] == {
        "input": 1_500_000, "output": 150_000, "cache_read": 750_000,
        "cache_write": 75_000, "requests": 2,
    }
    assert state["runs"]["r2"]["usage"] == usage(500_000)
    assert state["runs"]["r2"]["usage_raw"] == usage(1_500_000)


def test_new_thread_starts_usage_delta_from_zero():
    events = usage_events([("r1", 1_000_000)])
    events.extend([
        {"seq": 8, "ts": "t8", "type": "station_created",
         "data": {"station": {"name": "main#2", "line": "main"}}},
        {"seq": 9, "ts": "t9", "type": "thread_bound",
         "data": {"station": "main#2", "thread": "thread-b"}},
        {"seq": 10, "ts": "t10", "type": "run_requested", "task": "T1",
         "data": {"run": "r2", "kind": "delegate"}},
        {"seq": 11, "ts": "t11", "type": "run_started", "task": "T1",
         "data": {"run": "r2", "station": "main#2"}},
        {"seq": 12, "ts": "t12", "type": "run_ended", "task": "T1",
         "data": {"run": "r2", "result": "ok", "usage": usage(250_000)}},
    ])
    state = replay(events, empty())
    assert state["runs"]["r2"]["usage"] == usage(250_000)
    assert state["usage"]["T1"]["sidekick"]["input"] == 1_250_000


def test_old_run_ended_events_replay_cumulative_usage_as_deltas():
    state = replay(usage_events([("r1", 400), ("r2", 900), ("r3", 1_300)]), empty())
    assert state["usage"]["T1"]["sidekick"]["input"] == 1_300
    assert [state["runs"][run]["usage"]["input"] for run in ("r1", "r2", "r3")] == [400, 500, 400]


def test_usage_counter_reset_falls_back_to_new_raw_value():
    state = replay(usage_events([("r1", 1_000), ("r2", 800)]), empty())
    assert state["runs"]["r2"]["usage"]["input"] == 800
    assert state["usage"]["T1"]["sidekick"]["input"] == 1_800


def test_context_estimate_uses_incremental_input_and_running_average():
    assert _estimate_ctx(100_000, 5, 0, 0) == 40_000
    assert _estimate_ctx(400_000, 10, 100_000, 40_000) == 30_000


def test_context_estimate_handles_reset_without_negative_usage():
    assert _estimate_ctx(80, 4, 100, 20) == 20


def test_spawn_detached_uses_prompt_file_even_when_caller_stdin_is_pipe(tmp_path):
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("提示文件内容", encoding="utf-8")
    result_file = tmp_path / "child.json"
    harness = f"""
import sys, time
from pathlib import Path
sys.path.insert(0, {str(CORE)!r})
from fusion_core.util import spawn_detached
target = Path({str(result_file)!r})
child = "import json,os,stat,sys; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps([stat.S_ISREG(os.fstat(0).st_mode),sys.stdin.buffer.read().decode()]),encoding='utf-8')"
spawn_detached([sys.executable, '-c', child, str(target)], {str(tmp_path)!r}, None,
               Path({str(prompt_file)!r}), Path({str(tmp_path / 'out.log')!r}), Path({str(tmp_path / 'err.log')!r}))
deadline = time.monotonic() + 10
while not target.exists() and time.monotonic() < deadline:
    time.sleep(0.05)
"""
    p = subprocess.run([sys.executable, "-c", harness], input=b"caller pipe content",
                       capture_output=True, timeout=15, check=False)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    assert result_file.exists()
    assert json.loads(result_file.read_text(encoding="utf-8")) == [True, "提示文件内容"]


def test_run_closes_stdin_so_reader_gets_eof(tmp_path):
    result = run([sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"],
                 cwd=tmp_path, timeout=10)
    assert result["exit"] == 0
    assert result["output"].strip() == "''"
