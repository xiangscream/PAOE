"""Round trip through the public CLI, including a replay after later work."""

import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "code/personal-agent-os/scripts"
sys.path.insert(0, str(SCRIPTS))
from paos_cat_activation import CatActivationProblem
from paos_installation import write_installation_descriptor
from paos_phase_cli import DEFAULT_CAT_URL, add_phase_parsers, execute_phase
from paos_registry import ProjectRegistry
from paos_stage import deliver
from paos_todo import parse_todo, render_todo


class StageCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
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

    def _execute_args(self, **overrides):
        values = dict(
            command="stage",
            stage_command="deliver",
            home="S010",
            task="EX",
            operation="example",
            artifact=["out.md"],
            intent=["original.md"],
            result="First result",
            next_action="Review it",
            waiting="",
            current=False,
            cat_url=DEFAULT_CAT_URL,
            full_result=False,
        )
        values.update(overrides)
        return SimpleNamespace(**values)

    def _add_cat_role(self):
        doc = parse_todo(self.todo.read_text(encoding="utf8"))
        doc["tasks"][0]["source_refs"] = ["cat-role:room-one"]
        self.todo.write_text(
            render_todo(
                home_kind=doc["home_kind"],
                home_id=doc["home_id"],
                project_id=doc["project_id"],
                pinned=doc["pinned"],
                tasks=doc["tasks"],
                **doc["current"],
            ),
            encoding="utf8",
        )

    def test_stage_and_context_read_default_existing_cat_endpoint(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command", required=True)
        add_phase_parsers(sub)
        stage = parser.parse_args(
            ["stage", "deliver", "S010", "--task", "EX", "--id", "example",
             "--artifact", "out.md", "--intent", "original.md",
             "--result", "r", "--next", "n"]
        )
        read = parser.parse_args(["context", "read", "S010", "--task", "EX"])
        self.assertEqual(stage.cat_url, DEFAULT_CAT_URL)
        self.assertEqual(read.cat_url, DEFAULT_CAT_URL)

    def test_stage_cat_failure_returns_missing_and_sources_without_bodies(self):
        self._add_cat_role()
        before = self.todo.read_bytes()
        args = self._execute_args()
        failure = CatActivationProblem(
            "cat_unreachable", "CAT unreachable", {"path": "/api/rooms/room-one/team"}
        )
        with patch("paos_phase_cli.live_role", side_effect=failure):
            result = execute_phase(
                args,
                self.install,
                lambda home, installation_path: {"staff_number": "S010"},
                lambda url, service: None,
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "stage_context_incomplete")
        self.assertEqual(result["missing"][0]["reason"], "cat_unreachable")
        self.assertTrue(result["read_hint"].startswith("paos context read S010"))
        self.assertFalse(result["context"]["ok"])
        self.assertEqual(result["context"]["reason"], "stage")
        self.assertIn("references", result["context"])
        self.assertNotIn("body", result["context"]["documents"][0])
        self.assertTrue(all("body" not in source for source in result["sources"]))
        self.assertEqual(before, self.todo.read_bytes())

    def test_stage_full_result_keeps_full_context_only_when_requested(self):
        self._add_cat_role()
        args = self._execute_args(full_result=True)
        failure = CatActivationProblem("cat_unreachable", "CAT unreachable")
        with patch("paos_phase_cli.live_role", side_effect=failure):
            result = execute_phase(
                args,
                self.install,
                lambda home, installation_path: {"staff_number": "S010"},
                lambda url, service: None,
            )
        self.assertIn("body", result["context"]["documents"][0])
        self.assertTrue(all("body" not in source for source in result["sources"]))

    def test_delivery_replay_and_consume_after_later_edits(self):
        large_original = "Current business\n" * 20000
        (self.project / "INDEX.md").write_text(large_original, encoding="utf8")
        got = self.cli(*self.args)
        self.assertTrue(got["ok"])
        self.assertEqual(got["schema"], "paoe-stage-delivery/v1")
        self.assertNotIn("context", got)
        self.assertLess(len(json.dumps(got)), 2048)
        context = self.cli("context", "read", "S010", "--task", "EX", "--reason", "stage")
        self.assertTrue(context["ok"])
        self.assertTrue(all("body" in original for original in context["documents"]))
        self.assertIn(large_original, [original["body"] for original in context["documents"]])
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

    def test_registered_cross_project_source_and_saved_versions(self):
        experience = self.root / "experience"
        experience.mkdir()
        artifact = experience / "topic.md"
        artifact.write_text("Human approved topic", encoding="utf-8")
        ProjectRegistry(self.install).register(
            "3005", root_path=str(experience), homes=["S072"], coordinator_home_id="S072"
        )
        args = self.args.copy()
        args[args.index("--artifact") + 1] = str(artifact)
        got = self.cli(*args)
        self.assertTrue(got["ok"])
        self.assertIn(str(artifact), got["sources"])
        rows = self.cli("content", "changes")["changes"]
        seq = next(row["seq"] for row in rows if row["locator"] == str(artifact))
        artifact.write_text("New human edit", encoding="utf-8")
        self.assertEqual(self.cli("content", "show", str(seq))["after"]["body"], "Human approved topic")
        self.assertTrue(self.cli(*args)["replayed"])
        self.cli("content", "consume", "S010", "--through", str(rows[-1]["seq"]), "--result-ref", str(artifact))
        self.assertEqual(self.cli("content", "status", "S010")["pending_count"], 0)
        self.assertEqual(self.cli("content", "changes", "--home", "S010")["changes"], [])

    def test_unregistered_source_does_not_mutate_task(self):
        artifact = self.root / "not-registered.md"
        artifact.write_text("Outside registered content", encoding="utf-8")
        args = self.args.copy()
        args[args.index("--artifact") + 1] = str(artifact)
        before = self.todo.read_bytes()
        got = self.cli(*args, expected=1)
        self.assertIn("所选项目原件不可读", got["error"])
        self.assertEqual(self.todo.read_bytes(), before)
        self.assertEqual(self.cli("content", "changes")["changes"], [])

    def test_rooter_can_deliver_registered_project_originals(self):
        rooter = self.root / "rooter"
        rooter.mkdir()
        descriptor = json.loads(self.install.read_text(encoding="utf-8"))
        descriptor["rooter_home"] = str(rooter)
        self.install.write_text(json.dumps(descriptor), encoding="utf-8")
        Path(descriptor["agent_numbers_config"]).write_text(
            json.dumps({"3002-s010": "S010", "rooter-001": "S035"}), encoding="utf-8"
        )
        (rooter / "AGENTS.md").write_text("[共同背景](background.md)", encoding="utf-8")
        (rooter / "background.md").write_text("Shared background", encoding="utf-8")
        (rooter / "ENTRY.md").write_text("Rooter entry", encoding="utf-8")
        (rooter / "TODO.md").write_text(render_todo(
            home_kind="rooter", home_id="rooter-001", project_id="", objective="Deliver",
            next_action="Save the approved design", context_refs=["task:EX"],
            tasks=[dict(id="EX", title="EXM design", state="doing")]), encoding="utf-8")
        args = self.args.copy()
        args[2] = "S035"
        args[args.index("--artifact") + 1] = str(self.project / "out.md")
        args[args.index("--intent") + 1] = str(self.project / "original.md")
        got = self.cli(*args)
        self.assertTrue(got["ok"])
        self.assertEqual(got["home_id"], "rooter-001")
        self.assertEqual(parse_todo((rooter / "TODO.md").read_text(encoding="utf-8"))["tasks"][0]["result"], "First result")

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
        presence = self.cli(*args, "--presence-only")
        self.assertEqual((presence["action"], presence["reason"]), ("stop", "presence_only"))
        self.assertEqual(self.cli(*args, "--interrupted")["action"], "stop")
        self.assertEqual(self.cli(*args)["action"], "continue")
        self.assertEqual(self.cli(*args)["action"], "stop")
        self.assertEqual(self.cli(*args, "--reentry")["action"], "stop")
        self.assertEqual(parse_todo(self.todo.read_text(encoding="utf8"))["tasks"][0]["state"], "doing")
