"""A conversation/UI decision is attributable, versioned, and cannot approve by omission."""
import copy
import unittest
from unittest.mock import patch

import test_team_plan as plan_fixtures
from paos_human_action import confirm, review
from paos_team import propose, read_action, receipt_path


class DecisionTests(unittest.TestCase):
    setUp = plan_fixtures.PlanTests.setUp

    def choice(self, action, payload, *, choice="approve", channel="conversation"):
        seen = review(action, payload, self.homes.__getitem__, self.client)
        return {"choice": choice, "channel": channel, "recorded_by": "S042",
                "source_ref": "codex://original-thread/message/original-decision",
                "quote": "通过本版，继续。", "subject": seen["subject"]}

    def test_one_conversation_decision_applies_and_replays_without_any_dialog(self):
        args = {"owner": "S042", "task": "T1", "version": self.scope["version"]}
        decision = self.choice("open-plan", args)
        data = self.base / "Data"
        with patch("paos_human_action._display", side_effect=AssertionError("second confirmation")):
            first = confirm(data, "open-plan", self.id, args, self.homes.__getitem__, self.client, decision=decision)
            again = confirm(data, "open-plan", self.id, args, self.homes.__getitem__, self.client, decision=decision)
        self.assertFalse(first["replayed"])
        self.assertTrue(again["replayed"])
        proof = read_action(data, self.id)
        self.assertEqual(proof["channel"], "conversation-human-decision")
        self.assertEqual(proof["decision"]["source_ref"], decision["source_ref"])
        self.assertEqual(proof["decision"]["quote"], decision["quote"])
        self.assertEqual(len(list((data / "human-actions").glob("ha-*.json"))), 1)
        with self.assertRaises(ValueError):
            confirm(data, "open-plan", self.id, args, self.homes.__getitem__, self.client,
                    decision={**decision, "quote": "different decision"})

    def test_changed_plan_cannot_use_earlier_conversation_approval(self):
        args = {"owner": "S042", "task": "T1", "version": self.scope["version"]}
        decision = self.choice("open-plan", args)
        self.plan.write_text("## Scope\nDifferent scope", encoding="utf-8")
        self.client.reset_mock()
        with self.assertRaises(ValueError):
            confirm(self.base / "Data", "open-plan", self.id, args,
                    self.homes.__getitem__, self.client, decision=decision)
        self.assertFalse(receipt_path(self.base / "Data", self.id).exists())
        self.client.request.assert_not_called()

    def test_each_nonapproval_is_recorded_without_any_business_action_and_cannot_authorize_cat(self):
        for n, (choice, state) in enumerate((("reject", "rejected"), ("revise", "changes_requested"), ("defer", "deferred"))):
            for action in ("open-plan", "approve-roles", "save-role", "accept-goal"):
                with self.subTest(choice=choice, action=action):
                    ident = "ha-" + format(n * 4 + ["open-plan", "approve-roles", "save-role", "accept-goal"].index(action), "032x")
                    payload = {"owner": "S042", "room": "room-one", "task": "T1"}
                    decision = {"choice": choice, "channel": "conversation", "recorded_by": "S042",
                                "source_ref": "chat://original/message", "quote": "暂不通过",
                                "subject": {"owner": "S042", "task": "T1"}}
                    self.client.reset_mock()
                    result = confirm(self.base / "Data", action, ident, payload,
                                     self.homes.__getitem__, self.client, decision=decision)
                    self.assertEqual((result["state"], result["applied"]), (state, None))
                    self.client.request.assert_not_called()
                    self.assertEqual(read_action(self.base / "Data", ident, require_approval=False)["decision"]["choice"], choice)
                    with self.assertRaises(ValueError):
                        read_action(self.base / "Data", ident)
                    self.assertTrue(confirm(self.base / "Data", action, ident, payload,
                                            self.homes.__getitem__, self.client, decision=decision)["replayed"])

    def test_all_four_approvals_share_exact_subject_and_never_open_a_dialog(self):
        self.scope = propose(self.homes["S042"], "S042", "T1", "plan.md#Scope",
                             ["S042", "S063"], "human_confirm")["plan"]
        self.team.update(plan=self.scope, revision=2, roles_receipt=self.id)
        self.team["roles"]["S042"] = {**copy.deepcopy(self.role), "home": "S042"}
        for name in ("guide.md", "review.md"):
            (self.project / name).write_text(name, encoding="utf-8")
        actions = [
            ("open-plan", {"owner": "S042", "task": "T1", "version": self.scope["version"]}),
            ("approve-roles", {"room": "room-one", "expected_revision": 2}),
            ("save-role", {"room": "room-one", "home": "S063", "expected_revision": 1,
                           "role": {"duty": "Review", "arrangement": "Read inputs", "deliverables": "review.md"}}),
            ("accept-goal", {"room": "room-one", "task": "T1", "artifact": "guide.md",
                             "basis": "review.md", "remaining": "none", "read_to": 4}),
        ]
        for n, (action, payload) in enumerate(actions):
            with self.subTest(action=action):
                decision = self.choice(action, payload, channel="ui" if n % 2 else "conversation")
                with patch("paos_human_action._display", side_effect=AssertionError("unexpected dialog")):
                    out = confirm(self.base / "Data", action, "ha-" + format(n + 20, "032x"), payload,
                                  self.homes.__getitem__, self.client, decision=decision)
                self.assertTrue(out["ok"])
                self.assertEqual(read_action(self.base / "Data", out["receipt_id"])["subject"], decision["subject"])

    def test_missing_or_ambiguous_decision_is_not_approval(self):
        args = {"owner": "S042", "task": "T1", "version": self.scope["version"]}
        valid = self.choice("open-plan", args)
        for bad in ({}, {**valid, "choice": ""}, {**valid, "choice": []},
                    {**valid, "source_ref": ""}, {**valid, "quote": ""}, {**valid, "subject": {}}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                confirm(self.base / "Data", "open-plan", self.id, args,
                        self.homes.__getitem__, self.client, decision=bad)
        self.assertFalse(receipt_path(self.base / "Data", self.id).exists())


if __name__ == "__main__":
    unittest.main()
