"""CAT callers share member, recipient and task-room contracts."""
import argparse
import json
import io
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import test_board
from front.paos_front_server import make_server
from paos_cat_cli import add_cat_parser, execute_cat


class CatCliTests(unittest.TestCase):
    def test_post_paths_keep_the_requested_reminder_scope(self):
        parser = argparse.ArgumentParser()
        add_cat_parser(parser.add_subparsers(required=True))
        for verb, flags, fields in (
            ("send", [], {"target_ids": [], "reply_to": None}),
            ("send", ["--notify"], {"target_ids": [], "notify": True, "reply_to": None}),
            ("send", ["--no-notify"], {"target_ids": [], "notify": False, "reply_to": None}),
            ("send", ["--mention", "S029", "--mention", "S040"],
             {"target_ids": ["S029", "S040"], "reply_to": None}),
            ("send", ["--mention", "S029", "--invite"],
             {"target_ids": ["S029"], "reply_to": None, "invite": True}),
            ("invite", ["--to", "S069"], {"target_ids": ["S069"], "invite": True}),
        ):
            with self.subTest(verb=verb, flags=flags):
                args = parser.parse_args([
                    "cat", verb, "room-one", "--from", "S010", "--body", "question",
                    "--message-id", "original", *flags,
                ])
                client = Mock()
                execute_cat(args, client, lambda value, *_, **__: value)
                client.request.assert_called_once_with("POST", "/api/rooms/room-one/messages", {
                    "message_id": "original", "sender_id": "S010", "body": "question", **fields,
                })

    def test_room_recovery_progress_preview_and_close_use_the_backend_contract(self):
        parser = argparse.ArgumentParser()
        add_cat_parser(parser.add_subparsers(required=True))
        cases = [
            (["list", "--home", "S040"], "GET", "/api/rooms?home_id=S040", None),
            (["preview", "room-one", "--from", "human", "--mention", "S029", "--mention", "S040"],
             "POST", "/api/rooms/room-one/message-preview",
             {"sender_id": "human", "target_ids": ["S029", "S040"], "invite": False}),
            (["preview", "room-one", "--from", "S010", "--notify"],
             "POST", "/api/rooms/room-one/message-preview",
             {"sender_id": "S010", "target_ids": [], "invite": False, "notify": True}),
            (["progress", "room-one", "--home", "S040", "--presence", "offline", "--read-to", "7"],
             "POST", "/api/rooms/room-one/members/S040/progress", {"presence": "offline", "last_read_seq": 7}),
            (["close", "room-one", "--from", "S040", "--action", "request"],
             "POST", "/api/rooms/room-one/close", {"actor_id": "S040", "action": "request"}),
            (["close", "room-one", "--from", "human", "--action", "confirm"],
             "POST", "/api/rooms/room-one/close", {"actor_id": "human", "action": "confirm"}),
            (["create", "--title", "真实任务", "--from", "S010", "--owner", "S040",
              "--close-policy", "human_confirm", "--project-id", "3002", "--index-path", "Works/task/INDEX.md"],
             "POST", "/api/rooms", {"title": "真实任务", "created_by": "S010", "owner_id": "S040",
              "close_policy": "human_confirm", "task_context": {"project_id": "3002", "index_path": "Works/task/INDEX.md"}}),
        ]
        for flags, method, path, payload in cases:
            with self.subTest(flags=flags):
                client = Mock()
                execute_cat(parser.parse_args(["cat", *flags]), client, lambda v, *_a, **_k: v)
                expected = (method, path) if payload is None else (method, path, payload)
                client.request.assert_called_once_with(*expected)

    def test_room_summary_keeps_the_index_without_dumping_message_history(self):
        parser = argparse.ArgumentParser()
        add_cat_parser(parser.add_subparsers(required=True))
        context = {"project_id": "3002", "index_path": "Works/task/INDEX.md"}
        client = Mock()
        client.request.return_value = {"ok": True, "room": {
            "id": "room-one", "task_context": context, "messages": [{"seq": 8, "body": "large history"}],
            "owner_id": "S040", "close_policy": "human_confirm"}}
        result = execute_cat(parser.parse_args(["cat", "show", "room-one"]), client, None)
        self.assertEqual(result["summary"]["task_context"], context)
        self.assertEqual(result["summary"]["counts"]["last_seq"], 8)
        self.assertNotIn("messages", result["summary"])


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
            for path, content_type in (("/", "text/html"), ("/cat", "text/html"), ("/cat/", "text/html"),
                                       ("/assets/app.js", "javascript"), ("/assets/app.css", "text/css")):
                with self.subTest(path=path), urlopen(self.origin + path) as response:
                    self.assertIn(content_type, response.headers["Content-Type"])
                    self.assertTrue(response.read())
        self.assertEqual(self.call("/cat/../installation.json")[0], 404)
        self.assertEqual(self.call("/assets/%2e%2e/%2e%2e/installation.json")[0], 404)

    def test_missing_ui_does_not_block_file_api_or_create_files(self):
        (self.fixture.front_dist / "index.html").unlink()
        status, missing = self.call("/cat")
        self.assertEqual(status, 503)
        self.assertEqual(missing["error_code"], "frontend_assets_missing")
        self.assertTrue(self.call("/api/dashboard?project=1001")[1]["ok"])
        self.assertFalse((self.fixture.front_dist / "index.html").exists())

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

    def test_related_rooms_use_registered_members_and_never_load_or_write_messages(self):
        rooms = [{"id": "one"}, {"id": "two"}]
        replies = [{"ok": True, "rooms": rooms},
                   {"ok": True, "members": [{"home_id": "1001-s001"}, {"home_id": "human"}]},
                   {"ok": True, "members": [{"home_id": "2001-s009"}]}]
        with patch.object(self.board, "cat", side_effect=replies) as call:
            status, value = self.call("/api/cat/rooms?project=1001")
        self.assertEqual(status, 200)
        self.assertEqual(value["rooms"], [rooms[0]])
        self.assertEqual([c.args[0] for c in call.call_args_list],
                         [["list"], ["members", "one"], ["members", "two"]])
        with patch.object(self.board, "cat", side_effect=[replies[0], {"ok": False, "error_code": "unreachable"}]):
            self.assertFalse(self.call("/api/cat/rooms?project=1001")[1]["ok"])

    def test_invalid_collaboration_status_input_does_not_call_cli(self):
        with patch.object(self.board, "cat") as cat, patch.object(self.board, "run_paos") as cli:
            status, value = self.call("/api/collaboration?project=1001&mode=invalid&message_id=original")
            self.assertEqual(status, 422)
            self.assertEqual(value["error_code"], "collaboration_mode_invalid")
            self.assertEqual(self.call("/api/collaboration?project=3002&mode=chat&message_id=original")[0], 422)
        cat.assert_not_called()
        cli.assert_not_called()

    def test_human_reply_uses_one_existing_join_and_one_original_send(self):
        for fields, flag, dispatch in (
            ({}, None, "queued"),
            ({"notify": False}, "--no-notify", "skipped"),
            ({"notify": True}, "--notify", "queued"),
        ):
            with self.subTest(flag=flag):
                replies = [
                    {"ok": True, "member": {"home_id": "human", "state": "participant"}},
                    {"ok": True, "accepted": True, "dispatch": dispatch, "message": {"id": "same-id"}},
                ]
                with patch.object(self.board, "cat", side_effect=replies) as call:
                    status, receipt = self.call("/api/room/room-one/message", {
                        "body": "回复原讨论", "message_id": "same-id", "reply_to": "original", **fields,
                    })
                self.assertEqual(status, 200)
                self.assertEqual(receipt["dispatch"], dispatch)
                self.assertEqual(call.call_args_list[0].args[0],
                    ["join", "room-one", "--home", "human", "--label", "Human"])
                self.assertEqual(call.call_args_list[1].args[0],
                    ["send", "room-one", "--from", "human", "--body", "-",
                     "--message-id", "same-id", "--reply-to", "original"] + ([flag] if flag else []))
                self.assertEqual(call.call_args_list[1].kwargs["input_text"], "回复原讨论")

    def test_recipient_preview_is_read_only_and_selected_send_keeps_the_same_targets(self):
        targets = ["S029", "S040"]
        with patch.object(self.board, "cat", return_value={
                "ok": True, "recipient_mode": "selected", "recipients": targets}) as call:
            status, preview = self.call("/api/room/room-one/message-preview", {"target_ids": targets})
        self.assertEqual(status, 200)
        self.assertEqual(preview["recipients"], targets)
        call.assert_called_once_with(["preview", "room-one", "--from", "human",
                                      "--mention", "S029", "--mention", "S040"])
        with patch.object(self.board, "cat", side_effect=[{"ok": True}, {"ok": True, "accepted": True}]) as call:
            self.call("/api/room/room-one/message", {"target_ids": targets, "body": "@不解析正文", "message_id": "selected"})
        self.assertEqual(call.call_args_list[-1].args[0], [
            "send", "room-one", "--from", "human", "--body", "-", "--message-id", "selected",
            "--mention", "S029", "--mention", "S040"])
        self.assertEqual(call.call_args_list[-1].kwargs["input_text"], "@不解析正文")

    def test_invitation_keeps_join_of_targets_and_message_in_the_backend_transaction(self):
        for suffix, extra in (("invite", {}), ("message", {"invite": True})):
            with self.subTest(suffix=suffix), patch.object(
                    self.board, "cat", side_effect=[{"ok": True}, {"ok": True}]) as call:
                self.call("/api/room/room-one/" + suffix, {"target_ids": ["S069", "S040"],
                    "body": "请一起讨论", "message_id": "invited", **extra})
            self.assertEqual(call.call_count, 2)
            self.assertEqual(call.call_args_list[-1].args[0], ["send", "room-one", "--from", "human", "--body", "-",
                "--message-id", "invited", "--invite", "--mention", "S069", "--mention", "S040"])

    def test_invalid_selected_targets_do_not_join_or_send(self):
        with patch.object(self.board, "cat") as cat:
            for targets in ("S040", [4], [""]):
                status, value = self.call("/api/room/room-one/message", {"body": "kept", "target_ids": targets})
                self.assertEqual(status, 422)
                self.assertEqual(value["error_code"], "targets_invalid")
        cat.assert_not_called()

    def test_progress_and_close_forward_explicit_human_actions(self):
        with patch.object(self.board, "cat", return_value={"ok": True}) as cat:
            self.call("/api/room/room-one/progress", {"last_read_seq": 7})
            self.assertEqual(cat.call_args.args[0], ["progress", "room-one", "--home", "human", "--read-to", "7"])
            self.call("/api/room/room-one/close", {"action": "confirm"})
            self.assertEqual(cat.call_args.args[0], ["close", "room-one", "--from", "human", "--action", "confirm"])
        with patch.object(self.board, "cat") as cat:
            self.assertEqual(self.call("/api/room/room-one/progress", {"last_read_seq": True})[0], 422)
            self.assertEqual(self.call("/api/room/room-one/progress", {"home_id": "S040", "presence": "online"})[0], 422)
        cat.assert_not_called()

    def test_page_cannot_choose_an_agent_signature(self):
        with patch.object(self.board, "cat") as call:
            status, value = self.call("/api/room/room-one/message",
                {"sender_id": "1001-s001", "body": "wrong signature"})
        self.assertEqual(status, 422)
        self.assertEqual(value["error_code"], "human_sender_only")
        call.assert_not_called()

    def test_people_and_new_room_use_registered_team_labels_without_home_runtime_reads(self):
        numbers = self.fixture.base / "AGENT-NUMBERS.json"
        numbers.write_text(json.dumps({"1001-s001": "S040", "1001-s002": "S063", "2001-s009": "S009"}), encoding="utf-8")
        installation = json.loads(self.fixture.install.read_text(encoding="utf-8"))
        installation["agent_numbers_config"] = str(numbers)
        self.fixture.install.write_text(json.dumps(installation), encoding="utf-8")
        self.board.installation["agent_numbers_config"] = str(numbers)
        team = self.fixture.roots["1001"] / "TEAM.md"
        team.write_text("# 团队\n## 当前成员\n### S040\n- 职责/专长：产品定义\n", encoding="utf-8")
        before = team.read_bytes()
        with patch.object(self.board, "agent", side_effect=AssertionError("no runtime reads")):
            status, value = self.call("/api/cat/people")
        self.assertEqual(status, 200)
        self.assertEqual({p["id"] for p in value["people"]}, {"1001-s001", "1001-s002", "2001-s009"})
        self.assertEqual(value["people"][0]["name"], "S040 · 产品定义")
        self.assertEqual(team.read_bytes(), before)
        with patch.object(self.board, "cat", side_effect=[
                {"ok": True, "room": {"id": "room-new"}}, {"ok": True}, {"ok": True}]) as call:
            status, receipt = self.call("/api/room", {"title": "讨论", "members": ["1001-s001", "1001-s002"]})
        self.assertEqual(receipt, {"ok": True, "room_id": "room-new"})
        self.assertEqual(call.call_args_list[1].args[0],
                         ["join", "room-new", "--home", "1001-s001", "--label", "S040 · 产品定义"])

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

    def test_static_assets_ignore_a_host_that_maps_js_to_text_plain(self):
        """Regression: Windows may register .js as text/plain in its MIME database."""
        with patch("front.paos_front_server.mimetypes.guess_type",
                   return_value=("text/plain", None)):
            with urlopen(self.origin + "/assets/app.js") as response:
                self.assertIn("javascript", response.headers["Content-Type"])
                self.assertTrue(response.read())
            with urlopen(self.origin + "/assets/app.css") as response:
                self.assertIn("text/css", response.headers["Content-Type"])
                self.assertTrue(response.read())

if __name__ == "__main__":
    unittest.main()
