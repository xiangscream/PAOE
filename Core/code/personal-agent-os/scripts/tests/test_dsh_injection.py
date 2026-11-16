import errno
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import paos_wakeup
import runtime_injection as injection
from paos_contact import runtime_contact, save_native_targets


class DshInjectionTests(unittest.TestCase):
    request_id = "a" * 32
    secret = "s" * 64

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.dsh = self.root / "dsh" / "wake-receiver"
        self.dsh.mkdir(parents=True)
        self.receiver = self.dsh / "receiver.json"
        self.secret_file = self.dsh / "secret"
        self.secret_file.write_text(self.secret + "\n", encoding="utf-8")
        self.write_record()
        self.target = {"runtime": "dsh", "session_id": "dsh-session",
                       "receiver_file": str(self.receiver)}
        for p in (patch.object(Path, "home", return_value=self.home),
                  patch.object(injection.uuid, "uuid4", return_value=uuid.UUID(hex=self.request_id))):
            p.start()
            self.addCleanup(p.stop)

    def write_record(self, **overrides):
        record = {
            "schema": "dsh-wake-receiver/v1",
            "url": "http://127.0.0.1:8791",
            "secretFile": str(self.secret_file),
            "pid": os.getpid(),
            "heartbeatAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        record.update(overrides)
        self.receiver.write_text(json.dumps(record), encoding="utf-8")

    def accepted(self, **overrides):
        payload = {
            "ok": True, "accepted": True, "sessionId": "dsh-session",
            "requestId": self.request_id, "mode": "queue",
            "note": "accepted means admitted to the Session inbox",
        }
        payload.update(overrides)
        return payload, 200

    def http_error(self, status, code="wake/fixture", reason="fixture"):
        body = json.dumps({"ok": False, "accepted": False, "code": code,
                           "reason": reason, "retry": status == 409}).encode()
        return HTTPError("http://127.0.0.1:8791/wake", status, "fixture", {}, io.BytesIO(body))

    def test_accepted_receipt_preserves_request_identity_and_never_exposes_secret(self):
        with patch.object(injection, "_request", return_value=self.accepted()) as request:
            result = injection.inject(self.target, "读取本人 TODO\n中文")
        self.assertEqual(result, {
            "accepted": True, "runtime": "dsh", "session_id": "dsh-session",
            "http_status": 200, "request_id": self.request_id,
            "native_disposition": "queue",
        })
        request.assert_called_once()
        args = request.call_args.args
        self.assertEqual(args[1], "http://127.0.0.1:8791")
        self.assertEqual(args[2:4], ("POST", "/wake"))
        self.assertEqual(args[4], {
            "sessionId": "dsh-session", "text": "读取本人 TODO\n中文",
            "mode": "queue", "requestId": self.request_id,
        })
        self.assertEqual(request.call_args.kwargs["authorization"], "Bearer " + self.secret)
        self.assertNotIn(self.secret, json.dumps(result))

    def test_steer_mode_is_forwarded_and_echoed(self):
        self.target["mode"] = "steer"
        with patch.object(injection, "_request", return_value=self.accepted(mode="steer")) as request:
            result = injection.inject(self.target, "提醒")
        self.assertEqual(request.call_args.args[4]["mode"], "steer")
        self.assertEqual(result["native_disposition"], "steer")

    def test_explicit_model_is_rejected_before_any_native_access(self):
        with patch.object(injection, "_request") as request:
            with self.assertRaisesRegex(ValueError, "不接受显式 model"):
                injection.inject(self.target, "提醒", model="human-model")
        request.assert_not_called()

    def test_invalid_mode_is_rejected_before_any_native_access(self):
        for mode in ("later", ["queue"]):
            with self.subTest(mode=mode):
                self.target["mode"] = mode
                with patch.object(injection, "_request") as request:
                    with self.assertRaisesRegex(ValueError, "queue or steer"):
                        injection.inject(self.target, "提醒")
                request.assert_not_called()

    def test_missing_or_invalid_receiver_config_never_posts(self):
        cases = [
            ({"receiver_file": ""}, "dsh_receiver_config_missing"),
            ({"receiver_file": str(self.root / "missing.json")}, "dsh_receiver_missing"),
        ]
        for target, code in cases:
            with self.subTest(code=code), patch.object(injection, "_request") as request:
                with self.assertRaises(injection.InjectionError) as raised:
                    injection.inject({**self.target, **target}, "提醒")
                self.assertEqual(raised.exception.code, code)
                request.assert_not_called()
        self.write_record(schema="other")
        with patch.object(injection, "_request") as request:
            with self.assertRaises(injection.InjectionError) as raised:
                injection.inject(self.target, "提醒")
        self.assertEqual(raised.exception.code, "dsh_receiver_invalid")
        request.assert_not_called()

    def test_non_loopback_endpoint_and_missing_secret_never_post(self):
        self.write_record(url="http://localhost:8791")
        with patch.object(injection, "_request") as request:
            with self.assertRaises(injection.InjectionError) as raised:
                injection.inject(self.target, "提醒")
        self.assertEqual(raised.exception.code, "dsh_receiver_invalid")
        request.assert_not_called()
        self.write_record(secretFile=str(self.dsh / "missing-secret"))
        with patch.object(injection, "_request") as request:
            with self.assertRaises(injection.InjectionError) as raised:
                injection.inject(self.target, "提醒")
        self.assertEqual(raised.exception.code, "dsh_secret_unreadable")
        request.assert_not_called()

    def test_invalid_receiver_port_is_a_config_error_not_a_crash(self):
        self.write_record(url="http://127.0.0.1:99999")
        with patch.object(injection, "_request") as request:
            with self.assertRaises(injection.InjectionError) as raised:
                injection.inject(self.target, "提醒")
        self.assertEqual(raised.exception.code, "dsh_receiver_invalid")
        request.assert_not_called()
        project_root = self.root / "project"
        project_root.mkdir()
        save_native_targets(project_root, {"agent": {**self.target, "receiver_file": str(self.receiver)}})
        contact = runtime_contact(project_root, "agent")
        self.assertEqual(contact["receiver"]["state"], "receiver_record_invalid")
        self.assertEqual(contact["receiver"]["reason"], "invalid_endpoint")

    def test_non_utf8_secret_is_a_structured_config_error_without_echo(self):
        self.secret_file.write_bytes(b"\xff" * 64)
        with patch.object(injection, "_request") as request:
            with self.assertRaises(injection.InjectionError) as raised:
                injection.inject(self.target, "提醒")
        self.assertEqual(raised.exception.code, "dsh_secret_unreadable")
        self.assertEqual(raised.exception.state, "receiver_not_prepared")
        self.assertFalse(raised.exception.details()["retry"])
        self.assertNotIn("\ufffd", str(raised.exception))
        self.assertNotIn("0xff", json.dumps(raised.exception.details()))
        request.assert_not_called()

    def test_contact_heartbeat_missing_or_invalid_is_not_prepared(self):
        project_root = self.root / "project"
        project_root.mkdir()
        save_native_targets(project_root, {"agent": self.target})
        self.write_record(heartbeatAt=None)
        contact = runtime_contact(project_root, "agent")
        self.assertEqual(contact["receiver"]["state"], "receiver_heartbeat_unknown")
        self.assertFalse(contact["receiver"]["prepared"])
        self.assertEqual(contact["receiver"]["reason"], "heartbeat_missing")
        self.assertNotIn("由正常 DSH 工位 bind 登记", contact["receiver"]["next_action"])
        self.write_record(heartbeatAt="not-a-timestamp")
        contact = runtime_contact(project_root, "agent")
        self.assertEqual(contact["receiver"]["state"], "receiver_heartbeat_unknown")
        self.assertFalse(contact["receiver"]["prepared"])
        self.assertEqual(contact["receiver"]["reason"], "heartbeat_invalid")
        self.assertIsNone(contact["receiver"]["record_fresh"])
        self.assertNotIn("由正常 DSH 工位 bind 登记", contact["receiver"]["next_action"])

    def test_stop_prevents_any_receiver_access(self):
        stop = self.root / "STOP"
        stop.touch()
        self.target["stop_file"] = str(stop)
        with patch.object(injection, "_request") as request:
            with self.assertRaises(injection.InjectionError) as raised:
                injection.inject(self.target, "提醒")
        self.assertEqual(raised.exception.state, "native_stopped")
        request.assert_not_called()

    def test_definite_http_rejections_are_not_retried(self):
        for status, state in ((400, "native_rejected"), (401, "native_rejected"),
                              (403, "native_rejected"), (404, "native_rejected"),
                              (409, "native_busy"), (413, "native_rejected"),
                              (503, "native_unavailable")):
            with self.subTest(status=status), patch.object(
                    injection, "_request", side_effect=self.http_error(status)) as request:
                with self.assertRaises(injection.InjectionError) as raised:
                    injection.inject(self.target, "提醒")
                self.assertNotIsInstance(raised.exception, injection.InjectionUncertain)
                self.assertEqual(raised.exception.state, state)
                self.assertFalse(raised.exception.details()["retry"])
                self.assertEqual(raised.exception.diagnostic["http_status"], status)
                self.assertEqual(request.call_count, 1)
                self.assertNotIn(self.secret, json.dumps(raised.exception.details()))

    def test_server_error_and_transport_failures_are_unknown_and_never_retried(self):
        failures = [
            self.http_error(500),
            self.http_error(502),
            URLError(TimeoutError("fixture")),
            TimeoutError("fixture"),
            ConnectionResetError("fixture"),
        ]
        for failure in failures:
            with self.subTest(kind=type(failure).__name__), patch.object(
                    injection, "_request", side_effect=failure) as request:
                with self.assertRaises(injection.InjectionUncertain) as raised:
                    injection.inject(self.target, "提醒")
                self.assertFalse(raised.exception.details()["retry"])
                self.assertEqual(raised.exception.diagnostic["request_id"], self.request_id)
                self.assertEqual(request.call_count, 1)
                self.assertNotIn(self.secret, json.dumps(raised.exception.details()))

    def test_connection_refused_is_a_definite_offline_result(self):
        errors = (ConnectionRefusedError(errno.ECONNREFUSED, "fixture"),
                  URLError(ConnectionRefusedError(errno.ECONNREFUSED, "fixture")))
        for failure in errors:
            with self.subTest(kind=type(failure).__name__), patch.object(
                    injection, "_request", side_effect=failure) as request:
                with self.assertRaises(injection.InjectionError) as raised:
                    injection.inject(self.target, "提醒")
                self.assertNotIsInstance(raised.exception, injection.InjectionUncertain)
                self.assertEqual(raised.exception.code, "receiver_connection_refused")
                self.assertEqual(raised.exception.state, "receiver_offline")
                self.assertEqual(request.call_count, 1)

    def test_receipt_mismatch_is_unknown_after_one_post(self):
        cases = [
            self.accepted(sessionId="other"),
            self.accepted(requestId="b" * 32),
            self.accepted(mode="steer"),
            (None, 200),
            ({"ok": True, "accepted": True, "sessionId": "dsh-session"}, 500),
        ]
        for payload in cases:
            with self.subTest(payload=payload), patch.object(
                    injection, "_request", return_value=payload) as request:
                with self.assertRaises(injection.InjectionError) as raised:
                    injection.inject(self.target, "提醒")
                self.assertIsInstance(raised.exception, injection.InjectionUncertain)
                self.assertFalse(raised.exception.details()["retry"])
                self.assertEqual(request.call_count, 1)

    def test_receipt_accepted_false_is_a_definite_refusal(self):
        with patch.object(injection, "_request",
                          return_value=({"ok": True, "accepted": False}, 200)) as request:
            with self.assertRaises(injection.InjectionError) as raised:
                injection.inject(self.target, "提醒")
        self.assertNotIsInstance(raised.exception, injection.InjectionUncertain)
        self.assertEqual(raised.exception.code, "dsh_rejected")
        self.assertEqual(raised.exception.state, "native_rejected")
        self.assertEqual(request.call_count, 1)

    def test_real_loopback_receiver_gets_one_authenticated_wake_request(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length))
                self.server.seen = {
                    "path": self.path,
                    "authorization": self.headers.get("Authorization"),
                    "request_header": self.headers.get("X-PAOS-Request-ID"),
                    "body": body,
                }
                payload = json.dumps({
                    "ok": True, "accepted": True, "sessionId": body["sessionId"],
                    "requestId": body["requestId"], "mode": body["mode"],
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.write_record(url=f"http://127.0.0.1:{server.server_port}")
        result = injection.inject(self.target, "真实回环提醒")
        server.shutdown()
        thread.join(timeout=5)
        self.assertEqual(result["request_id"], self.request_id)
        self.assertEqual(server.seen["path"], "/wake")
        self.assertEqual(server.seen["authorization"], "Bearer " + self.secret)
        self.assertEqual(server.seen["request_header"], self.request_id)
        self.assertEqual(server.seen["body"], {
            "sessionId": "dsh-session", "text": "真实回环提醒",
            "mode": "queue", "requestId": self.request_id,
        })

    def test_bind_requires_absolute_receiver_file_and_valid_mode(self):
        project_root = self.root / "project"
        project_root.mkdir()
        common = dict(root=project_root, project_id="p1", agent_id="agent-original",
                      runtime_id=None, native_session_id="dsh-session",
                      driver_name="dsh")
        with self.assertRaises(paos_wakeup.WakeProblem) as raised:
            paos_wakeup.bind_wakeup(**common, driver_config={})
        self.assertEqual(raised.exception.code, "wake_dsh_receiver_config_required")
        with self.assertRaises(paos_wakeup.WakeProblem) as raised:
            paos_wakeup.bind_wakeup(**common, driver_config={"receiver_file": "relative.json"})
        self.assertEqual(raised.exception.code, "wake_dsh_receiver_config_invalid")
        with self.assertRaises(paos_wakeup.WakeProblem) as raised:
            paos_wakeup.bind_wakeup(**common, driver_config={"receiver_file": str(self.receiver), "mode": "later"})
        self.assertEqual(raised.exception.code, "wake_dsh_mode_invalid")
        result = paos_wakeup.bind_wakeup(
            **common,
            driver_config={"receiver_file": str(self.receiver), "mode": "steer",
                           "secretFile": str(self.secret_file), "token": "fixture-token"},
        )
        self.assertEqual(result["target"]["mode"], "steer")
        self.assertNotIn("secretFile", result["target"])
        self.assertNotIn("token", result["target"])
        stored = paos_wakeup.load_native_targets(project_root)
        self.assertEqual(stored["agent-original"]["receiver_file"], str(self.receiver))
        self.assertNotIn(self.secret, json.dumps(stored))
        self.assertNotIn("fixture-token", json.dumps(stored))

    def test_contact_status_reads_discovery_not_secret_and_declares_stop_scope(self):
        project_root = self.root / "project"
        project_root.mkdir()
        save_native_targets(project_root, {"agent": self.target})
        contact = runtime_contact(project_root, "agent")
        self.assertEqual(contact["runtime"], "dsh")
        self.assertEqual(contact["receiver"]["state"], "receiver_record_present")
        self.assertTrue(contact["receiver"]["prepared"])
        self.assertEqual(contact["receiver"]["reason"], "")
        self.assertEqual(contact["receiver"]["next_action"], "")
        self.assertIsNone(contact["receiver"]["repair_owner"])
        self.assertNotIn("receiver_file_not_registered", json.dumps(contact))
        self.assertTrue(contact["receiver"]["secret_registered"])
        self.assertTrue(contact["receiver"]["secret_present"])
        self.assertFalse(contact["native_cancel_supported"])
        self.assertEqual(contact["stop_effect"], "blocks_future_injections_only")
        self.assertEqual(contact["attach"]["reason"], "attach_undefined_for_driver:dsh")
        self.assertIsNone(contact["attach"]["command"])
        self.assertNotIn(self.secret, json.dumps(contact))

    def test_contact_status_reports_missing_receiver_without_inventing_online(self):
        project_root = self.root / "project"
        project_root.mkdir()
        target = {**self.target, "receiver_file": str(self.root / "missing.json")}
        save_native_targets(project_root, {"agent": target})
        contact = runtime_contact(project_root, "agent")
        self.assertEqual(contact["receiver"]["state"], "receiver_record_missing")
        self.assertFalse(contact["receiver"]["prepared"])
        self.assertIsNone(contact["receiver"]["pid_alive"])


if __name__ == "__main__":
    unittest.main()
