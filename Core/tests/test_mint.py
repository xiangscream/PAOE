"""Explicit business checkpoints: durable one-shot effects through the old transport."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'code/personal-agent-os/scripts'))
import test_history_archive as fixtures
from paos_mint import MintRunner, arrange, cat_event, ledger, reminder_once
from paos_stage import render, deliver
from paos_todo import read_todo, write_todo, TodoProblem


class MintTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.HistoryArchiveTests()
        self.f.setUp()
        self.f.root.joinpath('numbers.json').write_text('{}', encoding='utf-8')
        self.addCleanup(self.f.doCleanups)
        self.ident = '3002-s002'
        self.path = self.f.vault / 'Workstations' / self.ident
        self.home = dict(home_kind='project_agent', home_id=self.ident, project_id='3002',
                         home_path=str(self.path), project_root=str(self.f.vault))
        self.now = datetime(2030, 1, 1, tzinfo=timezone.utc)
        self.put([dict(id='RUN', title='Real responsibility', state='doing')])
        self.wake = Mock(return_value={'accepted': True, 'completed': False})

    def put(self, tasks, home=None):
        home = Path(home or self.path)
        doc = read_todo(home / 'TODO.md')
        doc['tasks'] = tasks
        (home / 'TODO.md').write_text(render(doc), encoding='utf-8')

    def point(self, ident='P1', task='RUN', on='manual', at=None):
        return arrange(self.home, task, ident=ident, at=(at or self.now).isoformat(),
                       on=on, source='Works/original.md')

    def runner(self, **kwargs):
        return MintRunner(self.f.install, wake=self.wake, **kwargs)

    def test_due_recovered_after_sleep_and_restart_only_once(self):
        self.point()
        self.assertEqual(self.runner().step(self.now - timedelta(seconds=1)), [])
        result = self.runner().step(self.now + timedelta(hours=3))
        self.assertEqual(result[0]['status'], 'submitted')
        self.assertEqual(self.runner().step(self.now + timedelta(days=3)), [])
        self.wake.assert_called_once()
        self.assertIn('ENTRY.md', self.wake.call_args.args[2])
        self.assertEqual(read_todo(self.path / 'TODO.md')['tasks'][0]['state'], 'doing')

    def test_ordinary_text_and_future_save_do_not_wake(self):
        self.put([dict(id='RUN', title='Original', state='doing', notify_after=[
            dict(to=self.ident, when='完成后', source_ref='original')])])
        self.point(at=self.now + timedelta(days=1))
        runner = self.runner()
        runner.changed(self.path / 'TODO.md')
        self.assertEqual(runner.step(self.now), [])
        self.wake.assert_not_called()

    def test_waiting_does_not_block_other_eligible_task_or_grouped_due_points(self):
        self.put([dict(id='WAIT', title='Wait', state='waiting', waiting='Owner reply'),
                  dict(id='RUN', title='Run', state='doing')])
        self.point(task='WAIT')
        self.point(task='RUN', ident='P2')
        self.point(task='RUN', ident='P3')
        result = self.runner().step(self.now)
        self.assertEqual([r['status'] for r in result].count('suppressed'), 1)
        self.assertEqual([r['status'] for r in result].count('submitted'), 2)
        self.wake.assert_called_once()

    def test_cancel_done_and_explicit_pause_suppress(self):
        self.point()
        arrange(self.home, 'RUN', ident='P1', cancel=True)
        self.assertEqual(self.runner().step(self.now)[0]['status'], 'suppressed')
        self.point(ident='P2')
        self.assertEqual(self.runner(paused=[self.ident]).step(self.now)[0]['status'], 'suppressed')
        self.point(ident='P3')
        doc = read_todo(self.path / 'TODO.md')
        doc['tasks'][0]['state'] = 'done'
        (self.path / 'TODO.md').write_text(render(doc), encoding='utf-8')
        self.assertEqual(self.runner().step(self.now)[0]['status'], 'suppressed')
        self.wake.assert_not_called()

    def test_native_rejection_or_unknown_never_automatically_retried(self):
        for ident, accepted in [('REJECT', False), ('UNKNOWN', None)]:
            self.point(ident)
            self.wake.return_value = {'accepted': accepted, 'retry': False}
            result = self.runner().step(self.now)
            self.assertEqual(result[0]['status'], 'rejected' if accepted is False else 'uncertain')
            self.assertEqual(self.runner().step(self.now + timedelta(days=1)), [])
        self.assertEqual(self.wake.call_count, 2)

    def test_interrupted_reservation_stays_unknown_without_resend(self):
        from paos_content import pack
        from paos_mint import reserve
        self.point()
        reserve(self.f.data, self.ident, pack(['at', 'RUN', 'P1']))
        self.assertEqual(self.runner().step(self.now), [])
        self.wake.assert_not_called()

    def test_missing_timezone_and_conflicting_id_rejected(self):
        with self.assertRaises(TodoProblem):
            arrange(self.home, 'RUN', ident='P', at='2030-01-01T00:00:00', source='x')
        self.point()
        with self.assertRaises(ValueError):
            self.point(at=self.now + timedelta(hours=1))

    def test_natural_doing_arms_only_declared_arrangement(self):
        self.put([dict(id='RUN', title='Original', state='todo')])
        self.point(on='doing')
        self.assertEqual(self.runner().step(self.now), [])
        path = self.path / 'TODO.md'
        doc = read_todo(path)
        doc['tasks'][0]['state'] = 'doing'
        write_todo(path, render(doc))
        self.assertTrue(read_todo(path)['tasks'][0]['checkpoints'][0]['armed'])
        self.assertEqual(self.runner().step(self.now)[0]['status'], 'submitted')

    def test_natural_mail_claim_arms_existing_task_plan(self):
        self.point(on='claim')
        self.f.send('claim-point')
        self.f.call('mail', 'claim', '3002', self.ident, 'claim-point', '--task', 'RUN')
        doc = read_todo(self.path / 'TODO.md')
        self.assertTrue(doc['tasks'][0]['checkpoints'][0]['armed'])
        self.assertEqual(self.runner().step(self.now)[0]['status'], 'submitted')

    def test_natural_stage_arms_and_stage_notice_is_exact(self):
        self.point(on='stage')
        self.f.vault.joinpath('out.md').write_text('Actual stage result', encoding='utf-8')
        deliver(self.f.data, self.home, task_id='RUN', operation='STAGE', artifacts=['out.md'],
                intents=['out.md'], result='Done', next_action='Next', waiting='', current=False)
        self.assertTrue(read_todo(self.path / 'TODO.md')['tasks'][0]['checkpoints'][0]['armed'])
        self.assertEqual(self.runner().step(self.now)[0]['status'], 'submitted')

    def notification(self, when, source):
        self.put([dict(id='EVENT', title='Source task', state='done' if when == 'task_done' else 'doing',
                       notify_after=[dict(to=self.ident, when=when, source_ref=source)]),
                  dict(id='RUN', title='Actual target responsibility', state='doing')])

    def test_task_done_notification_keeps_source_and_target_business_state(self):
        self.notification('task_done', 'original')
        self.assertEqual(self.runner().step(self.now)[0]['status'], 'submitted')
        self.assertEqual(self.runner().step(self.now), [])
        self.assertEqual([t['state'] for t in read_todo(self.path / 'TODO.md')['tasks']], ['done', 'doing'])

    def test_cat_only_explicit_matching_room_and_message_deduplicates(self):
        self.notification('cat_checkpoint', 'cat:room-one#ready')
        self.assertEqual(self.runner().step(self.now), [])
        cat_event(self.f.data, 'other-room', 'M1', 'ready')
        self.assertEqual(self.runner().step(self.now), [])
        cat_event(self.f.data, 'room-one', 'M0', 'wrong-event')
        self.assertEqual(self.runner().step(self.now), [])
        cat_event(self.f.data, 'room-one', 'M1', 'ready')
        self.assertEqual(self.runner().step(self.now)[0]['status'], 'submitted')
        cat_event(self.f.data, 'room-one', 'M1', 'ready')
        self.assertEqual(self.runner().step(self.now), [])
        self.wake.assert_called_once()

    def test_original_reminder_and_checkpoint_share_source_in_both_orders(self):
        self.notification('task_done', 'mail:ORIGINAL')
        send = Mock(return_value={'accepted': True})
        reminder_once(self.f.install, self.ident, 'mail:ORIGINAL', send)
        self.assertEqual(self.runner().step(self.now), [])
        self.wake.assert_not_called()
        self.notification('task_done', 'mail:SECOND')
        self.runner().step(self.now)
        reminder_once(self.f.install, self.ident, 'mail:SECOND', send)
        self.assertEqual(send.call_count, 1)
        self.wake.assert_called_once()

    def test_rooter_uses_same_engine_without_cat_or_new_service(self):
        home = self.f.rooter
        self.put([dict(id='RUN', title='Rooter responsibility', state='doing')], home)
        rooter = dict(home_kind='rooter', home_id='rooter-001', project_id='', project_root='', home_path=str(home))
        arrange(rooter, 'RUN', ident='P', at=self.now.isoformat(), source='report.md')
        result = self.runner().step(self.now)
        self.assertEqual(result[0]['home'], 'rooter-001')
        self.wake.assert_called_once()

    def test_observer_routes_only_registered_todo_and_keeps_content_exclusion(self):
        runner = self.runner()
        runner.refresh()
        runner.changed(self.f.vault / 'Works/ordinary.md')
        self.assertFalse(runner.dirty)
        runner.changed(self.path / 'TODO.md')
        self.assertTrue(runner.dirty)

    def test_explicit_new_check_revisits_rejected_but_never_submitted_or_unknown(self):
        self.point()
        self.wake.return_value = {'accepted': False}
        self.runner().step(self.now)
        self.assertEqual(self.runner().step(self.now), [])
        self.runner().step(self.now, request_id='CHECK1')
        self.assertEqual(self.wake.call_count, 2)
        self.assertEqual(self.runner().step(self.now, request_id='CHECK1'), [])
        self.wake.return_value = {'accepted': True}
        self.runner().step(self.now, request_id='CHECK2')
        self.assertEqual(self.wake.call_count, 3)
        self.assertEqual(self.runner().step(self.now, request_id='CHECK3'), [])

    def test_delivery_wakes_waiting_recipient_without_unblocking_task(self):
        other = self.f.vault / 'Workstations/3002-s001'
        self.put([dict(id='WAIT', title='Wait for delivery', state='waiting', waiting='author result')], other)
        self.put([dict(id='SOURCE', title='Delivery', state='done', notify_after=[
            dict(to='3002-s001', when='task_done', source_ref='actual-result.md')])])
        self.assertEqual(self.runner().step(self.now)[0]['status'], 'submitted')
        self.assertEqual(read_todo(other / 'TODO.md')['tasks'][0]['state'], 'waiting')
        self.wake.assert_called_once()

    def test_stage_event_matches_accurate_operation(self):
        self.notification('stage_delivered', 'stage:READY')
        self.f.vault.joinpath('out.md').write_text('Actual result', encoding='utf-8')
        for operation in ('OTHER', 'READY'):
            deliver(self.f.data, self.home, task_id='EVENT', operation=operation,
                    artifacts=['out.md'], intents=['out.md'], result=operation,
                    next_action='Next', waiting='', current=False)
            result = self.runner().step(self.now)
            self.assertEqual(bool(result), operation == 'READY')
        self.wake.assert_called_once()

    def test_cat_cli_requires_quiet_and_publishes_only_explicit_signal(self):
        import paos
        from paos_cat_cli import execute_cat
        client = Mock()
        client.request.return_value = {'ok': True}
        publish = Mock(return_value={'published': True})
        base = ['cat', 'send', 'room-one', '--from', self.ident, '--body', 'Actual input', '--message-id', 'M1']
        args = paos.build_parser().parse_args(base + ['--checkpoint', 'ready', '--notify'])
        with self.assertRaises(ValueError):
            execute_cat(args, client, lambda value, *a, **kw: value, checkpoint=publish)
        client.request.assert_not_called()
        args = paos.build_parser().parse_args(base + ['--checkpoint', 'ready', '--no-notify'])
        execute_cat(args, client, lambda value, *a, **kw: value, checkpoint=publish)
        publish.assert_called_once_with('room-one', 'M1', 'ready')
        args = paos.build_parser().parse_args(base + ['--no-notify'])
        execute_cat(args, client, lambda value, *a, **kw: value, checkpoint=publish)
        self.assertEqual(publish.call_count, 1)

    def test_unknown_from_submit_stays_durable_and_other_home_input_untouched(self):
        self.point()
        self.wake.side_effect = OSError('receipt lost')
        self.assertEqual(self.runner().step(self.now)[0]['status'], 'uncertain')
        self.assertEqual(self.runner().step(self.now, request_id='NO-RESEND'), [])
        self.wake.assert_called_once()

    def test_claim_without_arrangement_reports_missing_without_inventing_time(self):
        self.f.send('no-arrangement')
        result = self.f.call('mail', 'claim', '3002', self.ident, 'no-arrangement', '--task', 'RUN')[1]
        self.assertEqual(result['checkpoint_schedule']['state'], 'schedule_missing')
        self.assertEqual(read_todo(self.path / 'TODO.md')['tasks'][0]['checkpoints'], [])

    def test_current_waiting_only_blocks_selected_timer(self):
        self.put([dict(id='RUN', title='Focused', state='doing'), dict(id='OTHER', title='Other work', state='doing')])
        self.point()
        self.point(ident='P2', task='OTHER')
        doc = read_todo(self.path / 'TODO.md')
        doc['current'].update(context_refs=['task:RUN'], waiting='Human decision')
        (self.path / 'TODO.md').write_text(render(doc), encoding='utf-8')
        result = self.runner().step(self.now)
        self.assertEqual([r['status'] for r in result], ['suppressed', 'submitted'])
        self.wake.assert_called_once()

    def test_missing_home_is_visible_and_does_not_make_another_home_idle(self):
        other = self.f.vault / 'Workstations/3002-s001/TODO.md'
        other.unlink()
        events = []
        runner = self.runner(emit=events.append)
        self.point()
        self.assertEqual(runner.step(self.now)[0]['status'], 'submitted')
        self.assertTrue(any(e.get('status') == 'unavailable' and e.get('home') == '3002-s001' for e in events))

    def test_persistent_pause_applies_to_new_runner_and_explicit_check(self):
        self.point()
        self.f.call('mint', 'pause', self.ident, '--reason', 'Human paused')
        result = self.runner().step(self.now, request_id='WHILE-PAUSED')
        self.assertEqual(result[0]['status'], 'suppressed')
        self.wake.assert_not_called()
        self.f.call('mint', 'resume', self.ident)
        self.runner().step(self.now, request_id='AFTER-RESUME')
        self.wake.assert_called_once()

    def test_paused_notification_source_slot_can_be_explicitly_rechecked(self):
        self.notification('task_done', 'mail:PAUSED-DELIVERY')
        self.assertEqual(self.runner(paused=[self.ident]).step(self.now)[0]['status'], 'suppressed')
        self.assertEqual(self.runner().step(self.now), [])
        self.assertEqual(self.runner().step(self.now, request_id='OWNER-RESUME')[0]['status'], 'submitted')
        self.wake.assert_called_once()

    def test_ledger_preserves_native_request_id_separately_from_explicit_check(self):
        self.point()
        self.wake.return_value = {'accepted': True, 'request_id': 'native-request-123'}
        result = self.runner().step(self.now, request_id='owner-check-456')
        self.assertEqual(result[0]['receipt']['request_id'], 'native-request-123')
        self.assertEqual(result[0]['receipt']['check_request_id'], 'owner-check-456')

    def test_cat_saved_fact_survives_local_event_publication_error(self):
        import paos
        from paos_cat_cli import execute_cat
        args = paos.build_parser().parse_args(['cat', 'send', 'room-one', '--from', self.ident,
            '--body', 'Original', '--message-id', 'original-id', '--checkpoint', 'ready', '--no-notify'])
        client = Mock()
        client.request.return_value = {'ok': True, 'message_id': 'original-id'}
        publish = Mock(side_effect=OSError('journal unavailable'))
        result = execute_cat(args, client, lambda value, *a, **kw: value, checkpoint=publish)
        self.assertFalse(result['ok'])
        self.assertTrue(result['cat_saved'])
        self.assertEqual(result['message_id'], 'original-id')
        self.assertEqual(client.request.call_count, 1)

    def test_waiting_timer_resumes_on_actual_task_transition_not_ordinary_save(self):
        self.put([dict(id='RUN', title='Wait for decision', state='waiting', waiting='Human input')])
        self.point()
        self.assertEqual(self.runner().step(self.now)[0]['status'], 'suppressed')
        self.assertEqual(self.runner().step(self.now), [])
        doc = read_todo(self.path / 'TODO.md')
        doc['tasks'][0].update(state='doing', waiting='')
        write_todo(self.path / 'TODO.md', render(doc))
        self.assertEqual(self.runner().step(self.now)[0]['status'], 'submitted')
        self.assertEqual(self.runner().step(self.now + timedelta(days=1)), [])
        self.wake.assert_called_once()

    def test_new_formal_stage_can_recheck_busy_timer_without_blind_retry(self):
        self.point()
        self.wake.return_value = {'accepted': False, 'state': 'native_busy'}
        self.runner().step(self.now)
        doc = read_todo(self.path / 'TODO.md')
        doc['tasks'][0]['result'] = 'Ordinary edited note'
        write_todo(self.path / 'TODO.md', render(doc))
        self.assertEqual(self.runner().step(self.now), [])
        self.f.vault.joinpath('out.md').write_text('Actual stage result', encoding='utf-8')
        deliver(self.f.data, self.home, task_id='RUN', operation='NEW-STAGE', artifacts=['out.md'],
                intents=['out.md'], result='Actual result', next_action='Continue', waiting='', current=False)
        self.wake.return_value = {'accepted': True}
        self.assertEqual(self.runner().step(self.now)[0]['status'], 'submitted')
        self.assertEqual(self.wake.call_count, 2)


@unittest.skipUnless(os.name == 'nt', 'Actual Windows observer subscriptions')
class MintObserverTests(unittest.TestCase):
    def test_project_and_rooter_todo_atomic_save_use_existing_observer_only(self):
        import test_content_watch as fixtures_watch
        from paos_content_watch import ContentWatcher
        from paos_content import list_changes
        from paos_installation import write_installation_descriptor
        from paos_todo import render_todo
        f = fixtures_watch.ContentWatchTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        numbers = f.root / 'numbers.json'
        numbers.write_text('{}', encoding='utf-8')
        write_installation_descriptor(f.install, source_root=str(Path(__file__).resolve().parents[1] / 'code/personal-agent-os'),
            data_root=str(f.data), library_roots_config=str(f.root / 'libraries.json'),
            rooter_home=str(f.rooter), agent_numbers_config=str(numbers))
        project_home = f.project / 'Workstations/S031'
        project_home.mkdir(parents=True)
        for home, kind, ident, project in ((project_home, 'project_agent', 'S031', '3002'),
                                           (f.rooter, 'rooter', 'rooter-001', '')):
            home.joinpath('TODO.md').write_text(render_todo(home_kind=kind, home_id=ident, project_id=project,
                objective='Actual responsibility', next_action='Continue original',
                tasks=[dict(id='RUN', title='Run', state='doing')]), encoding='utf-8')
            home.joinpath('ENTRY.md').write_text('Original entry', encoding='utf-8')
        wake = Mock(return_value={'accepted': True})
        mint = MintRunner(f.install, wake=wake)
        watcher = ContentWatcher(f.scope, mint=mint, settle_seconds=0)
        watcher.start()
        self.addCleanup(watcher.close)
        self.assertIn(f.rooter, watcher.streams)
        for home, kind, ident, project in ((project_home, 'project_agent', 'S031', '3002'),
                                           (f.rooter, 'rooter', 'rooter-001', '')):
            ref = dict(home_kind=kind, home_id=ident, project_id=project,
                       home_path=str(home), project_root=str(f.project) if project else '')
            arrange(ref, 'RUN', ident='AFTER-START', at='2020-01-01T00:00:00+00:00', source='original.md')
        f.wait_for(lambda: wake.call_count == 2, watcher)
        self.assertFalse(any('TODO.md' in row['locator'] for row in list_changes(f.data, 0, 500)['changes']))
        for _ in range(3):
            watcher.step()
        self.assertEqual(wake.call_count, 2)


if __name__ == '__main__':
    unittest.main()
