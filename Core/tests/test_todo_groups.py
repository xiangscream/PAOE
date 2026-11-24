"""Read-only TODO work-group projection tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code" / "personal-agent-os" / "scripts"))

import test_headless
from paos_todo import render_todo
from paos_todo_groups import project_groups


class TodoGroupUnitTests(unittest.TestCase):
    def test_groups_preserve_order_rooms_and_original_tasks(self):
        tasks = [
            {"id": "T-1", "source_refs": [
                "work-group: PAOE 0.1", "cat-role:room-a/S032"]},
            {"id": "T-2", "source_refs": [
                "cat-room:room-b", "work-group:PAOE 0.1"]},
            {"id": "T-3", "source_refs": ["work-group:Another"]},
            {"id": "T-4", "source_refs": []},
        ]
        groups = project_groups(tasks)
        self.assertEqual([group["name"] for group in groups],
                         ["PAOE 0.1", "Another", None])
        self.assertEqual([task["id"] for task in groups[0]["tasks"]],
                         ["T-1", "T-2"])
        self.assertEqual(groups[0]["rooms"], ["room-a", "room-b"])
        self.assertEqual(groups[1]["rooms"], [])
        self.assertEqual([task["id"] for task in groups[2]["tasks"]], ["T-4"])
        self.assertIs(groups[0]["tasks"][0], tasks[0])

    def test_ambiguous_or_empty_group_labels_fall_back_to_ungrouped(self):
        tasks = [
            {"id": "T-1", "source_refs": [
                "work-group:One", "work-group:Two"]},
            {"id": "T-2", "source_refs": ["work-group:"]},
            {"id": "T-3", "source_refs": ["work-group:One", "work-group:One"]},
        ]
        groups = project_groups(tasks)
        self.assertEqual([group["name"] for group in groups], ["One", None])
        self.assertEqual([task["id"] for task in groups[0]["tasks"]], ["T-3"])
        self.assertEqual([task["id"] for task in groups[1]["tasks"]],
                         ["T-1", "T-2"])

    def test_role_room_requires_exact_room_and_home_shape(self):
        groups = project_groups([
            {"id": "T-1", "source_refs": [
                "cat-role:room-a/S032", "cat-role:room-b",
                "cat-role:/S032", "cat-room:room-c", "cat-room:"]},
        ])
        self.assertEqual(groups[0]["rooms"], ["room-a", "room-c"])


class TodoGroupReadModelTests(unittest.TestCase):
    def setUp(self):
        self.f = test_headless.HeadlessTests(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()

    def _todo(self):
        tasks = [
            {"id": "T-1", "title": "主工作一", "state": "doing",
             "source_refs": ["work-group:PAOE 0.1", "cat-role:room-a/S032"]},
            {"id": "T-2", "title": "主工作二", "state": "doing",
             "source_refs": ["work-group:PAOE 0.1", "cat-room:room-b"]},
            {"id": "T-3", "title": "零散事项", "state": "todo"},
        ]
        todo = render_todo(
            home_kind="project_agent", home_id="3002-s001", project_id="3002",
            objective="读分组", next_action="检查 todo.groups", tasks=tasks)
        (self.f.vault / "Workstations/3002-s001/TODO.md").write_text(
            todo, encoding="utf-8")

    def test_attention_show_exposes_read_only_todo_groups(self):
        self._todo()
        before = (self.f.vault / "Workstations/3002-s001/TODO.md").read_bytes()
        result = self.f.call("attention", "show", "3002", "3002-s001")[1]
        groups = result["todo"]["groups"]
        self.assertEqual([group["name"] for group in groups],
                         ["PAOE 0.1", None])
        self.assertEqual([task["id"] for task in groups[0]["tasks"]],
                         ["T-1", "T-2"])
        self.assertEqual(groups[0]["rooms"], ["room-a", "room-b"])
        self.assertEqual([task["id"] for task in groups[1]["tasks"]], ["T-3"])
        self.assertEqual(
            before,
            (self.f.vault / "Workstations/3002-s001/TODO.md").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
