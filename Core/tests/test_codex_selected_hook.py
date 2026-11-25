"""Before/apply/restore through actual Windows command handlers in isolated Homes."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_codex_context_hook as fixture_module
import paos_codex_hook_install as install

SCRIPTS = Path(__file__).resolve().parents[1] / 'code/personal-agent-os/scripts'


@unittest.skipUnless(os.name == 'nt', 'Windows command configuration')
class SelectedHookTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.CodexContextHookTests('test_unknown_session_is_noop')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.hooks = self.root / 'hooks.json'
        self.packet = self.root / 'packet'
        self.env = dict(self.fixture.environment, PAOS_INSTALLATION_FILE=str(self.fixture.install))
        old = f'"{sys.executable}" -X utf8 -B "{SCRIPTS / "codex_receiver_session_start.py"}"'
        self.handler = dict(type='command', command=old, timeout=10, statusMessage='Original message')
        self.original = {'description': 'Keep exact original', 'hooks': {
            'SessionStart': [{'matcher': '^(startup|resume)$', 'hooks': [self.handler]}],
            'UserPromptSubmit': [{'hooks': [self.handler]}],
            'Stop': [{'hooks': [{'type': 'command', 'command': 'echo original-other-stop', 'timeout': 4}]}],
            'PreToolUse': [{'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'echo other'}]}]}}
        self.original_bytes = (json.dumps(self.original, indent=4) + '\r\n').encode()
        self.hooks.write_bytes(self.original_bytes)
        contact = json.loads(self.fixture.contact.read_bytes())
        other = copy.deepcopy(contact['S010'])
        other['session_id'] = 's052-example'
        other['extension']['receiver_runtime_file'] = str(self.root / 'other/runtime.json')
        contact['S052'] = other
        self.fixture.contact.write_text(json.dumps(contact))
        registry_path = self.fixture.data / 'project-registry/projects/3002.json'
        registry = json.loads(registry_path.read_bytes())
        registry['homes'].append('S052')
        registry_path.write_text(json.dumps(registry))
        (self.fixture.project / 'Workstations/S052').mkdir(parents=True)

    def prepare(self):
        return install.prepare(self.hooks, self.packet, ['own-session'], self.fixture.install)

    def matching(self, config, event):
        for group in config['hooks'].get(event['hook_event_name'], []):
            if event['hook_event_name'] == 'SessionStart' and not re.search(group.get('matcher', ''), event['source']):
                continue
            for handler in group['hooks']:
                if 'codex_' in handler['command']:
                    yield handler

    def invoke(self, config, event):
        outputs = []
        for handler in self.matching(config, event):
            result = subprocess.run(handler['command'], input=json.dumps(event).encode(),
                                    capture_output=True, env=self.env, timeout=35)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.append(json.loads(result.stdout))
        return outputs

    def events(self, session):
        return [dict(hook_event_name='SessionStart', session_id=session, source=s)
                for s in ('startup', 'resume', 'compact')] + [
                    dict(hook_event_name='UserPromptSubmit', session_id=session, prompt='private'),
                    dict(hook_event_name='Stop', session_id=session, turn_id='turn-one', stop_hook_active=False)]

    def test_before_after_restore_selected_and_other_sessions(self):
        selected_before = [self.invoke(self.original, e) for e in self.events('own-session')]
        log = self.fixture.runtime.with_name('runtime.json.lifecycle.jsonl')
        before_count = len(log.read_text().splitlines())
        before = {session: [self.invoke(self.original, e) for e in self.events(session)]
                  for session in ('s052-example', 'unregistered-example')}
        self.prepare()
        self.assertEqual(self.hooks.read_bytes(), self.original_bytes)
        install.apply(self.packet)
        candidate = json.loads(self.hooks.read_bytes())
        for session in before:
            for index, event in enumerate(self.events(session)):
                outputs = self.invoke(candidate, event)
                self.assertEqual([r for r in outputs if r], [r for r in before[session][index] if r])
                self.assertFalse(any('PAOE 本次必读原文' in str(r) or r.get('decision') == 'block' for r in outputs))
        for index, event in enumerate(self.events('own-session')[:4]):
            results = self.invoke(candidate, event)
            new = [r for r in results if 'PAOE 本次必读原文' in r.get('hookSpecificOutput', {}).get('additionalContext', '')]
            self.assertEqual(len(new), 1)
            self.assertEqual([r for r in results if r not in new], selected_before[index])
        event = self.events('own-session')[-1]
        outputs = self.invoke(candidate, event)
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0].get('decision'), 'block')
        self.assertEqual(self.invoke(candidate, event), [{}])
        # Legacy observers see three events. The selected handler observes all four.
        records = [json.loads(s) for s in log.read_text().splitlines()]
        self.assertEqual([row['entrypoint'] for row in records[before_count:]],
                         ['receiver', 'context', 'receiver', 'context', 'context', 'receiver', 'context'])
        install.apply(self.packet, restore=True)
        self.assertEqual(self.hooks.read_bytes(), self.original_bytes)
        for session in before:
            self.assertEqual([self.invoke(json.loads(self.hooks.read_bytes()), e) for e in self.events(session)], before[session])
        self.assertEqual([self.invoke(json.loads(self.hooks.read_bytes()), e) for e in self.events('own-session')], selected_before)

    def test_other_hook_definitions_and_legacy_metadata_preserved(self):
        self.prepare()
        candidate = json.loads((self.packet / 'candidate.json').read_bytes())
        self.assertEqual(candidate['description'], self.original['description'])
        self.assertEqual(candidate['hooks']['PreToolUse'], self.original['hooks']['PreToolUse'])
        self.assertEqual(candidate['hooks']['Stop'][0], self.original['hooks']['Stop'][0])
        for event in ('SessionStart', 'UserPromptSubmit'):
            original = self.original['hooks'][event][0]
            self.assertEqual(candidate['hooks'][event][0], original)

    def test_selected_stop_file_and_mismatched_owner_remain_enforced(self):
        self.prepare()
        candidate = json.loads((self.packet / 'candidate.json').read_bytes())
        self.fixture.stop.write_text('Human STOP')
        for event in self.events('own-session'):
            active = [r for r in self.invoke(candidate, event) if 'continue' in r]
            self.assertEqual(len(active), 1)
            self.assertFalse(active[0]['continue'])
            self.assertIn('STOP', active[0]['stopReason'])
        self.fixture.stop.unlink()
        self.env['CODEX_THREAD_ID'] = 'different-owner'
        active = [r for r in self.invoke(candidate, self.events('own-session')[0]) if 'continue' in r]
        self.assertFalse(active[0]['continue'])

    def test_unreviewed_append_preserves_trusted_definitions_and_positions(self):
        self.prepare()
        candidate = json.loads((self.packet / 'candidate.json').read_bytes())
        trusted_only = copy.deepcopy(candidate)
        for event, groups in self.original['hooks'].items():
            self.assertEqual(candidate['hooks'][event][:len(groups)], groups)
            trusted_only['hooks'][event] = candidate['hooks'][event][:len(groups)]
        self.assertEqual(trusted_only, self.original)
        for session in ('own-session', 's052-example', 'unregistered-example'):
            for event in self.events(session):
                self.assertEqual(self.invoke(trusted_only, event), self.invoke(self.original, event))

    def test_selected_handler_checks_owner_receiver_on_each_read_event(self):
        hook = fixture_module.hook
        env = dict(self.env, CODEX_THREAD_ID='own-session', CODEX_APP_TOOLS_PIPE_PATH='fixture')
        with patch.dict(os.environ, env, clear=True):
            for event in self.events('own-session')[:4]:
                with self.subTest(event=event), \
                     patch.object(hook, 'prepare_current', return_value='receiver_prepare_reused: fixture') as prepare, \
                     patch.object(hook, 'observe_hook_entry') as observe, \
                     patch.object(hook, 'call_context', wraps=hook.call_context) as context:
                    result = hook.run_hook(event, self.fixture.install)
                    original = result['hookSpecificOutput']['additionalContext']
                    self.assertIn('PAOE 本次必读原文', original)
                    self.assertNotIn('[PAOE 接收器]', original)
                    prepare.assert_called_once()
                    self.assertEqual(prepare.call_args.kwargs['event'], event)
                    self.assertEqual(prepare.call_args.kwargs['expected_home']['home_id'], 'S010')
                    observe.assert_called_once_with(event, installation_path=self.fixture.install, entrypoint='context')
                    context.assert_called_once()

    def test_selected_without_legacy_or_owner_preserves_read_and_requests_same_owner_tool(self):
        self.prepare()
        candidate = json.loads((self.packet / 'candidate.json').read_bytes())
        for event in ('SessionStart', 'UserPromptSubmit'):
            candidate['hooks'][event].pop(0)
        self.env['CODEX_APP_TOOLS_PIPE_PATH'] = 'fixture'
        log = self.fixture.runtime.with_name('runtime.json.lifecycle.jsonl')
        for event in self.events('own-session')[:4]:
            with self.subTest(event=event):
                [result] = self.invoke(candidate, event)
                self.assertEqual(result['systemMessage'],
                                 'receiver_prepare_skipped: original_desktop_environment_missing')
                original = result['hookSpecificOutput']['additionalContext']
                self.assertIn('PAOE 本次必读原文', original)
                self.assertIn('Original entry', original)
                self.assertIn('orient 3002 S010 --resume', original)
        records = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(len(records), 4)
        self.assertTrue(all(row['entrypoint'] == 'context' for row in records))
        self.assertTrue(all(row['desktop_connection_present'] and not row['owner_thread_present']
                            and not row['owner_thread_matches'] for row in records))
        self.assertFalse(self.fixture.runtime.exists())

        self.env['CODEX_THREAD_ID'] = 'another-owner'
        [result] = self.invoke(candidate, self.events('own-session')[1])
        self.assertFalse(result['continue'])
        self.assertNotIn('hookSpecificOutput', result)
        self.assertEqual(len(log.read_text().splitlines()), 4)
        self.assertFalse(self.fixture.runtime.exists())

    def test_conflicting_apply_restore_and_candidate_mutation_do_not_overwrite(self):
        self.prepare()
        edited = self.original_bytes + b' '
        self.hooks.write_bytes(edited)
        with self.assertRaisesRegex(ValueError, 'conflict'):
            install.apply(self.packet)
        self.assertEqual(self.hooks.read_bytes(), edited)
        self.hooks.write_bytes(self.original_bytes)
        install.apply(self.packet)
        changed = self.hooks.read_bytes() + b' '
        self.hooks.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, 'conflict'):
            install.apply(self.packet, restore=True)
        self.assertEqual(self.hooks.read_bytes(), changed)
        (self.packet / 'candidate.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Candidate'):
            install.apply(self.packet)

    def test_missing_duplicate_or_modified_original_is_explicit_conflict(self):
        for mutation in ('missing', 'duplicate', 'matcher', 'new-hook', 'windows-override'):
            original = copy.deepcopy(self.original)
            if mutation == 'missing':
                original['hooks'].pop('UserPromptSubmit')
            elif mutation == 'duplicate':
                original['hooks']['SessionStart'].append(copy.deepcopy(original['hooks']['SessionStart'][0]))
            elif mutation == 'matcher':
                original['hooks']['SessionStart'][0]['matcher'] = '.*'
            elif mutation == 'new-hook':
                original['hooks']['Stop'][0]['hooks'][0]['command'] = 'python paos_codex_hook.py'
            else:
                original['hooks']['Stop'][0]['hooks'][0]['commandWindows'] = 'python paos_codex_hook.py'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                install.build(original, ['own-session'], self.fixture.install)

    def test_unselected_new_hooks_do_not_read_missing_installation(self):
        self.prepare()
        candidate = json.loads((self.packet / 'candidate.json').read_bytes())
        self.fixture.install.unlink()
        for event in self.events('unregistered-example'):
            handler = list(self.matching(candidate, event))[-1]
            result = subprocess.run(handler['command'], input=json.dumps(event).encode(),
                                    capture_output=True, env=self.env, timeout=10)
            self.assertEqual(json.loads(result.stdout), {})

    def test_sibling_toml_conflict_is_checked_before_prepare_and_apply(self):
        toml = self.root / 'config.toml'
        trust = '[hooks.state.original]\ntrusted_hash="unchanged"\n'
        toml.write_text(trust)
        self.prepare()
        self.assertEqual(toml.read_text(), trust)
        toml.write_text('[[hooks.Stop]]\n[[hooks.Stop.hooks]]\ncommand="python paos_codex_hook.py"\ntype="command"\n')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            install.apply(self.packet)
        self.assertEqual(self.hooks.read_bytes(), self.original_bytes)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            install.prepare(self.hooks, self.root / 'newpacket', ['own-session'], self.fixture.install)

    def test_installer_cli_prepare_apply_and_exact_restore(self):
        command = [sys.executable, '-X', 'utf8', str(SCRIPTS / 'paos_codex_hook_install.py')]
        for args in ([ 'prepare', '--hooks-file', str(self.hooks), '--packet', str(self.packet),
                       '--session', 'own-session', '--installation-file', str(self.fixture.install)],
                     ['apply', '--packet', str(self.packet)],
                     ['restore', '--packet', str(self.packet)]):
            result = subprocess.run(command + args, capture_output=True, text=True, encoding='utf8', timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue(json.loads(result.stdout)['trust_review_required'])
        self.assertEqual(self.hooks.read_bytes(), self.original_bytes)


if __name__ == '__main__':
    unittest.main()
