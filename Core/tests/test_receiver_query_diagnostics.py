"""A failed process query must survive through the receiver view and send receipt."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "code" / "personal-agent-os" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import paos_contact
import runtime_injection
from wakeup_native import process_identity


@unittest.skipUnless(os.name == "nt", "Windows process-query diagnostic contract")
class ReceiverQueryDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime_file = Path(self.temp.name) / "receiver.json"
        self.target = {
            "runtime": "codex",
            "session_id": "session-fixture",
            "extension": {"receiver_runtime_file": str(self.runtime_file)},
        }
        self.runtime_file.write_text(json.dumps({
            "schema": "paos-codex-self-reminder/v1",
            "pid": 4242,
            "process_identity": "windows:123",
            "endpoint": "http://127.0.0.1:1",
            "session_id": "session-fixture",
            "token": "fixture-token",
        }), encoding="utf-8")

    def failed_open_process(self):
        kernel = MagicMock()
        kernel.OpenProcess.return_value = 0
        return patch.object(process_identity.ctypes, "WinDLL", return_value=kernel), \
            patch.object(process_identity.ctypes, "get_last_error", return_value=5)

    def test_receiver_view_keeps_caller_query_failure_and_ownership(self):
        win_dll, last_error = self.failed_open_process()
        with patch.object(paos_contact, "_local_pid_alive_probe", return_value=(True, None)), \
                win_dll, last_error:
            view = paos_contact._codex_receiver_view(self.target)
        self.assertEqual(view["state"], "process_unknown")
        self.assertEqual(view["reason"], "process_identity_query_unavailable")
        self.assertEqual(view["repair_owner"], "caller_installation_owner")
        self.assertEqual(view["diagnostic"]["phase"], "process_query")
        self.assertEqual(view["diagnostic"]["operation"], "OpenProcess")
        self.assertEqual(view["diagnostic"]["reason"], "process_access_denied")
        self.assertEqual(view["diagnostic"]["winerror"], 5)

    def test_reminder_receipt_keeps_caller_query_failure(self):
        win_dll, last_error = self.failed_open_process()
        with patch.object(paos_contact, "_local_pid_alive_probe", return_value=(True, None)), \
                win_dll, last_error:
            with self.assertRaises(runtime_injection.InjectionError) as raised:
                runtime_injection._codex_extension_send(self.target, "message", None)
        details = raised.exception.details()
        self.assertEqual(details["error_code"], "receiver_identity_unverified")
        self.assertEqual(details["repair_owner"], "caller_installation_owner")
        self.assertEqual(details["diagnostic"]["phase"], "process_query")
        self.assertEqual(details["diagnostic"]["operation"], "OpenProcess")
        self.assertEqual(details["diagnostic"]["reason"], "process_access_denied")
        self.assertEqual(details["diagnostic"]["winerror"], 5)


if __name__ == "__main__":
    unittest.main()
