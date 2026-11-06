"""Test generated ENTRY/TODO and Library discovery with disposable Homes.

The fixtures create external libraries from scratch; tests must not depend on
the long-retired library copies bundled in Core.  Native submission alone is
mocked; no model, production Home or real CAT service is required.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
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
from paos_todo import parse_todo, render_todo
from paos_library import ensure_workflow_library, ensure_skill_library, register_library_roots


def normalized_path(value):
    return str(value).replace("\\", "/")


class StageOneEntryTests(unittest.TestCase):
    def setUp(self):
        # Compose the existing fixture without importing its TestCase as another
        # discoverable suite or duplicating the Home/registry implementation.
        self.f = test_headless.HeadlessTests(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        (self.f.root / "numbers.json").write_text(json.dumps({
            "3002-s001": "S001", "3002-s002": "S002"
        }), encoding="utf-8")
        self.workflow = self.f.root / "workflow"
        self.skill = self.f.root / "skill"
        # An initialized external Library is enough.  The ENTRY generator
        # chooses System/Guide for work rules, not any of these documents.
        for relative in ("Guides/example.md", "Workflows/example.md"):
            target = self.workflow / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# external fixture\n", encoding="utf-8")
        # A portable checkout outside System needs an explicit Guide locator.
        # Never let this fixture depend on directories beside the test checkout.
        self.guide = self.f.root / 'System Guide'
        self.guide.mkdir()
        for name in ('README.md', 'guide-work-method.md', 'ops-entry.md'):
            (self.guide / name).write_text('# '+name+'\n', encoding='utf-8')

    def new_home(self):
        fingerprint = hashlib.sha256(self.f.record.read_bytes()).hexdigest()
        self.f.call("project", "home-add", "3002", "3002-s003",
                    "--expected-fingerprint", fingerprint)
        result = self.f.call("workstation", "init", "3002", "3002-s003",
                             "--guide-root", str(self.guide))[1]
        return Path(result["workstation_path"])

    def test_real_cli_entry_uses_explicit_installation_and_registered_resources(self):
        home = self.new_home()
        text = (home / "ENTRY.md").read_text(encoding="utf-8")
        for expected in (self.f.install, SCRIPTS / "paos.py",
                         self.guide / "ops-entry.md",
                         self.skill / "CATALOG.md", self.f.tools):
            self.assertIn(normalized_path(expected), normalized_path(text))
        self.assertIn("--installation-file", text)
        self.assertIn("# Fixture", text)
        self.assertIn(normalized_path(self.guide / "README.md"), normalized_path(text))
        self.assertNotIn("wf-agent-work-cycle.md", text)
        self.assertNotIn("C:/Users/remo", normalized_path(text))
        self.assertNotIn("/home/remo", text)
        self.assertNotIn("## 工作约定", text)
        self.assertIn("当前工作与项目", text)

    def test_guide_root_can_be_explicit_and_is_not_the_workflow_library(self):
        guide = self.guide
        fingerprint = hashlib.sha256(self.f.record.read_bytes()).hexdigest()
        self.f.call('project', 'home-add', '3002', '3002-s003',
                    '--expected-fingerprint', fingerprint)
        result = self.f.call('workstation', 'init', '3002', '3002-s003',
                             '--guide-root', str(guide))[1]
        text = Path(result['workstation_path'], 'ENTRY.md').read_text(encoding='utf-8')
        self.assertIn(normalized_path(guide / 'ops-entry.md'), normalized_path(text))
        self.assertNotIn('wf-agent-work-cycle.md', text)
        self.assertNotIn(normalized_path(self.workflow / 'Guides' / 'ops-entry.md'), normalized_path(text))

    def test_retired_protocols_root_is_explicit_error(self):
        rc, data = self.f.call('workstation', 'init', '3002', '3002-s001',
                               '--protocols-root', str(self.workflow), ok=False)
        self.assertNotEqual(rc, 0)
        self.assertEqual(data['error_code'], 'workstation_protocols_root_retired')

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
        text = normalized_path((home / "ENTRY.md").read_text(encoding="utf-8"))
        for name in ("INDEX.md", "TEAM.md", "AGENTS.md"):
            self.assertFalse((self.f.vault / name).exists())
            matching = [row for row in text.splitlines() if normalized_path(self.f.vault / name) in row]
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
        item = next(row for row in workflow["items"] if row["id"] == "daily-intake")
        self.assertEqual(item["library_kind"], "workflow")
        self.assertEqual(item["relative_path"], "Workflows/intake.md")
        original = self.workflow / item["relative_path"]
        self.assertEqual(item["source_sha256"], hashlib.sha256(original.read_bytes()).hexdigest())
        destination = self.skill / "clean-writing" / "SKILL.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            "---\nschema: paos-skill/v1\nid: clean-writing\ntitle: Clean Writing\n"
            "description: Improve work documents\ntags: writing\nversion: 1\n"
            "status: active\n---\n# Clean Writing\n", encoding="utf-8")
        skill = self.f.call("library", "search", "clean-writing", "--kind", "skill")[1]
        item = next(row for row in skill["items"] if row["id"] == "clean-writing")
        self.assertEqual(item["library_kind"], "skill")
        self.assertEqual(self.skill / item["relative_path"], destination)
        self.assertEqual(item["source_sha256"], hashlib.sha256(destination.read_bytes()).hexdigest())
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
        # Only live Source documentation belongs to this test.  System/Guide
        # has its own link check in the System release workflow.
        paths = [ROOT / 'code/personal-agent-os/AGENTS.md',
                 ROOT / 'code/personal-agent-os/README.md']
        for path in paths:
            text = path.read_text(encoding="utf-8")
            # Code examples describe generated documents, not links in this file.
            text = re.sub(r"```.*?```", "", text, flags=re.S)
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
        # The generated Home TODO is the test target, not a copied workflow
        # template or a second source of the TODO contract.
        text = (self.new_home() / "TODO.md").read_text(encoding="utf-8")
        self.assertEqual(parse_todo(text)["schema"], "paos-todo/v4")


    def run_generated_entry(self, home, *args, env=None):
        """Execute the actual ENTRY command from the Home, not the fixture's helper."""
        entry = (home / "ENTRY.md").read_text(encoding="utf-8")
        match = re.search(r"```(?:sh|powershell)\n([^\n]+)\n```", entry)
        self.assertIsNotNone(match, entry)
        command = match.group(1)
        if os.name == "nt":
            suffix = " ".join("'" + item.replace("'", "''") + "'" for item in ("--json", *args))
            argv = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "$ErrorActionPreference='Stop'; " + command + " " + suffix + "; exit $LASTEXITCODE"]
        else:
            argv = [*shlex.split(command), "--json", *args]
        result = subprocess.run(argv, cwd=home, env=env if env is not None else dict(os.environ),
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_relative_installation_file_is_pinned_before_entry_is_written(self):
        fingerprint = hashlib.sha256(self.f.record.read_bytes()).hexdigest()
        self.f.call("project", "home-add", "3002", "3002-s003",
                    "--expected-fingerprint", fingerprint)
        env = dict(os.environ, PAOS_INSTALLATION_FILE=str(self.f.root / "wrong-installation.json"),
                   PAOS_LIBRARY_ROOTS_CONFIG="")
        process = subprocess.run([sys.executable, str(SCRIPTS / "paos.py"),
                                  "--installation-file", "installation.json", "--json",
                                  "workstation", "init", "3002", "3002-s003",
                                  "--entry-template", str(self.f.entry_template)],
                                 cwd=self.f.root, env=env, capture_output=True, text=True,
                                 encoding="utf-8", timeout=30)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        home = Path(json.loads(process.stdout)["workstation_path"])
        entry = (home / "ENTRY.md").read_text(encoding="utf-8")
        self.assertIn(normalized_path(self.f.install), normalized_path(entry))
        self.assertIn("--library-roots-config", entry)
        # A same-named descriptor in the new CWD must not hijack this Home.
        (home / "installation.json").write_text("{}", encoding="utf-8")
        installed = self.run_generated_entry(home, "health", env=env)
        self.assertEqual(Path(installed["installation"]), self.f.install)
        roots = self.run_generated_entry(home, "library", "roots", "show", env=env)
        self.assertEqual(Path(roots["config_path"]), self.f.libconfig)

    def test_generated_entry_pins_roots_even_with_conflicting_valid_env(self):
        home = self.new_home()
        alternate_workflow = self.f.root / "other-workflow"
        alternate_skill = self.f.root / "other-skill"
        ensure_workflow_library(alternate_workflow)
        ensure_skill_library(alternate_skill)
        (alternate_workflow / "Workflows" / "other.md").write_text(
            "---\nschema: paos-workflow/v1\nid: only-in-b\ntitle: B method\n"
            "description: An unrelated library\nstatus: active\n---\n# B\n",
            encoding="utf-8")
        alternate_config = self.f.root / "other-library-roots.json"
        register_library_roots(alternate_config, workflow_root=alternate_workflow,
                               skill_root=alternate_skill)
        env = dict(os.environ,
                   PAOS_LIBRARY_ROOTS_CONFIG=str(alternate_config),
                   PAOS_INSTALLATION_FILE=str(self.f.root / "wrong-installation.json"))
        entry = (home / "ENTRY.md").read_text(encoding="utf-8")
        self.assertIn(normalized_path(self.workflow), normalized_path(entry))
        self.assertNotIn(normalized_path(alternate_workflow), normalized_path(entry))
        roots = self.run_generated_entry(home, "library", "roots", "show", env=env)
        self.assertEqual(Path(roots["config_path"]), self.f.libconfig)
        self.assertEqual(Path(roots["workflow_root"]), self.workflow)
        a = self.run_generated_entry(home, "library", "search", "daily-intake",
                                     "--kind", "workflow", env=env)
        self.assertEqual([item["id"] for item in a["items"]], ["daily-intake"])
        b = self.run_generated_entry(home, "library", "search", "only-in-b",
                                     "--kind", "workflow", env=env)
        self.assertEqual(b["match_count"], 0)

if __name__ == "__main__":
    unittest.main()
