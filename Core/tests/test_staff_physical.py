"""Physical S-number Home: registry, legacy alias, Board people/agent."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE / "code/personal-agent-os/scripts"
sys.path.insert(0, str(PACKAGE))
sys.path.insert(0, str(SCRIPTS))
from front.paos_front_server import Board
from paos import _allocate_staff_number
from paos_agent_numbers import load_numbers, staff_number
from paos_attention_service import AttentionServiceProblem, resolve_home_by_registry
from paos_installation import write_installation_descriptor
from paos_registry import ProjectRegistry
from paos_todo import render_todo, write_todo


class StaffPhysicalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="staff-physical-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.install = self.base / "installation.json"
        self.data = self.base / "data"
        self.project = self.base / "project"
        self.project.mkdir()
        self.numbers = self.base / "AGENT-NUMBERS.json"
        self.numbers.write_text(json.dumps({"1001-s001": "S040"}), encoding="utf-8")
        write_installation_descriptor(
            self.install, source_root=str(SCRIPTS.parent), data_root=str(self.data),
            library_roots_config=str(self.base / "library-roots.json"),
            agent_numbers_config=str(self.numbers))
        self.registry = ProjectRegistry(self.install)
        self.registry.register("1001", root_path=str(self.project),
                               coordinator_home_id="S040", homes=["S040"])
        home = self.project / "Workstations/S040"
        (home / "mailbox").mkdir(parents=True)
        (home / "notices").mkdir()
        (home / "ENTRY.md").write_text("# S040\n", encoding="utf-8")
        write_todo(home / "TODO.md", render_todo(
            home_kind="project_agent", home_id="S040", project_id="1001",
            objective="实体 S 工位", next_action="读取原信"))
        (self.project / "TEAM.md").write_text(
            "## 当前成员\n### S040\n- 职责/专长：实体桥验证\n- 成员状态：在队\n",
            encoding="utf-8")

    def test_s_home_resolves_directly_and_old_id_only_as_alias(self):
        direct = resolve_home_by_registry("S040", installation_file=str(self.install))
        self.assertEqual(direct["home_id"], "S040")
        self.assertEqual(Path(direct["home_path"]).parts[-2:], ("Workstations", "S040"))
        legacy = resolve_home_by_registry("1001-s001", installation_file=str(self.install))
        self.assertEqual(legacy["home_id"], "S040")
        self.assertEqual(Path(legacy["home_path"]).parts[-2:], ("Workstations", "S040"))
        self.assertEqual(staff_number("S040", installation_path=self.install), "S040")
        self.assertEqual(staff_number("1001-s001", installation_path=self.install), "S040")

    def test_new_staff_registration_and_init_use_the_same_number(self):
        cli = [sys.executable, "-X", "utf8", "-B", str(SCRIPTS / "paos.py"),
               "--installation-file", str(self.install), "--json"]
        original = self.registry._path("1001").read_bytes()
        revision = hashlib.sha256(original).hexdigest()
        registered = subprocess.run(
            cli + ["project", "home-add", "1001", "S099", "--expected-fingerprint", revision],
            capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(registered.returncode, 0, registered.stderr)
        created = subprocess.run(cli + ["workstation", "init", "1001", "S099"],
                                 capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertTrue((self.project / "Workstations/S099/ENTRY.md").is_file())
        self.assertEqual(load_numbers(self.numbers)["S099"], "S099")

        other = self.base / "other-project"
        other.mkdir()
        duplicate = subprocess.run(cli + ["project", "register", "2002", "--root", str(other),
                                         "--coordinator", "S099"],
                                   capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertEqual(json.loads(duplicate.stderr)["error_code"], "staff_home_already_registered")
        self.assertFalse(self.registry._path("2002").exists())

    def test_board_exposes_canonical_id_and_read_only_legacy_alias(self):
        board = Board(self.install)
        people = board.people()
        row = people[0]
        self.assertEqual(row["id"], "S040")
        self.assertEqual(row["staff_number"], "S040")
        self.assertEqual(row["legacy_home_ids"], ["1001-s001"])
        self.assertIn("S040", row["name"])
        agent = board.agent("S040")
        self.assertEqual(agent["id"], "S040")
        self.assertTrue(agent["ok"])
        dashboard = board.dashboard("1001", include_cat=False)
        summary = next(item for item in dashboard["agents"] if item["id"] == "S040")
        self.assertEqual(summary["staff_number"], "S040")
        self.assertEqual(summary["legacy_home_ids"], ["1001-s001"])

    def test_pre_migration_s_and_old_id_both_resolve_the_registered_old_home(self):
        old_project = self.base / "old-project"
        (old_project / "Workstations/2002-s001").mkdir(parents=True)
        self.registry.register("2002", root_path=str(old_project),
                               coordinator_home_id="2002-s001", homes=["2002-s001"])
        numbers = json.loads(self.numbers.read_text(encoding="utf-8"))
        numbers["2002-s001"] = "S099"
        self.numbers.write_text(json.dumps(numbers), encoding="utf-8")
        old = resolve_home_by_registry("2002-s001", installation_file=str(self.install))
        self.assertEqual(old["home_id"], "2002-s001")
        by_s = resolve_home_by_registry("S099", installation_file=str(self.install))
        self.assertEqual(by_s["home_id"], "2002-s001")
        still_s = resolve_home_by_registry("S040", installation_file=str(self.install))
        self.assertEqual(still_s["home_id"], "S040")

    def test_bad_number_registry_is_not_silently_swallowed(self):
        self.numbers.write_text("{bad json", encoding="utf-8")
        with self.assertRaises(AttentionServiceProblem) as raised:
            resolve_home_by_registry("S099", installation_file=str(self.install))
        self.assertEqual(raised.exception.code, "attention_agent_numbers_invalid")

    def test_agent_resolve_entry_is_read_only_and_returns_canonical_identity(self):
        import subprocess
        cli = [sys.executable, "-X", "utf8", str(SCRIPTS / "paos.py"),
               "--installation-file", str(self.install), "--json",
               "agent", "resolve", "1001-s001"]
        result = subprocess.run(cli, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["home_id"], "S040")
        self.assertEqual(payload["staff_number"], "S040")
        self.assertEqual(payload["legacy_home_id"], "1001-s001")
        self.assertEqual(payload["project_id"], "1001")
        self.assertEqual(payload["home_kind"], "project_agent")
        self.assertEqual(Path(payload["home_path"]).parts[-2:], ("Workstations", "S040"))

    def test_rooter_resolve_keeps_install_path_and_separates_staff_number(self):
        import subprocess
        rooter_dir = self.base / "Rooter S197"
        rooter_dir.mkdir()
        numbers = json.loads(self.numbers.read_text(encoding="utf-8"))
        numbers["rooter-001"] = "S197"
        self.numbers.write_text(json.dumps(numbers), encoding="utf-8")
        write_installation_descriptor(
            self.install, source_root=str(SCRIPTS.parent), data_root=str(self.data),
            library_roots_config=str(self.base / "library-roots.json"),
            agent_numbers_config=str(self.numbers), rooter_home=str(rooter_dir))
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "paos.py"),
             "--installation-file", str(self.install), "--json",
             "agent", "resolve", "rooter-001"],
            text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["home_id"], "rooter-001")
        self.assertEqual(payload["staff_number"], "S197")
        self.assertEqual(payload["legacy_home_id"], "rooter-001")
        self.assertEqual(Path(payload["home_path"]).resolve(), rooter_dir.resolve())

    def test_rooms_keep_old_cat_seat_after_physical_s_move(self):
        from unittest.mock import patch
        board = Board(self.install)
        replies = [
            {"ok": True, "rooms": [{"id": "old-room"}]},
            {"ok": True, "members": [{"home_id": "1001-s001"}]},
        ]
        with patch.object(board, "cat", side_effect=replies):
            result = board.rooms("1001")
        self.assertTrue(result["ok"])
        self.assertEqual([room["id"] for room in result["rooms"]], ["old-room"])

    def test_rooter_migration_plan_and_execute_preserve_mail_and_before_state(self):
        import subprocess
        old_project = self.base / "migration-project"
        home = old_project / "Workstations/2002-s001"
        (home / "mailbox").mkdir(parents=True)
        (home / "mailbox/old-message.md").write_text("old mail\n", encoding="utf-8")
        write_todo(home / "TODO.md", render_todo(
            home_kind="project_agent", home_id="2002-s001", project_id="2002",
            objective="旧工位", next_action="迁移"))
        (home / "ENTRY.md").write_text("# 2002-s001\n", encoding="utf-8")
        self.registry.register("2002", root_path=str(old_project),
                               coordinator_home_id="2002-s001", homes=["2002-s001"])
        numbers = json.loads(self.numbers.read_text(encoding="utf-8"))
        numbers["2002-s001"] = "S099"
        self.numbers.write_text(json.dumps(numbers), encoding="utf-8")
        command = [sys.executable, "-X", "utf8", str(SCRIPTS / "paos_migrate_home.py"),
                   "--installation-file", str(self.install), "--project", "2002",
                   "--old-home", "2002-s001", "--new-home", "S099"]
        planned = subprocess.run(command, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(planned.returncode, 0, planned.stderr)
        plan = json.loads(planned.stdout)
        self.assertEqual(plan["old_home_id"], "2002-s001")
        self.assertTrue(home.is_dir())
        before = self.base / "before.json"
        executed = subprocess.run(command + ["--execute", "--before-state", str(before)],
                                  text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertFalse(home.exists())
        new_home = old_project / "Workstations/S099"
        self.assertTrue((new_home / "mailbox/old-message.md").is_file())
        self.assertEqual(self.registry.read("2002")["homes"], ["S099"])
        todo = (new_home / "TODO.md").read_text(encoding="utf-8")
        self.assertIn('home_id: "S099"', todo)
        self.assertTrue(before.is_file())
        mail = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "paos.py"),
             "--installation-file", str(self.install), "--json",
             "mail", "list", "2002", "2002-s001"],
            text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(mail.returncode, 0, mail.stderr)
        self.assertGreaterEqual(json.loads(mail.stdout)["count"], 1)

    def test_workstation_allocation_does_not_duplicate_migrated_s_value(self):
        before = load_numbers(self.numbers)
        args = argparse.Namespace(session_id="S040", agent_numbers_file=str(self.numbers))
        self.assertEqual(_allocate_staff_number(args, self.install), "S040")
        self.assertEqual(load_numbers(self.numbers), before)
        fresh = argparse.Namespace(session_id="S100", agent_numbers_file=str(self.numbers))
        self.assertEqual(_allocate_staff_number(fresh, self.install), "S100")
        self.assertEqual(load_numbers(self.numbers)["S100"], "S100")


if __name__ == "__main__":
    unittest.main()
