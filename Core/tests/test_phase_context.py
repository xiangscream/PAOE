"""A cold start reads source text, identifies missing inputs, and leaves the Home alone."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code" / "personal-agent-os" / "scripts"))
from paos_context import read_context
from paos_todo import render_todo


class ContextReadTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / "Workstations" / "S001"
        (self.home / "mailbox").mkdir(parents=True)
        self.ref = dict(
            project_root=str(self.root),
            home_path=str(self.home),
            home_id="S001",
            home_kind="project_agent",
        )
        (self.root / "AGENTS.md").write_text("[共同背景](background.md)", encoding="utf8")
        (self.root / "INDEX.md").write_text("Business outcome\n", encoding="utf8")
        (self.root / "TEAM.md").write_text("### S001\nReview\n### S002\nOther role\n", encoding="utf8")
        (self.root / "background.md").write_text("Why it matters", encoding="utf8")
        (self.home / "ENTRY.md").write_text("Start here", encoding="utf8")
        (self.home / "TODO.md").write_text(
            render_todo(
                home_kind="project_agent",
                home_id="S001",
                project_id="3002",
                objective="Read",
                next_action="Use the original",
                tasks=[
                    dict(id="T1", title="Read first message", source_refs=["mail:one"], state="doing"),
                    dict(id="T2", title="Other responsibility", state="todo"),
                ],
            ),
            encoding="utf8",
        )
        self.source = self.home / "mailbox" / "one.md"
        self.source.write_text("The actual request", encoding="utf8")

    def test_phase_includes_current_role_and_original_not_other_task(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        got = read_context(self.ref, staff_number="S001", task_id="T1", reason="compact")
        self.assertTrue(got["ok"], got["missing"])
        bodies = {d["kind"]: d["body"] for d in got["documents"]}
        self.assertEqual(bodies["input"], "The actual request")
        self.assertIn("Review", bodies["role"])
        self.assertNotIn("Other role", bodies["role"])
        self.assertIn("T1", bodies["task"])
        self.assertNotIn("Other responsibility", "\n".join(bodies.values()))
        self.assertEqual(
            before,
            {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()},
        )

    def test_missing_original_is_actionable_and_not_a_load_receipt(self):
        self.source.unlink()
        (self.home / "AGENTS.md").write_text("", encoding="utf8")
        got = read_context(self.ref, staff_number="S001", task_id="T1")
        self.assertTrue(got["ok"])
        self.assertEqual({x["kind"] for x in got["omitted"]}, {"home_rules", "input"})
        got = read_context(self.ref, staff_number="S001", task_id="T1", sources=["mail:one.md"])
        self.assertFalse(got["ok"])
        self.assertEqual(
            got["missing"], [{"kind": "input", "path": str(self.source), "reason": "missing"}]
        )
        self.assertTrue(any(d["kind"] == "background" for d in got["documents"]))

    def test_installation_home_has_no_project_team_or_index(self):
        rooter = dict(
            home_kind="rooter", home_id="rooter-001", home_path=str(self.home), project_root=""
        )
        (self.home / "AGENTS.md").write_text("[共同背景](../..//background.md)", encoding="utf8")
        (self.home / "TODO.md").write_text(
            render_todo(
                home_kind="rooter", home_id="rooter-001", objective="Maintain", next_action="Read"
            ),
            encoding="utf8",
        )
        got = read_context(rooter, staff_number="S035", sources=["mail:one.md"])
        self.assertTrue(got["ok"], got["missing"])
        self.assertEqual(
            {x["kind"] for x in got["documents"]}, {"guide", "entry", "current", "background", "input"}
        )

    def test_hook_follows_the_single_current_task_anchor(self):
        from paos_todo import update_todo_current

        update_todo_current(self.home / "TODO.md", {"context_refs": ["task:T1"]})
        got = read_context(self.ref, staff_number="S001")
        self.assertEqual(got["task_id"], "T1")
        self.assertTrue(
            any(d["kind"] == "task" and "Read first message" in d["body"] for d in got["documents"])
        )
