import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import wakeup_native.codex_transport as transport
import wakeup_native.codex_receiver as receiver


@unittest.skipUnless(os.name == 'nt', 'Default Windows application transport')
class ApplicationTransportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.descriptor = {'configured': True, 'data_root': str(self.root)}
        self.old_pipe = r'\\.\pipe\codex-app-tools-fixture-old'
        self.new_pipe = r'\\.\pipe\codex-app-tools-fixture-new'
        self.env = {'CODEX_HOME': str(self.root / 'home'), 'CODEX_APP_TOOLS_PIPE_PATH': self.old_pipe}
        self.old_host = {'pid': 11, 'process_identity': 'windows:1000'}
        self.new_host = {'pid': 12, 'process_identity': 'windows:2000'}
        self.hosts = {self.old_pipe: self.old_host, self.new_pipe: self.new_host}
        native = patch.object(transport, 'pipe_host', side_effect=lambda pipe: self.hosts[pipe])
        self.inspect = native.start()
        self.addCleanup(native.stop)
        process = patch.object(transport, 'process_snapshot', return_value={'alive': False})
        self.process = process.start()
        self.addCleanup(process.stop)
        self.scope = transport.desktop_scope(self.env)
        self.path = transport.publish_current(self.descriptor, self.env)

    def test_publication_is_application_only_and_idempotent(self):
        before = self.path.read_bytes(), self.path.stat().st_mtime_ns
        self.assertEqual(transport.publish_current(self.descriptor, self.env), self.path)
        self.assertEqual((self.path.read_bytes(), self.path.stat().st_mtime_ns), before)
        self.assertEqual(set(json.loads(before[0])), {'schema', 'scope', 'pipe', 'pid', 'process_identity'})
        self.assertEqual(transport.current_pipe(self.path, self.scope), self.old_pipe)

    def test_new_host_replaces_dead_host_and_delayed_old_event_cannot_overwrite(self):
        transport.publish_current(self.descriptor, {**self.env, 'CODEX_APP_TOOLS_PIPE_PATH': self.new_pipe})
        current = self.path.read_bytes()
        self.assertEqual(transport.current_pipe(self.path, self.scope), self.new_pipe)
        def inspect(pipe):
            if pipe == self.old_pipe:
                raise FileNotFoundError('Old application connection no longer exists')
            return self.hosts[pipe]
        self.inspect.side_effect = inspect
        with self.assertRaises(FileNotFoundError):
            transport.publish_current(self.descriptor, self.env)
        self.assertEqual(self.path.read_bytes(), current)

    def test_live_or_unknown_previous_instance_is_preserved(self):
        before = self.path.read_bytes()
        for previous in ({'alive': True, 'identity': 'windows:1000'}, {'alive': None}):
            with self.subTest(previous=previous):
                self.process.return_value = previous
                with self.assertRaises(transport.TransportProblem):
                    transport.publish_current(self.descriptor, {**self.env, 'CODEX_APP_TOOLS_PIPE_PATH': self.new_pipe})
                self.assertEqual(self.path.read_bytes(), before)

    def test_two_connections_in_same_live_application_are_explicitly_ambiguous(self):
        self.hosts[self.new_pipe] = self.old_host
        before = self.path.read_bytes()
        with self.assertRaisesRegex(transport.TransportProblem, 'ambiguous'):
            transport.publish_current(self.descriptor, {**self.env, 'CODEX_APP_TOOLS_PIPE_PATH': self.new_pipe})
        self.assertEqual(self.path.read_bytes(), before)

    def test_same_application_can_replace_a_verified_missing_connection(self):
        self.hosts[self.new_pipe] = self.old_host
        def inspect(pipe):
            if pipe == self.old_pipe:
                raise FileNotFoundError('Old application connection no longer exists')
            return self.hosts[pipe]
        self.inspect.side_effect = inspect
        transport.publish_current(self.descriptor, {**self.env, 'CODEX_APP_TOOLS_PIPE_PATH': self.new_pipe})
        self.assertEqual(transport.current_pipe(self.path, self.scope), self.new_pipe)

    def test_same_application_preserves_record_when_old_connection_is_unverified(self):
        self.hosts[self.new_pipe] = self.old_host
        original = self.path.read_bytes()
        def inspect(pipe):
            if pipe == self.old_pipe:
                raise PermissionError('Cannot verify old connection')
            return self.hosts[pipe]
        self.inspect.side_effect = inspect
        with self.assertRaises(PermissionError):
            transport.publish_current(self.descriptor, {**self.env, 'CODEX_APP_TOOLS_PIPE_PATH': self.new_pipe})
        self.assertEqual(self.path.read_bytes(), original)

    def test_other_scope_cannot_publish_or_read_this_transport(self):
        other = {**self.env, 'CODEX_HOME': str(self.root / 'another-home')}
        original = self.path.read_bytes()
        with self.assertRaisesRegex(transport.TransportProblem, 'scope_mismatch'):
            transport.publish_current(self.descriptor, other)
        self.inspect.reset_mock()
        with self.assertRaisesRegex(transport.TransportProblem, 'scope_mismatch'):
            transport.current_pipe(self.path, transport.desktop_scope(other))
        self.inspect.assert_not_called()
        self.assertEqual(self.path.read_bytes(), original)

    def test_explicit_profile_is_rejected_before_publication(self):
        before = self.path.read_bytes()
        with self.assertRaisesRegex(transport.TransportProblem, 'profile_unsupported'):
            transport.publish_current(self.descriptor, {**self.env, 'CODEX_ELECTRON_USER_DATA_PATH': 'another'})
        self.assertEqual(self.path.read_bytes(), before)

    def test_server_pid_reuse_and_missing_publication_are_visible(self):
        self.hosts[self.old_pipe] = {**self.old_host, 'process_identity': 'windows:3000'}
        with self.assertRaisesRegex(transport.TransportProblem, 'host_changed'):
            transport.current_pipe(self.path, self.scope)
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):
            transport.current_pipe(self.path, self.scope)

    def test_idle_receiver_selects_new_application_but_keeps_its_caller(self):
        transport.publish_current(self.descriptor, {**self.env, 'CODEX_APP_TOOLS_PIPE_PATH': self.new_pipe})
        old_client = Mock(pipe_path=self.old_pipe)
        new_client = Mock(pipe_path=self.new_pipe)
        new_client.thread_status.return_value = 'idle'
        reminder = receiver.SelfReminder(old_client, 'fixed-owner', self.root / 'STOP',
                                         transport_file=self.path, transport_scope=self.scope)
        with patch.object(receiver, 'DesktopPipeClient', return_value=new_client) as client:
            result = reminder.send({'session_id': 'fixed-owner', 'message': 'real new task'})
        self.assertTrue(result['accepted'])
        self.assertFalse(result['completed'])
        client.assert_called_once_with(self.new_pipe, 'fixed-owner')
        new_client.thread_status.assert_called_once_with('fixed-owner')
        new_client.wake.assert_called_once_with('fixed-owner', 'real new task')
        old_client.thread_status.assert_not_called()
        old_client.wake.assert_not_called()

    def test_stop_or_wrong_target_never_reads_transport(self):
        stop = self.root / 'STOP'
        reminder = receiver.SelfReminder(Mock(), 'fixed-owner', stop,
                                         transport_file=self.path, transport_scope=self.scope)
        with patch.object(receiver, 'current_pipe') as read:
            with self.assertRaises(receiver.ReceiverError):
                reminder.send({'session_id': 'another', 'message': 'task'})
            stop.touch()
            with self.assertRaises(receiver.ReceiverError):
                reminder.send({'session_id': 'fixed-owner', 'message': 'task'})
            read.assert_not_called()

    def test_missing_transport_does_not_fall_back_to_captured_connection(self):
        self.path.unlink()
        client = Mock()
        reminder = receiver.SelfReminder(client, 'fixed-owner', self.root / 'STOP',
                                         transport_file=self.path, transport_scope=self.scope)
        with self.assertRaises(receiver.ReceiverError) as caught:
            reminder.send({'session_id': 'fixed-owner', 'message': 'task'})
        self.assertEqual(caught.exception.code, 'desktop_transport_unavailable')
        self.assertEqual(caught.exception.diagnostic['operation'], 'application_transport')
        client.thread_status.assert_not_called()
        client.wake.assert_not_called()

    def test_invalid_record_is_preserved_and_never_resolved(self):
        self.path.write_text('{"schema":"unknown"}', encoding='utf-8')
        self.inspect.reset_mock()
        with self.assertRaisesRegex(transport.TransportProblem, 'record_invalid'):
            transport.current_pipe(self.path, self.scope)
        self.inspect.assert_not_called()
        self.assertEqual(self.path.read_text(), '{"schema":"unknown"}')

    def test_unknown_send_result_does_not_reselect_transport_or_retry(self):
        transport.publish_current(self.descriptor, {**self.env, 'CODEX_APP_TOOLS_PIPE_PATH': self.new_pipe})
        client = Mock(pipe_path=self.new_pipe)
        client.thread_status.return_value = 'idle'
        client.wake.side_effect = OSError('missing receipt')
        reminder = receiver.SelfReminder(Mock(pipe_path=self.old_pipe), 'fixed-owner', self.root / 'STOP',
                                         transport_file=self.path, transport_scope=self.scope)
        with patch.object(receiver, 'DesktopPipeClient', return_value=client), \
             patch.object(receiver, 'current_pipe', wraps=transport.current_pipe) as lookup:
            with self.assertRaises(receiver.ReceiverError) as caught:
                reminder.send({'session_id': 'fixed-owner', 'message': 'task'})
            self.assertEqual(caught.exception.code, 'delivery_not_confirmed')
            lookup.assert_called_once()
        client.wake.assert_called_once()


@unittest.skipUnless(os.name == 'nt', 'Windows pipe host evidence')
class NativeHostTests(unittest.TestCase):
    def test_product_and_instance_must_both_match_the_supplied_pipe(self):
        root = Path(tempfile.gettempdir())
        image = str(root / 'WindowsApps' / 'OpenAI.Codex_26.1120.6357.0_x64__2p2nqsd0c76g0' / 'app' / 'ChatGPT.exe')
        snapshot = {'alive': True, 'identity': 'windows:1000'}
        for supplied_image, snapshots, valid in (
                (image, [snapshot, snapshot], True),
                (str(root / 'different-product' / 'ChatGPT.exe'), [snapshot], False),
                (image, [snapshot, {'alive': True, 'identity': 'windows:2000'}], False)):
            with self.subTest(image=supplied_image, valid=valid), \
                 patch.object(ctypes, 'WinDLL') as load, patch('msvcrt.get_osfhandle', return_value=7), \
                 patch('builtins.open'), patch.object(transport, 'process_snapshot', side_effect=snapshots):
                kernel = load.return_value
                kernel.OpenProcess.return_value = 99

                def server(handle, output):
                    output._obj.value = 41
                    return True

                def query(handle, flags, output, length):
                    output.value = supplied_image
                    return True

                kernel.GetNamedPipeServerProcessId.side_effect = server
                kernel.QueryFullProcessImageNameW.side_effect = query
                if valid:
                    self.assertEqual(transport.pipe_host(r'\\.\pipe\codex-app-tools-fixture'),
                                     {'pid': 41, 'process_identity': 'windows:1000'})
                else:
                    with self.assertRaises(transport.TransportProblem):
                        transport.pipe_host(r'\\.\pipe\codex-app-tools-fixture')


if __name__ == '__main__':
    unittest.main()
