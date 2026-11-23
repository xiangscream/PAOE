"""Installation Data paths and explicit machine-store migration."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import subprocess

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE / "code/personal-agent-os/scripts"
sys.path.insert(0, str(SCRIPTS))
from paos_data_paths import (
    contact_store_path, mail_dispatch_dir, project_scope, ui_board_path,
)
from paos_data_migration import execute, plan, rollback
from paos_contact import load_native_targets, save_native_targets
from paos_installation import write_installation_descriptor
from paos_mail import send_mail
from paos_mail_tracking import handoff_status
from paos_registry import ProjectRegistry
from paos_wakeup import bind_wakeup, unbind_wakeup
from codex_receiver_session_start import registered_target
from paos_installation import load_installation_descriptor


class DataMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="paoe-data-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.install = self.base / "installation.json"
        self.data = self.base / "Data"
        self.rooter = self.base / "rooter"
        self.rooter.mkdir()
        write_installation_descriptor(
            self.install, source_root=str(PACKAGE / "code/personal-agent-os"),
            data_root=str(self.data), library_roots_config=str(self.base / "libs.json"),
            rooter_home=str(self.rooter))
        self.registry = ProjectRegistry(self.install)
        for project_id in ("1001", "1002", "1003", "1004", "1005"):
            root = self.base / f"project-{project_id}"
            root.mkdir()
            self.registry.register(project_id, root_path=str(root),
                                   coordinator_home_id=f"{project_id}-s001",
                                   homes=[f"{project_id}-s001"])
            self._old_contact(root, {f"{project_id}-s001": {"runtime": "codex"}})
            (root / ".paos/mail/dispatch").mkdir(parents=True)
            (root / ".paos/mail/dispatch/msg-1.json").write_text("{}", encoding="utf-8")
            (root / ".paos/ui").mkdir(parents=True)
            (root / ".paos/ui/board.json").write_text(
                json.dumps({"nodes": {f"{project_id}-s001": {"x": 1, "y": 2}}}),
                encoding="utf-8")
        self._old_contact(self.rooter, {"rooter-001": {"runtime": "codex"}})
        (self.rooter / ".paos/mail/dispatch").mkdir(parents=True)
        (self.rooter / ".paos/mail/dispatch/rooter-1.json").write_text("{}", encoding="utf-8")
        (self.rooter / ".paos/ui").mkdir(parents=True)
        (self.rooter / ".paos/ui/board.json").write_text("{}", encoding="utf-8")

    def _old_contact(self, root: Path, value: dict):
        path = root / "private-data/contact/native-targets.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_plan_execute_and_rollback(self):
        self.assertEqual(contact_store_path(self.install),
                         self.data / "contact/native-targets.json")
        self.assertEqual(mail_dispatch_dir(project_scope("1001"), self.install),
                         self.data / "mail/project-1001/dispatch")
        self.assertEqual(ui_board_path(project_scope("1001"), self.install),
                         self.data / "ui/project-1001/board.json")
        planned = plan(self.install)
        self.assertEqual(set(planned["contact_keys"]),
                         {"1001-s001", "1002-s001", "1003-s001", "1004-s001", "1005-s001", "rooter-001"})
        self.assertEqual(len(planned["mail"]), 6)
        self.assertEqual(len(planned["ui"]), 6)
        before = self.base / "before.json"
        result = execute(self.install, before)
        self.assertTrue(before.is_file())
        self.assertEqual(result["mail_moved"], 6)
        self.assertTrue((self.data / "contact/native-targets.json").is_file())
        self.assertTrue((self.data / "mail/project-1001/dispatch/msg-1.json").is_file())
        self.assertTrue((self.data / "ui/rooter/board.json").is_file())
        self.assertFalse((self.base / "project-1001/.paos/mail/dispatch").exists())
        rollback(before)
        self.assertTrue((self.base / "project-1001/.paos/mail/dispatch/msg-1.json").is_file())
        self.assertTrue((self.base / "project-1001/.paos/ui/board.json").is_file())
        self.assertFalse((self.data / "contact/native-targets.json").exists())

    def test_contact_and_dispatch_writers_use_installation_data(self):
        target = {"1001-s001": {"runtime": "codex", "session_id": "s1"}}
        stored = save_native_targets(self.base, target, self.install)
        self.assertEqual(stored, contact_store_path(self.install))
        self.assertEqual(load_native_targets(self.base, self.install), target)
        project = self.registry.read("1001")
        home = self.base / "project-1001/Workstations/1001-s001"
        (home / "mailbox").mkdir(parents=True)
        result = send_mail(
            root=self.base / "project-1001", project=project,
            subject="s", body="b", recipients=["1001-s001"],
            message_id="new-dispatch", installation_path=self.install)
        self.assertTrue((self.data / "mail/project-1001/dispatch/new-dispatch.json").is_file())
        self.assertFalse((self.base / "project-1001/.paos/mail/dispatch/new-dispatch.json").exists())
        self.assertEqual(result["dispatch_path"],
                         str(self.data / "mail/project-1001/dispatch/new-dispatch.json"))

    def test_contact_conflict_aborts_before_mutation(self):
        # Same key, different target in the second project.
        path = self.base / "project-1002/private-data/contact/native-targets.json"
        path.write_text(json.dumps({"1001-s001": {"runtime": "other"}}),
                        encoding="utf-8")
        with self.assertRaises(ValueError):
            plan(self.install)
        self.assertFalse((self.data / "contact/native-targets.json").exists())

    def test_execute_replay_preserves_new_bindings_and_dispatch(self):
        before = self.base / 'before.json'
        execute(self.install, before)
        contacts = contact_store_path(self.install)
        value = json.loads(contacts.read_text())
        value['1001-s002'] = {'runtime':'manual','project_id':'1001','session_id':'new'}
        contacts.write_text(json.dumps(value),encoding='utf-8')
        record = self.data/'mail/project-1001/dispatch/new.json'
        record.write_text('{"new":true}',encoding='utf-8')
        self.assertTrue(execute(self.install,before)['replayed'])
        self.assertEqual(json.loads(contacts.read_text()),value)
        rollback(before)
        restored = self.base/'project-1001/private-data/contact/native-targets.json'
        self.assertEqual(json.loads(restored.read_text())['1001-s002']['session_id'],'new')
        self.assertTrue((self.base/'project-1001/.paos/mail/dispatch/new.json').exists())
        self.assertTrue(rollback(before)['replayed'])
        self.assertTrue((self.base/'before.backup/rollback-current/contact.json').exists())

    def test_rollback_preserves_updated_and_deleted_contacts_and_ui(self):
        before=self.base/'before.json';execute(self.install,before)
        contacts=contact_store_path(self.install);value=json.loads(contacts.read_text())
        value['1001-s001']['session_id']='new-session';del value['1002-s001']
        contacts.write_text(json.dumps(value),encoding='utf-8')
        (self.data/'ui/project-1001/board.json').write_text('{"layout":"new"}',encoding='utf-8')
        rollback(before)
        self.assertEqual(json.loads((self.base/'project-1001/private-data/contact/native-targets.json').read_text())['1001-s001']['session_id'],'new-session')
        self.assertEqual(json.loads((self.base/'project-1002/private-data/contact/native-targets.json').read_text()),{})
        self.assertEqual(json.loads((self.base/'project-1001/.paos/ui/board.json').read_text()),{'layout':'new'})

    def test_partial_execute_resumes_without_replacing_moved_files(self):
        import paos_data_migration as migration
        before=self.base/'before.json';move=migration.shutil.move;calls=[]
        def fail_second(src,dst):
            calls.append(src)
            if len(calls)==2:raise OSError('synthetic interruption')
            return move(src,dst)
        with patch.object(migration.shutil,'move',side_effect=fail_second):
            with self.assertRaises(OSError):execute(self.install,before)
        execute(self.install,before)
        self.assertTrue((self.data/'mail/project-1001/dispatch/msg-1.json').exists())
        self.assertTrue((self.data/'mail/project-1002/dispatch/msg-1.json').exists())
        rollback(before)

    def test_unroutable_new_contact_blocks_rollback_without_deleting_data(self):
        before=self.base/'before.json';execute(self.install,before)
        contacts=contact_store_path(self.install);value=json.loads(contacts.read_text())
        value['unknown']={'runtime':'manual'};contacts.write_text(json.dumps(value),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'no registered rollback owner'):rollback(before)
        self.assertEqual(json.loads(contacts.read_text()),value)
        self.assertTrue((self.data/'mail/project-1001/dispatch/msg-1.json').exists())

    def test_bind_unbind_read_the_same_central_store(self):
        before=self.base/'before.json';execute(self.install,before)
        contacts=contact_store_path(self.install);old=(self.base/'project-1001/private-data/contact/native-targets.json').read_bytes()
        bind_wakeup(root=self.base/'project-1001',project_id='1001',agent_id='1001-s002',
                    runtime_id='manual',native_session_id='session',driver_name='manual',installation_path=self.install)
        self.assertIn('1002-s001',json.loads(contacts.read_text()))
        unbind_wakeup(root=self.base/'project-1001',agent_id='1001-s002',installation_path=self.install)
        self.assertIn('rooter-001',json.loads(contacts.read_text()))
        self.assertEqual((self.base/'project-1001/private-data/contact/native-targets.json').read_bytes(),old)

    def test_registered_owner_is_not_duplicated_across_project_roots(self):
        execute(self.install,self.base/'before.json')
        for pid in ('1001','1002'):(self.base/f'project-{pid}/Workstations/{pid}-s001').mkdir(parents=True)
        values=load_native_targets(self.base,self.install);values['1001-s001']['session_id']='one-thread'
        save_native_targets(self.base,values,self.install)
        home,_=registered_target('one-thread',load_installation_descriptor(self.install))
        self.assertEqual(home['project_id'],'1001')

    def test_scope_created_only_after_cutover_is_returned_on_rollback(self):
        import shutil
        shutil.rmtree(self.base/'project-1002/.paos/mail/dispatch')
        (self.base/'project-1002/.paos/ui/board.json').unlink()
        before=self.base/'before.json';execute(self.install,before)
        target=self.data/'mail/project-1002/dispatch';target.mkdir(parents=True)
        (target/'new.json').write_text('{}',encoding='utf-8')
        ui=self.data/'ui/project-1002/board.json';ui.parent.mkdir(parents=True)
        ui.write_text('{"new":true}',encoding='utf-8')
        rollback(before)
        self.assertTrue((self.base/'project-1002/.paos/mail/dispatch/new.json').exists())
        self.assertTrue((self.base/'project-1002/.paos/ui/board.json').exists())

    def test_same_message_id_is_independent_by_sender_scope(self):
        for pid in ('1001','1002'):
            member=f'{pid}-s001';root=self.base/f'project-{pid}'
            (root/f'Workstations/{member}/mailbox').mkdir(parents=True)
            send_mail(root=root,project=self.registry.read(pid),subject=pid,body=pid,
                      recipients=[member],message_id='same-id',installation_path=self.install)
            got=handoff_status(root,'same-id',None,installation_file=self.install)
            self.assertEqual(got['subject'],pid)
        root=self.rooter;member='rooter-001'
        (root/f'Workstations/{member}/mailbox').mkdir(parents=True)
        send_mail(root=root,project={'id':'rooter','homes':[member],'sessions':[{'id':member}]},
                  subject='rooter',body='rooter',recipients=[member],message_id='same-id',installation_path=self.install)
        got=handoff_status(root,'same-id',None,installation_file=self.install)
        self.assertEqual(got['subject'],'rooter')
        self.assertTrue((self.data/'mail/rooter/dispatch/same-id.json').exists())

    def test_cli_plan_execute_and_rollback(self):
        before=self.base/'cli-before.json'
        def cli(*args):
            result=subprocess.run([sys.executable,'-X','utf8',str(SCRIPTS/'paos_data_cli.py'),
                '--installation-file',str(self.install),'data','migrate',*args],
                capture_output=True,text=True,encoding='utf-8',timeout=20)
            self.assertEqual(result.returncode,0,result.stderr+result.stdout)
            return json.loads(result.stdout)
        snapshot={str(p):p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        self.assertEqual(len(cli('plan')['contact_routes']),6)
        self.assertEqual(snapshot,{str(p):p.read_bytes() for p in self.base.rglob('*') if p.is_file()})
        cli('execute','--before-state',str(before))
        self.assertTrue(cli('execute','--before-state',str(before))['replayed'])
        cli('rollback','--before-state',str(before))
        self.assertTrue(cli('rollback','--before-state',str(before))['replayed'])

    def test_old_contact_conflict_blocks_rollback_before_any_restore(self):
        before=self.base/'before.json';execute(self.install,before)
        old=self.base/'project-1001/private-data/contact/native-targets.json'
        old.write_text('{"changed":true}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Old Contact changed'):rollback(before)
        self.assertTrue(contact_store_path(self.install).exists())
        self.assertFalse((self.base/'project-1001/.paos/mail/dispatch').exists())

    def test_receipt_cannot_be_inside_a_moved_store(self):
        before=self.base/'project-1001/.paos/mail/dispatch/receipt.json'
        snapshot={str(p):p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(ValueError,'outside the stores'):execute(self.install,before)
        self.assertEqual(snapshot,{str(p):p.read_bytes() for p in self.base.rglob('*') if p.is_file()})


if __name__ == "__main__":
    unittest.main()
