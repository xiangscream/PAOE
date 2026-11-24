from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import paos_exm_publish as publish
from paos_exm_originals import BatchError
from paos_installation import write_installation_descriptor
from paos_registry import ProjectRegistry


def codex_record(message_id, text):
    return {"type": "event_msg", "payload": {
        "type": "item_completed", "thread_id": "isolated-thread", "turn_id": "turn-a",
        "completed_at_ms": 1791423939394, "item": {
            "type": "UserMessage", "id": message_id, "content": [
                {"type": "text", "text": text},
                {"type": "localImage", "path": "fixture/附件.png"},
            ],
        },
    }}


class OriginalPublicationTests(unittest.TestCase):
    def setUp(self):
        home = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.installation = home / "installation.json"
        self.data = home / "Data"
        self.exm = home / "EXM"
        self.exm.mkdir()
        self.project = home / "Project"
        self.project.mkdir()
        self.source = home / "selected.jsonl"
        self.origins = home / "verified.json"
        self.dest = self.exm / "Sessions" / "Codex" / "selected.md"
        self.db = self.data / "exm" / "originals.sqlite3"
        write_installation_descriptor(self.installation, source_root=str(SCRIPTS.parent),
                                      data_root=str(self.data), library_roots_config=str(home / "roots.json"))
        registry = ProjectRegistry(self.installation)
        registry.register("3002", root_path=str(self.project), coordinator_home_id="S034")
        registry.register("3005", root_path=str(self.exm), coordinator_home_id="S072")
        self.selection = {
            "format": "codex-rollout", "session_id": "isolated-thread", "project_id": "3002",
            "exm_project_id": "3005",
            "input_file": str(self.source), "page": "Sessions/Codex/selected.md",
            "origins_file": str(self.origins), "work_group": "书写验收",
        }
        self.origins.write_text(json.dumps({
            key: {"kind": "human", "evidence_ref": f"fixture native composer:{key}"}
            for key in ("a", "b", "c")
        }), encoding="utf-8")

    def write(self, *records):
        self.source.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")

    def run_import(self, **options):
        return publish.publish_originals(self.installation, **(self.selection | options))

    def read_cursor(self):
        if not self.db.exists():
            return None
        with closing(sqlite3.connect(self.db)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='originals'").fetchone():
                return None
            row = db.execute("SELECT cursor FROM originals").fetchone()
        return json.loads(row[0]) if row else None

    def test_append_preserves_exact_text_attachments_and_human_edits_without_duplicate(self):
        raw = "  用户原文\r\n```\n<!-- paoe-exm-originals pretend -->\n最后一行  "
        authored = b"\xef\xbb\xbf# Existing page\r\n\r\nA human note with trailing spaces.  \r\n"
        self.dest.parent.mkdir(parents=True)
        self.dest.write_bytes(authored)
        self.write(codex_record("a", raw))
        one = self.run_import()
        self.assertEqual(one["saved"], 1)
        first = self.dest.read_bytes()
        self.assertTrue(first.startswith(authored))
        self.assertIn(raw.encode(), first)
        self.assertIn('"path": "fixture/附件.png"'.encode(), first)
        self.assertNotIn(raw, json.dumps(self.read_cursor(), ensure_ascii=False))

        edited = first.replace(b"A human note", b"An edited human note") + b"\nHuman postscript.\n"
        self.dest.write_bytes(edited)
        duplicate = self.run_import()
        self.assertEqual(duplicate["saved"], 0)
        self.assertEqual(self.dest.read_bytes(), edited)
        self.write(codex_record("a", raw), codex_record("b", raw))
        self.assertEqual(self.run_import()["saved"], 1)
        self.assertTrue(self.dest.read_bytes().startswith(edited))
        self.assertEqual(self.dest.read_bytes().count(raw.encode()), 2)

    def test_revisions_and_changing_back_keep_each_original(self):
        for text in ("first!", "revised!", "first!"):
            self.write(codex_record("a", text))
            self.assertEqual(self.run_import()["saved"], 1)
        page = self.dest.read_bytes()
        self.assertEqual(page.count(b"\nfirst!\n"), 2)
        self.assertEqual(page.count(b"\nrevised!\n"), 1)
        self.assertEqual(self.read_cursor()["messages"]["a"]["revision"], 3)
        self.assertEqual(self.run_import()["saved"], 0)
        self.assertEqual(self.dest.read_bytes(), page)

    def test_failure_and_range_past_eof_keep_previous_checkpoint_and_page(self):
        self.write(codex_record("a", "first"))
        self.run_import()
        before = self.dest.read_bytes()
        prior = self.read_cursor()
        self.write(codex_record("a", "first"), codex_record("unknown", "unknown"))
        refused = self.run_import()
        self.assertFalse(refused["cursor_committed"])
        self.assertEqual(refused["issues"][0]["reason"], "origin_unverified")
        self.write(codex_record("a", "changed"))
        with self.assertRaisesRegex(BatchError, "past the supplied file"):
            self.run_import(end_line=2)
        self.source.write_text('{"bad"', encoding="utf-8")
        with self.assertRaisesRegex(BatchError, "invalid JSONL"):
            self.run_import()
        self.assertEqual(self.read_cursor(), prior)
        self.assertEqual(self.dest.read_bytes(), before)

    def test_later_range_and_overlapping_reread_keep_later_checkpoint(self):
        self.write(codex_record("a", "first"), codex_record("b", "next"))
        self.assertEqual(self.run_import(end_line=1)["position"]["line"], 1)
        self.assertEqual(self.run_import(start_line=2)["position"]["line"], 2)
        original = self.dest.read_bytes()
        self.assertEqual(self.run_import(end_line=1)["position"]["line"], 2)
        self.assertEqual(self.dest.read_bytes(), original)

    def test_hard_process_exit_after_page_and_before_cursor_recovers_with_a_newer_input(self):
        self.write(codex_record("a", "first version"))
        program = (
            "import json, os, sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import paos_exm_publish as p\n"
            "p._save_cursor = lambda *args: os._exit(71)\n"
            "p.publish_originals(sys.argv[2], **json.loads(sys.argv[3]))\n"
        )
        result = subprocess.run([sys.executable, "-B", "-c", program, str(SCRIPTS),
                                 str(self.installation), json.dumps(self.selection)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 71, result.stderr)
        self.assertIsNone(self.read_cursor())
        original = self.dest.read_bytes()
        self.write(codex_record("a", "revised after restart"), codex_record("b", "new after restart"))
        resumed = self.run_import()
        self.assertEqual((resumed["saved"], resumed["recovered"]), (2, 1))
        self.assertTrue(self.dest.read_bytes().startswith(original))
        self.assertEqual(self.read_cursor()["messages"]["a"]["revision"], 2)
        self.assertEqual(self.run_import()["saved"], 0)

    def test_empty_no_human_batch_only_advances_data(self):
        self.write({"type": "event_msg", "payload": {"type": "task_started"}})
        result = self.run_import()
        self.assertTrue(result["cursor_committed"])
        self.assertEqual(result["saved"], 0)
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.read_cursor()["position"]["line"], 1)

    def test_concurrent_edit_detected_before_replace_and_preserved(self):
        self.write(codex_record("a", "initial"))
        self.run_import()
        human = self.dest.read_bytes() + b"\nConcurrent human note.\n"
        prior = self.read_cursor()
        self.write(codex_record("a", "new version"))
        flush = os.fsync

        def edit_during_flush(fd):
            flush(fd)
            self.dest.write_bytes(human)

        with patch.object(publish.os, "fsync", side_effect=edit_during_flush):
            with self.assertRaisesRegex(BatchError, "changed during"):
                self.run_import()
        self.assertEqual(self.dest.read_bytes(), human)
        self.assertEqual(self.read_cursor(), prior)

    def test_concurrent_importers_share_one_published_revision(self):
        self.write(codex_record("a", "first"))
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(self.run_import) for _ in range(2)]
            self.assertEqual(sorted(future.result()["saved"] for future in pending), [0, 1])
        self.assertEqual(self.dest.read_bytes().count(b"\nfirst\n"), 1)
        self.assertEqual(self.read_cursor()["messages"]["a"]["revision"], 1)

    def test_page_is_scoped_and_cannot_be_rebound(self):
        self.write(codex_record("a", "initial"))
        with self.assertRaisesRegex(BatchError, "within registered EXM"):
            self.run_import(page=str(self.project / "outside.md"))
        self.run_import()
        with self.assertRaisesRegex(BatchError, "keep the registered"):
            self.run_import(page="Sessions/somewhere-else.md")
        with self.assertRaisesRegex(BatchError, "keep the registered"):
            self.run_import(work_group="different stream")
        self.assertFalse((self.exm / "Sessions" / "somewhere-else.md").exists())

    def test_missing_published_revision_stops_instead_of_recreating_it(self):
        self.write(codex_record("a", "initial"))
        self.run_import()
        prior = self.read_cursor()
        self.dest.write_bytes(b"# Replaced by editor.\n")
        with self.assertRaisesRegex(BatchError, "published originals are missing"):
            self.run_import()
        self.assertEqual(self.dest.read_bytes(), b"# Replaced by editor.\n")
        self.assertEqual(self.read_cursor(), prior)

    def test_public_cli_reads_normal_dsh_zip_and_reports_replay(self):
        archive = self.source.with_suffix(".zip")
        records = [{"type": "session", "id": "dsh-fixture", "version": 4}, {
            "type": "user/message", "surfaceOp": "append", "seq": 0, "time": 1791423939394,
            "data": {"id": "dsh-msg-1", "source": {"kind": "user"}, "content": [
                {"type": "text", "text": "DSH 原话"},
            ]},
        }]
        with ZipFile(archive, "w") as output:
            output.writestr("session.v4.jsonl", "\n".join(json.dumps(row) for row in records) + "\n")
        command = [sys.executable, "-B", "-X", "utf8", str(SCRIPTS / "paos.py"),
                   "--installation-file", str(self.installation), "--json", "context", "originals", "--format", "dsh-export",
                   "--session", "dsh-fixture", "--project", "3002", "--input", str(archive),
                   "--exm-project", "3005",
                   "--page", "Sessions/DSH.md"]
        for expected in (1, 0):
            result = subprocess.run(command, capture_output=True, encoding="utf-8", timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["saved"], expected)
            self.assertTrue(Path(receipt["page"]).is_file())

    def test_experience_project_is_explicit_and_portable(self):
        elsewhere = self.exm.parent / "OtherExperience"
        elsewhere.mkdir()
        ProjectRegistry(self.installation).register("3008", root_path=str(elsewhere), coordinator_home_id="S073")
        self.write(codex_record("a", "Selected experience"))
        result = self.run_import(exm_project_id="3008")
        self.assertTrue(Path(result["page"]).is_relative_to(elsewhere))
        self.assertIn(b"Selected experience", Path(result["page"]).read_bytes())
        self.assertFalse(self.dest.exists())

    def test_public_cli_bad_zip_is_structured_and_does_not_advance(self):
        archive = self.source.with_suffix(".zip")
        archive.write_bytes(b"not an export ZIP")
        result = subprocess.run([
            sys.executable, "-B", "-X", "utf8", str(SCRIPTS / "paos.py"),
            "--installation-file", str(self.installation), "--json", "context", "originals",
            "--format", "dsh-export", "--session", "dsh-fixture", "--project", "3002",
            "--exm-project", "3005", "--input", str(archive), "--page", "Sessions/DSH.md",
        ], capture_output=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 1)
        receipt = json.loads(result.stdout or result.stderr)
        self.assertFalse(receipt["ok"])
        self.assertIn("valid export ZIP", receipt["error"])
        self.assertIsNone(self.read_cursor())
        self.assertFalse(self.dest.exists())


if __name__ == "__main__":
    unittest.main()
