"""Physical S-number Home: registry, legacy alias, Board people/agent."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE / "code/personal-agent-os/scripts"
sys.path.insert(0, str(PACKAGE))
sys.path.insert(0, str(SCRIPTS))
from front.paos_front_server import Board
from paos_agent_numbers import staff_number
from paos_attention_service import resolve_home_by_registry
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


if __name__ == "__main__":
    unittest.main()
