"""Stage-two contact/resource discovery using disposable local PAOE fixtures.

Read-only discovery never probes the native Runtime or touches production Homes.
Existing Mail/Notice delivery is covered by the independent headless suite.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import test_headless

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "code" / "personal-agent-os" / "scripts" / "paos.py"


class StageTwoDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.f = test_headless.HeadlessTests(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()

    def snapshot(self):
        return {str(path.relative_to(self.f.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.f.root.rglob("*") if path.is_file()}

    def test_peers_find_registered_roles_and_separate_rooter_without_writes(self):
        team = self.f.vault / "TEAM.md"
        team.write_text(
            "# Team\n\n## 当前成员\n\n### 3002-s001\n- 职责/专长：总体组织\n"
            "### 3002-s002\n- 职责/专长：接口、测试与日志\n"
            "## 历史与变化\n### 3002-s003\n- 职责/专长：过期角色\n",
            encoding="utf-8",
        )
        ghost = self.f.vault / "Workstations" / "3002-s099"
        self.f.make_home(ghost, "3002-s099", "3002")
        original = self.snapshot()
        peers = self.f.call("peers", "3002", "3002-s001")[1]
        self.assertEqual([row["agent_id"] for row in peers["peers"]], ["3002-s002"])
        self.assertEqual(peers["peers"][0]["role_summary"], "接口、测试与日志")
        self.assertEqual(peers["peers"][0]["role_source"], str(team))
        self.assertTrue(peers["team_source"]["exists"])
        self.assertEqual(peers["coordinator_home_id"], "3002-s001")
        self.assertEqual(peers["roster_filter"], "fixed_workstation")
        self.assertEqual(peers["roster_scope"], "project_registry")
        support = peers["installation_support"]
        self.assertEqual(len(support), 1)
        self.assertEqual(support[0]["agent_id"], "rooter-001")
        self.assertEqual(support[0]["scope"], "installation")
        self.assertTrue(support[0]["entry_exists"])
        self.assertEqual(support[0]["runtime_state"], "not_probed")
        self.assertNotIn("rooter-001", [row["agent_id"] for row in peers["peers"]])
        self.assertEqual(original, self.snapshot())

    def test_team_and_plain_peers_expose_same_authoritative_contact_routes(self):
        team = self.f.vault / "TEAM.md"
        team.write_text("# Team\n\n## 当前成员\n### 3002-s002\n- 职责/专长：影像设备联调\n",
                        encoding="utf-8")
        result = self.f.call("team", "3002", "3002-s001")[1]
        self.assertEqual([row["agent_id"] for row in result["agents"]], ["3002-s001", "3002-s002"])
        self.assertEqual(result["agents"][1]["role_summary"], "影像设备联调")
        self.assertEqual(result["installation_support"][0]["home_path"], str(self.f.rooter))
        self.assertNotIn("rooter-001", [row["agent_id"] for row in result["agents"]])
        # The exact same code path renders human-readable routes without writing.
        import io
        import contextlib
        scripts = ROOT / "code" / "personal-agent-os" / "scripts"
        sys.path.insert(0, str(scripts))
        import paos
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(paos.main(["--installation-file", str(self.f.install),
                                        "peers", "3002", "3002-s001"]), 0)
        self.assertIn("Role / expertise (TEAM): 影像设备联调", out.getvalue())
        self.assertIn("Installation support: rooter-001", out.getvalue())

    def test_unregistered_rooter_and_absent_team_do_not_fabricate_contacts(self):
        config = json.loads(self.f.install.read_text(encoding="utf-8"))
        config["rooter_home"] = ""
        self.f.install.write_text(json.dumps(config), encoding="utf-8")
        peers = self.f.call("peers", "3002", "3002-s001")[1]
        self.assertEqual(peers["installation_support"], [])
        self.assertFalse(peers["team_source"]["exists"])
        self.assertEqual(peers["peers"][0]["role_summary"], "")
        self.assertFalse((self.f.vault / "TEAM.md").exists())

    def test_library_search_points_to_authoritative_source_not_copy(self):
        response = self.f.call("library", "search", "daily-intake", "--kind", "workflow")[1]
        found = next(item for item in response["items"] if item["id"] == "daily-intake")
        source = self.f.root / "workflow" / "Workflows" / "intake.md"
        self.assertEqual(found["relative_path"], "Workflows/intake.md")
        self.assertEqual(found["source_locator"], str(source).replace("\\", "/"))
        self.assertEqual(Path(found["source_path"]), source)
        self.assertEqual(Path(found["source_path"]).read_bytes(), source.read_bytes())
        self.assertEqual(found["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())

    def test_cli_help_has_contact_routes_and_library_source_semantics(self):
        for args, terms in [
            (("peers", "--help"), ("TEAM.md", "rooter-001", "no native probe")),
            (("team", "--help"), ("TEAM.md", "Rooter", "no native probe")),
            (("agent", "send", "--help"), ("sender context", "rooter-001", "--remind")),
            (("library", "search", "--help"), ("source_locator", "--kind")),
            (("library", "tools", "--help"), ("installed", "authorized")),
        ]:
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, str(CLI), *args], cwd=self.f.root,
                                        env=dict(os.environ), text=True, capture_output=True,
                                        encoding="utf-8", timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                for term in terms:
                    self.assertIn(term, result.stdout)


if __name__ == "__main__":
    unittest.main()
