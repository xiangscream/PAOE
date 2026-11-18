"""Rooter cutover keeps Contact and TODO current across the directory rename."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'code/personal-agent-os/scripts'
sys.path.insert(0, str(SCRIPTS))
from paos_installation import write_installation_descriptor
from paos_migrate_home import MigrationProblem, _execute, plan
from paos_registry import ProjectRegistry


class StaffMigrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.installation = self.root / 'installation.json'
        numbers = self.root / 'AGENT-NUMBERS.json'
        numbers.write_text('{"3002-s001":"S040"}', encoding='utf-8')
        write_installation_descriptor(
            self.installation, source_root=str(SCRIPTS.parent), data_root=str(self.root / 'data'),
            library_roots_config=str(self.root / 'library-roots.json'), agent_numbers_config=str(numbers),
        )
        project = self.root / 'project'
        self.registry = ProjectRegistry(self.installation)
        self.old = project / 'Workstations/3002-s001'
        self.new = self.old.with_name('S040')
        self.old.mkdir(parents=True)
        self.todo = b'---\r\nhome_id: "3002-s001"\r\n---\r\n\r\nKeep the original task.\r\n'
        (self.old / 'TODO.md').write_bytes(self.todo)
        (self.old / 'STOP').write_bytes(b'pause stays')
        self.contact = project / 'private-data/contact/native-targets.json'
        self.contact.parent.mkdir(parents=True)
        self.target = {'runtime': 'codex', 'session_id': 'original-thread', 'stop_file': str(self.old / 'STOP'),
                       'extension': {'receiver_runtime_file': str(self.old / 'receiver.json')}}
        self.contact.write_text(json.dumps({self.old.name: self.target}), encoding='utf-8')
        self.original_contact = self.contact.read_bytes()
        self.registry.register('3002', root_path=str(project), coordinator_home_id=self.old.name, homes=[self.old.name])
        self.before = self.root / 'before.json'

    def migration(self):
        return plan('3002', self.old.name, self.new.name, str(self.installation))

    def test_contact_follows_the_same_home_without_changing_its_native_session(self):
        result = _execute(self.migration(), str(self.installation), self.before)
        self.assertTrue(result['contact_updated'])
        self.assertFalse(self.old.exists())
        self.assertEqual(self.registry.read_record('3002')['coordinator_home_id'], 'S040')
        self.assertEqual((self.new / 'TODO.md').read_bytes(), self.todo.replace(b'3002-s001', b'S040'))
        self.assertEqual((self.new / 'STOP').read_bytes(), b'pause stays')
        updated = json.loads(self.contact.read_bytes())
        registered_home = Path(self.registry.read_record('3002')['root_path']) / 'Workstations/S040'
        self.assertEqual(updated, {'S040': {**self.target, 'stop_file': str(registered_home / 'STOP'),
                         'extension': {'receiver_runtime_file': str(registered_home / 'receiver.json')}}})
        snapshot = json.loads(self.before.read_bytes())
        self.assertEqual(Path(snapshot['contact_before_path']).read_bytes(), self.original_contact)

    def test_registry_conflict_restores_both_contact_and_todo(self):
        pending = self.migration()
        registry = Path(pending['registry_path'])
        foreign_edit = registry.read_bytes() + b'\n'
        registry.write_bytes(foreign_edit)

        with self.assertRaises(MigrationProblem) as failure:
            _execute(pending, str(self.installation), self.before)

        self.assertEqual(failure.exception.code, 'migration_execute_failed')
        self.assertEqual(registry.read_bytes(), foreign_edit)
        self.assertFalse(self.new.exists())
        self.assertEqual((self.old / 'TODO.md').read_bytes(), self.todo)
        self.assertEqual(self.contact.read_bytes(), self.original_contact)
