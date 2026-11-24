"""Isolated native Windows rule notifications through the existing observer."""

import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event, Thread
import time
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "code" / "personal-agent-os" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from paos_agents_common import END, START, managed_section, source_block
from paos_content import list_changes
from paos_content_watch_cli import add_watch_parser, execute_watch
from paos_content_watch_win32 import api
from paos_installation import write_installation_descriptor
from paos_registry import ProjectRegistry
from paos_rules_sync import DOCUMENTS, RulesSync


class RulesSyncTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.data = self.home / "Data"
        system = self.home / "System"
        source = system / "Core" / "code" / "personal-agent-os"
        source.mkdir(parents=True)
        self.templates = system / "Project-Template"
        self.templates.mkdir()
        self.rooter = system / "rooter"
        self.rooter.mkdir()
        self.installation = self.home / "installation.json"
        write_installation_descriptor(
            self.installation, source_root=str(source), rooter_home=str(self.rooter),
            data_root=str(self.data), library_roots_config=str(self.home / "library-roots.json"),
        )
        self.registry = ProjectRegistry(self.installation)
        self.projects = {"3002": self.register("3002"), "3003": self.register("3003")}
        for document in DOCUMENTS:
            self.template(document, "始版")
        for scope in (*self.projects.values(), self.rooter):
            self.initialize(scope)
        self.events = []

    def register(self, number, *, only_directory=False):
        root = self.home / number
        root.mkdir()
        if not only_directory:
            self.registry.register(number, root_path=str(root), coordinator_home_id="S034")
        return root

    def template(self, document, text, *, atomic=False):
        path = self.templates / document
        out = path.with_suffix(".tmp") if atomic else path
        out.write_text(f"# System\n{START}\n{text}\n{END}\n", encoding="utf-8")
        if atomic:
            os.replace(out, path)

    def initialize(self, root, *, documents=DOCUMENTS):
        for document in documents:
            source = source_block(self.templates / document)
            text = f"# Local {root.name}\n{START}\n{managed_section(source)}{END}\n项目人工补充  \n"
            (root / document).write_bytes(text.replace("\n", "\r\n").encode("utf-8"))

    def wait_for(self, test):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if test():
                return
            time.sleep(0.025)
        self.fail(f"Expected Windows watcher result did not arrive: {self.events[-4:]}")

    def row(self, target, doc, status, *, after=0):
        return any(event["event"] == "rules_sync" and any(
            row["target"] == target and row["document"] == doc and row["status"] == status
            for row in event["targets"]) for event in self.events[after:])

    def start(self):
        parser = argparse.ArgumentParser()
        add_watch_parser(parser.add_subparsers(dest="content_command"))
        args = parser.parse_args(["watch"])
        stop, ready = Event(), Event()
        result = []

        def emit(event):
            self.events.append(event)
            if event["event"] == "ready":
                ready.set()

        worker = Thread(target=lambda: result.append(
            execute_watch(args, self.installation, stop=stop, emit=emit)))
        worker.start()

        def finish():
            stop.set()
            worker.join(10)
            self.assertFalse(worker.is_alive())
            self.assertTrue(result)
            return result[0]

        self.addCleanup(finish)
        self.assertTrue(ready.wait(8), self.events)
        return finish

    def assert_narrow_update(self, root, document, expected):
        content = (root / document).read_bytes()
        self.assertTrue(content.startswith(f"# Local {root.name}\r\n{START}\r\n".encode()))
        self.assertTrue(content.endswith(f"{END}\r\n项目人工补充  \r\n".encode()))
        self.assertIn(expected.encode("utf-8"), content)

    @unittest.skipUnless(os.name == "nt", "Windows native notifications")
    def test_normal_save_atomic_replace_new_registry_and_restart(self):
        private = self.rooter / "TODO.md"
        private.write_bytes(b"Rooter original")
        finish = self.start()
        self.template("AGENTS.md", "运行时直接保存")
        self.wait_for(lambda: self.row("rooter", "AGENTS.md", "updated"))
        for scope in (*self.projects.values(), self.rooter):
            self.assert_narrow_update(scope, "AGENTS.md", "运行时直接保存")

        self.template("WORK-LEAD.md", "替换式保存", atomic=True)
        self.wait_for(lambda: self.row("rooter", "WORK-LEAD.md", "updated"))
        for scope in (*self.projects.values(), self.rooter):
            self.assert_narrow_update(scope, "WORK-LEAD.md", "替换式保存")

        newcomer = self.register("3004", only_directory=True)
        self.initialize(newcomer, documents=["AGENTS.md"])
        self.registry.register("3004", root_path=str(newcomer), coordinator_home_id="S034")
        self.wait_for(lambda: self.row("3004", "WORK-LEAD.md", "updated"))
        self.assertIn("替换式保存", (newcomer / "WORK-LEAD.md").read_text(encoding="utf-8"))
        self.assert_narrow_update(newcomer, "AGENTS.md", "运行时直接保存")
        self.assertTrue(finish()["ok"])

        before = (self.projects["3002"] / "AGENTS.md").stat().st_mtime_ns
        self.template("AGENTS.md", "运行时直接保存", atomic=True)  # Same public bytes.
        self.template("WORK-LEAD.md", "停机期间的新稿", atomic=True)
        finish = self.start()
        self.assertEqual((self.projects["3002"] / "AGENTS.md").stat().st_mtime_ns, before)
        self.assert_narrow_update(self.rooter, "WORK-LEAD.md", "停机期间的新稿")
        self.assertIn("停机期间的新稿", (newcomer / "WORK-LEAD.md").read_text(encoding="utf-8"))
        self.assertTrue(finish()["ok"])
        self.assertEqual(private.read_bytes(), b"Rooter original")
        locators = [row["locator"] for row in list_changes(self.data, 0, 500)["changes"]]
        for prefix in (self.data, self.rooter, self.templates):
            self.assertFalse(any(Path(locator).is_relative_to(prefix) for locator in locators))

    @unittest.skipUnless(os.name == "nt", "Windows native file sharing")
    def test_real_target_conflict_and_lock_do_not_block_healthy_targets(self):
        wrong = self.projects["3003"] / "AGENTS.md"
        original = wrong.read_bytes()
        conflict = original.replace("始版".encode(), "人工改了公共区".encode())
        wrong.write_bytes(conflict)
        locked = self.rooter / "AGENTS.md"
        old_locked = locked.read_bytes()
        kernel = api()
        # Read sharing without delete sharing stops the real replace until the editor closes.
        handle = kernel.CreateFileW(str(locked), 0x80000000, 1, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            finish = self.start()
            self.template("AGENTS.md", "其他目标继续")
            self.wait_for(lambda: self.row("rooter", "AGENTS.md", "write_failed")
                          and self.row("3002", "AGENTS.md", "updated"))
            self.assertTrue(self.row("3003", "AGENTS.md", "conflict"))
            self.assertEqual(wrong.read_bytes(), conflict)
            self.assertEqual(locked.read_bytes(), old_locked)
        finally:
            kernel.CloseHandle(handle)
        self.wait_for(lambda: self.row("rooter", "AGENTS.md", "updated"))
        self.assert_narrow_update(self.rooter, "AGENTS.md", "其他目标继续")

        wrong.write_bytes(original)
        self.wait_for(lambda: self.row("3003", "AGENTS.md", "updated"))
        self.assert_narrow_update(self.projects["3003"], "AGENTS.md", "其他目标继续")
        self.assertTrue(finish()["ok"])

    @unittest.skipUnless(os.name == "nt", "Windows native notifications")
    def test_invalid_source_and_registry_clearly_reported_and_recovered(self):
        registry_path = self.data / "project-registry/projects/3003.json"
        registration = registry_path.read_bytes()
        registry_path.write_bytes(b'{"invalid":')
        agents = self.templates / "AGENTS.md"
        agents.write_bytes(b"Invalid template")
        before = (self.projects["3002"] / "AGENTS.md").read_bytes()
        finish = self.start()
        self.assertTrue(self.row("system", "AGENTS.md", "source_error"))
        self.assertTrue(self.row("3003", None, "unavailable"))
        self.template("WORK-LEAD.md", "其他母本正常")
        self.wait_for(lambda: self.row("rooter", "WORK-LEAD.md", "updated"))
        self.assertEqual((self.projects["3002"] / "AGENTS.md").read_bytes(), before)
        self.template("AGENTS.md", "恢复母本", atomic=True)
        registry_path.write_bytes(registration)
        self.wait_for(lambda: self.row("3003", "AGENTS.md", "updated"))
        self.assert_narrow_update(self.projects["3003"], "AGENTS.md", "恢复母本")
        self.assertTrue(finish()["ok"])

    @unittest.skipUnless(os.name == "nt", "Windows native reconnection")
    def test_unavailable_registered_root_starts_other_targets_and_recovers(self):
        missing = self.projects["3003"]
        away = missing.with_name("temporarily-away")
        missing.rename(away)
        self.template("AGENTS.md", "启动有离线项目")
        finish = self.start()
        self.assertTrue(self.row("3003", "AGENTS.md", "unavailable"))
        self.assertTrue(self.row("3002", "AGENTS.md", "updated"))
        (away / "while-offline.md").write_text("surviving offline change", encoding="utf-8")
        away.rename(missing)
        self.wait_for(lambda: self.row("3003", "AGENTS.md", "updated"))
        self.wait_for(lambda: any(event["event"] == "reconnected" and event["root"] == str(missing)
                                  for event in self.events))
        self.assert_narrow_update(missing, "AGENTS.md", "启动有离线项目")
        def recorded(name):
            return any(row["locator"] == str(missing / name)
                       for row in list_changes(self.data, 0, 500)["changes"])
        self.wait_for(lambda: recorded("while-offline.md"))
        (missing / "after-reconnect.md").write_text("new native event", encoding="utf-8")
        self.wait_for(lambda: recorded("after-reconnect.md"))
        self.assertTrue(finish()["ok"])

    def test_public_status_is_read_only_and_shows_each_target(self):
        self.template("AGENTS.md", "只检查")
        file = self.projects["3002"] / "AGENTS.md"
        before = file.read_bytes()
        command = [sys.executable, "-B", "-X", "utf8", str(SCRIPTS / "paos.py"),
                   "--installation-file", str(self.installation), "--json",
                   "content", "watch", "--rules-status"]
        proc = subprocess.run(command, capture_output=True, encoding="utf-8", timeout=10)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertFalse(report["ok"])
        self.assertEqual({(row["target"], row["status"]) for row in report["targets"]
                          if row["document"] == "AGENTS.md"},
                         {("3002", "stale"), ("3003", "stale"), ("rooter", "stale")})
        self.assertEqual(file.read_bytes(), before)
        self.assertFalse((self.data / "content").exists())

    def test_unchanged_pass_preserves_entire_target_bytes_and_mtime(self):
        rules = RulesSync(self.installation)
        rules.refresh()
        path = self.rooter / "AGENTS.md"
        before = path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ino
        report, retry = rules.reconcile(apply=True)
        self.assertTrue(report["ok"])
        self.assertFalse(retry)
        self.assertTrue(all(row["status"] == "in-sync" for row in report["targets"]))
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ino), before)


if __name__ == "__main__":
    unittest.main()
