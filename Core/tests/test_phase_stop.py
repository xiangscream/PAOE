"""Stop decisions must not confuse free text, task waits and room presence."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code/personal-agent-os/scripts"))
from paos_phase_stop import on_stop
from paos_todo import render_todo


class PhaseStopTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.home = self.base / "S010"
        self.home.mkdir()
        self.ref = dict(home_path=str(self.home), home_id="S010")
        self.writes = []
        owner = self
        class Client:
            def request(self, method, path, body=None):
                owner.writes.append((method, path, body))
                return {"rooms": [dict(id="one", status="open", presence="online")]} if method == "GET" else {}
        self.client = Client()

    def todo(self, tasks=None, waiting="", inflight=""):
        (self.home / "TODO.md").write_text(render_todo(
            home_kind="project_agent", home_id="S010", project_id="3002", objective="Current",
            next_action="Continue current", waiting=waiting, inflight=inflight, context_refs=["task:T1"],
            tasks=tasks if tasks is not None else [dict(id="T1", title="Main", state="doing")]), encoding="utf-8")

    def stop(self, **args):
        return on_stop(self.base / "Data", self.ref, staff="S010", event=args.pop("event", "native-1"),
                       task_id="", interrupted=False, reentry=args.pop("reentry", False),
                       waiting_human=False, client=self.client, **args)

    def test_inflight_description_does_not_globally_stop_or_flicker_presence(self):
        for value in ("无。", "S034 is preparing a report", "background job is running"):
            self.todo(inflight=value)
            result = self.stop(event=value)
            self.assertEqual(result["action"], "continue")
            self.assertEqual(result["rooms_offline"], [])
        self.assertEqual(self.writes, [])

    def test_waiting_current_skips_to_independent_task(self):
        self.todo([dict(id="T1", title="Main", state="doing"), dict(id="T2", title="Independent", state="todo")],
                  waiting="Waiting for original author")
        result = self.stop()
        self.assertEqual(result["task_id"], "T2")
        self.assertIn("T2", result["next_action"])
        self.assertEqual(self.writes, [])

    def test_real_waiting_and_reentry_keep_existing_stop_boundary(self):
        self.todo(waiting="Human input")
        result = self.stop()
        self.assertEqual(result["action"], "stop")
        self.assertEqual(result["rooms_offline"], ["one"])
        self.assertEqual(self.stop(reentry=True)["reason"], "reentry")

    def test_same_native_event_is_not_reissued(self):
        self.todo()
        self.assertEqual(self.stop()["action"], "continue")
        self.assertEqual(self.stop()["reason"], "already_observed")
        self.assertEqual(self.stop(event="native-2")["action"], "continue")


if __name__ == "__main__":
    unittest.main()
