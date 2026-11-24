"""The web and Obsidian team surfaces use the same Core decisions."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

import test_board

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from front.paos_front_server import dispatch_request
from front.paos_obsidian_bridge import handle_request


class TeamBoardTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_board.BoardTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.board = self.fixture.board
        self.board.cat_url = "http://127.0.0.1:18871"
        self.ticket = "ha-" + "7" * 32

    def plugin(self, method, path, body=None):
        return handle_request(self.board, {"method": method, "path": path, "body": body},
                              vault_root=self.fixture.roots["1001"])

    def test_plan_and_room_use_original_core_views(self):
        plan = {"ok": True, "plan": {"project": "1001", "version": "reviewed"}, "body": "原计划"}
        self.board.run_paos = Mock(return_value=plan)
        self.assertEqual(self.plugin("GET", "/api/team-plan?owner=1001-s001&task=T-001"), (200, plan))
        self.board.run_paos.assert_called_once_with(["team-plan", "plan", "1001-s001", "--task", "T-001"])
        members = {"ok": True, "room": "r", "team": {"plan": {"project": "1001"}},
                   "cards": {"1001-s001": {"task": {"id": "T-001", "artifact": "result.md"}}}}
        self.board.run_paos.return_value = members
        self.assertEqual(dispatch_request(self.board, "GET", "/api/room/r/team"), (200, members))
        self.assertEqual(self.plugin("GET", "/api/room/r/team"), (200, members))
        self.board.run_paos.assert_called_with(["team-plan", "members", "--room", "r",
                                                "--cat-url", self.board.cat_url])

    def test_only_ordinary_room_means_no_panel(self):
        self.board.run_paos = Mock(return_value={"ok": False, "error_code": "not_dedicated_room"})
        self.assertEqual(self.plugin("GET", "/api/room/r/team"),
                         (200, {"ok": True, "room": "r", "team": None, "cards": {}}))
        unavailable = {"ok": False, "error_code": "unreachable", "error": "CAT unavailable"}
        self.board.run_paos.return_value = unavailable
        self.assertEqual(self.plugin("GET", "/api/room/r/team"), (200, unavailable))

    def test_plugin_rejects_other_project_before_opening_a_confirmation(self):
        self.board.run_paos = Mock(return_value={"ok": True, "team": {"plan": {"project": "2001"}}})
        self.assertEqual(self.plugin("GET", "/api/room/other/team")[1]["error_code"], "project_scope_mismatch")
        self.board.room = Mock(return_value={"ok": True, "task_context": {"project_id": "2001"}})
        self.board.run_paos.reset_mock()
        for action, subject in (("open-plan", {"owner": "2001-s009", "task": "T-001", "version": "v"}),
                                ("approve-roles", {"room": "other", "expected_revision": 5})):
            with self.subTest(action=action):
                status, out = self.plugin("POST", "/api/team/confirm",
                    {"action": action, "receipt_id": self.ticket, "input": subject})
                self.assertEqual((status, out["error_code"]), (422, "project_scope_mismatch"))
        self.board.run_paos.assert_not_called()

    def test_confirm_only_sends_typed_input_and_preserves_core_outcomes(self):
        self.board.room = Mock(return_value={"ok": True, "task_context": {"project_id": "1001"}})
        self.board.run_paos = Mock()
        for action, subject in (
            ("open-plan", {"owner": "1001-s001", "task": "T-001", "version": "v"}),
            ("approve-roles", {"room": "r", "expected_revision": 5}),
            ("save-role", {"room": "r", "home": "1001-s001", "expected_revision": 5,
                           "role": {"duty": "核原件", "arrangement": "本周核查", "deliverables": "result.md"}}),
            ("accept-goal", {"room": "r", "task": "T-001", "artifact": "result.md",
                             "basis": "review.md", "remaining": "无", "read_to": 8}),
        ):
            with self.subTest(action=action):
                result = {"ok": True, "state": "cancelled"} if action == "save-role" else {
                    "ok": True, "receipt_id": self.ticket, "applied": {"room_id": "r"}}
                self.board.run_paos.return_value = result
                payload = {"action": action, "receipt_id": self.ticket, "input": subject}
                self.assertEqual(self.plugin("POST", "/api/team/confirm", payload), (200, result))
                args, kwargs = self.board.run_paos.call_args
                self.assertEqual(args[0], ["team-plan", "confirm", action, "--id", self.ticket,
                                          "--input", "-", "--cat-url", self.board.cat_url])
                self.assertEqual(json.loads(kwargs["input_text"]), subject)
                self.assertIsNone(kwargs["timeout"])
        self.board.run_paos.reset_mock()
        bad = {"action": "task-accept", "receipt_id": self.ticket, "input": {}}
        self.assertEqual(dispatch_request(self.board, "POST", "/api/team/confirm", bad)[1]["error_code"],
                         "team_action_unknown")
        self.board.run_paos.assert_not_called()
