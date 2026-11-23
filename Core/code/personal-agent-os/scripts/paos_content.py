"""Local originals and versioned changes shared by delivery and the content watcher."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from paos_context import local_source


def scoped_file(root: Path, locator: str) -> Path:
    path = local_source(root, locator)
    if path is None or not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"所选项目原件不可读：{locator}")
    return path


def original_version(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def db_path(data: Path) -> Path:
    return data / "content" / "events.sqlite3"


@contextmanager
def changes_db(data: Path):
    path = db_path(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=5)) as db:
        db.row_factory = sqlite3.Row
        db.executescript("""
        CREATE TABLE IF NOT EXISTS changes (
          seq INTEGER PRIMARY KEY, locator TEXT NOT NULL, version TEXT NOT NULL,
          kind TEXT NOT NULL, origin TEXT NOT NULL,
          recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(locator,version)
        );
        CREATE TABLE IF NOT EXISTS stages (
          home TEXT NOT NULL, operation TEXT NOT NULL, request TEXT NOT NULL,
          sources TEXT NOT NULL, finished INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(home,operation)
        );
        CREATE TABLE IF NOT EXISTS stop_events (
          home TEXT NOT NULL, event TEXT NOT NULL, PRIMARY KEY(home,event)
        );
        CREATE TABLE IF NOT EXISTS consumers (
          home TEXT PRIMARY KEY, through_seq INTEGER NOT NULL, result_ref TEXT NOT NULL
        );
        """)
        with db:
            yield db


def record_version(db, locator, version, kind, origin):
    db.execute(
        """INSERT INTO changes(locator,version,kind,origin) VALUES(?,?,?,?)
                  ON CONFLICT(locator,version) DO NOTHING""",
        (locator, version, kind, origin),
    )
    return db.execute(
        "SELECT seq FROM changes WHERE locator=? AND version=?", (locator, version)
    ).fetchone()[0]


def list_changes(data, after, limit):
    if after < 0 or not 1 <= limit <= 500:
        raise ValueError("游标须非负，limit 范围为 1 至 500")
    path = db_path(data)
    if not path.exists():
        return {"ok": True, "changes": [], "cursor": after}
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM changes WHERE seq>? ORDER BY seq LIMIT ?", (after, limit)
            )
        ]
    return {"ok": True, "changes": rows, "cursor": rows[-1]["seq"] if rows else after}


def consume(data, home, through, result_ref):
    root = Path(home["project_root"] or home["home_path"])
    output = scoped_file(root, result_ref)
    with changes_db(data) as db:
        if not db.execute("SELECT 1 FROM changes WHERE seq=?", (through,)).fetchone():
            raise ValueError("through 必须指向实际存在的变化")
        prior = db.execute(
            "SELECT through_seq,result_ref FROM consumers WHERE home=?", (home["home_id"],)
        ).fetchone()
        if prior and (through < prior[0] or through == prior[0] and str(output) != prior[1]):
            raise ValueError("消费游标已前进或同一游标的成果不一致")
        db.execute(
            "INSERT OR REPLACE INTO consumers(home,through_seq,result_ref) VALUES(?,?,?)",
            (home["home_id"], through, str(output)),
        )
    return {"ok": True, "home_id": home["home_id"], "cursor": through, "result_ref": str(output)}


def pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
