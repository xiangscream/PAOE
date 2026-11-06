"""Portable bootstrap contracts with synthetic *external* Libraries.

Learning notes: ``setUp`` is a fixture factory; each test starts with fresh
paths, so failures never risk a real Home.  Assertions on before/after bytes
are more useful than just asserting an exception for safety-critical writers.
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import portable


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = (Path(self.temp.name) / "portable source").resolve()
        (self.root / "config").mkdir(parents=True)
        for name in portable.SCHEMAS:
            shutil.copyfile(portable.ROOT / "config" / f"{name}.example.json",
                            self.root / "config" / f"{name}.example.json")
        cli = self.root / "code/personal-agent-os/scripts/paos.py"
        cli.parent.mkdir(parents=True)
        cli.write_text("# synthetic CLI\n", encoding="utf-8")
        self.external = (Path(self.temp.name) / "independent libraries").resolve()
        self.workflow = self.external / "workflow"
        self.skill = self.external / "skill"
        for root in (self.workflow, self.skill):
            root.mkdir(parents=True)
            (root / "README.md").write_text("# fixture\n", encoding="utf-8")
        for dirname in ("Guides", "Workflows", "Templates", ".paos"):
            (self.workflow / dirname).mkdir()
        for dirname in (".paos", ".paos/usage-events"):
            (self.skill / dirname).mkdir(parents=True, exist_ok=True)
        self.tool = self.external / "tools.md"
        self.tool.write_text("# Tool Catalog\n", encoding="utf-8")

    def snapshot(self, root=None):
        root = root or self.root
        return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def init(self, **kwargs):
        return portable.initialize(self.root, workflow_root=str(self.workflow),
                                   skill_root=str(self.skill), **kwargs)

    def configured(self):
        return portable.configured_pair(self.root, portable.expected_configs(self.root))

    def change_template(self, name="installation", **fields):
        path = self.root / "config" / f"{name}.example.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(fields)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_plan_is_read_only_and_has_no_fake_library_paths(self):
        before = self.snapshot()
        config = portable.expected_configs(self.root)
        self.assertEqual(config["library-roots"]["workflow_root"], "")
        self.assertEqual(config["library-roots"]["skill_root"], "")
        self.assertEqual(before, self.snapshot())

    def test_plan_does_not_depend_on_cwd(self):
        cwd = Path.cwd()
        try:
            os.chdir(self.temp.name)
            self.assertEqual(portable.expected_configs(self.root)["installation"]["data_root"],
                             str(self.root / "data"))
        finally:
            os.chdir(cwd)

    def test_init_requires_explicit_registered_external_roots(self):
        before = self.snapshot()
        with self.assertRaises(portable.PortableError):
            portable.initialize(self.root)
        self.assertEqual(before, self.snapshot())

    def test_init_writes_pair_and_only_local_data(self):
        outside = self.snapshot(self.external)
        result = self.init()
        self.assertTrue(result["created"])
        config = self.configured()
        self.assertEqual(config["library-roots"]["workflow_root"], str(self.workflow))
        self.assertEqual(config["library-roots"]["skill_root"], str(self.skill))
        self.assertTrue(config["library-roots"]["registered_at"])
        self.assertEqual(list((self.root / "data").iterdir()), [])
        self.assertEqual(outside, self.snapshot(self.external))
        self.assertFalse((self.root / "libraries").exists())

    def test_tool_catalog_is_optional_or_explicit(self):
        self.init(tool_catalog=str(self.tool))
        self.assertEqual(self.configured()["library-roots"]["tool_catalog"], str(self.tool))
        self.assertTrue(portable.doctor(self.root)["configuration_ok"])

    def test_repeated_init_without_roots_preserves_original_bytes(self):
        self.init()
        before = self.snapshot()
        self.assertFalse(portable.initialize(self.root)["created"])
        self.assertEqual(before, self.snapshot())

    def test_external_library_cannot_be_core_owned(self):
        internal = self.root / "fake-workflow"
        shutil.copytree(self.workflow, internal)
        with self.assertRaises(portable.PortableError):
            portable.initialize(self.root, workflow_root=str(internal), skill_root=str(self.skill))
        self.assertFalse(portable.local_dir(self.root).exists())

    def test_missing_external_library_is_rejected_without_repair(self):
        (self.skill / ".paos/usage-events").rmdir()
        outside = self.snapshot(self.external)
        with self.assertRaises(portable.PortableError):
            self.init()
        self.assertEqual(outside, self.snapshot(self.external))
        self.assertFalse(portable.local_dir(self.root).exists())

    def test_missing_source_cli_rejects_install(self):
        (self.root / "code/personal-agent-os/scripts/paos.py").unlink()
        with self.assertRaises(portable.PortableError):
            self.init()

    def test_rooter_binding_must_exist_and_remain(self):
        with self.assertRaises(portable.PortableError):
            self.init(rooter_home=str(self.root / "missing"))
        home = self.root / "home"
        home.mkdir()
        self.init(rooter_home=str(home))
        other = self.root / "other"
        other.mkdir()
        with self.assertRaises(portable.PortableError):
            portable.initialize(self.root, rooter_home=str(other))
        self.assertEqual(self.configured()["installation"]["rooter_home"], str(home))

    def test_agent_number_locator_preserved(self):
        number = self.root / "numbers.json"
        number.write_text('{"num":10}', encoding="utf-8")
        self.init(agent_numbers=str(number))
        self.assertEqual(number.read_text(encoding="utf-8"), '{"num":10}')

    def test_invalid_template_and_traversal_rejected(self):
        self.change_template(data_root="<PAOS_ROOT>/../escape")
        with self.assertRaises(portable.PortableError):
            self.init()
        self.assertFalse((self.root / "data").exists())

    def test_invalid_schema_and_unknown_field_rejected(self):
        self.change_template(schema="not-a-schema")
        with self.assertRaises(portable.PortableError):
            self.init()
        self.change_template(schema=portable.SCHEMAS["installation"], extra_field=True)
        with self.assertRaises(portable.PortableError):
            self.init()

    def test_existing_invalid_config_not_overwritten(self):
        self.init()
        path = portable.local_dir(self.root) / "installation.json"
        path.write_text("invalid-json", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(portable.PortableError):
            portable.initialize(self.root)
        self.assertEqual(before, self.snapshot())

    def test_existing_partial_config_not_repaired(self):
        portable.local_dir(self.root).mkdir()
        (portable.local_dir(self.root) / "library-roots.json").write_text("{}", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(portable.PortableError):
            portable.initialize(self.root)
        self.assertEqual(before, self.snapshot())

    def test_registered_external_root_loss_fails_doctor(self):
        self.init()
        (self.skill / ".paos/usage-events").rmdir()
        self.assertFalse(portable.doctor(self.root)["configuration_ok"])
        before = self.snapshot(self.external)
        with self.assertRaises(portable.PortableError):
            portable.initialize(self.root)
        self.assertEqual(before, self.snapshot(self.external))

    def test_registered_tool_missing_is_reported(self):
        self.init(tool_catalog=str(self.tool))
        self.tool.unlink()
        self.assertFalse(portable.doctor(self.root)["configuration_ok"])

    def test_doctor_is_read_only_and_does_not_verify_runtime(self):
        self.init()
        before = self.snapshot()
        doctor = portable.doctor(self.root)
        self.assertTrue(doctor["configuration_ok"], doctor)
        self.assertFalse(doctor["runtime_verified"])
        self.assertFalse(doctor["business_verified"])
        self.assertFalse(doctor["cli_verified"])
        self.assertEqual(before, self.snapshot())

    def test_unconfigured_doctor_does_not_initialize(self):
        before = self.snapshot()
        self.assertFalse(portable.doctor(self.root)["configuration_ok"])
        self.assertEqual(before, self.snapshot())

    def test_relocated_package_requires_re_registration(self):
        self.init()
        new_root = Path(self.temp.name) / "new checkout"
        shutil.copytree(self.root, new_root)
        self.assertFalse(portable.doctor(new_root)["configuration_ok"])
        self.assertTrue(portable.doctor(self.root)["configuration_ok"])

    def test_registered_external_data_root_is_preserved_by_doctor_and_reinit(self):
        self.init()
        outside = Path(self.temp.name) / "existing data"
        outside.mkdir()
        (outside / "keep.json").write_text('{"original":"retain"}', encoding="utf-8")
        config = portable.local_dir(self.root) / "installation.json"
        value = json.loads(config.read_text(encoding="utf-8"))
        value["data_root"] = str(outside)
        config.write_text(json.dumps(value), encoding="utf-8")
        before, external = self.snapshot(), self.snapshot(outside)
        self.assertTrue(portable.doctor(self.root)["configuration_ok"])
        self.assertFalse(portable.initialize(self.root)["created"])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(external, self.snapshot(outside))

    def test_external_data_root_missing_or_relative_is_not_created(self):
        self.init()
        config = portable.local_dir(self.root) / "installation.json"
        original = json.loads(config.read_text(encoding="utf-8"))
        missing = Path(self.temp.name) / "missing data"
        relative_target = Path.cwd() / "relative-data"
        self.assertFalse(relative_target.exists())
        for locator in (str(missing), "relative-data"):
            value = {**original, "data_root": locator}
            config.write_text(json.dumps(value), encoding="utf-8")
            before = self.snapshot()
            self.assertFalse(portable.doctor(self.root)["configuration_ok"])
            with self.assertRaises(portable.PortableError):
                portable.initialize(self.root)
            self.assertEqual(before, self.snapshot())
            self.assertFalse(missing.exists())
            self.assertFalse(relative_target.exists())

    def test_data_root_symlink_outside_core_is_not_written(self):
        target = Path(self.temp.name) / "data outside"
        target.mkdir()
        try:
            (self.root / "data").symlink_to(target, target_is_directory=True)
        except OSError as err:
            self.skipTest(f"symlink unsupported: {err}")
        with self.assertRaises(portable.PortableError):
            self.init()
        self.assertEqual(list(target.iterdir()), [])

    def test_staging_json_failure_publishes_neither_config(self):
        original = json.dump
        calls = 0
        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic failure")
            return original(*args, **kwargs)
        with patch.object(portable.json, "dump", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.init()
        self.assertFalse(portable.local_dir(self.root).exists())
        self.assertEqual(list((self.root / "config").glob(".portable-*")), [])

    def test_staging_rename_failure_cleans_staging(self):
        with patch.object(Path, "rename", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                self.init()
        self.assertFalse(portable.local_dir(self.root).exists())

    def test_legacy_installation_collision_refused(self):
        (self.root / "config/installation.json").write_text("existing", encoding="utf-8")
        with self.assertRaises(portable.PortableError):
            self.init()

    def test_cli_exit_codes_and_read_only_plan(self):
        with patch.object(portable, "ROOT", self.root), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(portable.main(["plan"]), 0)
            self.assertEqual(portable.main(["doctor"]), 1)
            self.assertEqual(portable.main(["init"]), 2)
            self.assertEqual(portable.main(["init", "--workflow-root", str(self.workflow),
                                            "--skill-root", str(self.skill)]), 0)
            self.assertEqual(portable.main(["doctor"]), 0)


if __name__ == "__main__":
    unittest.main()
