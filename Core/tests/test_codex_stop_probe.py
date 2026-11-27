"""Only validate the finite probe protocol; these are not Desktop results."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("codex_stop_probe", Path(__file__).parent / "manual/codex_stop_probe.py")
probe_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe_module)


class CodexStopProbeTests(unittest.TestCase):
    def test_two_blocks_then_stop_record_actual_supplied_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "evidence.jsonl"
            stop = root / "STOP"
            first = dict(session_id="trial", turn_id="native-1", hook_event_name="Stop", stop_hook_active=False)
            second = dict(first, turn_id="native-2", stop_hook_active=True)
            self.assertIn("PROBE-A", probe_module.probe(first, "trial", path, stop)["reason"])
            self.assertIn("PROBE-B", probe_module.probe(second, "trial", path, stop)["reason"])
            self.assertEqual(probe_module.probe(second, "trial", path, stop), {})
            self.assertEqual(probe_module.probe(second, "trial", path, stop), {})
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records[1]["event"]["turn_id"], "native-2")
            self.assertTrue(records[1]["event"]["stop_hook_active"])
            self.assertEqual(probe_module.probe(first, "other", path, stop), {})
            before = path.read_bytes()
            stop.touch()
            self.assertEqual(probe_module.probe(first, "trial", path, stop), {})
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
