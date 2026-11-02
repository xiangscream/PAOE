"""Stage-one entry/navigation contracts using real CLI and disposable Homes.

Native submission alone is stubbed; no paid model or production Home is used.
These tests do not establish that an LLM actually followed the work cycle.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
from urllib.parse import unquote

import test_headless

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "code" / "personal-agent-os" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import paos
from paos_todo import parse_todo


class StageOneEntryTests(unittest.TestCase):
    def setUp(self):
        # Compose the existing fixture without importing its TestCase as another
        # discoverable suite or duplicating the Home/registry implementation.
        self.f = test_headless.HeadlessTests(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.workflow = self.f.root / "workflow"
        self.skill = self.f.root / "skill"
        for relative in (
            "Workflows/wf-agent-work-cycle.md",
            "Guides/guide-work-method.md",
            "Guides/ops-entry.md",
            "Templates/workstation-todo.md",
        ):
            target = self.workflow / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "libraries" / "workflow" / relative, target)

    def new_home(self):
        import hashlib
        fingerprint = hashlib.sha256(self.f.record.read_bytes()).hexdigest()
        self.f.call("project", "home-add", "3002", "3002-s003",
                    "--expected-fingerprint", fingerprint)
        result = self.f.call("workstation", "init", "3002", "3002-s003")[1]
        return Path(result["workstation_path"])

    def test_real_cli_entry_uses_explicit_installation_and_registered_resources(self):
        home = self.new_home()
        text = (home / "ENTRY.md").read_text(encoding="utf-8")
        for expected in (str(self.f.install), str(SCRIPTS / "paos.py"),
                         str(self.workflow / "Guides" / "ops-entry.md"),
                         str(self.skill / "CATALOG.md"), str(self.f.tools)):
            self.assertIn(expected, text)
        self.assertIn("--installation-file", text)
        self.assertIn("#恢复", text)
        self.assertNotIn("C:\\Users\\remo", text)
        self.assertNotIn("/home/remo", text)
        self.assertNotIn("## 工作约定", text)
        self.assertIn("当前工作与项目", text)

    def test_rendered_cli_command_runs_from_other_directory_with_wrong_env(self):
        text = (self.new_home() / "ENTRY.md").read_text(encoding="utf-8")
        match = re.search(r"```(?:sh|powershell)\n([^\n]+)\n```", text)
        self.assertIsNotNone(match, text)
        command = match.group(1)
        if os.name == "nt":
            argv = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "$ErrorActionPreference='Stop'; " + command + " --json health; exit $LASTEXITCODE"]
        else:
            argv = [*shlex.split(command), "--json", "health"]
        result = subprocess.run(argv, cwd=self.f.root, env=dict(os.environ),
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(Path(data["installation"]), self.f.install)
        self.assertFalse(data["runtime_verified"])

    def test_existing_entry_and_human_todo_edits_survive_repeated_init(self):
        home = self.new_home()
        entry, todo = home / "ENTRY.md", home / "TODO.md"
        entry.write_text(entry.read_text(encoding="utf-8") + "\n人工备注：继续保留。\n", encoding="utf-8")
        todo.write_text(todo.read_text(encoding="utf-8").replace(
            "# Pinned\n", "# Pinned\n\n人工要求：本次只维护相关入口。\n", 1), encoding="utf-8")
        before = (entry.read_bytes(), todo.read_bytes())
        self.f.call("workstation", "init", "3002", "3002-s003")
        self.assertEqual(before, (entry.read_bytes(), todo.read_bytes()))

    def test_missing_project_notes_are_visible_not_created_for_navigation(self):
        home = self.new_home()
        text = (home / "ENTRY.md").read_text(encoding="utf-8")
        for name in ("INDEX.md", "TEAM.md", "AGENTS.md"):
            self.assertFalse((self.f.vault / name).exists())
            matching = [row for row in text.splitlines() if str(self.f.vault / name) in row]
            self.assertTrue(matching, name)
            self.assertTrue(any("不可读" in row for row in matching), matching)

    def test_initial_todo_routes_to_recovery_without_forcing_all_catalogs(self):
        todo = parse_todo((self.new_home() / "TODO.md").read_text(encoding="utf-8"))
        self.assertEqual(todo["schema"], "paos-todo/v4")
        self.assertIn("ENTRY", todo["current"]["next_action"])
        self.assertIn("恢复", todo["current"]["next_action"])
        self.assertNotIn("GUIDE / OPS", todo["current"]["next_action"])

    def test_resource_commands_use_registered_roots_not_sibling_assumptions(self):
        workflow = self.f.call("library", "search", "daily-intake", "--kind", "workflow")[1]
        self.assertIn(str(self.workflow / "Workflows" / "intake.md"),
                      json.dumps(workflow, ensure_ascii=False))
        destination = self.skill / "clean-writing" / "SKILL.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "libraries" / "skill" / "clean-writing" / "SKILL.md", destination)
        skill = self.f.call("library", "search", "clean-writing", "--kind", "skill")[1]
        self.assertIn(str(destination), json.dumps(skill, ensure_ascii=False))
        tools = self.f.call("library", "tools")[1]
        self.assertEqual(Path(tools["path"]), self.f.tools)
        self.assertEqual(tools["raw_markdown"], self.f.tools.read_text(encoding="utf-8"))

    def test_documented_rooter_route_delivers_and_reminds_once_without_fake_project(self):
        self.f.call("wake", "bind", "rooter", "rooter-001", "--driver", "opencode",
                    "--native-session-id", "ses_stage1_rooter")
        args = ("agent", "send", "3002", "--to", "rooter-001", "--sender-kind", "agent",
                "--sender-id", "3002-s001", "--subject", "安装协助", "--body", "请按原工位检查入口。",
                "--message-id", "stage1-rooter-help", "--remind")
        with patch.object(paos, "native_inject", return_value={
                "accepted": True, "runtime": "opencode", "session_id": "ses_stage1_rooter"}) as inject:
            first = self.f.call(*args)[1]
            self.f.call(*args)
        self.assertTrue(first["runtime_wake_performed"])
        inject.assert_called_once()
        self.assertEqual(inject.call_args.kwargs["target"]["session_id"], "ses_stage1_rooter")
        files = list((self.f.rooter / "mailbox").glob("*.md"))
        self.assertEqual(len(files), 1)
        self.assertIn("请按原工位检查入口。", files[0].read_text(encoding="utf-8"))
        self.assertEqual(self.f.call("attention", "rooter-show")[1]["home"]["home_kind"], "rooter")
        self.assertFalse((self.f.records / "rooter.json").exists())
        self.assertFalse((self.f.vault / "Workstations" / "rooter-001").exists())

    def test_changed_navigation_links_and_anchors_resolve(self):
        paths = [ROOT / "AGENTS.md"] + [ROOT / "libraries" / "workflow" / p for p in (
            "Guides/guide-work-method.md", "Guides/ops-entry.md",
            "Workflows/wf-agent-work-cycle.md", "Templates/workstation-entry.md",
            "Templates/workstation-todo.md")]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            # Templates' placeholder links describe layout, not live locators.
            for target in re.findall(r"\[[^\]\n]+\]\(([^)\n]+)\)", text):
                if "<" in target or "://" in target:
                    continue
                filename, _, fragment = unquote(target).partition("#")
                destination = (path.parent / filename).resolve() if filename else path
                with self.subTest(source=path.name, target=target):
                    self.assertTrue(destination.is_file(), str(destination))
                    if fragment:
                        headings = re.findall(r"^#{1,6} +(.+)$", destination.read_text(encoding="utf-8"), re.M)
                        anchors = {re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-") for h in headings}
                        self.assertIn(fragment, anchors)

    def test_todo_template_example_keeps_the_existing_v4_parser(self):
        text = (ROOT / "libraries" / "workflow" / "Templates" / "workstation-todo.md").read_text(encoding="utf-8")
        match = re.search(r"```markdown\n(.*?)\n```", text, re.S)
        self.assertIsNotNone(match)
        self.assertEqual(parse_todo(match.group(1) + "\n")["schema"], "paos-todo/v4")


if __name__ == "__main__":
    unittest.main()
