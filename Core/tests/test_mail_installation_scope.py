"""Explicit installations own both dispatch and cross-Home recipient resolution."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/'code/personal-agent-os/scripts'
sys.path.insert(0,str(SCRIPTS))
from paos_attention_service import send_mail_source, request_mail_activation, resolve_home_by_registry, read_source_status, AttentionServiceProblem
from paos_installation import write_installation_descriptor
from paos_registry import ProjectRegistry
from paos_todo import render_todo, write_todo
from paos_mail_tracking import handoff_status


class MailInstallationScopeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.default=self.make_install('default')
        self.explicit=self.make_install('explicit')
        env=patch.dict(os.environ,{'PAOS_INSTALLATION_FILE':str(self.default['install'])})
        env.start();self.addCleanup(env.stop)

    def make_install(self,name):
        base=self.root/name;base.mkdir()
        install=base/'installation.json';data=base/'Data';rooter=base/'rooter'
        numbers=base/'numbers.json';numbers.write_text('{}',encoding='utf-8')
        write_installation_descriptor(install,source_root=str(SCRIPTS.parent),data_root=str(data),
            library_roots_config=str(base/'libraries.json'),rooter_home=str(rooter),agent_numbers_config=str(numbers))
        registry=ProjectRegistry(install);homes={}
        for pid,hid in [('1001','S010'),('1002','S020'),('', 'rooter-001')]:
            project=base/('project-'+pid) if pid else rooter
            home=project/'Workstations'/hid if pid else rooter
            (home/'mailbox').mkdir(parents=True);(home/'notices').mkdir()
            write_todo(home/'TODO.md',render_todo(home_kind='project_agent' if pid else 'rooter',
                home_id=hid,project_id=pid,objective=name+' original',next_action='Read original'))
            homes[hid]=home
            if pid:registry.register(pid,root_path=str(project),homes=[hid],coordinator_home_id=hid)
        return dict(base=base,install=install,data=data,homes=homes,project=registry.read('1001'))

    def snapshot(self,base):
        return {str(p.relative_to(base)):p.read_bytes() if p.is_file() else None for p in base.rglob('*')}

    def send(self,mid='scope-001'):
        b=self.explicit
        return send_mail_source(root=Path(b['project']['root_path']),project=b['project'],
            subject='Explicit scope',body='Only installation B',recipients=['S020','rooter-001'],
            sender_kind='agent',sender_id='S010',message_id=mid,request_activation=False,
            installation_path=b['install'])

    def test_external_send_status_and_notify_stay_in_explicit_installation(self):
        a,b=self.default,self.explicit;before=self.snapshot(a['base'])
        sent=self.send();self.assertFalse(sent['runtime_wake_performed'])
        for hid in ('S020','rooter-001'):
            self.assertTrue((b['homes'][hid]/'mailbox/scope-001.md').exists())
            self.assertFalse((a['homes'][hid]/'mailbox/scope-001.md').exists())
        lookup=lambda hid:resolve_home_by_registry(hid,installation_file=str(b['install']))
        state=handoff_status(Path(b['project']['root_path']),'scope-001',lookup,installation_file=b['install'])
        self.assertEqual([r['state'] for r in state['deliveries']],['delivered','delivered'])
        result=request_mail_activation(root=Path(b['project']['root_path']),project=b['project'],
            message_id='scope-001',installation_path=b['install'])
        self.assertFalse(result['runtime_wake_performed'])
        self.assertEqual({r['state'] for r in result['results']},{'activation_requested'})
        for hid in ('S020','rooter-001'):
            notices=list((b['homes'][hid]/'notices').glob('*.md'))
            self.assertEqual(len(notices),1)
            status=read_source_status(home_ref=lookup(hid),source_kind='mail',source_ref='scope-001',
                                     installation_file=str(b['install']))
            self.assertTrue(status['notice']['activation_requested_at'])
            self.assertEqual(status['notice']['home_id'],hid)
        self.assertEqual(self.snapshot(a['base']),before)
        dispatch=b['data']/'mail/project-1001/dispatch/scope-001.json'
        original=dispatch.read_bytes();self.send()
        self.assertEqual(dispatch.read_bytes(),original)
        self.assertEqual(self.snapshot(a['base']),before)

    def test_missing_explicit_recipient_does_not_use_default_copy(self):
        b=self.explicit
        (b['data']/'project-registry/projects/1002.json').unlink()
        before=self.snapshot(self.default['base'])
        with self.assertRaises(AttentionServiceProblem):self.send('missing-recipient')
        self.assertEqual(self.snapshot(self.default['base']),before)

    def test_invalid_default_descriptor_cannot_affect_explicit_send(self):
        self.default['install'].write_text('invalid default installation',encoding='utf-8')
        before=self.snapshot(self.default['base'])
        self.send('default-not-read')
        self.assertTrue((self.explicit['homes']['rooter-001']/'mailbox/default-not-read.md').exists())
        self.assertEqual(self.snapshot(self.default['base']),before)


if __name__=='__main__':unittest.main()
