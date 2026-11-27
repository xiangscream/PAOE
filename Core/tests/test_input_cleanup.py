"""Recipient deletion keeps delivery idempotent without keeping the message."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "code/personal-agent-os/scripts"
sys.path.insert(0, str(SCRIPTS))
import test_history_archive as archive_fixture
from paos_input_cleanup import delete_input, read_deleted
from paos_notice import create_notice, notice_archive_files
from paos_todo import read_todo, render_todo


class InputCleanupTests(unittest.TestCase):
    def setUp(self):
        self.f = archive_fixture.HistoryArchiveTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.home = self.f.vault / "Workstations/3002-s002"
        self.ref = {"home_kind": "project_agent", "home_id": "3002-s002", "project_id": "3002",
                    "home_path": str(self.home), "project_root": str(self.f.vault)}

    def send(self, mid="cleanup-test-001", done=True):
        notice = self.f.send(mid)["notices"]["items"][0]["notice_id"]
        if done:
            self.f.mark_done(notice)
        return notice

    def delete(self, mid="cleanup-test-001", **kwargs):
        return delete_input(self.ref, message_id=mid, preserved_ref="Works/durable.md", **kwargs)

    def test_delete_and_same_id_replay_do_not_recreate_or_activate(self):
        notice = self.send()
        self.assertEqual(self.delete()["state"], "deleted")
        self.assertFalse((self.home / "mailbox/cleanup-test-001.md").exists())
        self.assertEqual(notice_archive_files(self.home, notice), [])
        replay = self.f.send("cleanup-test-001")
        self.assertEqual(replay["mail"]["deliveries"][0]["state"], "deleted")
        self.assertEqual(replay["notices"]["items"], [])
        with patch("paos._remind_via_native") as remind:
            self.f.call("agent", "send", "3002", "--to", "3002-s002", "--sender-kind", "agent",
                        "--sender-id", "3002-s001", "--subject", "历史输入", "--body", "这条输入已处理，可以归档。",
                        "--message-id", "cleanup-test-001", "--remind")
        remind.assert_not_called()
        self.assertEqual(self.delete()["state"], "deleted")
        marker = read_deleted(self.home, "mail", "cleanup-test-001")
        self.assertNotIn("body", marker)
        self.assertNotIn("history_root", marker)

    def test_active_task_dependency_blocks_even_if_notice_handled(self):
        self.send()
        (self.home / "TODO.md").write_text(render_todo(
            home_kind="project_agent", home_id="3002-s002", project_id="3002", objective="Use original", next_action="Read",
            tasks=[dict(id="T1", title="Needs original", state="doing", source_refs=["mail:cleanup-test-001"])]), encoding="utf-8")
        self.assertEqual(self.delete()["state"], "active_dependency")
        self.assertIsNone(read_deleted(self.home, "mail", "cleanup-test-001"))

    def test_unread_requires_real_withdrawal_decision_does_not_fake_read(self):
        notice = self.send(done=False)
        with self.assertRaises(ValueError):
            self.delete()
        with self.assertRaises(ValueError):
            self.delete(disposition="superseded")
        self.delete(disposition="superseded", decided_by="human", decision_ref="Decisions/replace.md")
        marker = read_deleted(self.home, "mail", "cleanup-test-001")
        self.assertFalse(marker["was_read"])
        self.assertFalse(marker["was_handled"])
        self.assertEqual(notice_archive_files(self.home, notice), [])

    def test_partial_deletion_suppresses_redelivery_then_finishes(self):
        self.send()
        unlink = Path.unlink
        def fail_notice(path, *args, **kwargs):
            if path.parent == self.home / "notices":
                raise PermissionError("isolated unlink failure")
            return unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", fail_notice):
            result = self.delete()
        self.assertEqual(result["state"], "cleanup_pending")
        replay = self.f.send("cleanup-test-001")
        self.assertEqual(replay["mail"]["deliveries"][0]["state"], "deleted")
        self.assertEqual(self.delete()["state"], "deleted")

    def test_standalone_notice_does_not_reappear(self):
        from paos_notice import handle_notice, mark_notice_read
        args = dict(home_path=self.home, home_kind="project_agent", home_id="3002-s002",
                    project_id="3002", source_kind="cat", source_ref="room-event-001", summary="Test")
        notice = create_notice(**args)
        mark_notice_read(home_path=self.home, notice_id=notice["notice_id"],
                         reader_home_kind="project_agent", reader_home_id="3002-s002", reader_project_id="3002")
        handle_notice(home_path=self.home, notice_id=notice["notice_id"], resolution="done", action_ref="out.md")
        result = delete_input(self.ref, notice_id=notice["notice_id"], preserved_ref="out.md")
        self.assertEqual(result["state"], "deleted")
        self.assertEqual(create_notice(**args)["state"], "deleted")

    def test_mail_result_closes_auto_task_and_cleans_in_one_existing_exit(self):
        self.send(done=False)
        claimed = self.f.call("mail", "claim", "3002", "3002-s002", "cleanup-test-001")[1]
        result = self.f.call("mail", "result", "3002", "3002-s002", "cleanup-test-001",
                             "--result", "delivered", "--cleanup-inputs", "--preserved-ref", "Works/out.md")[1]
        self.assertEqual(result["task_state"], "done")
        self.assertTrue(result["cleanup"]["complete"])
        task = next(t for t in read_todo(self.home / "TODO.md")["tasks"] if t["id"] == claimed["task_id"])
        self.assertEqual(task["state"], "done")

    def test_two_recipients_and_external_home_are_independent(self):
        mid = "cleanup-cross-001"
        args = ("attention", "send", "3002", "--to", "3002-s002", "--to", "2001-s009",
                "--sender-kind", "agent", "--sender-id", "3002-s001", "--subject", "Shared",
                "--body", "Original", "--message-id", mid)
        sent = self.f.call(*args)[1]
        local = next(n for n in sent["notices"]["items"] if n["home_id"] == "3002-s002")
        self.f.mark_done(local["notice_id"])
        self.delete(mid)
        replay = self.f.call(*args)[1]
        states = {d["recipient_agent_id"]: d["state"] for d in replay["mail"]["deliveries"]}
        self.assertEqual(states["3002-s002"], "deleted")
        self.assertEqual(states["2001-s009"], "already_delivered")
        external = self.f.other_vault / "Workstations/2001-s009"
        ref = dict(self.ref, home_id="2001-s009", project_id="2001", home_path=str(external))
        notice = replay["notices"]["external_routes"][0]["notice_id"]
        self.f.call("attention", "read", "2001", "2001-s009", notice)
        self.f.call("attention", "handle", "2001", "2001-s009", notice, "--resolution", "done", "--action-ref", "out.md")
        self.assertEqual(delete_input(ref, message_id=mid, preserved_ref="out.md")["state"], "deleted")
        again = self.f.call(*args)[1]
        self.assertEqual(again["notices"]["external_routes"][0]["mail_state"], "deleted")

    def test_task_accept_uses_same_cleanup_without_changing_result(self):
        (self.f.root / "numbers.json").write_text('{"3002-s002":"S002"}', encoding="utf-8")
        mid = "cleanup-test-001"
        self.send(done=False)
        task_id = self.f.call("mail", "claim", "3002", "3002-s002", mid)[1]["task_id"]
        for name in ("out.md", "basis.md"):
            (self.f.vault / name).write_text("Actual artifact", encoding="utf-8")
        args = ("task", "accept", "3002-s002", "--task", task_id,
                "--artifact", "out.md", "--basis", "basis.md", "--remaining", "none",
                "--cleanup-inputs", "--preserved-ref", "out.md")
        result = self.f.call(*args)[1]
        self.assertTrue(result["task_done"])
        self.assertTrue(result["cleanup"]["complete"])
        again = self.f.call(*args)[1]
        self.assertTrue(again["replayed"])
        self.assertTrue(again["cleanup"]["complete"])

    def test_rooter_path_is_not_required_to_equal_its_identity(self):
        from paos_notice import list_notices
        path = self.f.rooter.with_name("rooter S035")
        self.f.rooter.rename(path)
        installation = json.loads(self.f.install.read_text(encoding="utf-8"))
        installation["rooter_home"] = str(path)
        self.f.install.write_text(json.dumps(installation), encoding="utf-8")
        args = ("attention", "send", "3002", "--to", "rooter-001", "--sender-kind", "agent",
                "--sender-id", "3002-s001", "--subject", "Rooter", "--body", "Original", "--message-id", "cleanup-rooter-001")
        self.f.call(*args)
        notice_id = list_notices(path)["items"][0]["notice_id"]
        self.f.call("attention", "rooter-read", notice_id)
        self.f.call("attention", "rooter-handle", notice_id, "--resolution", "done", "--action-ref", "out.md")
        ref = dict(home_kind="rooter", home_id="rooter-001", project_id="", home_path=str(path))
        self.assertEqual(delete_input(ref, message_id="cleanup-rooter-001", preserved_ref="out.md")["state"], "deleted")
        self.assertEqual(self.f.call(*args)[1]["notices"]["external_routes"][0]["mail_state"], "deleted")

    def test_explicit_supersession_can_delete_mail_without_fabricating_notice(self):
        notice_id = self.send(done=False)
        (self.home / "notices" / (notice_id + ".md")).unlink()
        with self.assertRaisesRegex(ValueError, "缺少 Notice 消费证明"):
            self.delete()
        self.assertEqual(self.delete(disposition="superseded", decided_by="Human",
                                     decision_ref="Decisions/end.md")["state"], "deleted")
        marker = read_deleted(self.home, "mail", "cleanup-test-001")
        self.assertTrue(marker["notice_missing"])
        self.assertIsNone(marker["was_read"])
        self.assertIsNone(marker["was_handled"])
        self.assertEqual(notice_archive_files(self.home, notice_id), [])
        replay = self.f.send("cleanup-test-001")
        self.assertEqual(replay["mail"]["deliveries"][0]["state"], "deleted")
        self.assertEqual(replay["notices"]["items"], [])

    def test_missing_notice_does_not_override_an_unfinished_task(self):
        notice_id = self.send(done=False)
        (self.home / "notices" / (notice_id + ".md")).unlink()
        (self.home / "TODO.md").write_text(render_todo(
            home_kind="project_agent", home_id="3002-s002", project_id="3002", objective="Work", next_action="Read",
            tasks=[dict(id="T1", title="Needs mail", state="doing", source_refs=["mail:cleanup-test-001"])]), encoding="utf-8")
        self.assertEqual(self.delete(disposition="withdrawn", decided_by="Human",
                                     decision_ref="Decisions/end.md")["state"], "active_dependency")
        self.assertIsNone(read_deleted(self.home, "mail", "cleanup-test-001"))


if __name__ == "__main__":
    unittest.main()
