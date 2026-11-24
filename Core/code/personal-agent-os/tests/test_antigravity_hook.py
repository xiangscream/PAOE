"""Antigravity adapter dispatches only for the registered conversation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from paos_antigravity_hook import run_hook
from paos_contact import save_native_targets
from paos_installation import write_installation_descriptor
from paos_registry import ProjectRegistry


class AntigravityHookTests(unittest.TestCase):
    session_id = "00000000-0000-0000-0000-000000000001"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.installation = self.root / "installation.json"
        write_installation_descriptor(
            self.installation, source_root=str(Path(__file__).resolve().parents[1]),
            data_root=str(self.root / "Data"),
            library_roots_config=str(self.root / "libraries.json"),
        )
        ProjectRegistry(self.installation).register(
            "3999", root_path=str(self.root), homes=["S034"], coordinator_home_id="S034",
        )
        (self.root / "Workstations" / "S034").mkdir(parents=True)
        save_native_targets(self.root, {
            "S034": {"runtime": "antigravity", "session_id": self.session_id},
        }, installation_path=self.installation)
        self.reader = self.enterContext(patch("paos_antigravity_hook.subprocess.run"))

    def invoke(self, event="PreInvocation", session_id=None, cat_url=None, **extra):
        return run_hook(event, {
            "conversationId": session_id or self.session_id,
            "lastUserInput": "untrusted prompt",
            "transcriptPath": "must-not-be-read",
            **extra,
        }, "3999", "S034", self.installation, cat_url)

    def receipt(self, **fields):
        self.reader.return_value = subprocess.CompletedProcess(
            args=[], returncode=1 if fields.get("ok") is False else 0,
            stdout=json.dumps({
                "schema": "paoe-context/v1",
                "home_id": "S034",
                "reason": "request",
                "ok": True,
                "missing": [],
                "documents": [{
                    "kind": "current", "path": "TODO.md", "body": "# Current\n完整原文\n",
                }],
                **fields,
            }), stderr="",
        )

    def test_each_request_uses_fresh_complete_context_for_the_registered_owner(self):
        self.receipt()
        first = self.invoke(invocationNum=0)
        self.assertIn("# Current\n完整原文\n", first["injectSteps"][0]["ephemeralMessage"])
        argv = self.reader.call_args.args[0]
        self.assertEqual(argv[2:], ["--installation-file", str(self.installation),
                          "--json", "context", "read", "S034", "--reason", "request"])
        self.assertNotIn("untrusted prompt", argv)
        self.receipt(documents=[{"kind": "input", "path": "INPUT.md", "body": "下一阶段正文"}])
        second = self.invoke(invocationNum=1)
        self.assertIn("下一阶段正文", second["injectSteps"][0]["ephemeralMessage"])
        self.assertNotIn("完整原文", second["injectSteps"][0]["ephemeralMessage"])
        self.assertEqual(self.reader.call_count, 2)

    def test_unrelated_conversation_never_runs_reader_or_receives_context(self):
        self.assertEqual(self.invoke(session_id="other-conversation"), {})
        self.reader.assert_not_called()

    def test_contact_uses_the_same_installation_as_the_context_reader(self):
        other = self.root / "other-installation.json"
        write_installation_descriptor(
            other, source_root=str(Path(__file__).resolve().parents[1]),
            data_root=str(self.root / "OtherData"),
            library_roots_config=str(self.root / "libraries.json"),
        )
        save_native_targets(self.root, {
            "S034": {"runtime": "antigravity", "session_id": "00000000-0000-0000-0000-000000000002"},
        }, installation_path=other)
        self.receipt()
        with patch.dict(os.environ, {"PAOS_INSTALLATION_FILE": str(other)}):
            got = self.invoke()
        self.assertIn("完整原文", got["injectSteps"][0]["ephemeralMessage"])
        self.assertEqual(self.reader.call_args.args[0][2:4], ["--installation-file", str(self.installation)])

    def test_registered_role_reader_uses_the_configured_cat_endpoint(self):
        endpoint = "http://127.0.0.1:12345"
        self.receipt(documents=[{"kind": "active_role", "path": "cat-role:room-fixture", "body": "当前有效角色原文"}])
        got = self.invoke(cat_url=endpoint)
        self.assertIn("当前有效角色原文", got["injectSteps"][0]["ephemeralMessage"])
        self.assertEqual(self.reader.call_args.args[0][5:], [
            "context", "read", "S034", "--reason", "request", "--cat-url", endpoint,
        ])

    def test_missing_required_input_returns_explicit_termination_without_partial_documents(self):
        self.receipt(ok=False, missing=[{"kind": "input", "path": "INPUT.md", "reason": "missing"}])
        actual = self.invoke()
        self.assertEqual(actual["terminationBehavior"], "terminate")
        self.assertIn("input（missing）", actual["injectSteps"][0]["errorMessage"]["userMessage"])
        self.assertNotIn("完整原文", str(actual))

    def test_invalid_reader_result_stops_a_registered_turn(self):
        self.receipt(home_id="S070")
        self.assertEqual(self.invoke()["terminationBehavior"], "terminate")
        self.receipt()
        self.reader.return_value.stdout = "not json"
        self.assertEqual(self.invoke()["terminationBehavior"], "terminate")

    def test_reader_timeout_becomes_valid_native_termination_response(self):
        self.reader.side_effect = subprocess.TimeoutExpired([], 8)
        self.assertEqual(self.invoke()["terminationBehavior"], "terminate")
        self.reader.assert_called_once()

    def test_stop_updates_presence_without_asking_for_a_continuation(self):
        self.receipt()
        for termination in ("NO_TOOL_CALL", "TERMINAL_CUSTOM_HOOK", "TERMINAL_CANCELED"):
            for idle in (True, False):
                with self.subTest(termination=termination, idle=idle):
                    self.assertEqual(self.invoke(
                        "Stop", executionNum=0, terminationReason=termination, fullyIdle=idle,
                        cat_url="http://127.0.0.1:12345",
                    ), {"decision": "stop"})
                    self.assertEqual(self.reader.call_args.args[0][5:], [
                        "context", "stop", "S034", "--event", "antigravity:" + self.session_id + ":0",
                        "--reentry", "--cat-url", "http://127.0.0.1:12345",
                    ])

    def test_unrelated_stop_never_calls_common_action(self):
        self.assertEqual(self.invoke("Stop", session_id="other-conversation", executionNum=0), {})
        self.reader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
