import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "code/personal-agent-os/scripts"
sys.path.insert(0, str(SCRIPTS))
from paos_human_action import confirm
from paos_stage import task_snapshot
from paos_team import propose, read_action, enroll, live_role
from paos_todo import render_todo


class PlanTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.project = self.base / "Project"
        self.homes = {}
        for seat in ("S042", "S063"):
            path = self.project / "Workstations" / seat
            path.mkdir(parents=True)
            self.homes[seat] = {
                "home_kind": "project_agent",
                "home_id": seat,
                "project_id": "3004",
                "home_path": str(path),
                "project_root": str(self.project),
            }
            (path / "TODO.md").write_text(
                render_todo(
                    home_kind="project_agent",
                    home_id=seat,
                    project_id="3004",
                    objective="My existing responsibility",
                    next_action="Continue",
                    tasks=[dict(id="T1", state="doing", title="Organize notes")],
                ),
                encoding="utf8",
            )
        self.plan = self.project / "plan.md"
        self.plan.write_text(
            "# Our plan\n## Scope\nProduce a guide\n## Progress\nDrafting", encoding="utf8"
        )
        got = propose(self.homes["S042"], "S042", "T1", "plan.md#Scope", ["S042", "S063"], "owner")
        self.scope = got["plan"]
        self.role = {
            "home": "S063",
            "role": {"duty": "Review", "arrangement": "Check inputs", "deliverables": "a.md"},
            "approved": False,
            "revision": 1,
        }
        self.team = {
            "plan": self.scope,
            "roles_receipt": "",
            "accepted": None,
            "roles": {"S063": self.role},
        }
        from unittest.mock import Mock

        self.client = Mock()
        self.client.request.return_value = {"team": self.team}
        self.id = "ha-" + "1" * 32

    def test_generic_task_data_or_arbitrary_approved_flag_cannot_issue_a_receipt(self):
        args = {"owner": "S042", "task": "T1", "version": self.scope["version"], "approved": True}
        with patch("paos_human_action._display", return_value=False):
            answer = confirm(
                self.base / "Data", "open-plan", self.id, args, self.homes.__getitem__, self.client
            )
        self.assertEqual(answer["state"], "cancelled")
        self.assertFalse((self.base / "Data" / "human-actions").exists())
        self.client.request.assert_not_called()
        with self.assertRaises(FileNotFoundError):
            read_action(self.base / "Data", self.id)

    def test_approval_binds_reviewed_scope_and_is_not_reprompted_on_replay(self):
        data = self.base / "Data"
        self.plan.write_text(
            "# Our plan\n## Scope\nProduce a guide\n## Progress\nReady", encoding="utf8"
        )
        args = {"owner": "S042", "task": "T1", "version": self.scope["version"]}
        with patch("paos_human_action._display", return_value=True) as display:
            self.assertTrue(
                confirm(data, "open-plan", self.id, args, self.homes.__getitem__, self.client)["ok"]
            )
            self.assertTrue(
                confirm(data, "open-plan", self.id, args, self.homes.__getitem__, self.client)["ok"]
            )
            display.assert_called_once()
        self.assertEqual(read_action(data, self.id)["subject"], self.scope)
        self.plan.write_text("## Scope\nAnother deliverable\n", encoding="utf8")
        with patch("paos_human_action._display") as display:
            with self.assertRaises(ValueError):
                confirm(data, "open-plan", "ha-" + "2" * 32, args, self.homes.__getitem__, self.client)
            display.assert_not_called()

    def test_only_a_released_role_links_to_its_own_task_preserving_current(self):
        home = self.homes["S063"]
        before = (Path(home["home_path"]) / "TODO.md").read_bytes()
        with self.assertRaises(ValueError):
            enroll(home, "S063", "room1", "T1", self.client, self.homes.__getitem__)
        self.assertEqual((Path(home["home_path"]) / "TODO.md").read_bytes(), before)
        self.team["roles_receipt"] = self.id
        self.role["approved"] = True
        answer = enroll(home, "S063", "room1", "T1", self.client, self.homes.__getitem__)
        self.assertEqual(answer["task_id"], "T1")
        _, _, doc, task = task_snapshot(home, "T1")
        self.assertEqual(task["source_refs"], ["cat-role:room1"])
        self.assertEqual(doc["current"]["objective"], "My existing responsibility")
        self.plan.write_text("## Scope\nAltered goal", encoding="utf8")
        with self.assertRaises(ValueError):
            live_role(self.client, "room1", "S063", self.homes.__getitem__)
