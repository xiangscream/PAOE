"""Exercise notice entry boundaries against disposable registered Homes only."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SYSTEM = next(p for p in Path(__file__).resolve().parents if (p / 'Core/code/personal-agent-os/scripts/paos.py').is_file())
SCRIPTS = SYSTEM / 'Core/code/personal-agent-os/scripts'
MOTHER = SYSTEM / 'Project-Template/Workstations/_workstation/notices'
sys.path.insert(0, str(SCRIPTS))
import codex_receiver_session_start
import paos_contact


class WakeEntryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='paoe-wake-entry-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / 'Project/Workstations/3002-s099'
        notices = self.home / 'notices'; notices.mkdir(parents=True)
        for name in ('codex.py', 'opencode.py', 'wake_entry.py'):
            shutil.copyfile(MOTHER / name, notices / name)
        self.install = self.root / 'installation.json'
        self.install.write_text(json.dumps({
            'schema': 'paos-installation/v1', 'source_root': str(SCRIPTS.parent),
            'data_root': str(self.root/'data'),
            'library_roots_config': str(self.root/'libraries.json'),
        }), 'utf-8')
        record = self.root / 'data/project-registry/projects/3002.json'
        record.parent.mkdir(parents=True)
        record.write_text(json.dumps({'schema': 'paos-project-registry/v1', 'id': '3002',
            'root_path': str(self.root/'Project'), 'homes': ['3002-s099'],
            'coordinator_home_id': '3002-s099'}), 'utf-8')
        spec = importlib.util.spec_from_file_location('fixture_wake_entry', notices/'wake_entry.py')
        self.entry = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.entry)

    def snapshot(self):
        return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                if p.is_file() else None for p in self.root.rglob('*')}

    def call(self, driver, *args):
        with contextlib.redirect_stderr(io.StringIO()):
            return self.entry.main(driver, ['--installation-file', str(self.install), *args])

    def test_codex_binding_uses_this_home_and_explicit_installation(self):
        before = self.snapshot()
        with patch.dict(os.environ, {'PAOS_INSTALLATION_FILE': str(self.root/'wrong.json')}), \
             patch.object(self.entry.subprocess, 'run') as run:
            run.return_value.returncode = 0
            self.assertEqual(self.call('codex', 'bind', '--session-id', 'real-thread'), 0)
            command = run.call_args.args[0]
            self.assertEqual(command[command.index('bind')+1:],
                ['3002','3002-s099','--driver','codex','--native-session-id','real-thread'])
            self.assertEqual(run.call_args.kwargs['env']['PAOS_INSTALLATION_FILE'], str(self.install))
        self.assertEqual(before, self.snapshot())

    def test_opencode_binding_uses_the_supplied_private_config(self):
        config = self.root/'target.json'; config.write_text('{}','utf-8')
        before = self.snapshot()
        with patch.object(self.entry.subprocess, 'run') as run:
            run.return_value.returncode = 0
            self.assertEqual(self.call('opencode','bind','--session-id','real-session','--driver-config',str(config)),0)
            command = run.call_args.args[0]
            self.assertEqual(command[-2:], ['--driver-config',str(config.resolve())])
            self.assertEqual(command[command.index('--driver')+1], 'opencode')
        self.assertEqual(before, self.snapshot())

    def test_copied_entry_outside_registered_home_is_rejected(self):
        wrong = self.root/'other/Workstations/3002-s099/notices/wake_entry.py'
        wrong.parent.mkdir(parents=True); shutil.copyfile(MOTHER/'wake_entry.py',wrong)
        self.entry.__file__ = str(wrong)
        before = self.snapshot()
        with patch.object(self.entry.subprocess,'run') as run:
            self.assertEqual(self.call('codex','bind','--session-id','thread'),2)
            run.assert_not_called()
        self.assertEqual(before,self.snapshot())

    def test_prepare_requires_original_desktop_environment(self):
        before = self.snapshot()
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'','CODEX_APP_TOOLS_PIPE_PATH':''}), \
             patch.object(self.entry.subprocess,'run') as run:
            self.assertEqual(self.call('codex','prepare'),2); run.assert_not_called()
        self.assertEqual(before,self.snapshot())

    def test_prepare_rejects_another_owner(self):
        before = self.snapshot()
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'other-thread','CODEX_APP_TOOLS_PIPE_PATH':'test-only'}), \
             patch.object(codex_receiver_session_start,'registered_target',return_value=({'home_path':str(self.root/'Other')},{})) as resolve, \
             patch.object(self.entry.subprocess,'run') as run:
            self.assertEqual(self.call('codex','prepare'),2); run.assert_not_called()
            resolve.assert_called_once()
        self.assertEqual(before,self.snapshot())

    def test_prepare_calls_installed_owner_guard_once(self):
        before = self.snapshot()
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'owner-thread','CODEX_APP_TOOLS_PIPE_PATH':'test-only'}), \
             patch.object(codex_receiver_session_start,'registered_target',return_value=({'home_path':str(self.home)},{})) as resolve, \
             patch.object(self.entry.subprocess,'run') as run:
            run.return_value.returncode = 0
            self.assertEqual(self.call('codex','prepare'),0)
            resolve.assert_called_once(); run.assert_called_once()
            self.assertEqual(run.call_args.args[0][-2:],
                [str(SCRIPTS/'codex_receiver_session_start.py'),'--prepare-current'])
            self.assertEqual(run.call_args.kwargs['cwd'],SCRIPTS)
        self.assertEqual(before,self.snapshot())

    def test_wrong_harness_is_rejected_before_execution(self):
        before = self.snapshot()
        with patch.object(paos_contact,'load_native_targets',return_value={'3002-s099':{'runtime':'opencode'}}), \
             patch.object(self.entry.subprocess,'run') as run:
            self.assertEqual(self.call('codex','status'),2); run.assert_not_called()
        self.assertEqual(before,self.snapshot())

    def test_uncertain_or_failed_wake_is_not_retried(self):
        before = self.snapshot()
        with patch.object(self.entry.subprocess,'run') as run:
            run.return_value.returncode = 17
            self.assertEqual(self.call('opencode','wake','--prompt','resume original task'),17)
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0][-2:],['--prompt','resume original task'])
        self.assertEqual(before,self.snapshot())

    def test_real_status_is_read_only_without_native_session(self):
        before = self.snapshot(); actual_run = subprocess.run; receipts = []
        def capture(command, **kwargs):
            result = actual_run(command, **kwargs, capture_output=True, text=True, encoding='utf-8', timeout=15)
            receipts.append(result)
            return result
        with patch.object(self.entry.subprocess,'run',side_effect=capture):
            code = self.call('opencode','status')
        self.assertEqual(code,0,receipts[0].stdout+receipts[0].stderr)
        self.assertTrue(json.loads(receipts[0].stdout)['ok'])
        self.assertEqual(before,self.snapshot())


if __name__ == '__main__':
    unittest.main()
