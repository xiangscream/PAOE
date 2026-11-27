"""Normal completion evaluates existing input cleanup without a second business action."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'code/personal-agent-os/scripts'))
import test_input_cleanup as fixtures
from paos_input_cleanup import cleanup_task, read_deleted
from paos_stage import render
from paos_todo import read_todo


class DefaultCompletionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.InputCleanupTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f, self.home = self.fixture.f, self.fixture.home
        (self.f.root / 'numbers.json').write_text(json.dumps({'3002-s002': 'S002', 'rooter-001': 'S035'}))
        self.artifact = self.f.vault / 'out.md'
        self.artifact.write_text('Preserved result and necessary originals', encoding='utf-8')
        self.mid = 'cleanup-test-001'

    def claim(self, task=''):
        self.fixture.send(self.mid, done=False)
        args = ('--task', task) if task else ()
        return self.f.call('mail', 'claim', '3002', '3002-s002', self.mid, *args)[1]['task_id']

    def finish(self, *args):
        return self.f.call('mail', 'result', '3002', '3002-s002', self.mid, '--result', 'Done', *args)[1]

    def task(self, task_id):
        return next(t for t in read_todo(self.home / 'TODO.md')['tasks'] if t['id'] == task_id)

    def test_mail_default_uses_artifact_and_preserves_source_refs(self):
        task = self.claim()
        refs = self.task(task)['source_refs']
        result = self.finish('--artifact-ref', 'out.md')
        self.assertEqual(result['task_state'], 'done')
        self.assertTrue(result['cleanup']['complete'])
        self.assertFalse((self.home / 'mailbox' / (self.mid + '.md')).exists())
        self.assertEqual(self.task(task)['source_refs'], refs)
        self.assertEqual(read_deleted(self.home, 'mail', self.mid)['preserved_ref'], 'out.md')

    def test_explicit_preservation_overrides_artifact_and_old_flag_is_synonymous(self):
        for flag in ((), ('--cleanup-inputs',)):
            with self.subTest(flag=flag):
                self.mid = 'explicit-' + str(len(flag))
                self.claim()
                result = self.finish('--artifact-ref', 'missing.md', '--preserved-ref', 'out.md', *flag)
                self.assertTrue(result['cleanup']['complete'])
                self.assertEqual(read_deleted(self.home, 'mail', self.mid)['preserved_ref'], 'out.md')

    def test_missing_unreadable_and_input_itself_are_retained_after_business_completion(self):
        for mode in ('missing', 'unreadable', 'input'):
            with self.subTest(mode=mode):
                self.mid = 'retained-' + mode
                task = self.claim()
                ref = str(self.home / 'mailbox' / (self.mid + '.md')) if mode == 'input' else 'missing.md'
                result = self.finish(*(() if mode == 'missing' else ('--artifact-ref', ref)))
                self.assertEqual(result['task_state'], 'done')
                self.assertEqual(self.task(task)['state'], 'done')
                self.assertFalse(result['cleanup']['complete'])
                self.assertIn('input-cleanup', result['cleanup']['items'][0]['retry'])
                self.assertTrue((self.home / 'mailbox' / (self.mid + '.md')).exists())
                self.assertIsNone(read_deleted(self.home, 'mail', self.mid))
                repaired = self.f.call('input-cleanup', '3002-s002', '--task', task, '--preserved-ref', 'out.md')[1]
                self.assertTrue(repaired['complete'])

    def test_task_accept_defaults_to_its_verified_artifact(self):
        task = self.claim()
        refs = self.task(task)['source_refs']
        args = ('task', 'accept', '3002-s002', '--task', task, '--artifact', 'out.md',
                '--basis', 'out.md', '--remaining', 'none')
        result = self.f.call(*args)[1]
        self.assertTrue(result['task_done'] and result['cleanup']['complete'])
        self.assertTrue(self.f.call(*args)[1]['replayed'])
        self.assertEqual(self.task(task)['source_refs'], refs)

    def test_unreadable_automatic_artifact_does_not_rollback_mail_result(self):
        task = self.claim()
        original = Path.open
        def open_file(path, *args, **kwargs):
            if path == self.artifact.resolve():
                raise PermissionError('Isolated unreadable original')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', open_file):
            result = self.finish('--artifact-ref', 'out.md')
        self.assertEqual(self.task(task)['state'], 'done')
        self.assertFalse(result['cleanup']['complete'])
        self.assertTrue((self.home / 'mailbox' / (self.mid + '.md')).exists())

    def test_explicit_system_or_exm_locator_is_not_scoped_as_automatic_artifact(self):
        for area in ('System', 'EXM'):
            with self.subTest(area=area):
                self.mid = 'external-' + area
                self.claim()
                durable = self.f.root / area / 'original.md'
                durable.parent.mkdir()
                durable.write_text('Preserved original', encoding='utf-8')
                result = self.finish('--artifact-ref', 'missing.md', '--preserved-ref', str(durable))
                self.assertTrue(result['cleanup']['complete'])
                self.assertEqual(read_deleted(self.home, 'mail', self.mid)['preserved_ref'], str(durable))

    def test_explicit_input_self_reference_is_rejected_despite_valid_artifact(self):
        for mode in ('file', 'alias', 'sidecar'):
            self.mid = 'self-' + mode
            task = self.claim()
            if mode == 'sidecar':
                notice = self.f.call('mail', 'read', '3002', '3002-s002', self.mid)[1]['handling']['notice_id']
                ref = str(self.home / 'notices/.read' / (notice + '.json'))
            else:
                ref = 'mail:' + self.mid if mode == 'alias' else str(self.home / 'mailbox' / (self.mid + '.md'))
            result = self.finish('--artifact-ref', 'out.md', '--preserved-ref', ref)
            self.assertEqual(self.task(task)['state'], 'done')
            self.assertFalse(result['cleanup']['complete'])
            self.assertIn('输入自身', result['cleanup']['items'][0]['error'])

    def test_explicit_business_locator_keeps_published_contract(self):
        task = self.claim()
        result = self.f.call('task', 'accept', '3002-s002', '--task', task, '--artifact', 'out.md',
            '--basis', 'out.md', '--remaining', 'none', '--preserved-ref', 'https://example.com/authoritative-original')[1]
        self.assertTrue(result['task_done'])
        self.assertTrue(result['cleanup']['complete'])
        self.assertEqual(read_deleted(self.home, 'mail', self.mid)['preserved_ref'],
                         'https://example.com/authoritative-original')

    def test_unfinished_existing_task_is_not_closed_or_cleaned(self):
        path = self.home / 'TODO.md'
        doc = read_todo(path)
        doc['tasks'].append(dict(id='BROAD', title='Existing broad work', state='doing'))
        path.write_text(render(doc), encoding='utf-8')
        self.claim('BROAD')
        result = self.finish('--artifact-ref', 'out.md')
        self.assertEqual(result['cleanup']['state'], 'task_unfinished')
        self.assertEqual(self.task('BROAD')['state'], 'doing')
        self.assertTrue((self.home / 'mailbox' / (self.mid + '.md')).exists())

    def test_other_active_dependency_remains_protected(self):
        task = self.claim()
        path = self.home / 'TODO.md'
        doc = read_todo(path)
        doc['tasks'].append(dict(id='OTHER', title='Other work', state='doing', source_refs=['mail:' + self.mid]))
        path.write_text(render(doc), encoding='utf-8')
        result = self.finish('--artifact-ref', 'out.md')
        self.assertEqual(result['cleanup']['items'][0]['state'], 'active_dependency')
        self.assertEqual(self.task(task)['state'], 'done')

    def test_archived_input_is_skipped_without_requiring_another_preservation(self):
        task = self.claim()
        self.f.mark_done(self.fixture.f.call('mail', 'read', '3002', '3002-s002', self.mid)[1]['handling']['notice_id'])
        self.f.call('attention', 'archive-input', '3002', '3002-s002', '--message-id', self.mid,
                    '--history-root', str(self.f.root / 'history'))
        path = self.home / 'TODO.md'
        doc = read_todo(path)
        next(t for t in doc['tasks'] if t['id'] == task)['state'] = 'done'
        path.write_text(render(doc), encoding='utf-8')
        result = cleanup_task(self.fixture.ref, task)
        self.assertTrue(result['complete'])
        self.assertEqual(result['items'][0]['state'], 'archived_retained')

    def test_partial_failure_can_be_completed_without_repeating_mail_result(self):
        task = self.claim()
        unlink = Path.unlink
        def fail_notice(path, *args, **kwargs):
            if path.parent == self.home / 'notices':
                raise PermissionError('Isolated deletion failure')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', fail_notice):
            result = self.finish('--artifact-ref', 'out.md')
        self.assertEqual(self.task(task)['state'], 'done')
        self.assertFalse(result['cleanup']['complete'])
        self.assertTrue(self.f.call('input-cleanup', '3002-s002', '--task', task, '--preserved-ref', 'out.md')[1]['complete'])

    def test_rooter_auto_task_uses_registered_project_artifact(self):
        self.f.call('agent', 'send', '3002', '--to', 'rooter-001', '--sender-kind', 'agent',
            '--sender-id', '3002-s001', '--subject', 'Rooter work', '--body', 'Input', '--message-id', 'rooter-default')
        claimed = self.f.call('mail', 'rooter-claim', 'rooter-default')[1]
        result = self.f.call('mail', 'rooter-result', 'rooter-default', '--result', 'Done',
                            '--artifact-ref', str(self.artifact))[1]
        self.assertTrue(result['cleanup']['complete'])
        self.assertEqual(result['task_id'], claimed['task_id'])
        self.assertEqual(read_deleted(self.f.rooter, 'mail', 'rooter-default')['preserved_ref'], str(self.artifact))


if __name__ == '__main__':
    unittest.main()
