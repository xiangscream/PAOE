"""Real temporary originals, Windows events, and shared stage-version invariants."""

import json
import os
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event, Thread
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "code/personal-agent-os/scripts"
sys.path.insert(0, str(SCRIPTS))
from paos_content import list_changes, original_version
from paos_content_watch import ContentScope, ContentWatcher, single_watcher
from paos_content_watch_win32 import DirectorySubscription
from paos_content_watch_cli import add_watch_parser, execute_watch
from paos_installation import write_installation_descriptor
from paos_registry import ProjectRegistry
from paos_stage import deliver
from paos_todo import render_todo


class ContentWatchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.project = self.root / "project"
        self.project.mkdir()
        self.data = self.project / "machine-store"  # Not just a name-based exclusion.
        self.install = self.root / "installation.json"
        libraries = self.root / "libraries.json"
        self.workflow, self.skill = self.root / "workflow", self.root / "skill"
        self.workflow.mkdir()
        self.skill.mkdir()
        self.rooter = self.root / "rooter"
        self.rooter.mkdir()
        self.catalog = self.rooter / "catalog.md"
        self.catalog.write_text("tools", encoding="utf8")
        libraries.write_text(json.dumps(dict(schema="paos-library-roots/v1",
            workflow_root=str(self.workflow), skill_root=str(self.skill), tool_catalog=str(self.catalog))))
        write_installation_descriptor(self.install, source_root=str(SCRIPTS.parent),
            data_root=str(self.data), library_roots_config=str(libraries), rooter_home=str(self.rooter))
        ProjectRegistry(self.install).register("3002", root_path=str(self.project),
            homes=["S031"], coordinator_home_id="S031")
        self.scope = ContentScope(self.install)

    def write(self, relative, text="content"):
        file = self.project / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf8")
        return file

    def rows(self):
        return list_changes(self.data, 0, 500)["changes"]

    def wait_for(self, predicate, watcher=None):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if watcher:
                watcher.step()
            if predicate():
                return
            time.sleep(0.03)
        self.fail("Expected observable result did not arrive")

    def test_scope_originals_excludes_stores_homes_history_and_unregistered(self):
        good = self.write("Works/current.md")
        for name in ("machine-store/secret.md", "Data/x.md", "Workstations/S031/mailbox/x.md",
                     "History/old.md", "archive/x.md", ".git/config", "Works/.save.tmp", "Works/save.tmp"):
            self.write(name)
        self.rooter.joinpath("TODO.md").write_text("private")
        self.root.joinpath("unregistered.md").write_text("outside")
        self.workflow.joinpath("method.md").write_text("method")
        ContentWatcher(self.scope).reconcile(self.scope.watch_roots)
        self.assertEqual({r["locator"] for r in self.rows()},
                         {str(good), str(self.catalog), str(self.workflow / "method.md")})
        ContentWatcher(self.scope).reconcile(self.scope.watch_roots)
        self.assertEqual(len(self.rows()), 3)

    def test_stopped_changes_reconciled_and_stage_deliver_deduplicates_both_orders(self):
        artifact, intent = self.write("Works/out.md"), self.write("Works/intent.md", "intent")
        home = self.project / "Workstations/S031"
        home.mkdir(parents=True)
        home.joinpath("TODO.md").write_text(render_todo(home_kind="project_agent", home_id="S031",
            project_id="3002", objective="write", next_action="deliver",
            tasks=[dict(id="CW", title="content", state="doing")]), encoding="utf8")
        kwargs = dict(task_id="CW", operation="watch-stage", artifacts=["Works/out.md"],
            intents=["Works/intent.md"], result="done", next_action="review", waiting="", current=False)
        target = dict(home_id="S031", home_kind="project_agent", home_path=str(home),
                      project_root=str(self.project), project_id="3002")
        watcher = ContentWatcher(self.scope)
        watcher.reconcile([artifact])
        deliver(self.data, target, **kwargs)
        watcher.reconcile(self.scope.watch_roots)
        self.assertEqual(len([r for r in self.rows() if r["locator"] == str(artifact)]), 1)
        self.assertEqual(len([r for r in self.rows() if r["locator"] == str(intent)]), 1)
        artifact.write_text("changed while stopped")
        ContentWatcher(self.scope).reconcile(self.scope.watch_roots)
        self.assertEqual(len([r for r in self.rows() if r["locator"] == str(artifact)]), 2)

    @unittest.skipUnless(os.name == "nt", "Windows native notifications")
    def test_subscriptions_precede_startup_scan_and_capture_scan_race(self):
        created = self.project / "after-scan.md"
        events = []
        watcher = ContentWatcher(self.scope, emit=events.append, settle_seconds=0)
        original = watcher.reconcile
        def during_scan(paths):
            self.assertEqual(set(watcher.streams), set(self.scope.watch_roots))
            original(paths)
            created.write_text("created after snapshot")
        with patch.object(watcher, "reconcile", side_effect=during_scan):
            watcher.start()
        self.addCleanup(watcher.close)
        self.wait_for(lambda: any(r["locator"] == str(created) for r in self.rows()), watcher)
        self.assertEqual([e["event"] for e in events[:2]], ["subscribed", "ready"])

    @unittest.skipUnless(os.name == "nt", "Windows native notifications")
    def test_atomic_save_rename_and_continuous_save_use_final_paths(self):
        file = self.write("Works/draft.md", "old")
        watcher = ContentWatcher(self.scope, settle_seconds=0.1)
        watcher.start()
        self.addCleanup(watcher.close)
        tmp = self.write("Works/.editor.tmp", "new")
        os.replace(tmp, file)
        renamed = file.with_name("final.md")
        file.rename(renamed)
        for n in range(4):
            renamed.write_text(f"final {n}")
        self.wait_for(lambda: any(r["locator"] == str(renamed) for r in self.rows()), watcher)
        got = [r for r in self.rows() if r["locator"] == str(renamed)]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["version"], original_version(renamed))
        self.assertFalse(any(".tmp" in r["locator"] for r in self.rows()))

    @unittest.skipUnless(os.name == "nt", "Windows native notifications")
    def test_actual_buffer_overflow_is_reconciled(self):
        watcher = ContentWatcher(self.scope,
            subscription=lambda root: DirectorySubscription(root, buffer_size=128), settle_seconds=0)
        events = []
        watcher.emit = events.append
        watcher.start()
        self.addCleanup(watcher.close)
        for n in range(80):
            self.write(f"Works/{n:03}-long-original-name.md", str(n))
        self.wait_for(lambda: len(self.rows()) == 81, watcher)
        self.assertIn("overflow", [e["event"] for e in events])

    @unittest.skipUnless(os.name == "nt", "Windows native notifications")
    def test_directory_disconnect_resubscribes_then_reconciles(self):
        events = []
        watcher = ContentWatcher(self.scope, emit=events.append, settle_seconds=0)
        watcher.start()
        self.addCleanup(watcher.close)
        away = self.root / "workflow-away"
        self.workflow.rename(away)
        watcher.next_health = 0
        watcher.step()
        self.assertIn(self.workflow, watcher.retry_at)
        away.joinpath("offline.md").write_text("while disconnected")
        away.rename(self.workflow)
        watcher.retry_at[self.workflow] = 0
        watcher.step()
        self.assertNotIn(self.workflow, watcher.retry_at)
        self.assertTrue(any(r["locator"] == str(self.workflow / "offline.md") for r in self.rows()))
        self.assertIn("reconnected", [e["event"] for e in events])

    @unittest.skipUnless(os.name == "nt", "Windows lock")
    def test_single_process_lock_released_after_exit(self):
        with single_watcher(self.data):
            with self.assertRaisesRegex(RuntimeError, "already owns"):
                with single_watcher(self.data):
                    self.fail("Second observer acquired lock")
        with single_watcher(self.data):
            pass

    @unittest.skipUnless(os.name == "nt", "Windows coordinated native stop")
    def test_coordinated_stop_cancels_io_flushes_final_originals_and_releases(self):
        stop, ready = Event(), Event()
        watcher = ContentWatcher(self.scope, emit=lambda e: ready.set() if e["event"] == "ready" else None)
        result = []
        def run():
            result.append(watcher.run(stop))
        thread = Thread(target=run)
        thread.start()
        try:
            self.assertTrue(ready.wait(8))
            final = self.write("Works/final.md", "save immediately before stop")
        finally:
            stop.set()
            thread.join(8)
        self.assertFalse(thread.is_alive())
        self.assertTrue(result[0]["ok"], result)
        self.assertEqual(watcher.streams, {})
        self.assertTrue(any(r["locator"] == str(final) for r in self.rows()))
        with single_watcher(self.data):
            pass

    def test_missing_root_does_not_silently_start_partial_scope(self):
        self.skill.rmdir()
        with self.assertRaisesRegex(ValueError, "Invalid business"):
            ContentScope(self.install)

    @unittest.skipUnless(os.name == "nt", "Windows public entry")
    def test_public_registration_entry_stop_and_missing_installation(self):
        parser = argparse.ArgumentParser()
        add_watch_parser(parser.add_subparsers(dest="content_command"))
        args = parser.parse_args(["watch"])
        stop = Event()
        events = []
        def emit(event):
            events.append(event)
            if event["event"] == "ready":
                self.write("Works/public-entry.md", "last save")
                stop.set()
        result = execute_watch(args, self.install, stop=stop, emit=emit)
        self.assertTrue(result["ok"])
        self.assertEqual(events[-1]["event"], "stopped")
        self.assertTrue(any(r["locator"].endswith("public-entry.md") for r in self.rows()))
        proc = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / "paos_content_watch_cli.py"),
            "--installation-file", str(self.root / "absent.json"), "content", "watch"],
            capture_output=True, text=True, encoding="utf8", timeout=10)
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(json.loads(proc.stdout)["ok"])

    @unittest.skipUnless(os.name == "nt", "Windows junction boundary")
    def test_junction_does_not_import_unregistered_content(self):
        outside = self.root / "outside"
        outside.mkdir()
        outside.joinpath("private.md").write_text("outside")
        junction = self.project / "linked"
        proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
                              capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        try:
            ContentWatcher(self.scope).reconcile(self.scope.watch_roots)
            self.assertFalse(any("private.md" in r["locator"] for r in self.rows()))
            self.assertFalse(self.scope.allows(junction / "private.md"))
        finally:
            junction.rmdir()  # Unlink the verified temporary junction; do not recurse.

    @unittest.skipUnless(os.name == "nt", "Windows native cleanup")
    def test_scan_failure_cancels_every_already_subscribed_root(self):
        watcher = ContentWatcher(self.scope)
        with patch.object(watcher, "reconcile", side_effect=ValueError("invalid original")):
            with self.assertRaisesRegex(ValueError, "invalid original"):
                watcher.start()
        self.assertEqual(watcher.streams, {})


if __name__ == "__main__":
    unittest.main()
