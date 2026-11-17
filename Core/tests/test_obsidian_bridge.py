"""Obsidian process bridge: same Board request map, no HTTP listener, scoped project."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_board

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE))
from front.paos_obsidian_bridge import handle_request, resolve_context


class ObsidianBridgeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_board.BoardTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.board = self.fixture.board
        self.vault = self.fixture.roots["1001"]
        self.other = self.fixture.roots["2001"]

    def call(self, method, path, body=None, vault=None):
        return handle_request(self.board, {"method": method, "path": path, "body": body},
                              vault_root=vault or self.vault)

    def test_context_matches_exact_project_and_system_roots(self):
        status, context = self.call("GET", "/api/obsidian/context")
        self.assertEqual(status, 200)
        self.assertEqual(context["kind"], "project")
        self.assertEqual(context["project"], "1001")
        source = Path(self.board.installation["source_root"]).resolve()
        status, system = self.call("GET", "/api/obsidian/context", vault=source.parents[2])
        self.assertEqual(status, 200)
        self.assertEqual(system["kind"], "system")
        status, unknown = self.call("GET", "/api/obsidian/context", vault=self.fixture.base / "unknown")
        self.assertEqual(status, 422)
        self.assertEqual(unknown["error_code"], "vault_not_registered")

    def test_project_reads_inject_current_project_and_reject_other_homes(self):
        status, dashboard = self.call("GET", "/api/dashboard")
        self.assertEqual(status, 200)
        self.assertEqual(dashboard["project"], "1001")
        status, other = self.call("GET", "/api/agent/2001-s009")
        self.assertEqual(status, 422)
        self.assertEqual(other["error_code"], "project_scope_mismatch")
        status, mismatch = self.call("GET", "/api/dashboard?project=2001")
        self.assertEqual(status, 422)
        self.assertEqual(mismatch["error_code"], "project_scope_mismatch")

    def test_layout_save_is_current_project_only(self):
        status, saved = self.call("PUT", "/api/layout",
                                  {"layout": {"nodes": {"1001-s001": {"x": 10, "y": 20}},
                                              "viewport": {"x": 1, "y": 2, "zoom": 1}}})
        self.assertEqual(status, 200)
        self.assertTrue((self.vault / ".paos/ui/board.json").is_file())
        status, rejected = self.call("PUT", "/api/layout",
                                     {"project": "2001", "layout": {"nodes": {}}})
        self.assertEqual(status, 422)
        self.assertEqual(rejected["error_code"], "project_scope_mismatch")

    def test_human_mail_uses_existing_writer_and_one_message_identity(self):
        self.board.run_paos = Mock(return_value={"ok": True})
        status, result = self.call("POST", "/api/collaboration", {
            "project": "1001", "mode": "mail", "members": ["1001-s001"],
            "topic": "隔离测试", "body": "读取原件", "message_id": "bridge-mail-001",
            "remind": False,
        })
        self.assertEqual(status, 200)
        self.assertEqual(result["state"], "saved")
        self.assertEqual(result["message_id"], "bridge-mail-001")
        args = self.board.run_paos.call_args.args[0]
        self.assertEqual(args[:3], ["agent", "send", "1001"])
        self.assertIn("--sender-id", args)
        self.assertIn("human", args)
        self.assertIn("bridge-mail-001", args)
        self.assertEqual(self.board.run_paos.call_args.kwargs["input_text"], "读取原件")

    def test_cat_reads_and_room_scope_use_existing_board_calls(self):
        with patch.object(self.board, "cat", return_value={"ok": True, "rooms": []}) as cat:
            status, value = self.call("GET", "/api/cat/rooms")
        self.assertEqual(status, 200)
        self.assertTrue(value["ok"])
        cat.assert_called_once_with(["list"])
        status, rejected = self.call("POST", "/api/room", {
            "title": "隔离房", "members": ["1001-s001", "2001-s009"]})
        self.assertEqual(status, 422)
        self.assertEqual(rejected["error_code"], "project_scope_mismatch")
        status, stream = self.call("GET", "/api/room/room-one/events?after=5")
        self.assertEqual(status, 400)
        self.assertEqual(stream["error_code"], "stream_not_supported")

    def test_standalone_process_reads_one_json_and_writes_one_json(self):
        request = json.dumps({"method": "GET", "path": "/api/obsidian/context"})
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(PACKAGE / "front/paos_obsidian_bridge.py"),
             "--installation-file", str(self.fixture.install), "--vault-root", str(self.vault)],
            input=request, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value["status"], 200)
        self.assertEqual(value["body"]["kind"], "project")
        self.assertEqual(value["body"]["project"], "1001")
        self.assertEqual(result.stderr, "")

    def test_unknown_result_is_not_turned_into_success(self):
        with patch.object(self.board, "send_message", return_value={
                "ok": False, "error_code": "delivery_unknown", "message_submitted": None}):
            status, result = self.call("POST", "/api/room/room-one/message", {
                "body": "测试", "message_id": "bridge-chat-001"})
        self.assertEqual(status, 200)
        self.assertFalse(result["ok"])
        self.assertFalse(result["message_submitted"] is True)


if __name__ == "__main__":
    unittest.main()
