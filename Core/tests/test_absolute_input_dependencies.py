"""File locators and ID locators protect the same Home input."""
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'code/personal-agent-os/scripts'))
import test_same_home_cleanup as fixtures
from paos_input_cleanup import read_deleted
from paos_notice import create_notice, mark_notice_read, handle_notice
from paos_stage import render
from paos_todo import read_todo


class AbsoluteInputDependencyTests(unittest.TestCase):
    def setUp(self):
        self.make_fixture()

    def make_fixture(self, handled=True):
        self.f = fixtures.SameHomeCleanupTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.consume(handled=handled)
        self.f.migrate()
        self.home = self.f.home
        self.mail = self.home / 'mailbox' / (self.f.mid + '.md')
        self.notice = self.home / 'notices' / (self.f.notice + '.md')

    def tasks(self, source, state='doing', extra=()):
        path = self.home / 'TODO.md'
        doc = read_todo(path)
        doc['tasks'] = [dict(id='KEEP', title='Needs original', state=state, source_refs=[source]), *extra]
        path.write_text(render(doc), encoding='utf-8')

    def snapshot(self):
        return {p.relative_to(self.home): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}

    def test_absolute_mail_and_original_notice_protect_doing_and_waiting(self):
        for kind in ('mail', 'notice'):
            for state in ('doing', 'waiting'):
                self.make_fixture()
                path = getattr(self, kind)
                with self.subTest(path=path.name, state=state):
                    self.tasks(str(path), state)
                    before = self.snapshot()
                    result = self.f.cleanup(ok=False)[1]
                    self.assertEqual(result['state'], 'active_dependency')
                    self.assertEqual(result['tasks'], ['KEEP'])
                    self.assertEqual(self.snapshot(), before)
                    self.assertIsNone(read_deleted(self.home, 'mail', self.f.mid))

    @unittest.skipUnless(os.name == 'nt', 'Native Windows path spellings')
    def test_windows_forward_and_backslashes_identify_same_input(self):
        for kind in ('mail', 'notice'):
            for spelling in ('backslash', 'forward', 'case'):
                self.make_fixture()
                path = getattr(self, kind)
                locator = {'backslash': str(path), 'forward': path.as_posix(), 'case': str(path).swapcase()}[spelling]
                with self.subTest(locator=locator):
                    self.tasks(locator)
                    before = self.snapshot()
                    self.assertEqual(self.f.cleanup(ok=False)[1]['state'], 'active_dependency')
                    self.assertEqual(self.snapshot(), before)

    def test_done_and_cancelled_dependencies_allow_cleanup_and_reentry(self):
        self.tasks(str(self.mail), 'done', [dict(id='OLD', title='Cancelled original', state='cancelled',
                                                source_refs=[str(self.notice)])])
        self.assertEqual(self.f.cleanup()[1]['state'], 'deleted')
        self.assertTrue(self.f.cleanup()[1]['replayed'])
        record = read_deleted(self.home, 'mail', self.f.mid)
        self.assertEqual(record['notice_id'], self.f.notice)
        self.assertTrue(record['was_read'] and record['was_handled'])

    def test_other_file_and_other_home_same_mid_do_not_protect_this_input(self):
        other = self.home.with_name('3003-s002') / 'mailbox' / self.mail.name
        before = other.read_bytes()
        self.tasks(str(other), extra=[dict(id='RESULT', title='Needs result', state='waiting',
                                          source_refs=[str(self.f.f.vault / 'result.md')])])
        self.assertEqual(self.f.cleanup()[1]['state'], 'deleted')
        self.assertEqual(other.read_bytes(), before)

    def test_existing_id_references_still_protect(self):
        for source in ('mail:' + self.f.mid, 'notice:' + self.f.notice):
            self.tasks(source)
            before = self.snapshot()
            self.assertEqual(self.f.cleanup(ok=False)[1]['state'], 'active_dependency')
            self.assertEqual(self.snapshot(), before)

    def test_standalone_notice_absolute_path_protects_then_releases(self):
        item = create_notice(home_path=self.home, home_kind='project_agent', home_id=self.f.current,
            project_id='3003', source_kind='cat', source_ref='dependency-event', summary='Original')
        ident = item['notice_id']
        mark_notice_read(home_path=self.home, notice_id=ident, reader_home_kind='project_agent',
                         reader_home_id=self.f.current, reader_project_id='3003')
        handle_notice(home_path=self.home, notice_id=ident, resolution='Done', action_ref='result.md')
        path = self.home / 'notices' / (ident + '.md')
        self.tasks(str(path), 'waiting')
        before = self.snapshot()
        result = self.f.f.call('input-cleanup', self.f.current, '--notice-id', ident,
                              '--preserved-ref', 'result.md', ok=False)[1]
        self.assertEqual(result['state'], 'active_dependency')
        self.assertEqual(self.snapshot(), before)
        self.assertIsNone(read_deleted(self.home, 'notice', ident))
        self.tasks(str(path), 'done')
        self.assertEqual(self.f.f.call('input-cleanup', self.f.current, '--notice-id', ident,
                                     '--preserved-ref', 'result.md')[1]['state'], 'deleted')

    def completion(self, command):
        # Claim belongs to the completing Task; another active Task needs the same original file.
        self.make_fixture(handled=False)
        task = self.f.f.call('mail', 'claim', '3003', self.f.current, self.f.mid)[1]['task_id']
        path = self.home / 'TODO.md'
        doc = read_todo(path)
        doc['tasks'].append(dict(id='KEEP', title='Needs original file', state='doing',
                                 source_refs=[str(self.notice)]))
        path.write_text(render(doc), encoding='utf-8')
        before = {p: p.read_bytes() for p in (self.mail, self.notice)}
        if command == 'mail':
            result = self.f.f.call('mail', 'result', '3003', self.f.current, self.f.mid,
                                  '--result', 'Done', '--artifact-ref', 'result.md')[1]
        else:
            result = self.f.f.call('task', 'accept', self.f.current, '--task', task,
                                  '--artifact', 'result.md', '--basis', 'result.md', '--remaining', 'none')[1]
        self.assertFalse(result['cleanup']['complete'])
        self.assertEqual(result['cleanup']['items'][0]['state'], 'active_dependency')
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.assertIsNone(read_deleted(self.home, 'mail', self.f.mid))
        doc = read_todo(path)
        self.assertEqual(next(t for t in doc['tasks'] if t['id'] == task)['state'], 'done')
        next(t for t in doc['tasks'] if t['id'] == 'KEEP')['state'] = 'done'
        path.write_text(render(doc), encoding='utf-8')
        self.assertEqual(self.f.cleanup()[1]['state'], 'deleted')

    def test_default_mail_completion_keeps_other_active_file_dependency(self):
        self.completion('mail')

    def test_default_task_completion_keeps_other_active_file_dependency(self):
        self.completion('task')


if __name__ == '__main__':
    unittest.main()
