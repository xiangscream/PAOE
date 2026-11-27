"""Already archived inputs retain their original recipient and history bytes after migration."""
import json
from pathlib import Path
import unittest

import test_same_home_cleanup as fixture
from paos_stage import render
from paos_todo import read_todo
from paos_input_cleanup import read_deleted


class HistoricalArchiveCleanupTests(unittest.TestCase):
    def setUp(self):
        self.x = fixture.SameHomeCleanupTests()
        self.x.setUp()
        self.addCleanup(self.x.doCleanups)
        x = self.x
        self.task = x.f.call('mail', 'claim', '3003', x.old, x.mid)[1]['task_id']
        x.consume()
        path = x.home / 'TODO.md'
        doc = read_todo(path)
        task = next(t for t in doc['tasks'] if t['id'] == self.task)
        task.update(state='done', artifact_ref='result.md')
        task['source_refs'].append('notice:' + x.notice)
        path.write_text(render(doc), encoding='utf-8')
        self.history = x.f.root / 'history'
        x.f.call('attention', 'archive-input', '3003', x.old, '--message-id', x.mid,
                  '--history-root', str(self.history))
        x.migrate()
        self.marker = x.home / 'mailbox/.archived' / (x.mid + '.json')
        self.original_marker = self.marker.read_bytes()
        self.original_history = {p.relative_to(self.history): p.read_bytes()
                                 for p in self.history.rglob('*') if p.is_file()}

    def cleanup(self, ok=True):
        x = self.x
        return x.f.call('input-cleanup', x.current, '--task', self.task,
                         '--preserved-ref', 'result.md', ok=ok)

    def assert_preserved(self):
        self.assertEqual(self.marker.read_bytes(), self.original_marker)
        self.assertEqual({p.relative_to(self.history): p.read_bytes()
                          for p in self.history.rglob('*') if p.is_file()}, self.original_history)
        self.assertIsNone(read_deleted(self.x.home, 'mail', self.x.mid))

    def test_archive_and_original_notice_alias_are_retained_and_reentry_is_read_only(self):
        result = self.cleanup()[1]
        self.assertTrue(result['complete'])
        self.assertEqual(result['items'], [{'source_ref': self.x.mid, 'state': 'archived_retained'}])
        self.assertEqual(self.cleanup()[1]['items'], result['items'])
        self.assertEqual(self.x.cleanup()[1]['state'], 'archived_retained')
        self.assert_preserved()

    def test_other_unfinished_references_do_not_change_the_archive_or_todo(self):
        path = self.x.home / 'TODO.md'
        doc = read_todo(path)
        doc['tasks'].append(dict(id='ACTIVE', state='doing', title='Keep references',
                                source_refs=['mail:' + self.x.mid, 'notice:' + self.x.notice]))
        path.write_text(render(doc), encoding='utf-8')
        before = path.read_bytes()
        self.assertTrue(self.cleanup()[1]['complete'])
        self.assertEqual(path.read_bytes(), before)
        self.assert_preserved()

    def test_foreign_archive_is_rejected_without_rewriting_it(self):
        record = json.loads(self.original_marker)
        record['recipient_agent_id'] = '3003-s002'
        self.marker.write_text(json.dumps(record), encoding='utf-8')
        before = self.marker.read_bytes()
        self.assertNotEqual(self.cleanup(ok=False)[0], 0)
        self.assertEqual(self.marker.read_bytes(), before)
        self.assertIsNone(read_deleted(self.x.home, 'mail', self.x.mid))

    def test_archive_after_migration_also_covers_original_notice_reference(self):
        y = fixture.SameHomeCleanupTests()
        y.setUp()
        self.addCleanup(y.doCleanups)
        task = y.f.call('mail', 'claim', '3003', y.old, y.mid)[1]['task_id']
        y.consume()
        y.migrate()
        path = y.home / 'TODO.md'
        doc = read_todo(path)
        chosen = next(t for t in doc['tasks'] if t['id'] == task)
        chosen.update(state='done', artifact_ref='result.md')
        chosen['source_refs'].append('notice:' + y.notice)
        path.write_text(render(doc), encoding='utf-8')
        y.f.call('attention', 'archive-input', '3003', y.current, '--message-id', y.mid,
                 '--history-root', str(y.f.root / 'history'))
        marker = y.home / 'mailbox/.archived' / (y.mid + '.json')
        original = marker.read_bytes()
        result = y.f.call('input-cleanup', y.current, '--task', task, '--preserved-ref', 'result.md')[1]
        self.assertTrue(result['complete'])
        self.assertEqual(len(result['items']), 1)
        self.assertEqual(result['items'][0]['state'], 'archived_retained')
        self.assertEqual(marker.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
