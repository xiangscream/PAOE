"""Before/apply/restore through actual Windows command handlers in isolated Homes."""
import copy
import ctypes
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
from urllib.request import ProxyHandler, Request, build_opener

import test_codex_context_hook as fixture_module
import paos_codex_hook_install as install

SCRIPTS = Path(__file__).resolve().parents[1] / 'code/personal-agent-os/scripts'


def breakaway_restriction():
    """Skip real detached-child tests only for a verified restrictive Windows Job."""
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
            ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
            ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
            ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD),
            ('SchedulingClass', wintypes.DWORD),
        ]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.IsProcessInJob.argtypes = (wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL))
    kernel.IsProcessInJob.restype = wintypes.BOOL
    kernel.QueryInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                               wintypes.DWORD, ctypes.c_void_p)
    kernel.QueryInformationJobObject.restype = wintypes.BOOL
    inside = wintypes.BOOL()
    if not kernel.IsProcessInJob(kernel.GetCurrentProcess(), None, ctypes.byref(inside)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not inside.value:
        return None
    limits = BasicLimits()
    if not kernel.QueryInformationJobObject(None, 2, ctypes.byref(limits), ctypes.sizeof(limits), None):
        raise ctypes.WinError(ctypes.get_last_error())
    if limits.LimitFlags & (0x800 | 0x1000):  # BREAKAWAY_OK or SILENT_BREAKAWAY_OK.
        return None
    return f'Current Windows Job explicitly disallows breakaway (LimitFlags={limits.LimitFlags:#x})'


@unittest.skipUnless(os.name == 'nt', 'Windows Job capability')
class BreakawayCapabilityTests(unittest.TestCase):
    def test_only_known_restrictive_job_skips_the_real_child_test(self):
        for in_job, flags, restricted in ((False, 0, False), (True, 0x2000, True),
                                           (True, 0x800, False), (True, 0x1000, False)):
            with self.subTest(in_job=in_job, flags=flags), patch.object(ctypes, 'WinDLL') as load:
                kernel = load.return_value

                def membership(process, job, output):
                    output._obj.value = in_job
                    return True

                def limits(job, information_class, output, size, returned):
                    self.assertEqual(information_class, 2)
                    output._obj.LimitFlags = flags
                    return True

                kernel.IsProcessInJob.side_effect = membership
                kernel.QueryInformationJobObject.side_effect = limits
                self.assertEqual(breakaway_restriction() is not None, restricted)
                self.assertEqual(kernel.QueryInformationJobObject.call_count, int(in_job))

    def test_job_query_failure_is_an_error_and_does_not_become_a_skip(self):
        for operation in ('IsProcessInJob', 'QueryInformationJobObject'):
            with self.subTest(operation=operation), patch.object(ctypes, 'WinDLL') as load:
                kernel = load.return_value

                def membership(process, job, output):
                    output._obj.value = True
                    return operation != 'IsProcessInJob'

                kernel.IsProcessInJob.side_effect = membership
                kernel.QueryInformationJobObject.return_value = False
                with self.assertRaises(OSError):
                    breakaway_restriction()


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

    def test_selected_without_connection_preserves_read_and_requests_same_owner_tool(self):
        self.prepare()
        candidate = json.loads((self.packet / 'candidate.json').read_bytes())
        for event in ('SessionStart', 'UserPromptSubmit'):
            candidate['hooks'][event].pop(0)
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
        self.assertTrue(all(not row['desktop_connection_present'] and not row['owner_thread_present']
                            and not row['owner_thread_matches'] for row in records))
        self.assertFalse(self.fixture.runtime.exists())

        self.env['CODEX_THREAD_ID'] = 'another-owner'
        [result] = self.invoke(candidate, self.events('own-session')[1])
        self.assertFalse(result['continue'])
        self.assertNotIn('hookSpecificOutput', result)
        self.assertEqual(len(log.read_text().splitlines()), 4)
        self.assertFalse(self.fixture.runtime.exists())

    def test_native_hook_without_owner_prepares_and_reuses_real_isolated_receiver(self):
        restriction = breakaway_restriction()
        if restriction is not None:
            self.skipTest(restriction)
        other_home = self.fixture.project / 'Workstations/S052'
        team = self.fixture.project / 'TEAM.md'
        team.write_text(team.read_text(encoding='utf-8') + '\n### S052\nAnother publisher\n', encoding='utf-8')
        (other_home / 'ENTRY.md').write_text('Another native publisher', encoding='utf-8')
        (other_home / 'TODO.md').write_text(fixture_module.render_todo(
            home_kind='project_agent', home_id='S052', project_id='3002',
            objective='Publish the replacement application connection', next_action='Read own input', tasks=[]),
            encoding='utf-8')
        contacts = json.loads(self.fixture.contact.read_bytes())
        contacts['S052']['stop_file'] = str(self.root / 'other/STOP')
        self.fixture.contact.write_text(json.dumps(contacts), encoding='utf-8')
        install.prepare(self.hooks, self.packet, ['own-session', 's052-example'], self.fixture.install)
        candidate = json.loads((self.packet / 'candidate.json').read_bytes())
        for name in ('SessionStart', 'UserPromptSubmit'):
            candidate['hooks'][name].pop(0)
        self.env['CODEX_APP_TOOLS_PIPE_PATH'] = 'isolated-native-hook-fixture'
        self.env['USERPROFILE'] = str(self.root / 'isolated-user')
        # Keep native host discovery synthetic while exercising the actual Hook/receiver processes.
        shim = self.root / 'native-boundary'
        shim.mkdir()
        calls = self.root / 'native-calls.jsonl'
        (shim / 'sitecustomize.py').write_text(
            "import json\n"
            "from pathlib import Path\n"
            "from importlib.util import find_spec\n"
            "import wakeup_native.codex_app_tools as tools\n"
            "if find_spec('wakeup_native.codex_transport') is not None:\n"
            "    import wakeup_native.codex_transport as transport\n"
            "    def host(pipe):\n"
            "        replacement = pipe == 'isolated-replacement-connection'\n"
            "        return {'pid': 100002 if replacement else 100001,\n"
            "                'process_identity': 'windows:2000' if replacement else 'windows:1000'}\n"
            "    transport.pipe_host = host\n"
            "    transport.process_snapshot = lambda pid: {'alive': False}\n"
            "class NativeClient:\n"
            "    def __init__(self, pipe, caller):\n"
            "        self.pipe_path, self.caller_thread_id = pipe, caller\n"
            "    def thread_status(self, target): return 'idle'\n"
            "    def wake(self, target, message):\n"
            f"        with Path({str(calls)!r}).open('a', encoding='utf-8') as output:\n"
            "            output.write(json.dumps({'pipe': self.pipe_path, 'caller': self.caller_thread_id,\n"
            "                                     'target': target, 'message': message}) + '\\n')\n"
            "tools.DesktopPipeClient = NativeClient\n", encoding='utf-8')
        self.env['PYTHONPATH'] = os.pathsep.join((str(shim), str(SCRIPTS)))
        from wakeup_native.process_identity import process_snapshot, stop_windows_instance
        from wakeup_native.codex_receiver import desktop_connection_identity

        def dispose(pid=None, runtime_file=self.fixture.runtime, stop_file=self.fixture.stop):
            if pid is None:
                if not runtime_file.exists():
                    return
                pid = json.loads(runtime_file.read_bytes())['pid']
            process = process_snapshot(pid, str(runtime_file), str(stop_file))
            if process.get('alive'):
                self.assertTrue(process.get('invocation_matches'))
                stop_windows_instance(pid, process['identity'])
        self.addCleanup(dispose)
        [first] = self.invoke(candidate, self.events('own-session')[0])
        self.assertIn('receiver_prepare_started: S010 PID ', first['systemMessage'])
        pid = int(re.search(r'PID (\d+)', first['systemMessage'])[1])

        def wait_ready(expected_pid, runtime_file=self.fixture.runtime):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if runtime_file.is_file():
                    try:
                        value = json.loads(runtime_file.read_bytes())
                    except json.JSONDecodeError:
                        pass  # Exclusive publication is still being written by the child.
                    else:
                        if value['pid'] == expected_pid:
                            return value
                time.sleep(0.02)
            self.fail('Isolated receiver did not publish readiness')

        runtime = wait_ready(pid)
        self.assertEqual(runtime['pid'], pid)
        self.assertEqual(runtime['session_id'], 'own-session')
        status = build_opener(ProxyHandler({})).open(Request(
            runtime['endpoint'] + '/status', headers={'Authorization': 'Bearer ' + runtime['token']}), timeout=2)
        with status:
            status_body = json.load(status)
        self.assertEqual(status_body['desktop_connection_id'],
                         desktop_connection_identity(self.env['CODEX_APP_TOOLS_PIPE_PATH']))
        original = self.fixture.runtime.read_bytes()
        for event in self.events('own-session')[1:4]:
            [result] = self.invoke(candidate, event)
            self.assertIn(f'receiver_prepare_reused: S010 PID {pid}', result['systemMessage'])
            self.assertNotIn('[PAOE 接收器]', result['hookSpecificOutput']['additionalContext'])
        self.assertEqual(self.fixture.runtime.read_bytes(), original)
        self.assertNotIn('CODEX_THREAD_ID', self.env)

        self.env['CODEX_APP_TOOLS_PIPE_PATH'] = 'isolated-replacement-connection'
        publisher_runtime = Path(contacts['S052']['extension']['receiver_runtime_file'])
        self.addCleanup(dispose, None, publisher_runtime, Path(contacts['S052']['stop_file']))
        [publisher] = self.invoke(candidate, self.events('s052-example')[1])
        self.assertIn('receiver_prepare_started: S052 PID ', publisher['systemMessage'])
        publisher_pid = int(re.search(r'PID (\d+)', publisher['systemMessage'])[1])
        wait_ready(publisher_pid, publisher_runtime)
        self.assertEqual(self.fixture.runtime.read_bytes(), original)
        request = Request(runtime['endpoint'] + '/send', method='POST',
                          headers={'Authorization': 'Bearer ' + runtime['token'], 'Content-Type': 'application/json'},
                          data=json.dumps({'session_id': 'own-session', 'message': 'new real handoff'}).encode())
        with build_opener(ProxyHandler({})).open(request, timeout=5) as response:
            self.assertTrue(json.load(response)['accepted'])
        self.assertEqual([json.loads(line) for line in calls.read_text().splitlines()], [
            {'pipe': 'isolated-replacement-connection', 'caller': 'own-session',
             'target': 'own-session', 'message': 'new real handoff'}])
        self.assertTrue(status_body['application_transport'])
        self.assertEqual(self.fixture.runtime.read_bytes(), original)
        [resumed] = self.invoke(candidate, self.events('own-session')[1])
        self.assertIn(f'receiver_prepare_reused: S010 PID {pid}', resumed['systemMessage'])
        self.env['CODEX_THREAD_ID'] = 'another-owner'
        [result] = self.invoke(candidate, self.events('own-session')[1])
        self.assertFalse(result['continue'])
        self.assertNotIn('hookSpecificOutput', result)
        self.assertEqual(self.fixture.runtime.read_bytes(), original)

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
