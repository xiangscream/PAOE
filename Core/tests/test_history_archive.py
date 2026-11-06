"""Synthetic contracts for moving handled Mail/Notice to an external batch."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'code' / 'personal-agent-os' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import paos
from paos_installation import write_installation_descriptor
from paos_mail import list_mail
from paos_notice import list_notices
from paos_orient import render_orient
from paos_contact import parse_team_payload
from paos_todo import render_todo


class HistoryArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'workspace'
        self.root.mkdir()
        self.root = self.root.resolve()
        self.data = self.root / 'data'
        records = self.data / 'project-registry' / 'projects'
        records.mkdir(parents=True)
        self.vault = self.root / 'project'
        self.rooter = self.root / 'Rooter' / 'rooter-001'
        self.install = self.root / 'installation.json'
        write_installation_descriptor(
            self.install,
            source_root=str(SCRIPTS.parent),
            library_roots_config=str(self.root / 'library-roots.json'),
            data_root=str(self.data),
            rooter_home=str(self.rooter),
            agent_numbers_config=str(self.root / 'numbers.json'),
        )
        self.project = {
            'schema': 'paos-project-registry/v1',
            'id': '3002',
            'root_path': str(self.vault),
            'homes': ['3002-s001', '3002-s002'],
            'coordinator_home_id': '3002-s001',
        }
        (records / '3002.json').write_text(
            json.dumps(self.project, ensure_ascii=False), encoding='utf-8'
        )
        for sid in ('3002-s001', '3002-s002'):
            self.make_home(self.vault / 'Workstations' / sid, sid, '3002')
        self.make_home(self.rooter, 'rooter-001', '')
        self.env = patch.dict(os.environ, {
            'HOME': str(self.root),
            'USERPROFILE': str(self.root),
            'PAOS_INSTALLATION_FILE': str(self.root / 'wrong-installation.json'),
            'PAOS_LIBRARY_ROOTS_CONFIG': '',
            'PAOS_BASE_URL': 'not even a URL',
            'PYTHONIOENCODING': 'utf-8',
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def make_home(self, path, sid, pid):
        (path / 'mailbox').mkdir(parents=True)
        (path / 'notices').mkdir()
        (path / 'ENTRY.md').write_text('# 入口\n参照项目最新口径。\n', encoding='utf-8')
        (path / 'TODO.md').write_text(
            render_todo(
                home_kind='project_agent' if pid else 'rooter',
                home_id=sid,
                project_id=pid,
                objective='处理并归档输入',
                next_action='核对历史批次',
            ),
            encoding='utf-8',
        )

    def call(self, *args, ok=True):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = paos.main([
                    '--installation-file', str(self.install), '--json', *args
                ])
            except SystemExit as exc:
                code = exc.code
        if ok:
            self.assertEqual(code, 0, err.getvalue() + out.getvalue())
        raw = out.getvalue() or err.getvalue()
        try:
            return code, json.loads(raw)
        except ValueError:
            return code, raw

    def send(self, message_id='msg-history-001'):
        return self.call(
            'attention', 'send', '3002', '--to', '3002-s002',
            '--sender-kind', 'agent', '--sender-id', '3002-s001',
            '--subject', '历史输入', '--body', '这条输入已处理，可以归档。',
            '--message-id', message_id,
        )[1]

    def mark_done(self, notice_id):
        self.call('attention', 'read', '3002', '3002-s002', notice_id)
        self.call(
            'attention', 'handle', '3002', '3002-s002', notice_id,
            '--resolution', '已处理', '--action-ref', 'Works/test.md',
        )

    def test_handled_mail_moves_with_notice_and_can_be_read_back(self):
        sent = self.send()
        notice_id = sent['notices']['items'][0]['notice_id']
        self.mark_done(notice_id)
        history = self.root / 'external-history'
        result = self.call(
            'attention', 'archive-input', '3002', '3002-s002',
            '--message-id', 'msg-history-001', '--history-root', str(history),
        )[1]
        self.assertEqual(result['state'], 'archived')
        self.assertFalse((self.vault / 'Workstations/3002-s002/mailbox/msg-history-001.md').exists())
        self.assertFalse((self.vault / 'Workstations/3002-s002/notices' / f'{notice_id}.md').exists())
        self.assertTrue((history / 'Workstations/3002-s002/mailbox/msg-history-001.md').is_file())
        self.assertTrue((history / 'Workstations/3002-s002/notices' / f'{notice_id}.md').is_file())
        read = self.call(
            'attention', 'history-read', '--history-root', str(history),
            '--agent-id', '3002-s002', '--message-id', 'msg-history-001',
        )[1]
        self.assertIn('这条输入已处理', read['mail']['markdown'])
        self.assertEqual(read['notice']['state'], 'handled')
        self.assertTrue(read['notice']['read'])
        self.assertEqual(list_mail(self.vault, '3002-s002')['count'], 0)

    def test_same_message_id_reentry_does_not_recreate_archived_mail_or_notice(self):
        sent = self.send()
        notice_id = sent['notices']['items'][0]['notice_id']
        self.mark_done(notice_id)
        history = self.root / 'external-history'
        self.call(
            'attention', 'archive-input', '3002', '3002-s002',
            '--message-id', 'msg-history-001', '--history-root', str(history),
        )
        before = (history / 'Workstations/3002-s002/notices' / f'{notice_id}.md').read_bytes()
        replay = self.send()
        self.assertFalse((self.vault / 'Workstations/3002-s002/mailbox/msg-history-001.md').exists())
        self.assertFalse((self.vault / 'Workstations/3002-s002/notices' / f'{notice_id}.md').exists())
        self.assertEqual(replay['mail']['deliveries'][0]['state'], 'archived')
        self.assertTrue(
            (self.vault / 'Workstations/3002-s002/mailbox/.archived/msg-history-001.json').is_file()
        )
        self.assertEqual(replay['notices']['items'], [])
        self.assertEqual(
            before,
            (history / 'Workstations/3002-s002/notices' / f'{notice_id}.md').read_bytes(),
        )

    def test_unread_or_unhandled_input_is_not_moved(self):
        sent = self.send('msg-history-002')
        notice_id = sent['notices']['items'][0]['notice_id']
        history = self.root / 'external-history'
        code, result = self.call(
            'attention', 'archive-input', '3002', '3002-s002',
            '--message-id', 'msg-history-002', '--history-root', str(history),
            ok=False,
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(result['error_code'], 'attention_history_unread')
        self.assertTrue((self.vault / 'Workstations/3002-s002/mailbox/msg-history-002.md').exists())

        self.call('attention', 'read', '3002', '3002-s002', notice_id)
        code, result = self.call(
            'attention', 'archive-input', '3002', '3002-s002',
            '--message-id', 'msg-history-002', '--history-root', str(history),
            ok=False,
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(result['error_code'], 'attention_history_unhandled')
        self.assertTrue((self.vault / 'Workstations/3002-s002/mailbox/msg-history-002.md').exists())

    def test_conflict_leaves_source_and_destination_unchanged(self):
        sent = self.send('msg-history-003')
        notice_id = sent['notices']['items'][0]['notice_id']
        self.mark_done(notice_id)
        history = self.root / 'external-history'
        target = history / 'Workstations/3002-s002/mailbox/msg-history-003.md'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'conflict')
        code, result = self.call(
            'attention', 'archive-input', '3002', '3002-s002',
            '--message-id', 'msg-history-003', '--history-root', str(history),
            ok=False,
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(result['error_code'], 'attention_history_conflict')
        self.assertTrue((self.vault / 'Workstations/3002-s002/mailbox/msg-history-003.md').exists())
        self.assertEqual(target.read_bytes(), b'conflict')

    def test_partial_delivery_retry_is_not_blocked_without_archive_marker(self):
        mailbox = self.vault / 'Workstations/3002-s002/mailbox'
        shutil.rmtree(mailbox)
        first = self.send('msg-partial-001')
        self.assertEqual(first['mail']['deliveries'][0]['state'], 'workstation_missing')
        mailbox.mkdir()
        replay = self.send('msg-partial-001')
        self.assertEqual(replay['mail']['deliveries'][0]['state'], 'delivered')
        self.assertTrue((mailbox / 'msg-partial-001.md').is_file())
        self.assertFalse((mailbox / '.archived/msg-partial-001.json').exists())

    def test_direct_notice_can_move_and_be_read_by_notice_id(self):
        source = self.root / 'incoming-direct.md'
        source.write_text('直接输入原件', encoding='utf-8')
        registered = self.call(
            'attention', 'source-register', '3002', '3002-s002',
            '--source-ref', str(source), '--summary', '直接输入',
        )[1]
        notice_id = registered['notice']['notice_id']
        self.mark_done(notice_id)
        history = self.root / 'external-history'
        self.call(
            'attention', 'archive-input', '3002', '3002-s002',
            '--notice-id', notice_id, '--history-root', str(history),
        )
        self.assertFalse(
            (self.vault / 'Workstations/3002-s002/notices' / f'{notice_id}.md').exists()
        )
        read = self.call(
            'attention', 'history-read', '--history-root', str(history),
            '--agent-id', '3002-s002', '--notice-id', notice_id,
        )[1]
        self.assertEqual(read['notice']['state'], 'handled')
        self.assertTrue(read['notice']['read'])
        self.assertEqual(read['notice']['summary'], '直接输入')

    def test_registered_home_label_does_not_say_unregistered(self):
        orient = render_orient({
            'identity': {'agent_id': '3002-s002', 'project_id': '3002', 'identity_id': None},
            'entry': {'available': True},
            'todo': {'trusted': True, 'current': {}},
            'project': {},
            'communication': {},
        })
        self.assertIn('registered Home', orient)
        self.assertNotIn('unregistered', orient)
        lines: list[str] = []
        parse_team_payload({
            'agents': [{
                'agent_id': '3002-s002',
                'identity_id': None,
                'membership_basis': 'fixed_workstation',
                'session_status': 'no_active_session',
                'workstation_todo': {},
            }]
        }, lines)
        self.assertIn('registered Home', '\n'.join(lines))
        self.assertNotIn('unregistered', '\n'.join(lines))


if __name__ == '__main__':
    unittest.main()
