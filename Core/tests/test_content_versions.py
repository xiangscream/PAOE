"""Retain observed transitions and originals without repairing on read."""

from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "code/personal-agent-os/scripts"
sys.path.insert(0, str(SCRIPTS))
from paos_content import changes_db, db_path, list_changes, record_version


class ContentVersionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name) / "data"

    def test_return_to_previous_text_is_a_new_observed_transition(self):
        with changes_db(self.data) as db:
            for version in ("a", "b", "a", "a"):
                record_version(db, "INDEX.md", version, "original", "watcher")
        rows = list_changes(self.data, 0, 50)["changes"]
        self.assertEqual([r["version"] for r in rows], ["a", "b", "a"])

    def test_snapshot_before_and_after_survive_source_change(self):
        from paos_content import read_change, snapshot_original
        path = self.data.parent / "INDEX.md"
        for text in ("当前：研究\n", "当前：已交付\n"):
            path.write_text(text, encoding="utf-8", newline="\n")
            version, body = snapshot_original(path)
            with changes_db(self.data) as db:
                record_version(db, str(path), version, "original", "watcher", body=body)
        path.write_text("new human edit", encoding="utf-8")
        got = read_change(self.data, 2)
        self.assertEqual(got["before"]["body"], "当前：研究\n")
        self.assertEqual(got["after"]["body"], "当前：已交付\n")
        self.assertEqual(path.read_text(encoding="utf-8"), "new human edit")

    def test_old_records_are_readable_without_creating_or_migrating_files(self):
        from paos_content import read_change
        path = db_path(self.data)
        path.parent.mkdir(parents=True)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE changes (seq INTEGER PRIMARY KEY, locator TEXT, version TEXT, "
                       "kind TEXT, origin TEXT, recorded_at TEXT, UNIQUE(locator,version))")
            db.execute("INSERT INTO changes VALUES(7,'INDEX.md','old','original','watcher','past')")
            db.execute("CREATE TABLE consumers (home TEXT PRIMARY KEY, through_seq INTEGER, result_ref TEXT)")
            db.execute("INSERT INTO consumers VALUES('S072',7,'Topics/accepted.md')")
        before = path.read_bytes()
        got = read_change(self.data, 7)
        self.assertIsNone(got["after"]["body"])
        self.assertEqual(got["after"]["state"], "not_captured")
        self.assertEqual(path.read_bytes(), before)
        with changes_db(self.data) as db:
            record_version(db, "INDEX.md", "new", "original", "watcher")
            record_version(db, "INDEX.md", "old", "original", "watcher")
        rows = list_changes(self.data, 0, 50)["changes"]
        self.assertEqual([r["seq"] for r in rows], [7, 8, 9])
        from paos_content import consumer_progress
        progress = consumer_progress(self.data, "S072")
        self.assertEqual((progress["cursor"], progress["pending_count"]), (7, 2))

    def test_missing_progress_read_is_pure_and_pending_is_explicit(self):
        from paos_content import consumer_progress
        self.assertEqual(consumer_progress(self.data, "S072")["pending_count"], 0)
        self.assertFalse(self.data.exists())
        with changes_db(self.data) as db:
            record_version(db, "INDEX.md", "a", "original", "watcher")
            record_version(db, "Works/a.md", "b", "artifact", "stage")
            db.execute("INSERT INTO consumers VALUES('S072',1,'Topics/result.md')")
        got = consumer_progress(self.data, "S072")
        self.assertEqual((got["cursor"], got["pending_count"], got["latest_seq"]), (1, 1, 2))

    def test_snapshot_must_match_the_registered_version(self):
        with self.assertRaisesRegex(ValueError, "版本"):
            with changes_db(self.data) as db:
                record_version(db, "INDEX.md", "incorrect", "original", "watcher", body=b"text")
        self.assertEqual(list_changes(self.data, 0, 50)["changes"], [])


if __name__ == "__main__":
    unittest.main()
