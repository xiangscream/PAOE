"""Rooter accepts registered Project originals without moving or mutating them."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'code/personal-agent-os/scripts'))
import test_history_archive as fixtures
from paos_team import acceptance_versions
from paos_todo import read_todo, render_todo


class RooterAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.HistoryArchiveTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        (self.f.root / 'numbers.json').write_text(json.dumps({'rooter-001': 'S035', '3002-s002': 'S002'}),
                                                encoding='utf-8')
        self.home = self.f.rooter
        self.target = 'rooter-001'
        self.ref = dict(home_kind='rooter', home_id=self.target, project_id='',
                        home_path=str(self.home), project_root='')
        self.artifact = self.f.vault / 'result.md'
        self.basis = self.f.other_vault / 'basis.md'
        self.artifact.write_bytes(b'Actual Project result\n')
        self.basis.write_bytes(b'Actual Project acceptance basis\n')
        self.todo = self.home / 'TODO.md'
        self.todo.write_text(render_todo(home_kind='rooter', home_id=self.target, project_id='',
            objective='Accept adopted result', next_action='Read result', context_refs=['task:R1'],
            tasks=[dict(id='R1', title='Adopted result', state='doing')]), encoding='utf-8')

    def accept(self, artifact=None, basis=None, *extra, ok=True):
        return self.f.call('task', 'accept', self.target, '--task', 'R1',
            '--artifact', str(artifact or self.artifact), '--basis', str(basis or self.basis),
            '--remaining', 'none', *extra, ok=ok)

    def test_registered_originals_are_read_only_and_reentry_is_idempotent(self):
        before = self.artifact.read_bytes(), self.basis.read_bytes()
        other_todo = (self.f.other_vault / 'Workstations/2001-s009/TODO.md').read_bytes()
        result = self.accept()[1]
        self.assertTrue(result['task_done'])
        self.assertFalse(result['replayed'])
        self.assertEqual(read_todo(self.todo)['tasks'][0]['artifact_ref'], str(self.artifact))
        after = self.todo.read_bytes()
        self.assertTrue(self.accept()[1]['replayed'])
        self.assertEqual(self.todo.read_bytes(), after)
        self.assertEqual((self.artifact.read_bytes(), self.basis.read_bytes()), before)
        self.assertEqual((self.f.other_vault / 'Workstations/2001-s009/TODO.md').read_bytes(), other_todo)
        self.assertFalse((self.home / 'result.md').exists())

    def test_missing_or_unregistered_originals_leave_task_unchanged(self):
        outside = self.f.root / 'unregistered' / 'result.md'
        outside.parent.mkdir()
        outside.write_text('Not registered', encoding='utf-8')
        original = self.todo.read_bytes()
        for path in (self.f.vault / 'missing.md', outside,
                     str(self.f.vault / '..' / 'unregistered' / 'result.md'),
                     'https://example.com/result.md'):
            with self.subTest(path=str(path)):
                code, failure = self.accept(artifact=path, ok=False)
                self.assertNotEqual(code, 0)
                self.assertIn('原件不可读', failure['error'])
                self.assertEqual(self.todo.read_bytes(), original)

    def test_project_scope_is_not_expanded_to_other_registered_projects(self):
        self.home = self.f.vault / 'Workstations/3002-s002'
        self.target = '3002-s002'
        self.todo = self.home / 'TODO.md'
        self.todo.write_text(render_todo(home_kind='project_agent', home_id=self.target, project_id='3002',
            objective='Accept result', next_action='Read result',
            tasks=[dict(id='R1', title='Result', state='doing')]), encoding='utf-8')
        before = self.todo.read_bytes()
        self.assertNotEqual(self.accept(ok=False)[0], 0)
        self.assertEqual(self.todo.read_bytes(), before)
        self.assertTrue(self.accept(basis=self.artifact)[1]['task_done'])
        self.assertTrue(self.accept(basis=self.artifact)[1]['replayed'])

    def test_waiting_governance_is_unchanged(self):
        doc = read_todo(self.todo)
        doc['tasks'][0]['waiting'] = 'A real outstanding dependency'
        from paos_stage import render
        self.todo.write_text(render(doc), encoding='utf-8')
        before = self.todo.read_bytes()
        self.assertNotEqual(self.accept(ok=False)[0], 0)
        self.assertEqual(self.todo.read_bytes(), before)

    def test_versions_use_same_scope_and_do_not_accept_changed_bytes(self):
        evidence = dict(artifact=str(self.artifact), basis=str(self.basis))
        roots = [str(self.f.vault), str(self.f.other_vault)]
        versions = acceptance_versions(self.ref, evidence, source_roots=roots)
        self.artifact.write_bytes(b'Changed Project result\n')
        self.assertNotEqual(acceptance_versions(self.ref, evidence, source_roots=roots), versions)
        self.artifact.unlink()
        self.assertEqual(acceptance_versions(self.ref, evidence, archived=versions, source_roots=roots), versions)
        with self.assertRaises(ValueError):
            acceptance_versions(self.ref, evidence, archived=versions)

    def test_cleanup_is_called_with_only_the_original_rooter_home(self):
        with patch('paos_input_cleanup.cleanup_task', return_value={'complete': True}) as cleanup:
            self.accept(None, None, '--cleanup-inputs', '--preserved-ref', str(self.artifact))
        self.assertEqual(cleanup.call_args.args[0]['home_path'], str(self.f.rooter))
        self.assertEqual(cleanup.call_args.args[0]['home_kind'], 'rooter')
        self.assertEqual(cleanup.call_args.args[1:], ('R1', str(self.artifact)))


if __name__ == '__main__':
    unittest.main()
