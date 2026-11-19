"""Quiet Mail claim/result CLI links a source to TODO and CAT stays silent."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE / "code/personal-agent-os/scripts"
sys.path.insert(0, str(PACKAGE))
sys.path.insert(0, str(SCRIPTS))
from paos_attention_service import send_mail_source
from paos_installation import write_installation_descriptor
from paos_registry import ProjectRegistry
from paos_todo import parse_todo, render_todo, update_todo_current, write_todo


class MailClaimTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mail-claim-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.project_root = self.base / "project"
        self.project_root.mkdir()
        self.install = self.base / "installation.json"
        self.data = self.base / "data"
        self.numbers = self.base / "AGENT-NUMBERS.json"
        self.numbers.write_text(json.dumps({"1001-s001": "S010", "1001-s002": "S032"}),
                                encoding="utf-8")
        write_installation_descriptor(
            self.install, source_root=str(SCRIPTS.parent), data_root=str(self.data),
            library_roots_config=str(self.base / "libraries.json"),
            agent_numbers_config=str(self.numbers))
        self.registry = ProjectRegistry(self.install)
        self.registry.register("1001", root_path=str(self.project_root),
                               coordinator_home_id="S010", homes=["S010", "S032"])
        self._make_home("S010", "sender", "sender")
        self._make_home("S032", "receiver", "receiver")
        self.project = self.registry.read("1001")
        send_mail_source(
            root=self.project_root, project=self.project,
            subject="需要接手", body="原信正文", recipients=["S032"],
            sender_kind="agent", sender_id="S010",
            message_id="claim-source-001", request_activation=False)

    def _make_home(self, home_id, owner, objective):
        home = self.project_root / "Workstations" / home_id
        (home / "mailbox").mkdir(parents=True)
        (home / "notices").mkdir()
        write_todo(home / "TODO.md", render_todo(
            home_kind="project_agent", home_id=home_id, project_id="1001",
            objective=objective, next_action="保持当前主线",
            waiting="T-EXIST" if owner == "receiver" else "",
            tasks=[{"id": "T-EXIST", "title": "既有任务", "state": "doing",
                    "source_refs": []}] if owner == "receiver" else []))

    def _cli(self, *args):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "paos.py"),
             "--installation-file", str(self.install), "--json", *args],
            text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_claim_links_existing_task_reads_and_is_quiet_idempotent(self):
        before = len(list((self.project_root / "Workstations/S032/mailbox").glob("*.md")))
        claimed = self._cli("mail", "claim", "1001", "S032",
                            "claim-source-001", "--task", "T-EXIST")
        self.assertTrue(claimed["ok"])
        self.assertEqual(claimed["task_id"], "T-EXIST")
        todo = parse_todo((self.project_root / "Workstations/S032/TODO.md").read_text(encoding="utf-8"))
        task = next(item for item in todo["tasks"] if item["id"] == "T-EXIST")
        self.assertIn("mail:claim-source-001", task["source_refs"])
        self.assertEqual(todo["current"]["waiting"], "T-EXIST")
        self.assertTrue(claimed["notice"]["read"])
        self.assertTrue(claimed["notice"]["claimed"])
        self.assertEqual(claimed["notice"]["claimed_by_home_id"], "S032")
        self.assertEqual(before, len(list((self.project_root / "Workstations/S032/mailbox").glob("*.md"))))
        again = self._cli("mail", "claim", "1001", "S032",
                          "claim-source-001", "--task", "T-EXIST")
        self.assertFalse(again["task_changed"])
        self.assertFalse(again["claim_changed"])
        # A broad existing Task is not auto-completed, and a non-exact
        # Waiting sentence is not truncated.
        update_todo_current(
            self.project_root / "Workstations/S032/TODO.md",
            {"waiting": "T-EXIST plus other work"})
        result = self._cli("mail", "result", "1001", "S032",
                           "claim-source-001", "--result", "step done")
        self.assertEqual(result["task_state"], "doing")
        todo = parse_todo((self.project_root / "Workstations/S032/TODO.md").read_text(encoding="utf-8"))
        task = next(item for item in todo["tasks"] if item["id"] == "T-EXIST")
        self.assertEqual(task["state"], "doing")
        self.assertEqual(todo["current"]["waiting"], "T-EXIST plus other work")

    def test_new_task_and_result_resolve_waiting_without_new_mail(self):
        claimed = self._cli("mail", "claim", "1001", "S032", "claim-source-001")
        task_id = claimed["task_id"]
        todo = parse_todo((self.project_root / "Workstations/S032/TODO.md").read_text(encoding="utf-8"))
        task = next(item for item in todo["tasks"] if item["id"] == task_id)
        self.assertEqual(task["state"], "doing")
        self.assertIn("mail:claim-source-001", task["source_refs"])
        update_todo_current(
            self.project_root / "Workstations/S032/TODO.md",
            {"waiting": task_id})
        before = len(list((self.project_root / "Workstations/S032/mailbox").glob("*.md")))
        result = self._cli("mail", "result", "1001", "S032",
                           "claim-source-001", "--task", task_id,
                           "--result", "已处理并交付")
        self.assertEqual(result["task_state"], "done")
        todo = parse_todo((self.project_root / "Workstations/S032/TODO.md").read_text(encoding="utf-8"))
        task = next(item for item in todo["tasks"] if item["id"] == task_id)
        self.assertEqual(task["state"], "done")
        self.assertEqual(task["result"], "已处理并交付")
        self.assertEqual(todo["current"]["waiting"], "")
        self.assertEqual(result["notice"]["state"], "handled")
        self.assertEqual(before, len(list((self.project_root / "Workstations/S032/mailbox").glob("*.md"))))


if __name__ == "__main__":
    unittest.main()
