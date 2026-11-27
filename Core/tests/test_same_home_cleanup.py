"""Migrated Home inputs keep their original identity and consumption evidence."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'code/personal-agent-os/scripts'))
import test_history_archive as fixtures
from paos_migrate_home import plan, _execute
from paos_registry import ProjectRegistry
from paos_todo import read_todo
from paos_stage import render
from paos_input_cleanup import read_deleted


class SameHomeCleanupTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.HistoryArchiveTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.old, self.current, self.mid = '3003-s001', 'S036', 'historical-consumed'
        self.home = self.f.vault / 'Workstations' / self.old
        self.f.make_home(self.home, self.old, '3003')
        self.f.make_home(self.home.with_name('3003-s002'), '3003-s002', '3003')
        ProjectRegistry(self.f.install).register('3003', root_path=str(self.f.vault),
            homes=[self.old, '3003-s002'], coordinator_home_id=self.old)
        (self.f.root / 'numbers.json').write_text(json.dumps({self.old: self.current, '3003-s002': 'S039'}))
        result = self.f.call('attention', 'send', '3003', '--to', self.old, '--to', '3003-s002', '--sender-kind', 'agent',
            '--sender-id', '3003-s002', '--subject', 'Original work', '--body', 'Original content',
            '--message-id', self.mid)[1]
        self.notice = result['notices']['items'][0]['notice_id']
        (self.f.vault / 'result.md').write_text('Durable original result', encoding='utf-8')

    def consume(self, handled=True):
        self.f.call('attention', 'read', '3003', self.old, self.notice)
        if handled:
            self.f.call('attention', 'handle', '3003', self.old, self.notice,
                        '--resolution', 'Done', '--action-ref', 'result.md')

    def migrate(self):
        _execute(plan('3003', self.old, self.current, str(self.f.install)), str(self.f.install), self.f.root / 'before.json')
        self.home = self.home.with_name(self.current)

    def cleanup(self, *extra, ok=True):
        return self.f.call('input-cleanup', self.current, '--message-id', self.mid,
                           '--preserved-ref', 'result.md', *extra, ok=ok)

    def test_consumed_original_is_located_and_deleted_without_rewriting_identity(self):
        self.consume()
        self.migrate()
        status = self.f.call('attention', 'source-status', '3003', self.current,
                             '--source-kind', 'mail', '--source-ref', self.mid)[1]
        self.assertEqual(status['notice']['home_id'], self.old)
        self.assertTrue(status['notice']['read'])
        before = (self.home / 'mailbox' / (self.mid + '.md')).read_bytes()
        result = self.cleanup()[1]
        self.assertEqual(result['state'], 'deleted')
        marker = read_deleted(self.home, 'mail', self.mid)
        self.assertEqual((marker['home_id'], marker['notice_id']), (self.current, self.notice))
        self.assertTrue(marker['was_read'] and marker['was_handled'])
        self.assertIn(self.old.encode(), before)
        self.assertFalse((self.home / 'notices' / (self.notice + '.md')).exists())
        self.assertTrue(self.cleanup()[1]['replayed'])
        status = self.f.call('attention', 'source-status', '3003', self.current,
                             '--source-kind', 'mail', '--source-ref', self.mid)[1]
        self.assertEqual(status['state'], 'deleted')

    def test_unread_and_unhandled_originals_are_retained(self):
        self.migrate()
        before = (self.home / 'mailbox' / (self.mid + '.md')).read_bytes()
        self.assertNotEqual(self.cleanup(ok=False)[0], 0)
        self.assertEqual((self.home / 'mailbox' / (self.mid + '.md')).read_bytes(), before)
        self.assertIsNone(read_deleted(self.home, 'mail', self.mid))

    def test_read_but_unhandled_original_is_retained(self):
        self.consume(handled=False)
        self.migrate()
        self.assertNotEqual(self.cleanup(ok=False)[0], 0)
        self.assertIsNone(read_deleted(self.home, 'mail', self.mid))

    def test_other_recipient_is_rejected_without_modifying_consumption(self):
        self.consume()
        self.migrate()
        mail = self.home / 'mailbox' / (self.mid + '.md')
        mail.write_text(mail.read_text(encoding='utf-8').replace('recipient_agent_id: "3003-s001"',
                        'recipient_agent_id: "3003-s002"'), encoding='utf-8')
        # A number mapping alone cannot authorize a name still registered to another Home.
        (self.f.root / 'numbers.json').write_text(json.dumps({self.old: self.current, '3003-s002': self.current}))
        from paos_notice import notice_archive_files
        files = [mail, *notice_archive_files(self.home, self.notice)]
        before = {p: p.read_bytes() for p in files}
        self.assertNotEqual(self.cleanup(ok=False)[0], 0)
        self.assertEqual({p: p.read_bytes() for p in files}, before)
        self.assertIsNone(read_deleted(self.home, 'mail', self.mid))

    def test_partial_historical_deletion_resumes_the_original_notice(self):
        self.consume()
        self.migrate()
        original = Path.unlink
        def fail_notice(path, *args, **kwargs):
            if path == self.home / 'notices' / (self.notice + '.md'):
                raise PermissionError('Isolated partial deletion')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'unlink', fail_notice):
            self.assertEqual(self.cleanup(ok=False)[1]['state'], 'cleanup_pending')
        result = self.cleanup()[1]
        self.assertTrue(result['replayed'])
        self.assertEqual(result['notice_id'], self.notice)
        self.assertFalse((self.home / 'notices' / (self.notice + '.md')).exists())

    def test_same_mid_replay_keeps_other_recipient_and_does_not_recreate_notice(self):
        other = self.home.with_name('3003-s002') / 'mailbox' / (self.mid + '.md')
        original = other.read_bytes()
        self.consume()
        self.migrate()
        self.cleanup()
        replay = self.f.call('attention', 'send', '3003', '--to', self.old, '--to', '3003-s002',
            '--sender-kind', 'agent', '--sender-id', '3003-s002', '--subject', 'Original work',
            '--body', 'Original content', '--message-id', self.mid)[1]
        # Immutable dispatch still names the pre-migration member; do not invent a new recipient set.
        self.assertEqual(replay['mail']['deliveries'][0]['state'], 'workstation_missing')
        self.assertEqual(other.read_bytes(), original)
        self.assertFalse(list((self.home / 'notices').glob('*.md')))
        code, conflict = self.f.call('agent', 'send', '3003', '--to', self.current, '--to', '3003-s002',
            '--sender-kind', 'agent', '--sender-id', '3003-s002', '--subject', 'Original work',
            '--body', 'Original content', '--message-id', self.mid, ok=False)
        self.assertNotEqual(code, 0)
        self.assertEqual(conflict['error_code'], 'mail_message_id_conflict')
        self.assertFalse((self.home / 'mailbox' / (self.mid + '.md')).exists())

    def test_standalone_historical_notice_readback_after_deletion(self):
        from paos_notice import create_notice, mark_notice_read, handle_notice
        item = create_notice(home_path=self.home, home_kind='project_agent', home_id=self.old,
            project_id='3003', source_kind='cat', source_ref='old-cat-event', summary='Original CAT input')
        ident = item['notice_id']
        mark_notice_read(home_path=self.home, notice_id=ident, reader_home_kind='project_agent',
                         reader_home_id=self.old, reader_project_id='3003')
        handle_notice(home_path=self.home, notice_id=ident, resolution='Done', action_ref='result.md')
        self.migrate()
        result = self.f.call('input-cleanup', self.current, '--notice-id', ident, '--preserved-ref', 'result.md')[1]
        self.assertEqual(result['state'], 'deleted')
        status = self.f.call('attention', 'source-status', '3003', self.current, '--source-kind', 'cat',
                             '--source-ref', 'old-cat-event')[1]
        self.assertEqual(status['state'], 'deleted')

    def test_foreign_notice_in_same_directory_is_not_authorized(self):
        from paos_notice import create_notice, mark_notice_read, handle_notice, notice_archive_files
        item = create_notice(home_path=self.home, home_kind='project_agent', home_id='3003-s002',
            project_id='3003', source_kind='cat', source_ref='foreign-event', summary='Foreign input')
        ident = item['notice_id']
        mark_notice_read(home_path=self.home, notice_id=ident, reader_home_kind='project_agent',
                        reader_home_id='3003-s002', reader_project_id='3003')
        handle_notice(home_path=self.home, notice_id=ident, resolution='Done', action_ref='result.md')
        self.migrate()
        files = notice_archive_files(self.home, ident)
        before = {p: p.read_bytes() for p in files}
        code, _ = self.f.call('input-cleanup', self.current, '--notice-id', ident,
                              '--preserved-ref', 'result.md', ok=False)
        self.assertNotEqual(code, 0)
        self.assertEqual({p: p.read_bytes() for p in files}, before)
        self.assertIsNone(read_deleted(self.home, 'notice', ident))

    def test_original_notice_and_mail_task_dependencies_both_protect(self):
        self.consume()
        self.migrate()
        path = self.home / 'TODO.md'
        for anchor in ('mail:' + self.mid, 'notice:' + self.notice):
            doc = read_todo(path)
            doc['tasks'] = [dict(id='ACTIVE', title='Keep input', state='doing', source_refs=[anchor])]
            path.write_text(render(doc), encoding='utf-8')
            result = self.cleanup(ok=False)[1]
            self.assertEqual(result['state'], 'active_dependency')
            self.assertEqual(result['tasks'], ['ACTIVE'])
            self.assertIsNone(read_deleted(self.home, 'mail', self.mid))

    def test_default_mail_result_uses_the_original_claim_and_notice(self):
        task = self.f.call('mail', 'claim', '3003', self.old, self.mid)[1]['task_id']
        self.migrate()
        result = self.f.call('mail', 'result', '3003', self.current, self.mid,
                             '--result', 'Finished', '--artifact-ref', 'result.md')[1]
        self.assertEqual(result['task_id'], task)
        self.assertTrue(result['cleanup']['complete'])
        self.assertEqual(result['cleanup']['items'][0]['state'], 'deleted')

    def test_default_task_accept_uses_original_read_and_claim(self):
        task = self.f.call('mail', 'claim', '3003', self.old, self.mid)[1]['task_id']
        self.migrate()
        result = self.f.call('task', 'accept', self.current, '--task', task,
            '--artifact', 'result.md', '--basis', 'result.md', '--remaining', 'none')[1]
        self.assertTrue(result['task_done'] and result['cleanup']['complete'])


if __name__ == '__main__':
    unittest.main()
