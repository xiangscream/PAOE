"""Windows process identity read path against the current test process."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code" / "personal-agent-os" / "scripts"))
from wakeup_native.process_identity import process_snapshot


@unittest.skipUnless(os.name == "nt", "Windows process identity contract")
class ProcessIdentityTests(unittest.TestCase):
    def test_current_process_identity_is_readable_without_receiver_invocation(self):
        first = process_snapshot(os.getpid(), None, None)
        second = process_snapshot(os.getpid(), None, None)
        self.assertIs(first.get("alive"), True)
        self.assertTrue(str(first.get("identity") or "").startswith("windows:"))
        self.assertEqual(first.get("identity"), second.get("identity"))
        self.assertIsNone(first.get("invocation_matches"))


    def test_windows_snapshot_uses_read_only_limited_information(self):
        import ctypes
        from wakeup_native import process_identity
        kernel = MagicMock()
        kernel.OpenProcess.return_value = 123
        def process_times(handle, created, exited, kernel_time, user_time):
            created._obj.dwLowDateTime = 7
            created._obj.dwHighDateTime = 0
            return True
        def exit_code(handle, value):
            value._obj.value = 259
            return True
        kernel.GetProcessTimes.side_effect = process_times
        kernel.GetExitCodeProcess.side_effect = exit_code
        with patch.object(process_identity.ctypes, "WinDLL", return_value=kernel):
            result = process_identity._windows_snapshot(4242, None, None)
        self.assertTrue(result["alive"])
        self.assertEqual(result["identity"], "windows:7")
        kernel.OpenProcess.assert_called_once_with(0x1000, False, 4242)
        kernel.GetExitCodeProcess.assert_called_once()
        kernel.WaitForSingleObject.assert_not_called()


if __name__ == "__main__":
    unittest.main()
