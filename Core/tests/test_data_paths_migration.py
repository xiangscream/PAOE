"""Installation Data paths and explicit machine-store migration."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE / "code/personal-agent-os/scripts"
sys.path.insert(0, str(SCRIPTS))
from paos_data_paths import (
    contact_store_path, mail_dispatch_dir, project_scope, ui_board_path,
)
from paos_data_migration import execute, plan, rollback
from paos_contact import load_native_targets, save_native_targets
from paos_installation import write_installation_descriptor
from paos_mail import send_mail
from paos_registry import ProjectRegistry


class DataMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="paoe-data-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.install = self.base / "installation.json"
        self.data = self.base / "Data"
        self.rooter = self.base / "rooter"
        self.rooter.mkdir()
        write_installation_descriptor(
            self.install, source_root=str(PACKAGE / "code/personal-agent-os"),
            data_root=str(self.data), library_roots_config=str(self.base / "libs.json"),
            rooter_home=str(self.rooter))
        self.registry = ProjectRegistry(self.install)
        for project_id in ("1001", "1002"):
            root = self.base / f"project-{project_id}"
            root.mkdir()
            self.registry.register(project_id, root_path=str(root),
                                   coordinator_home_id=f"{project_id}-s001",
                                   homes=[f"{project_id}-s001"])
            self._old_contact(root, {f"{project_id}-s001": {"runtime": "codex"}})
            (root / ".paos/mail/dispatch").mkdir(parents=True)
            (root / ".paos/mail/dispatch/msg-1.json").write_text("{}", encoding="utf-8")
            (root / ".paos/ui").mkdir(parents=True)
            (root / ".paos/ui/board.json").write_text(
                json.dumps({"nodes": {f"{project_id}-s001": {"x": 1, "y": 2}}}),
                encoding="utf-8")
        self._old_contact(self.rooter, {"rooter-001": {"runtime": "codex"}})
        (self.rooter / ".paos/mail/dispatch").mkdir(parents=True)
        (self.rooter / ".paos/mail/dispatch/rooter-1.json").write_text("{}", encoding="utf-8")
        (self.rooter / ".paos/ui").mkdir(parents=True)
        (self.rooter / ".paos/ui/board.json").write_text("{}", encoding="utf-8")

    def _old_contact(self, root: Path, value: dict):
        path = root / "private-data/contact/native-targets.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_plan_execute_and_rollback(self):
        self.assertEqual(contact_store_path(self.install),
                         self.data / "contact/native-targets.json")
        self.assertEqual(mail_dispatch_dir(project_scope("1001"), self.install),
                         self.data / "mail/project-1001/dispatch")
        self.assertEqual(ui_board_path(project_scope("1001"), self.install),
                         self.data / "ui/project-1001/board.json")
        planned = plan(self.install)
        self.assertEqual(set(planned["contact_keys"]),
                         {"1001-s001", "1002-s001", "rooter-001"})
        self.assertEqual(len(planned["mail"]), 3)
        self.assertEqual(len(planned["ui"]), 3)
        before = self.base / "before.json"
        result = execute(self.install, before)
        self.assertTrue(before.is_file())
        self.assertEqual(result["mail_moved"], 3)
        self.assertTrue((self.data / "contact/native-targets.json").is_file())
        self.assertTrue((self.data / "mail/project-1001/dispatch/msg-1.json").is_file())
        self.assertTrue((self.data / "ui/rooter/board.json").is_file())
        self.assertFalse((self.base / "project-1001/.paos/mail/dispatch").exists())
        rollback(before)
        self.assertTrue((self.base / "project-1001/.paos/mail/dispatch/msg-1.json").is_file())
        self.assertTrue((self.base / "project-1001/.paos/ui/board.json").is_file())
        self.assertFalse((self.data / "contact/native-targets.json").exists())

    def test_contact_and_dispatch_writers_use_installation_data(self):
        target = {"1001-s001": {"runtime": "codex", "session_id": "s1"}}
        stored = save_native_targets(self.base, target, self.install)
        self.assertEqual(stored, contact_store_path(self.install))
        self.assertEqual(load_native_targets(self.base, self.install), target)
        project = self.registry.read("1001")
        home = self.base / "project-1001/Workstations/1001-s001"
        (home / "mailbox").mkdir(parents=True)
        result = send_mail(
            root=self.base / "project-1001", project=project,
            subject="s", body="b", recipients=["1001-s001"],
            message_id="new-dispatch", installation_path=self.install)
        self.assertTrue((self.data / "mail/project-1001/dispatch/new-dispatch.json").is_file())
        self.assertFalse((self.base / "project-1001/.paos/mail/dispatch/new-dispatch.json").exists())
        self.assertEqual(result["dispatch_path"],
                         str(self.data / "mail/project-1001/dispatch/new-dispatch.json"))

    def test_contact_conflict_aborts_before_mutation(self):
        # Same key, different target in the second project.
        path = self.base / "project-1002/private-data/contact/native-targets.json"
        path.write_text(json.dumps({"1001-s001": {"runtime": "other"}}),
                        encoding="utf-8")
        with self.assertRaises(ValueError):
            plan(self.install)
        self.assertFalse((self.data / "contact/native-targets.json").exists())


if __name__ == "__main__":
    unittest.main()
