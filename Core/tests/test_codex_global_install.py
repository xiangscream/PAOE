"""Upgrade retained selected definitions once; route eleven Project Homes and Rooter."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import test_codex_selected_hook as fixture_module
from paos_installation import write_installation_descriptor
from paos_todo import render_todo
import paos_codex_hook_install as install


@unittest.skipUnless(os.name == 'nt', 'Windows command installation')
class GlobalInstallTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture_module.SelectedHookTests('test_installer_cli_prepare_apply_and_exact_restore')
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.root = self.base.root
        self.fixture = self.base.fixture
        self.sessions = ['own-session'] + [f'global-{n:02}' for n in range(2, 12)] + ['global-rooter']
        self.base.prepare()
        install.apply(self.base.packet)
        self.prior_bytes = self.base.hooks.read_bytes()
        self.packet = self.root / 'global-packet'

    def upgrade(self):
        return install.prepare(self.base.hooks, self.packet, self.sessions, self.fixture.install,
                               upgrade_from=self.base.packet)

    def test_upgrade_replaces_three_owned_groups_preserves_others_and_restores(self):
        current = json.loads(self.prior_bytes)
        extra = {'hooks': [dict(type='command', command='echo preserve-non-paoe', timeout=3)]}
        current['hooks']['SessionStart'].append(extra)
        self.base.hooks.write_bytes(install.encode(current))
        before = self.base.hooks.read_bytes()
        self.upgrade()
        candidate = json.loads((self.packet / 'candidate.json').read_bytes())
        slots, _ = install.previous_slots(self.base.packet)
        count = 0
        for event, groups in current['hooks'].items():
            self.assertEqual(len(candidate['hooks'][event]), len(groups))
            for index, group in enumerate(groups):
                got = candidate['hooks'][event][index]
                if slots.get(event) == index:
                    count += 1
                    command = got['hooks'][0]['command']
                    self.assertEqual(command.count('--session '), 12)
                    self.assertNotIn('--mode', command)
                else:
                    self.assertEqual(got, group)
        self.assertEqual(count, 3)
        self.assertEqual(self.base.hooks.read_bytes(), before)
        install.apply(self.packet)
        install.apply(self.packet, restore=True)
        self.assertEqual(self.base.hooks.read_bytes(), before)
        # A subsequent upgrade uses the recorded managed slots without adding handlers.
        install.apply(self.packet)
        second = self.root / 'second-upgrade'
        install.prepare(self.base.hooks, second, self.sessions[:2], self.fixture.install,
                        upgrade_from=self.packet)
        install.apply(second)
        install.apply(second, restore=True)
        self.assertEqual(self.base.hooks.read_bytes(), (self.packet / 'candidate.json').read_bytes())

    def test_upgrade_refuses_unknown_duplicate_or_modified_owned_definition(self):
        for change in ('modified', 'duplicate', 'wrong-packet', 'unknown-new'):
            current = json.loads(self.prior_bytes)
            if change == 'modified':
                current['hooks']['Stop'][1]['hooks'][0]['timeout'] = 7
            elif change == 'duplicate':
                current['hooks']['Stop'].append(copy.deepcopy(current['hooks']['Stop'][1]))
            elif change == 'unknown-new':
                current['hooks']['Stop'].append({'hooks': [dict(command='python paos_codex_hook.py')]})
            else:
                current['hooks']['Stop'][1]['hooks'][0]['command'] += ' --session outsider'
            self.base.hooks.write_bytes(install.encode(current))
            before = self.base.hooks.read_bytes()
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.upgrade()
            self.assertEqual(self.base.hooks.read_bytes(), before)
            self.assertFalse(self.packet.exists())

    def test_prior_packet_tamper_apply_conflict_and_no_implicit_upgrade(self):
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            install.build(json.loads(self.prior_bytes), self.sessions, self.fixture.install)
        self.upgrade()
        current = self.base.hooks.read_bytes() + b' '
        self.base.hooks.write_bytes(current)
        with self.assertRaisesRegex(ValueError, 'conflict'):
            install.apply(self.packet)
        self.assertEqual(self.base.hooks.read_bytes(), current)
        self.base.hooks.write_bytes(self.prior_bytes)
        prior_candidate = self.base.packet / 'candidate.json'
        prior_candidate.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Previous candidate'):
            install.apply(self.packet)
        self.assertEqual(self.base.hooks.read_bytes(), self.prior_bytes)

    def test_public_cli_accepts_twelve_sessions_and_retained_packet(self):
        command = [sys.executable, '-X', 'utf8', str(install.ROUTER.with_name('paos_codex_hook_install.py')),
                   'prepare', '--hooks-file', str(self.base.hooks), '--packet', str(self.packet),
                   '--installation-file', str(self.fixture.install), '--upgrade-from', str(self.base.packet)]
        for session in self.sessions:
            command.extend(['--session', session])
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf8', timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])
        self.assertEqual(self.base.hooks.read_bytes(), self.prior_bytes)

    def test_twelve_registered_homes_read_own_context_stop_once_and_ignore_others(self):
        project = self.fixture.project
        homes = ['S010'] + [f'S{n:03}' for n in range(101, 111)]
        record_path = self.fixture.data / 'project-registry/projects/3002.json'
        record = json.loads(record_path.read_bytes())
        record['homes'] = homes
        record_path.write_text(json.dumps(record))
        rooter = self.root / 'rooter-home'
        rooter.mkdir()
        write_installation_descriptor(self.fixture.install, source_root=str(fixture_module.SCRIPTS.parent),
            data_root=str(self.fixture.data), library_roots_config=str(self.root / 'libraries.json'),
            agent_numbers_config=str(self.root / 'numbers.json'), rooter_home=str(rooter))
        targets = {}
        for session, ident in zip(self.sessions, homes + ['rooter-001']):
            is_rooter = ident == 'rooter-001'
            home = rooter if is_rooter else project / 'Workstations' / ident
            home.mkdir(exist_ok=True)
            home.joinpath('ENTRY.md').write_text('Own entry ' + ident)
            if is_rooter:
                home.joinpath('AGENTS.md').write_text('[共同背景](background.md)', encoding='utf8')
                home.joinpath('background.md').write_text('Rooter background')
                home.joinpath('INDEX.md').write_text('Rooter project view')
            home.joinpath('TODO.md').write_text(render_todo(home_kind='rooter' if is_rooter else 'project_agent',
                home_id=ident, project_id='' if is_rooter else '3002', objective='ONLY-' + ident,
                next_action='continue ' + ident, context_refs=['task:T1'],
                tasks=[dict(id='T1', title='Task for ' + ident, state='doing')]), encoding='utf8')
            targets[ident] = dict(runtime='codex', session_id=session, stop_file=str(home / 'STOP'),
                extension=dict(receiver_runtime_file=str(home / 'runtime.json'), windows_python=sys.executable))
        project.joinpath('TEAM.md').write_text('\n'.join('### ' + h + '\nOwner' for h in homes))
        (self.root / 'numbers.json').write_text(json.dumps({h: h for h in homes} | {'rooter-001': 'S035'}))
        self.fixture.contact.write_text(json.dumps(targets))
        self.upgrade()
        config = json.loads((self.packet / 'candidate.json').read_bytes())
        handler = config['hooks']['UserPromptSubmit'][1]['hooks'][0]['command']
        stop_handler = config['hooks']['Stop'][1]['hooks'][0]['command']
        for session, ident in zip(self.sessions, homes + ['rooter-001']):
            with self.subTest(home=ident):
                event = dict(hook_event_name='UserPromptSubmit', session_id=session)
                result = subprocess.run(handler, input=json.dumps(event), capture_output=True,
                    text=True, encoding='utf8', env=self.base.env, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                response = json.loads(result.stdout)
                self.assertIn('ONLY-' + ident, response['hookSpecificOutput']['additionalContext'])
                event = dict(hook_event_name='Stop', session_id=session, turn_id='native-one', stop_hook_active=False)
                responses = []
                for _ in range(2):
                    result = subprocess.run(stop_handler, input=json.dumps(event), capture_output=True,
                        text=True, encoding='utf8', env=self.base.env, timeout=20)
                    responses.append(json.loads(result.stdout))
                self.assertEqual(responses[0].get('decision'), 'block')
                self.assertEqual(responses[1], {})
        for session in ('unregistered', 'registered-but-unselected'):
            if session.startswith('registered'):
                targets['S010']['session_id'] = session
                self.fixture.contact.write_text(json.dumps(targets))
            result = subprocess.run(handler, input=json.dumps(dict(hook_event_name='UserPromptSubmit', session_id=session)),
                capture_output=True, text=True, encoding='utf8', env=self.base.env, timeout=10)
            self.assertEqual(json.loads(result.stdout), {})


if __name__ == '__main__':
    unittest.main()
