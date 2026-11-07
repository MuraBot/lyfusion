"""事件库:`fusion/fusion.db`,sqlite3 WAL。所有写入都经过 `transaction()`。"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from . import SCHEMA
from .util import dumps, now

DDL = """
CREATE TABLE IF NOT EXISTS events (
    seq   INTEGER PRIMARY KEY AUTOINCREMENT,
    ts    TEXT NOT NULL,
    v     INTEGER NOT NULL,
    type  TEXT NOT NULL,
    task  TEXT,
    item  TEXT,
    actor TEXT NOT NULL,
    data  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lease (
    name      TEXT PRIMARY KEY,
    holder    TEXT NOT NULL,
    heartbeat REAL NOT NULL
);
"""


def connect(root: Path) -> sqlite3.Connection:
    path = root / "fusion" / "fusion.db"
    path.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(DDL)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    """写事务:BEGIN IMMEDIATE 先拿写锁,读状态、校验、追加事件在同一个事务里完成。"""
    for attempt in range(50):
        try:
            conn.execute("BEGIN IMMEDIATE")
            break
        except sqlite3.OperationalError as e:
            if "locked" not in str(e) and "busy" not in str(e):
                raise
            time.sleep(0.1 * (attempt + 1))
    else:
        raise sqlite3.OperationalError("事件库一直被锁住")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def append(conn: sqlite3.Connection, events: list[dict], actor: str) -> list[dict]:
    """在已开始的事务里追加事件,返回带 seq 的事件。"""
    out = []
    for e in events:
        ts = now()
        cur = conn.execute(
            "INSERT INTO events (ts, v, type, task, item, actor, data) VALUES (?,?,?,?,?,?,?)",
            (ts, SCHEMA, e["type"], e.get("task"), e.get("item"), e.get("actor", actor), dumps(e.get("data", {}))),
        )
        out.append({**e, "seq": cur.lastrowid, "ts": ts, "actor": e.get("actor", actor), "v": SCHEMA})
    return out


def read(conn: sqlite3.Connection, after: int = 0) -> list[dict]:
    rows = conn.execute(
        "SELECT seq, ts, v, type, task, item, actor, data FROM events WHERE seq > ? ORDER BY seq", (after,)
    ).fetchall()
    return [upgrade({"seq": r[0], "ts": r[1], "v": r[2], "type": r[3], "task": r[4], "item": r[5],
                     "actor": r[6], "data": json.loads(r[7])}) for r in rows]


def upgrade(event: dict) -> dict:
    """按事件格式版本升级旧事件。目前只有版本 1。"""
    return event


def export_jsonl(conn: sqlite3.Connection, path: Path) -> int:
    events = read(conn)
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(dumps(e) + "\n")
    return len(events)


# ---- 监督权:同一个项目只能有一个 serve 监督助手运行 ----

def take_lease(conn: sqlite3.Connection, holder: str, ttl: float = 30.0) -> bool:
    with transaction(conn):
        row = conn.execute("SELECT holder, heartbeat FROM lease WHERE name='supervisor'").fetchone()
        t = time.time()
        if row is None or row[0] == holder or t - row[1] > ttl:
            conn.execute("INSERT OR REPLACE INTO lease (name, holder, heartbeat) VALUES ('supervisor', ?, ?)",
                         (holder, t))
            return True
        return False


def release_lease(conn: sqlite3.Connection, holder: str) -> None:
    with transaction(conn):
        conn.execute("DELETE FROM lease WHERE name='supervisor' AND holder=?", (holder,))


def holder_id() -> str:
    return f"{os.getpid()}@{time.time():.0f}"
