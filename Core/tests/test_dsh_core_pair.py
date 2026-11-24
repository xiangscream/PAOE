"""Check the installed DSH message SDK against an isolated, real PAOE CLI, without a model call."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "code/personal-agent-os/scripts"
sys.path.insert(0, str(SCRIPTS))
from paos_installation import write_installation_descriptor
from paos_registry import ProjectRegistry
from paos_todo import render_todo


@unittest.skipUnless(
    os.environ.get("DSH_INSTALL_DIR") and shutil.which("node"), "requires the installed DSH and Node"
)
class DshCorePair(unittest.TestCase):
    def test_registered_session_reads_and_checks_its_real_core_originals(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            project = root / "project"
            home = project / "Workstations/S841"
            home.mkdir(parents=True)
            install = root / "installation.json"
            numbers = root / "numbers.json"
            numbers.write_text('{"3997-s001":"S841"}', encoding="utf-8")
            write_installation_descriptor(
                install,
                source_root=str(SCRIPTS.parent),
                data_root=str(root / "Data"),
                library_roots_config=str(root / "libraries.json"),
                agent_numbers_config=str(numbers),
            )
            ProjectRegistry(install).register(
                "3997", root_path=str(project), homes=["S841"], coordinator_home_id="S841"
            )
            for path, body in (
                (project / "AGENTS.md", "[共同背景](background.md)"),
                (project / "background.md", "SYNTHETIC-BACKGROUND-END"),
                (project / "INDEX.md", "Synthetic project"),
                (project / "TEAM.md", "### S841\nRead the originals"),
                (home / "ENTRY.md", "Original synthetic Home"),
            ):
                path.write_text(body, encoding="utf-8")
            (home / "TODO.md").write_text(
                render_todo(
                    home_kind="project_agent",
                    home_id="S841",
                    project_id="3997",
                    objective="Review the guide",
                    next_action="Continue the original task",
                    context_refs=["task:T1"],
                    tasks=[dict(id="T1", state="doing", title="TASK-ORIGINAL-END")],
                ),
                encoding="utf-8",
            )
            config = root / "target.json"
            config.write_text(
                json.dumps(
                    {"receiver_file": str(root / "receiver.json"), "stop_file": str(root / "STOP")}
                ),
                encoding="utf-8",
            )
            cli = [
                sys.executable,
                "-X",
                "utf8",
                "-B",
                str(SCRIPTS / "paos.py"),
                "--installation-file",
                str(install),
                "--json",
            ]
            bound = subprocess.run(
                [
                    *cli,
                    "wake",
                    "bind",
                    "3997",
                    "S841",
                    "--driver",
                    "dsh",
                    "--native-session-id",
                    "fixture-dsh-session",
                    "--driver-config",
                    str(config),
                ],
                capture_output=True,
                encoding="utf-8",
            )
            self.assertEqual(bound.returncode, 0, bound.stdout + bound.stderr)
            runner = Path(__file__).with_name("dsh_host_pair.mjs")
            result = subprocess.run(
                ["node", str(runner), str(install), sys.executable],
                capture_output=True,
                encoding="utf-8",
                timeout=40,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            trace_file = root / "Data/runtime/dsh-context/S841/events.jsonl"
            rows = [json.loads(line) for line in trace_file.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([r["action"] for r in rows].count("request_checked"), 2)
            self.assertEqual([r["action"] for r in rows].count("originals_read"), 1)
            self.assertEqual(rows[-1]["task"], "T1")
            self.assertNotIn("SYNTHETIC-BACKGROUND-END", trace_file.read_text(encoding="utf-8"))
