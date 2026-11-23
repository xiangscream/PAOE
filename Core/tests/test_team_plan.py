import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "code/personal-agent-os/scripts"
sys.path.insert(0, str(SCRIPTS))
from paos_human_action import confirm
from paos_stage import render, task_snapshot
from paos_team_plan_cli import accept_task
from paos_team import (
    propose,
    read_action,
    enroll,
    live_role,
    read_owner_acceptance,
    record_owner_acceptance,
    decision_subject,
    verify_goal,
)
from paos_todo import TodoProblem, render_todo


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

    def test_owner_acceptance_is_bound_to_the_original_plan_and_readable_deliverables(self):
        data = self.base / "Data"
        self.team.update(roles_receipt=self.id, revision=2)
        evidence = dict(
            task="T1", artifact="guide.md", basis="review.md", remaining="complete", read_to=4
        )
        for name in ("guide.md", "review.md"):
            (self.project / name).write_text(name, encoding="utf8")
        home = self.homes["S042"]
        key = record_owner_acceptance(data, "room1", self.team, evidence, home)
        self.assertEqual(record_owner_acceptance(data, "room1", self.team, evidence, home), key)
        checked = read_owner_acceptance(data, key, self.homes.__getitem__)["subject"]["acceptance"]
        self.assertEqual({k: v for k, v in checked.items() if k != "versions"}, evidence)
        self.assertEqual(set(checked["versions"]), {"basis", "artifact"})
        for name in ("guide.md", "review.md"):
            with self.subTest(name=name):
                original = (self.project / name).read_bytes()
                (self.project / name).write_bytes(b"x" * len(original))
                with self.assertRaisesRegex(ValueError, "内容版本"):
                    read_owner_acceptance(data, key, self.homes.__getitem__)
                (self.project / name).write_bytes(original)
        (self.project / "review.md").rename(self.project / "archived.md")
        with self.assertRaisesRegex(ValueError, "review.md"):
            read_owner_acceptance(data, key, self.homes.__getitem__)
        self.assertEqual(read_owner_acceptance(data, key)["subject"]["acceptance"], checked)

    def test_human_accept_checks_originals_during_confirmation_and_before_first_apply(self):
        home = self.homes["S042"]
        self.team["plan"] = propose(home, "S042", "T1", "plan.md#Scope", ["S042", "S063"],
                                    "human_confirm")["plan"]
        self.team.update(revision=2, roles_receipt=self.id)
        evidence = dict(room="room1", task="T1", artifact="guide.md", basis="review.md",
                        remaining="none", read_to=3)
        for key in ("basis", "artifact"):
            (self.project / evidence[key]).write_bytes(b"first")
        data = self.base / "Data"
        basis = self.project / "review.md"
        with patch("paos_human_action._display", side_effect=lambda *args: basis.write_bytes(b"later")):
            with self.assertRaisesRegex(ValueError, "确认期间"):
                confirm(data, "accept-goal", self.id, evidence, self.homes.__getitem__, self.client)
        self.assertFalse((data / "human-actions").exists())
        subject, _ = decision_subject("accept-goal", evidence, self.homes.__getitem__, self.client)
        verify_goal(subject, subject, self.homes.__getitem__, "human_confirm")
        basis.write_bytes(b"third")
        with self.assertRaisesRegex(ValueError, "内容版本"):
            verify_goal(subject, subject, self.homes.__getitem__, "human_confirm")

    def test_accept_collects_only_the_anchored_current_and_resumes_after_write_failure(self):
        home = self.homes["S042"]
        resolve = self.homes.__getitem__
        path, _, doc, task = task_snapshot(home, "T1")
        doc["current"].update(context_refs=["task:T1", "plan.md"], inflight="awaiting review")
        path.write_text(render(doc), encoding="utf8")
        for name in ("a.md", "b.md"):
            (self.project / name).write_text(name, encoding="utf8")
        self.role["approved"] = True
        self.team.update(revision=2, roles_receipt=self.id)
        args = SimpleNamespace(task="T1", artifact="a.md", basis="b.md", remaining="none",
                               room="r", read_to=1, carry=["S042/T1=review.md"])
        data = self.base / "Data"

        def request(method, route, payload=None):
            if method == "POST":
                read = read_owner_acceptance(data, payload["receipt_id"], resolve)
                self.team["accepted"] = read["subject"]["acceptance"]
            return {"team": self.team}

        self.client.request.side_effect = request
        with patch("paos_team_plan_cli.write_todo", side_effect=OSError("disk is full")):
            with self.assertRaises(TodoProblem) as failure:
                accept_task(home, "S042", args, self.client, resolve, data)
        self.assertTrue(failure.exception.details["room_closed"])
        self.assertEqual(task_snapshot(home, "T1")[3]["state"], "doing")
        result = accept_task(home, "S042", args, self.client, resolve, data)
        self.assertTrue(result["current_updated"])
        _, _, doc, task = task_snapshot(home, "T1")
        self.assertEqual(task["state"], "done")
        self.assertEqual(doc["current"]["context_refs"], ["plan.md"])
        self.assertEqual(doc["current"]["result_refs"], ["a.md", "b.md"])
        self.assertFalse(doc["current"]["inflight"] or doc["current"]["waiting"])
        self.assertNotEqual(doc["current"]["next_action"], "Continue")
        (self.project / "b.md").rename(self.project / "archived-b.md")
        self.assertTrue(accept_task(home, "S042", args, self.client, resolve, data)["replayed"])
        (self.project / "a.md").write_bytes(b"other")
        with self.assertRaisesRegex(ValueError, "内容版本"):
            accept_task(home, "S042", args, self.client, resolve, data)

    def test_unrelated_current_and_other_anchors_survive_acceptance(self):
        from paos_team_plan_cli import finish_current

        _, _, doc, task = task_snapshot(self.homes["S042"], "T1")
        cur = doc["current"]
        cur.update(context_refs=["task:T2"], inflight="Review T2")
        before = dict(cur)
        evidence = dict(artifact="a.md", basis="b.md", remaining="none")
        self.assertFalse(finish_current(cur, task, evidence))
        self.assertEqual(cur, before)
        cur["context_refs"] = ["task:T1", "task:T2"]
        self.assertTrue(finish_current(cur, task, evidence))
        self.assertEqual(cur["context_refs"], ["task:T2"])
        self.assertEqual(cur["inflight"], "Review T2")

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
