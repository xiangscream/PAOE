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
from paos_notice import (
    create_notice,
    handle_notice,
    list_notices,
    mark_notice_read,
)
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
        self.other_vault = self.root / 'other-project'
        self.other_project = {
            'schema': 'paos-project-registry/v1',
            'id': '2001',
            'root_path': str(self.other_vault),
            'homes': ['2001-s009'],
            'coordinator_home_id': '2001-s009',
        }
        (records / '2001.json').write_text(
            json.dumps(self.other_project, ensure_ascii=False), encoding='utf-8'
        )
        for sid in ('3002-s001', '3002-s002'):
            self.make_home(self.vault / 'Workstations' / sid, sid, '3002')
        self.make_home(
            self.other_vault / 'Workstations' / '2001-s009', '2001-s009', '2001'
        )
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
        self.assertTrue(read['mail']['handling']['handled'])
        self.assertEqual(read['mail']['handling']['state'], 'handled')
        self.assertEqual(read['mail']['handling']['reason'], '已处理')
        self.assertEqual(read['mail']['handling']['action_ref'], 'Works/test.md')
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

    def test_partial_delivery_multi_recipient_retries_only_missing_side(self):
        mailbox = self.vault / 'Workstations/3002-s002/mailbox'
        shutil.rmtree(mailbox)
        args = (
            'attention', 'send', '3002', '--to', '3002-s001', '--to', '3002-s002',
            '--sender-kind', 'agent', '--sender-id', '3002-s001',
            '--subject', '部分投递', '--body', '可重试的正文。',
            '--message-id', 'msg-partial-002',
        )
        first = self.call(*args)[1]
        first_states = {
            item['recipient_agent_id']: item['state']
            for item in first['mail']['deliveries']
        }
        self.assertEqual(first_states['3002-s001'], 'delivered')
        self.assertEqual(first_states['3002-s002'], 'workstation_missing')
        mailbox.mkdir()
        replay = self.call(*args)[1]
        replay_states = {
            item['recipient_agent_id']: item['state']
            for item in replay['mail']['deliveries']
        }
        self.assertEqual(replay_states['3002-s001'], 'already_delivered')
        self.assertEqual(replay_states['3002-s002'], 'delivered')
        self.assertTrue((mailbox / 'msg-partial-002.md').is_file())

    def test_cross_project_archive_marker_blocks_sender_replay(self):
        history = self.root / 'cross-history'
        args = (
            'attention', 'send', '3002', '--to', '2001-s009',
            '--sender-kind', 'agent', '--sender-id', '3002-s001',
            '--subject', '跨项目历史', '--body', '跨项目正文。',
            '--message-id', 'msg-cross-001',
        )
        sent = self.call(*args)[1]
        target_mail = self.other_vault / 'Workstations/2001-s009/mailbox/msg-cross-001.md'
        self.assertTrue(target_mail.is_file())
        target_home = self.other_vault / 'Workstations/2001-s009'
        notice_id = list_notices(target_home)['items'][0]['notice_id']
        self.call('attention', 'read', '2001', '2001-s009', notice_id)
        self.call(
            'attention', 'handle', '2001', '2001-s009', notice_id,
            '--resolution', '跨项目已处理', '--action-ref', 'Works/cross.md',
        )
        self.call(
            'attention', 'archive-input', '2001', '2001-s009',
            '--message-id', 'msg-cross-001', '--history-root', str(history),
        )
        self.assertFalse(target_mail.exists())
        self.assertTrue(
            (target_home / 'mailbox/.archived/msg-cross-001.json').is_file()
        )
        replay = self.call(*args)[1]
        self.assertFalse(target_mail.exists())
        self.assertEqual(list_notices(target_home)['count'], 0)
        self.assertEqual(
            replay['notices']['external_routes'][0]['mail_state'], 'archived'
        )
        read = self.call(
            'attention', 'history-read', '--history-root', str(history),
            '--agent-id', '2001-s009', '--message-id', 'msg-cross-001',
        )[1]
        self.assertEqual(read['notice']['state'], 'handled')

    def test_rooter_home_archive_reentry_and_history_read(self):
        args = (
            'attention', 'send', '3002', '--to', 'rooter-001',
            '--sender-kind', 'agent', '--sender-id', '3002-s001',
            '--subject', 'Rooter 历史', '--body', 'Rooter 正文。',
            '--message-id', 'msg-rooter-history-001',
        )
        self.call(*args)
        notice_id = list_notices(self.rooter)['items'][0]['notice_id']
        self.call('attention', 'rooter-read', notice_id)
        self.call(
            'attention', 'rooter-handle', notice_id,
            '--resolution', 'Rooter 已处理', '--action-ref', 'Works/rooter.md',
        )
        history = self.root / 'rooter-history'
        self.call(
            'attention', 'rooter-archive-input', '--message-id',
            'msg-rooter-history-001', '--history-root', str(history),
        )
        self.assertFalse((self.rooter / 'mailbox/msg-rooter-history-001.md').exists())
        self.assertTrue(
            (self.rooter / 'mailbox/.archived/msg-rooter-history-001.json').is_file()
        )
        replay = self.call(*args)[1]
        self.assertFalse((self.rooter / 'mailbox/msg-rooter-history-001.md').exists())
        self.assertEqual(list_notices(self.rooter)['count'], 0)
        self.assertEqual(
            replay['notices']['external_routes'][0]['mail_state'], 'archived'
        )
        read = self.call(
            'attention', 'rooter-history-read', '--history-root', str(history),
            '--message-id', 'msg-rooter-history-001',
        )[1]
        self.assertEqual(read['notice']['state'], 'handled')
        self.assertEqual(list_notices(self.rooter)['count'], 0)

    def test_rooter_legacy_full_filename_archives_with_original_identity(self):
        legacy_name = '2026-09-22-rooter-legacy'
        filename = f'{legacy_name}.md'
        mailbox = self.rooter / 'mailbox'
        (mailbox / filename).write_text(
            '# Rooter legacy\n\nRooter 旧信正文。\n', encoding='utf-8'
        )
        notice = create_notice(
            home_path=self.rooter,
            home_kind='rooter',
            home_id='rooter-001',
            project_id='',
            source_kind='mail',
            source_ref=f'rooter-mail-file:{filename}',
            summary='Rooter legacy',
        )
        mark_notice_read(
            home_path=self.rooter,
            notice_id=notice['notice_id'],
            reader_home_kind='rooter',
            reader_home_id='rooter-001',
            reader_project_id='',
        )
        handle_notice(
            home_path=self.rooter,
            notice_id=notice['notice_id'],
            resolution='Rooter 旧信已处理',
            action_ref='Works/rooter-legacy.md',
        )
        history = self.root / 'rooter-legacy-history'

        archived = self.call(
            'attention', 'rooter-archive-input', '--message-id', filename,
            '--history-root', str(history),
        )[1]

        self.assertEqual(archived['message_id'], legacy_name)
        self.assertEqual(archived['state'], 'archived')
        self.assertFalse((mailbox / filename).exists())
        self.assertTrue(
            (history / 'Workstations/rooter-001/mailbox' / filename).is_file()
        )
        self.assertTrue((mailbox / '.archived' / f'{legacy_name}.json').is_file())
        self.assertFalse((history / 'Workstations/rooter-001/mailbox' / f'{filename}.md').exists())
        read = self.call(
            'attention', 'rooter-history-read', '--history-root', str(history),
            '--message-id', filename,
        )[1]
        self.assertIn('Rooter 旧信正文', read['mail']['markdown'])
        self.assertEqual(read['notice']['state'], 'handled')
        self.assertEqual(
            read['notice']['source_ref'], f'rooter-mail-file:{filename}'
        )
        self.assertTrue(read['mail']['handling']['handled'])

    def test_rooter_local_reference_copy_keeps_original_recipient(self):
        message_id = 'msg-reference-copy-20261005'
        filename = f'{message_id}.md'
        mailbox = self.rooter / 'mailbox'
        (mailbox / filename).write_text(
            '---\nschema: paos-workstation-mail/v1\n'
            f'message_id: "{message_id}"\nproject_id: "3002"\n'
            'recipient_agent_id: "3002-s010"\ncreated_at: "2026-10-05T08:25:10Z"\n'
            'sender_kind: "agent"\nsender_id: "3002-s027"\n'
            'audience: "targeted"\nsubject: "reference copy"\n---\n\n'
            '# reference copy\n\nRooter 本地参考正文。\n',
            encoding='utf-8',
        )
        notice = create_notice(
            home_path=self.rooter,
            home_kind='rooter',
            home_id='rooter-001',
            project_id='',
            source_kind='mail',
            source_ref=message_id,
            summary='reference copy',
        )
        mark_notice_read(
            home_path=self.rooter,
            notice_id=notice['notice_id'],
            reader_home_kind='rooter',
            reader_home_id='rooter-001',
            reader_project_id='',
        )
        handle_notice(
            home_path=self.rooter,
            notice_id=notice['notice_id'],
            resolution='本地参考副本已处理',
            action_ref='Works/rooter-reference.md',
        )
        history = self.root / 'rooter-reference-history'

        archived = self.call(
            'attention', 'rooter-archive-input', '--message-id', filename,
            '--history-root', str(history),
        )[1]

        self.assertEqual(archived['message_id'], message_id)
        self.assertEqual(archived['state'], 'archived')
        self.assertFalse((mailbox / filename).exists())
        self.assertTrue(
            (history / 'Workstations/rooter-001/mailbox' / filename).is_file()
        )
        read = self.call(
            'attention', 'rooter-history-read', '--history-root', str(history),
            '--message-id', filename,
        )[1]
        self.assertEqual(
            read['mail']['metadata']['recipient_agent_id'], '3002-s010'
        )
        self.assertEqual(read['notice']['state'], 'handled')
        self.assertEqual(read['notice']['source_ref'], message_id)

    def test_rooter_missing_legacy_filename_returns_structured_error(self):
        history = self.root / 'rooter-missing-history'
        code, result = self.call(
            'attention', 'rooter-archive-input', '--message-id',
            'missing-rooter-legacy.md', '--history-root', str(history),
            ok=False,
        )
        self.assertNotEqual(code, 0)
        self.assertIn('attention_mail_missing', str(result))
        self.assertNotIn('Traceback', str(result))

    def test_history_read_legacy_mail_alias_projects_notice_handling(self):
        history = self.root / 'legacy-history'
        home = history / 'Workstations/2001-s009'
        (home / 'mailbox').mkdir(parents=True)
        (home / 'notices').mkdir()
        (home / 'mailbox/legacy-001.md').write_text(
            '---\nschema: paos-workstation-mail/v1\n'
            'recipient_agent_id: 2001-s009\n'
            'subject: Legacy\n---\n\n旧信正文\n',
            encoding='utf-8',
        )
        notice = create_notice(
            home_path=home,
            home_kind='project_agent',
            home_id='2001-s009',
            project_id='2001',
            source_kind='mail',
            source_ref='legacy-mail-file:legacy-001.md',
            summary='Legacy',
        )
        notice_id = notice['notice_id']
        mark_notice_read(
            home_path=home,
            notice_id=notice_id,
            reader_home_kind='project_agent',
            reader_home_id='2001-s009',
            reader_project_id='2001',
        )
        handle_notice(
            home_path=home,
            notice_id=notice_id,
            resolution='legacy 已处理',
            action_ref='Works/legacy.md',
        )
        read = self.call(
            'attention', 'history-read', '--history-root', str(history),
            '--agent-id', '2001-s009', '--message-id', 'legacy-001',
        )[1]
        self.assertEqual(read['notice']['state'], 'handled')
        self.assertEqual(read['notice']['source_ref'], 'legacy-mail-file:legacy-001.md')
        self.assertTrue(read['mail']['handling']['handled'])
        self.assertEqual(read['mail']['handling']['reason'], 'legacy 已处理')

    def test_legacy_chinese_filename_mail_can_be_archived_and_read_back(self):
        legacy_name = '2026-09-22-固定工位接班'
        home = self.vault / 'Workstations/3002-s002'
        mailbox = home / 'mailbox'
        (mailbox / f'{legacy_name}.md').write_text(
            '# 旧信\n\n旧信正文。\n', encoding='utf-8'
        )
        notice = create_notice(
            home_path=home,
            home_kind='project_agent',
            home_id='3002-s002',
            project_id='3002',
            source_kind='mail',
            source_ref=f'legacy-mail-file:{legacy_name}.md',
            summary='旧信',
        )
        mark_notice_read(
            home_path=home,
            notice_id=notice['notice_id'],
            reader_home_kind='project_agent',
            reader_home_id='3002-s002',
            reader_project_id='3002',
        )
        handle_notice(
            home_path=home,
            notice_id=notice['notice_id'],
            resolution='旧信已处理',
            action_ref='Works/legacy.md',
        )
        history = self.root / 'legacy-history'

        archived = self.call(
            'attention', 'archive-input', '3002', '3002-s002',
            '--message-id', f'{legacy_name}.md', '--history-root', str(history),
        )[1]

        self.assertEqual(archived['message_id'], legacy_name)
        self.assertEqual(archived['state'], 'archived')
        self.assertFalse((mailbox / f'{legacy_name}.md').exists())
        self.assertTrue(
            (history / 'Workstations/3002-s002/mailbox' / f'{legacy_name}.md').is_file()
        )
        self.assertTrue((mailbox / '.archived' / f'{legacy_name}.json').is_file())
        replay = self.call(
            'attention', 'archive-input', '3002', '3002-s002',
            '--message-id', f'{legacy_name}.md', '--history-root', str(history),
        )[1]
        self.assertEqual(replay['state'], 'already_archived')
        read = self.call(
            'attention', 'history-read', '--history-root', str(history),
            '--agent-id', '3002-s002', '--message-id', f'{legacy_name}.md',
        )[1]
        self.assertIn('旧信正文', read['mail']['markdown'])
        self.assertEqual(read['notice']['state'], 'handled')
        self.assertEqual(
            read['notice']['source_ref'], f'legacy-mail-file:{legacy_name}.md'
        )
        self.assertTrue(read['mail']['handling']['handled'])

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
