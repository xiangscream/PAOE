import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import wakeup_native.codex_receiver as receiver


class ReceiverConnectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.stop = self.root / "STOP"
        self.runtime = self.root / "runtime.json"
        self.old_client = Mock()
        self.current_client = Mock()
        self.current_client.thread_status.return_value = "idle"
        self.old = receiver.SelfReminder(self.old_client, "own", self.stop, "windows:123",
                                        receiver.desktop_connection_identity("old-pipe"))
        self.current = receiver.SelfReminder(self.current_client, "own", self.stop, "windows:123",
                                            receiver.desktop_connection_identity("OLD-PIPE"))
        server = receiver.make_server(self.old, "fixture-grant")
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        grant = {"schema": "paos-codex-self-reminder/v1", "pid": os.getpid(), "session_id": "own",
                 "endpoint": f"http://127.0.0.1:{server.server_port}", "token": "fixture-grant",
                 "process_identity": "windows:123", "receiver_behavior": "native_followup"}
        self.runtime.write_text(json.dumps(grant), encoding="utf-8")
        self.original = self.runtime.read_bytes()
        process = {"alive": True, "identity": "windows:123", "invocation_matches": True}
        for item in (
            patch("runtime_injection.Path.home", return_value=self.root),
            patch.object(receiver.SelfReminder, "from_desktop", return_value=self.current),
            patch("paos_contact._local_pid_alive", return_value=(True, None)),
            patch("wakeup_native.process_identity.process_snapshot", return_value=process),
            patch.object(receiver, "process_snapshot", return_value=process),
        ):
            item.start()
            self.addCleanup(item.stop)
        stop_process = patch.object(receiver, "stop_windows_instance")
        self.stop_process = stop_process.start()
        self.addCleanup(stop_process.stop)

    def reuse(self):
        return receiver.reusable_owned_runtime(self.runtime, self.stop)

    def assert_preserved(self):
        self.assertEqual(self.runtime.read_bytes(), self.original)
        self.old_client.thread_status.assert_not_called()
        self.old_client.wake.assert_not_called()
        self.current_client.wake.assert_not_called()

    def test_same_live_connection_is_reused_through_authenticated_http(self):
        self.assertEqual(self.reuse(), os.getpid())
        self.stop_process.assert_not_called()
        self.current_client.thread_status.assert_called_once_with("own")
        self.assert_preserved()

    def test_changed_connection_retires_only_authenticated_exact_self(self):
        self.current.desktop_connection_id = receiver.desktop_connection_identity("new-pipe")
        self.assertIsNone(self.reuse())
        self.stop_process.assert_called_once_with(os.getpid(), "windows:123")
        self.assert_preserved()  # Normal prepare, not this function, archives the old bytes.

    def test_old_behavior_without_connection_proof_is_unknown_not_reused(self):
        self.old.desktop_connection_id = None
        with self.assertRaises(receiver.ReceiverError) as caught:
            self.reuse()
        self.assertEqual(caught.exception.code, "receiver_connection_unknown")
        self.stop_process.assert_not_called()
        self.assert_preserved()

    def test_wrong_status_instance_cannot_be_reused_or_stopped(self):
        self.old.process_identity = "windows:999"
        with self.assertRaises(receiver.ReceiverError) as caught:
            self.reuse()
        self.assertEqual(caught.exception.code, "receiver_connection_unknown")
        self.current_client.thread_status.assert_not_called()
        self.stop_process.assert_not_called()
        self.assert_preserved()

    def test_current_host_unavailable_never_retires_old_receiver(self):
        self.current.desktop_connection_id = receiver.desktop_connection_identity("new-pipe")
        self.current_client.thread_status.side_effect = OSError("private-current-pipe")
        with self.assertRaises(receiver.ReceiverError) as caught:
            self.reuse()
        self.assertEqual(caught.exception.code, "receiver_connection_unknown")
        self.assertNotIn("private-current-pipe", str(caught.exception))
        self.stop_process.assert_not_called()
        self.assert_preserved()

    def test_stop_after_host_read_prevents_connection_rotation(self):
        self.current.desktop_connection_id = receiver.desktop_connection_identity("new-pipe")
        self.current_client.thread_status.side_effect = lambda _: self.stop.touch() or "idle"
        with self.assertRaises(receiver.ReceiverError) as caught:
            self.reuse()
        self.assertEqual(caught.exception.code, "native_stopped")
        self.stop_process.assert_not_called()
        self.assert_preserved()

    def test_connection_proof_does_not_publish_pipe_or_change_grant_schema(self):
        self.assertNotIn("old-pipe", json.dumps(self.old.status()))
        self.assertEqual(set(json.loads(self.original)), {"schema", "pid", "session_id", "endpoint", "token",
                                                         "process_identity", "receiver_behavior"})


if __name__ == "__main__":
    unittest.main()
