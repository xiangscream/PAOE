"""CAT page routes use the existing CLI, fixed Human identity and one send."""
import json
import io
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import test_board
from front.paos_front_server import make_server


class CatBoardTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_board.BoardTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.board = self.fixture.board
        self.server = make_server(self.board, port=0)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 3)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.origin = "http://127.0.0.1:" + str(self.server.server_port)

    def call(self, path, payload=None):
        request = Request(self.origin + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        try:
            response = urlopen(request)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_page_and_assets_are_readable_without_cat_or_project_writes(self):
        with patch.object(self.board, "cat", side_effect=AssertionError("static read must not join or send")):
            for path, content_type in (("/cat", "text/html"), ("/cat.css", "text/css"),
                                       ("/cat.mjs", "text/javascript"), ("/cat-state.mjs", "text/javascript"),
                                       ("/cat-vendor/vue.mjs", "text/javascript"), ("/cat-vendor/daisyui.css", "text/css"),
                                       ("/cat-content.mjs", "text/javascript"), ("/cat-components.mjs", "text/javascript"),
                                       ("/vendor/markdown-it-15.0.3.mjs", "text/javascript")):
                with self.subTest(path=path), urlopen(self.origin + path) as response:
                    self.assertIn(content_type, response.headers["Content-Type"])
                    self.assertTrue(response.read())
        self.assertEqual(self.call("/cat/../installation.json")[0], 404)

    def test_rooms_roster_and_incremental_messages_forward_only_their_read(self):
        with patch.object(self.board, "cat", return_value={"ok": True, "rooms": []}) as call:
            self.assertTrue(self.call("/api/cat/rooms")[1]["ok"])
            call.assert_called_once_with(["list"])
        with patch.object(self.board, "cat", return_value={"ok": True, "messages": []}) as call:
            self.call("/api/room/room-one/messages?after=7")
            call.assert_called_once_with(["read", "room-one", "--after", "7"])
        with patch.object(self.board, "cat", return_value={"ok": True, "members": []}) as call:
            self.call("/api/room/room-one/members")
            call.assert_called_once_with(["members", "room-one"])

    def test_human_reply_uses_one_existing_join_and_one_original_send(self):
        replies = [
            {"ok": True, "member": {"home_id": "human", "state": "participant"}},
            {"ok": True, "accepted": True, "dispatch": "queued", "message": {"id": "same-id"}},
        ]
        with patch.object(self.board, "cat", side_effect=replies) as call:
            status, receipt = self.call("/api/room/room-one/message",
                {"body": "回复原讨论", "message_id": "same-id", "reply_to": "original"})
        self.assertEqual(status, 200)
        self.assertEqual(receipt["dispatch"], "queued")
        self.assertEqual(call.call_args_list[0].args[0], ["join", "room-one", "--home", "human", "--label", "Human"])
        self.assertEqual(call.call_args_list[1].args[0],
            ["send", "room-one", "--from", "human", "--body", "回复原讨论",
             "--message-id", "same-id", "--reply-to", "original"])

    def test_page_cannot_choose_an_agent_signature(self):
        with patch.object(self.board, "cat") as call:
            status, value = self.call("/api/room/room-one/message",
                {"sender_id": "1001-s001", "body": "wrong signature"})
        self.assertEqual(status, 422)
        self.assertEqual(value["error_code"], "human_sender_only")
        call.assert_not_called()

    def test_people_and_new_room_use_registered_team_labels_without_home_runtime_reads(self):
        team = self.fixture.roots["1001"] / "TEAM.md"
        team.write_text("# 团队\n## 当前成员\n### 1001-s001\n- 职责/专长：产品定义\n", encoding="utf-8")
        before = team.read_bytes()
        with patch.object(self.board, "agent", side_effect=AssertionError("no runtime reads")):
            status, value = self.call("/api/cat/people")
        self.assertEqual(status, 200)
        self.assertEqual({p["id"] for p in value["people"]}, {"1001-s001", "1001-s002", "2001-s009"})
        self.assertEqual(value["people"][0]["name"], "1001-s001 · 产品定义")
        self.assertEqual(team.read_bytes(), before)
        with patch.object(self.board, "cat", side_effect=[
                {"ok": True, "room": {"id": "room-new"}}, {"ok": True}, {"ok": True}]) as call:
            status, receipt = self.call("/api/room", {"title": "讨论", "members": ["1001-s001", "1001-s002"]})
        self.assertEqual(receipt, {"ok": True, "room_id": "room-new"})
        self.assertEqual(call.call_args_list[1].args[0],
                         ["join", "room-new", "--home", "1001-s001", "--label", "1001-s001 · 产品定义"])

    def test_event_proxy_keeps_cursor_and_stream_bytes_without_cli_or_writes(self):
        self.board.cat_url = "http://127.0.0.1:12345"
        frame = b'id: 9\nevent: room\ndata: {"messages":[]}\n\n'
        with patch("front.paos_front_server.urlopen", return_value=io.BytesIO(frame)) as upstream, \
                patch.object(self.board, "cat", side_effect=AssertionError("SSE is read-only")):
            request = Request(self.origin + "/api/room/room-one/events?after=3", headers={"Last-Event-ID": "8"})
            with urlopen(request) as response:
                self.assertIn("text/event-stream", response.headers["Content-Type"])
                self.assertEqual(response.read(), frame)
        request = upstream.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:12345/api/rooms/room-one/events?after=3")
        self.assertEqual(request.get_header("Last-event-id"), "8")

    def test_invalid_cursor_does_not_read_or_write_cat(self):
        with patch.object(self.board, "cat") as call:
            for cursor in ("-1", "not-a-sequence"):
                status, value = self.call("/api/room/room-one/messages?after=" + cursor)
                self.assertEqual(status, 422)
                self.assertEqual(value["error_code"], "invalid_cursor")
        call.assert_not_called()

    def test_join_failure_does_not_send_and_paused_human_is_not_reactivated(self):
        with patch.object(self.board, "cat", return_value={"ok": False, "error_code": "unreachable"}) as call:
            _, value = self.call("/api/room/room-one/message", {"body": "kept"})
        self.assertFalse(value["message_submitted"])
        self.assertEqual(call.call_count, 1)
        replies = [
            {"ok": True, "member": {"home_id": "human", "state": "observer"}},
            {"ok": False, "status": 409, "error_code": "seat_not_participating"},
        ]
        with patch.object(self.board, "cat", side_effect=replies) as call:
            _, value = self.call("/api/room/room-one/message", {"body": "kept", "message_id": "paused"})
        self.assertFalse(value["ok"])
        self.assertEqual(value["status"], 409)
        self.assertEqual([c.args[0][0] for c in call.call_args_list], ["join", "send"])


if __name__ == "__main__":
    unittest.main()
