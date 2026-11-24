"""Local originals and versioned changes shared by delivery and the content watcher."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from paos_context import local_source


def scoped_file(root: Path, locator: str, *, source_roots=()) -> Path:
    path = local_source(root, locator)
    roots = (root, *source_roots)
    if path is None or not any(path.is_relative_to(Path(r).resolve()) for r in roots) or not path.is_file():
        raise ValueError(f"所选项目原件不可读：{locator}")
    return path


def original_version(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def snapshot_original(path: Path):
    """Retain text originals; large media continue to use their existing locator."""
    if path.suffix.casefold() not in {".md", ".txt"}:
        return original_version(path), None
    body = path.read_bytes()
    return hashlib.sha256(body).hexdigest(), body


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
          previous_seq INTEGER
        );
        CREATE TABLE IF NOT EXISTS versions (version TEXT PRIMARY KEY, body BLOB NOT NULL);
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
            db.execute("BEGIN IMMEDIATE")
            if "previous_seq" not in {r[1] for r in db.execute("PRAGMA table_info(changes)")}:
                # Keep existing sequence IDs and consumer receipts; old bytes stay unknown.
                db.execute("ALTER TABLE changes RENAME TO changes_v1")
                db.execute("""CREATE TABLE changes (
                  seq INTEGER PRIMARY KEY, locator TEXT NOT NULL, version TEXT NOT NULL,
                  kind TEXT NOT NULL, origin TEXT NOT NULL,
                  recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, previous_seq INTEGER)""")
                db.execute("""INSERT INTO changes SELECT seq,locator,version,kind,origin,recorded_at,
                  lag(seq) OVER (PARTITION BY locator ORDER BY seq) FROM changes_v1""")
                db.execute("DROP TABLE changes_v1")
            db.execute("CREATE INDEX IF NOT EXISTS changes_locator_seq ON changes(locator,seq)")
        with db:
            yield db


def save_snapshot(db, version, body):
    if body is not None:
        if hashlib.sha256(body).hexdigest() != version:
            raise ValueError("原件正文与登记版本不一致")
        db.execute("INSERT OR IGNORE INTO versions VALUES(?,?)", (version, body))


def record_version(db, locator, version, kind, origin, *, body=None):
    save_snapshot(db, version, body)
    prior = db.execute(
        "SELECT seq,version FROM changes WHERE locator=? ORDER BY seq DESC LIMIT 1", (locator,)
    ).fetchone()
    if prior and prior[1] == version:
        return prior[0]
    return db.execute(
        "INSERT INTO changes(locator,version,kind,origin,previous_seq) VALUES(?,?,?,?,?)",
        (locator, version, kind, origin, prior[0] if prior else None),
    ).lastrowid


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


def read_change(data, seq):
    if seq < 1 or not db_path(data).exists():
        raise ValueError("变化序号不存在")
    with closing(sqlite3.connect(db_path(data).as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM changes WHERE seq=?", (seq,)).fetchone()
        if row is None:
            raise ValueError("变化序号不存在")
        prior = db.execute(
            "SELECT * FROM changes WHERE locator=? AND seq<? ORDER BY seq DESC LIMIT 1",
            (row["locator"], seq),
        ).fetchone()
        has_versions = db.execute("SELECT 1 FROM sqlite_master WHERE name='versions'").fetchone()

        def original(change):
            if change is None:
                return {"state": "baseline", "version": None, "body": None}
            saved = db.execute("SELECT body FROM versions WHERE version=?", (change["version"],)).fetchone() if has_versions else None
            return {"state": "captured" if saved else "not_captured",
                    "version": change["version"],
                    "body": bytes(saved[0]).decode("utf-8-sig") if saved else None}

        return {"ok": True, "change": dict(row), "before": original(prior), "after": original(row)}


def consumer_progress(data, home_id):
    result = {"ok": True, "home_id": home_id, "cursor": 0, "result_ref": "",
              "latest_seq": 0, "pending_count": 0}
    if not db_path(data).exists():
        return result
    with closing(sqlite3.connect(db_path(data).as_uri() + "?mode=ro", uri=True)) as db:
        prior = db.execute("SELECT through_seq,result_ref FROM consumers WHERE home=?", (home_id,)).fetchone()
        if prior:
            result.update(cursor=prior[0], result_ref=prior[1])
        result["latest_seq"] = db.execute("SELECT coalesce(max(seq),0) FROM changes").fetchone()[0]
        result["pending_count"] = db.execute("SELECT count(*) FROM changes WHERE seq>?", (result["cursor"],)).fetchone()[0]
    return result


def consume(data, home, through, result_ref, *, source_roots=()):
    root = Path(home["project_root"] or home["home_path"])
    output = scoped_file(root, result_ref, source_roots=source_roots)
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
