"""Round trip through the public CLI, including a replay after later work."""

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "code/personal-agent-os/scripts"
sys.path.insert(0, str(SCRIPTS))
from paos_installation import write_installation_descriptor
from paos_registry import ProjectRegistry
from paos_stage import deliver
from paos_todo import parse_todo, render_todo


class StageCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.project = self.root / "p"
        self.home = self.project / "Workstations" / "S010"
        self.home.mkdir(parents=True)
        self.data = self.root / "data"
        self.install = self.root / "install.json"
        numbers = self.root / "numbers.json"
        numbers.write_text('{"3002-s010":"S010"}', encoding="utf8")
        write_installation_descriptor(
            self.install,
            source_root=str(SCRIPTS.parent),
            data_root=str(self.data),
            library_roots_config=str(self.root / "libraries.json"),
            agent_numbers_config=str(numbers),
        )
        ProjectRegistry(self.install).register(
            "3002", root_path=str(self.project), homes=["S010"], coordinator_home_id="S010"
        )
        for rel, text in {
            "AGENTS.md": "[共同背景](background.md)",
            "TEAM.md": "### S010\nLead",
            "INDEX.md": "Current business",
            "background.md": "Background",
            "Workstations/S010/ENTRY.md": "Read the guide",
            "original.md": "Human request",
            "out.md": "Reviewed finding",
        }.items():
            (self.project / rel).write_text(text, encoding="utf8")
        self.todo = self.home / "TODO.md"
        self.todo.write_text(
            render_todo(
                home_kind="project_agent",
                home_id="S010",
                project_id="3002",
                objective="Discuss",
                next_action="Deliver result",
                context_refs=["task:EX"],
                tasks=[dict(id="EX", title="One work item", state="doing")],
            ),
            encoding="utf8",
        )
        self.args = [
            "stage",
            "deliver",
            "S010",
            "--task",
            "EX",
            "--id",
            "example",
            "--artifact",
            "out.md",
            "--intent",
            "original.md",
            "--result",
            "First result",
            "--next",
            "Review it",
        ]

    def cli(self, *args, expected=0):
        p = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-B",
                str(SCRIPTS / "paos.py"),
                "--installation-file",
                str(self.install),
                "--json",
                *args,
            ],
            capture_output=True,
            text=True,
            encoding="utf8",
        )
        self.assertEqual(p.returncode, expected, p.stderr + p.stdout)
        return json.loads(p.stdout or p.stderr)

    def test_delivery_replay_and_consume_after_later_edits(self):
        got = self.cli(*self.args)
        self.assertTrue(got["context"]["ok"])
        doc = parse_todo(self.todo.read_text(encoding="utf8"))
        self.assertEqual(doc["tasks"][0]["state"], "doing")
        self.assertEqual(doc["current"]["next_action"], "Review it")
        changes = self.cli("content", "changes")
        self.assertEqual(len(changes["changes"]), 2)
        self.assertTrue(
            self.cli(
                "content",
                "consume",
                "S010",
                "--through",
                str(changes["cursor"]),
                "--result-ref",
                "out.md",
            )["ok"]
        )
        (self.project / "out.md").write_text("Later version", encoding="utf8")
        before = self.todo.read_bytes()
        self.assertTrue(self.cli(*self.args)["replayed"])
        self.assertEqual(self.todo.read_bytes(), before)
        different = self.args.copy()
        different[-1] = "Overwrites newer work"
        self.cli(*different, expected=1)
        self.assertEqual(len(self.cli("content", "changes")["changes"]), 2)

    def test_missing_source_has_no_task_or_content_effect(self):
        before = self.todo.read_bytes()
        (self.project / "out.md").unlink()
        self.cli(*self.args, expected=1)
        self.assertEqual(before, self.todo.read_bytes())
        self.assertEqual(self.cli("content", "changes")["changes"], [])

    def test_failure_after_todo_publishes_each_original_once_on_resume(self):
        home = dict(
            home_kind="project_agent",
            home_id="S010",
            project_id="3002",
            home_path=str(self.home),
            project_root=str(self.project),
        )
        kwargs = dict(
            task_id="EX",
            operation="example",
            artifacts=["out.md"],
            intents=["original.md"],
            result="First result",
            next_action="Review it",
            waiting="",
            current=False,
        )
        with patch("paos_stage.record_version", side_effect=sqlite3.OperationalError("interrupted")):
            with self.assertRaises(sqlite3.OperationalError):
                deliver(self.data, home, **kwargs)
        before = self.todo.read_bytes()
        self.assertEqual(self.cli("content", "changes")["changes"], [])
        self.cli(*self.args)
        self.assertEqual(before, self.todo.read_bytes())
        self.assertEqual(len(self.cli("content", "changes")["changes"]), 2)

    def test_stop_only_continues_active_unblocked_work_once(self):
        args = ["context", "stop", "S010", "--event", "run.1"]
        self.assertEqual(self.cli(*args, "--interrupted")["action"], "stop")
        self.assertEqual(self.cli(*args)["action"], "continue")
        self.assertEqual(self.cli(*args)["action"], "stop")
        self.assertEqual(self.cli(*args, "--reentry")["action"], "stop")
        self.assertEqual(parse_todo(self.todo.read_text(encoding="utf8"))["tasks"][0]["state"], "doing")
