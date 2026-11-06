"""Optional board against real disposable v4 Homes; no production or models."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE))
from front.paos_front_server import Board, BoardProblem, make_server
from paos_installation import write_installation_descriptor
from paos_library import ensure_skill_library, ensure_workflow_library, register_library_roots
from paos_notice import handle_notice, list_notices
from paos_registry import ProjectRegistry, RegistryProblem
from paos_todo import render_todo, write_todo


class BoardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="portable-board-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve() / "中文 空格工作区"
        self.base.mkdir()
        self.install = self.base / "installation.json"
        self.libs = self.base / "library-roots.json"
        workflow, skill = self.base / "workflow", self.base / "skill"
        ensure_workflow_library(workflow)
        ensure_skill_library(skill)
        (workflow / "Guides" / "working.md").write_text(
            "---\nschema: paos-workflow/v1\nid: guide-working\ntitle: 工作方法\nstatus: active\n---\n# 方法\n",
            encoding="utf-8")
        register_library_roots(self.libs, workflow_root=workflow, skill_root=skill)
        write_installation_descriptor(self.install,
                                      source_root=str(PACKAGE / "code/personal-agent-os"),
                                      data_root=str(self.base / "data"), library_roots_config=str(self.libs))
        self.registry = ProjectRegistry(self.install)
        self.roots = {}
        for project, homes in (("1001", ["1001-s001", "1001-s002"]), ("2001", ["2001-s009"])):
            root = self.base / f"项目-{project}"
            root.mkdir()
            self.roots[project] = root
            (root / "INDEX.md").write_text(f"# 项目 {project}\n唯一口径在本目录。", encoding="utf-8")
            self.registry.register(project, root_path=str(root), coordinator_home_id=homes[0], homes=homes)
            for home_id in homes:
                home = root / "Workstations" / home_id
                (home / "mailbox").mkdir(parents=True)
                (home / "notices").mkdir()
                (home / "ENTRY.md").write_text("# 从本人工位恢复", encoding="utf-8")
                write_todo(home / "TODO.md", render_todo(
                    home_kind="project_agent", home_id=home_id, project_id=project,
                    objective=f"维护项目 {project}", next_action="读取已交原件",
                    tasks=[{"id": "T-001", "title": "接续原件", "state": "doing"}]))
        self.board = Board(self.install)

    def test_v4_and_registered_project_not_old_machine_defaults(self):
        with patch.dict(os.environ, {"PAOS_INSTALLATION_FILE": "missing-old-install.json",
                                     "PAOS_BASE_URL": "not a service"}):
            result = self.board.dashboard()
        self.assertEqual(result["project"], "1001")
        self.assertEqual([a["id"] for a in result["agents"]], ["1001-s001", "1001-s002"])
        self.assertEqual(result["agents"][0]["objective"], "维护项目 1001")
        self.assertEqual(result["agents"][0]["tasks"]["doing"], 1)
        self.assertEqual(result["cat"]["error_code"], "cat_not_configured")
        self.assertEqual(result["examples"]["workflow"][0]["id"], "guide-working")
        other = self.board.dashboard("2001")
        self.assertEqual([a["id"] for a in other["agents"]], ["2001-s009"])
        self.assertIn("项目 2001", other["index"])
        with self.assertRaises(RegistryProblem):
            self.board.dashboard("3002")

    def test_real_cli_hint_delivers_once_and_notice_handling_is_projected(self):
        example = self.board.examples()["workflow"][0]
        result = self.board.hint("1001-s002", example)
        self.assertTrue(result["ok"], result)
        home = self.roots["1001"] / "Workstations/1001-s002"
        notices = list_notices(home)
        self.assertEqual(notices["pending_count"], 1)
        self.assertEqual(len(list((home / "mailbox").glob("*.md"))), 1)
        handle_notice(home_path=home, notice_id=notices["items"][0]["notice_id"], resolution="已采纳为参考")
        # The original Notice still declares pending; the formal reader merges its handled sidecar.
        self.assertIn('state: "pending"', next((home / "notices").glob("*.md")).read_text(encoding="utf-8"))
        self.assertEqual(self.board.agent("1001-s002")["pending_notices"], 0)

    def test_invalid_home_is_visible_without_hiding_other_agents(self):
        home = self.roots["1001"] / "Workstations/1001-s002"
        (home / "TODO.md").write_text("old v3 or broken original", encoding="utf-8")
        rows = self.board.dashboard("1001")["agents"]
        self.assertTrue(rows[0]["ok"])
        self.assertFalse(rows[1]["ok"])
        self.assertIn("error_code", rows[1])
        self.assertNotIn("pending_notices", rows[1])

    def test_other_home_todo_cannot_be_displayed_as_this_agent(self):
        home = self.roots["1001"] / "Workstations/1001-s002"
        (home / "TODO.md").write_text(render_todo(home_kind="project_agent", home_id="2001-s009",
                                                  project_id="2001", objective="别人的责任", next_action="接续"), encoding="utf-8")
        with self.assertRaises(BoardProblem) as raised:
            self.board.agent("1001-s002")
        self.assertEqual(raised.exception.code, "todo_identity_mismatch")

    def test_read_side_does_not_require_cat_or_core_network(self):
        with patch("socket.create_connection", side_effect=AssertionError("network not allowed")):
            self.assertTrue(self.board.dashboard()["ok"])
        self.assertEqual(self.board.create_room("讨论", ["1001-s001", "1001-s002"])["error_code"],
                         "cat_not_configured")

    def test_cli_timeout_keeps_result_unknown_and_does_not_repeat(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("paos", 90)) as run:
            result = self.board.run_paos(["health"])
        self.assertEqual(run.call_count, 1)
        self.assertEqual(result["error_code"], "cli_result_unknown")
        self.assertIs(result["retry"], False)

    def test_cli_cannot_start_reports_definite_failure_without_retrying(self):
        with patch("subprocess.run", side_effect=PermissionError("cannot start this Python")) as run:
            result = self.board.run_paos(["health"])
        self.assertEqual(run.call_count, 1)
        self.assertEqual(result["error_code"], "cli_start_failed")
        self.assertEqual(result["phase"], "process_start")
        self.assertEqual(result["error_type"], "PermissionError")
        self.assertTrue(result["retry"])

    def test_failed_join_cannot_report_success_or_send_message(self):
        with patch.object(self.board, "cat", return_value={"ok": False, "error_code": "seat_failed"}) as call:
            result = self.board.send_message("room-fixture", "human", "消息", "fixture-id")
        self.assertFalse(result["ok"])
        self.assertEqual(call.call_count, 1)

    def test_http_serves_same_file_reader_and_explicit_error(self):
        server = make_server(self.board, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 3)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        origin = f"http://127.0.0.1:{server.server_port}"
        with urlopen(origin + "/api/dashboard?project=1001") as response:
            data = json.load(response)
        self.assertEqual(data["coordinator"], "1001-s001")
        with urlopen(origin + "/") as response:
            self.assertIn("PAOS 画板", response.read().decode("utf-8"))
        request = Request(origin + "/api/room", data=json.dumps(
            {"title": "只测未配置", "members": ["1001-s001", "1001-s002"]}).encode(),
            headers={"Content-Type": "application/json"})
        with urlopen(request) as response:
            failure = json.load(response)
        self.assertFalse(failure["ok"])
        self.assertEqual(failure["error_code"], "cat_not_configured")


    def test_http_layout_and_document_routes(self):
        server = make_server(self.board, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 3)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        origin = f"http://127.0.0.1:{server.server_port}"
        with urlopen(origin + "/api/layout?project=1001") as response:
            self.assertEqual(json.load(response)["layout"]["nodes"], {})
        request = Request(origin + "/api/layout", method="PUT", data=json.dumps({
            "project": "1001",
            "layout": {"nodes": {"1001-s001": {"x": 4, "y": 5}},
                       "viewport": {"x": 0, "y": 0, "zoom": 1}},
        }).encode(), headers={"Content-Type": "application/json"})
        with urlopen(request) as response:
            self.assertEqual(json.load(response)["layout"]["nodes"]["1001-s001"]["y"], 5)
        with urlopen(origin + "/api/document?project=1001&path=INDEX.md") as response:
            self.assertIn("唯一口径", json.load(response)["body"])


    def test_existing_room_reuses_room_and_does_not_create_second(self):
        with patch.object(self.board, "cat", side_effect=[
            {"ok": True, "room": {"id": "room-existing"}},
            {"ok": True},
            {"ok": True},
            {"ok": True},
            {"ok": True, "dispatch": "queued"},
        ]) as call:
            result = self.board.collaboration({
                "project": "1001", "mode": "chat",
                "members": ["1001-s001", "1001-s002"], "room_id": "room-existing",
                "topic": "续接", "body": "继续", "message_id": "ui-existing-001",
            })
        self.assertTrue(result["ok"])
        self.assertEqual(result["room_id"], "room-existing")
        commands = [item.args[0][0] for item in call.call_args_list]
        self.assertNotIn("create", commands)
        self.assertEqual(call.call_count, 5)

    def test_paused_member_is_rejected_before_any_cli_call(self):
        root = self.roots["1001"]
        (root / "TEAM.md").write_text(
            "# TEAM\n\n## 当前成员\n\n### 1001-s001\n- 成员状态：暂停保留\n- 职责：暂停\n",
            encoding="utf-8")
        with patch.object(self.board, "run_paos") as run:
            with self.assertRaises(BoardProblem) as raised:
                self.board.collaboration({
                    "project": "1001", "mode": "mail", "members": ["1001-s001"],
                    "topic": "拒绝", "body": "不应发送", "message_id": "ui-paused-001",
                })
        self.assertEqual(raised.exception.code, "member_paused")
        self.assertEqual(run.call_count, 0)

    def test_unknown_cli_outcome_is_not_failed(self):
        with patch.object(self.board, "run_paos", return_value={
                "ok": False, "error_code": "cli_output_invalid", "error": "bad receipt"}):
            result = self.board.collaboration({
                "project": "1001", "mode": "mail", "members": ["1001-s002"],
                "topic": "未知", "body": "保留", "message_id": "ui-unknown-001",
            })
        self.assertEqual(result["state"], "unknown")

    def test_notification_maps_real_mail_activation_and_cat_dispatch(self):
        with patch.object(self.board, "run_paos", return_value={
                "ok": True, "activation": {"state": "native_accepted", "accepted": True}}):
            mail = self.board.collaboration({
                "project": "1001", "mode": "mail", "members": ["1001-s002"],
                "topic": "通知", "body": "正文", "message_id": "ui-notify-001", "remind": True,
            })
        self.assertEqual(mail["notification"], "accepted")
        with patch.object(self.board, "run_paos", return_value={
                "ok": True, "activation": {"accepted": True}}):
            no_remind = self.board.collaboration({
                "project": "1001", "mode": "mail", "members": ["1001-s002"],
                "topic": "不提醒", "body": "正文", "message_id": "ui-notify-002", "remind": False,
            })
        self.assertEqual(no_remind["notification"], "not_requested")

    def test_cat_http_error_without_status_is_unknown(self):
        with patch.object(self.board, "cat", return_value={
                "ok": False, "error_code": "http_error", "error": "500"}):
            result = self.board.collaboration({
                "project": "1001", "mode": "chat", "members": ["1001-s001", "1001-s002"],
                "topic": "主题", "body": "正文", "message_id": "ui-http-001",
            })
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(result["phase"], "create")

    def test_existing_room_with_unrelated_member_is_rejected(self):
        with patch.object(self.board, "cat", return_value={
                "ok": True, "room": {"id": "room-a", "members": [
                    {"home_id": "1001-s001"}, {"home_id": "2001-s009"}]}}) as call:
            with self.assertRaises(BoardProblem) as raised:
                self.board.collaboration({
                    "project": "1001", "mode": "chat",
                    "members": ["1001-s001", "1001-s002"], "room_id": "room-a",
                    "topic": "不匹配", "body": "正文", "message_id": "ui-room-mismatch",
                })
        self.assertEqual(raised.exception.code, "collaboration_room_mismatch")
        self.assertFalse(any(item.args[0][0] == "create" for item in call.call_args_list))

    def test_missing_mail_dispatch_is_not_found(self):
        with patch.object(self.board, "run_paos", return_value={
                "ok": False, "error_code": "mail_dispatch_missing", "error": "missing"}):
            result = self.board.collaboration_status("1001", "mail", "missing-id")
        self.assertEqual(result["state"], "not_found")

    def test_dashboard_is_summary_and_agent_detail_has_full_text(self):
        dashboard = self.board.dashboard("1001")
        row = next(item for item in dashboard["agents"] if item["id"] == "1001-s001")
        self.assertNotIn("todo", row)
        self.assertNotIn("mails", row)
        detail = self.board.agent("1001-s001")
        self.assertIn("todo", detail)
        self.assertIn("mails", detail)

    def test_mail_collaboration_status_uses_real_status_command(self):
        sent = self.board.collaboration({
            "project": "1001", "mode": "mail", "members": ["1001-s002"],
            "topic": "状态", "body": "核对保存", "message_id": "ui-status-001",
        })
        self.assertEqual(sent["state"], "saved")
        status = self.board.collaboration_status("1001", "mail", "ui-status-001")
        self.assertEqual(status["state"], "saved")
        self.assertTrue(status["result"].get("ok"))


    def test_team_fields_paused_registered_and_team_only_are_visible(self):
        root = self.roots["1001"]
        (root / "TEAM.md").write_text(
            "# TEAM\n\n## 当前成员\n\n### 1001-s001\n"
            "- 成员状态：在队\n- 职责：协调\n- 名称：一号\n\n"
            "### 1001-s002\n- 成员状态：暂停保留，不是当前执行者\n- 职责：暂停岗位\n\n"
            "### 9999-s999\n- 成员状态：在队\n- 职责：未登记同事\n- 名称：外部同事\n",
            encoding="utf-8")
        dashboard = self.board.dashboard("1001")
        self.assertTrue(dashboard["team"]["path"].endswith("TEAM.md"))
        self.assertIn("当前成员", dashboard["team"]["body"])
        rows = {item["id"]: item for item in dashboard["agents"]}
        self.assertEqual(rows["1001-s001"]["name"], "一号")
        self.assertTrue(rows["1001-s001"]["can_contact"])
        self.assertFalse(rows["1001-s002"]["can_contact"])
        self.assertTrue(rows["1001-s002"]["registered"])
        self.assertFalse(rows["9999-s999"]["registered"])
        self.assertFalse(rows["9999-s999"]["can_contact"])
        self.assertEqual(self.board.agent("1001-s001")["role"], "协调")

    def test_layout_is_ui_only_and_does_not_touch_team_or_todo(self):
        root = self.roots["1001"]
        team_before = (root / "Workstations/1001-s001/TODO.md").read_bytes()
        empty = self.board.layout("1001")
        self.assertEqual(empty["layout"]["nodes"], {})
        with self.assertRaises(BoardProblem):
            self.board.save_layout("1001", {"nodes": {"1001-s001": {"x": "bad", "y": 1}}})
        saved = self.board.save_layout("1001", {"nodes": {"1001-s001": {"x": 10, "y": 20}},
                                                "viewport": {"x": 1, "y": 2, "zoom": 0.8}})
        self.assertEqual(saved["layout"]["nodes"]["1001-s001"]["x"], 10)
        self.assertEqual(self.board.layout("1001")["layout"]["viewport"]["zoom"], 0.8)
        self.assertEqual(team_before, (root / "Workstations/1001-s001/TODO.md").read_bytes())
        self.assertFalse((root / "TEAM.md").exists())

    def test_document_and_resource_are_read_only_and_bounded(self):
        root = self.roots["1001"]
        doc = self.board.document("1001", "INDEX.md")
        self.assertIn("唯一口径", doc["body"])
        with self.assertRaises(BoardProblem):
            self.board.document("1001", "../2001/INDEX.md")
        resource = self.board.resource("workflow", "guide-working")
        self.assertEqual(resource["resource"]["id"], "guide-working")
        with self.assertRaises(BoardProblem):
            self.board.resource("workflow", "not-registered")

    def test_mail_collaboration_uses_human_sender_stable_id_and_remind_flag(self):
        with patch.object(self.board, "run_paos", return_value={"ok": True, "activation": {"state": "accepted"}}) as run:
            result = self.board.collaboration({
                "project": "1001", "mode": "mail", "members": ["1001-s002"],
                "topic": "补充资料", "body": "请查看参考", "message_id": "ui-fixed-001",
                "remind": True,
            })
        self.assertEqual(result["state"], "saved")
        args = run.call_args.args[0]
        self.assertIn("--sender-kind", args)
        self.assertIn("human", args)
        self.assertIn("--remind", args)
        self.assertIn("ui-fixed-001", args)

    def test_chat_collaboration_partial_join_returns_room_id(self):
        with patch.object(self.board, "cat", side_effect=[
            {"ok": True, "room": {"id": "room-x"}},
            {"ok": True},
            {"ok": False, "error": "join failed", "error_code": "join_failed"},
        ]):
            result = self.board.collaboration({
                "project": "1001", "mode": "chat", "members": ["1001-s001", "1001-s002"],
                "topic": "主题", "body": "正文", "message_id": "ui-chat-001",
            })
        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "partial")
        self.assertEqual(result["room_id"], "room-x")


if __name__ == "__main__":
    unittest.main()
