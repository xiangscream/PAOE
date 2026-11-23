"""Exercise the Codex adapter against the real common CLI in isolated Homes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import io
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[1] / "code/personal-agent-os/scripts"
sys.path.insert(0, str(SCRIPTS))
import paos_codex_hook as hook
from paos_installation import write_installation_descriptor
from paos_registry import ProjectRegistry
from paos_todo import render_todo


class CodexContextHookTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = self.root / 'project'
        self.home = self.project / 'Workstations/S010'
        self.home.mkdir(parents=True)
        self.install = self.root / 'install.json'
        self.data = self.root / 'data'
        numbers = self.root / 'numbers.json'
        numbers.write_text('{"3002-s010":"S010"}', encoding='utf-8')
        write_installation_descriptor(self.install, source_root=str(SCRIPTS.parent),
            data_root=str(self.data), library_roots_config=str(self.root/'libraries.json'),
            agent_numbers_config=str(numbers))
        ProjectRegistry(self.install).register('3002', root_path=str(self.project),
            homes=['S010'], coordinator_home_id='S010')
        for name, text in {'AGENTS.md':'[共同背景](background.md)', 'TEAM.md':'### S010\nOwner',
            'INDEX.md':'Project original', 'background.md':'History original',
            'Workstations/S010/ENTRY.md':'Original entry'}.items():
            (self.project/name).write_text(text, encoding='utf-8')
        self.todo = self.home/'TODO.md'
        self.write_todo()
        self.stop = self.root/'STOP'
        self.runtime = self.root/'receiver/runtime.json'
        self.runtime.parent.mkdir()
        target = {'runtime':'codex', 'session_id':'own-session', 'stop_file':str(self.stop),
            'extension':{'receiver_runtime_file':str(self.runtime), 'windows_python':sys.executable}}
        self.contact = self.project/'private-data/contact/native-targets.json'
        self.contact.parent.mkdir(parents=True)
        self.contact.write_text(json.dumps({'S010':target}), encoding='utf-8')
        self.environment = {k:v for k,v in os.environ.items() if k not in
            {'CODEX_THREAD_ID','CODEX_APP_TOOLS_PIPE_PATH'}}

    def write_todo(self, waiting=''):
        self.todo.write_text(render_todo(home_kind='project_agent',home_id='S010',project_id='3002',
            objective='Work',next_action='Read the next original',waiting=waiting,context_refs=['task:T1'],
            tasks=[dict(id='T1',title='Original work',state='doing')]), encoding='utf-8')

    def invoke(self, event, *args):
        result = subprocess.run([sys.executable,'-X','utf8',str(SCRIPTS/'paos_codex_hook.py'),
            '--installation-file',str(self.install),*args],input=json.dumps(event),capture_output=True,
            encoding='utf-8',env=self.environment,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout)

    def read_event(self, source='resume'):
        return dict(session_id='own-session',hook_event_name='SessionStart',source=source)

    def stop_event(self, active=False):
        return dict(session_id='own-session',hook_event_name='Stop',turn_id='native-turn',stop_hook_active=active)

    def test_startup_resume_compact_and_request_return_complete_originals(self):
        original = '完整原文\n' * 4000 + 'END-OF-ORIGINAL'
        (self.project/'INDEX.md').write_text(original,encoding='utf-8')
        before = self.todo.read_bytes(),self.contact.read_bytes()
        events=[self.read_event(s) for s in ('startup','resume','compact')]
        events.append(dict(session_id='own-session',hook_event_name='UserPromptSubmit',prompt='private prompt'))
        for event in events:
            with self.subTest(event=event['hook_event_name'],source=event.get('source')):
                result=self.invoke(event)
                text=result['hookSpecificOutput']['additionalContext']
                self.assertIn(original,text)
                self.assertIn('task:T1',text)
                self.assertIn('Original work',text)
                self.assertNotIn('private prompt',text)
        self.assertEqual((self.todo.read_bytes(),self.contact.read_bytes()),before)
        self.assertFalse(self.runtime.exists())

    def test_missing_required_original_explicitly_stops(self):
        (self.project/'background.md').unlink()
        for event in [self.read_event(),dict(session_id='own-session',hook_event_name='UserPromptSubmit')]:
            result=self.invoke(event)
            self.assertFalse(result['continue'])
            self.assertIn('background',result['stopReason'])
            self.assertNotIn('hookSpecificOutput',result)

    def test_unknown_session_is_noop(self):
        self.assertEqual(self.invoke({**self.read_event(),'session_id':'unregistered'}),{})
        self.assertFalse(self.data.joinpath('content').exists())

    def test_current_owner_mismatch_cannot_read_another_home(self):
        self.environment['CODEX_THREAD_ID']='different-owner'
        result=self.invoke(self.read_event())
        self.assertFalse(result['continue'])
        self.assertNotIn('hookSpecificOutput',result)

    def test_stop_file_blocks_read_and_continuation(self):
        self.stop.write_text('Human STOP',encoding='utf-8')
        before=self.todo.read_bytes()
        for event in [self.read_event(),self.stop_event()]:
            self.assertFalse(self.invoke(event)['continue'])
        self.assertEqual(self.todo.read_bytes(),before)

    def test_stop_continues_once_without_completing_task(self):
        before=self.todo.read_bytes()
        first=self.invoke(self.stop_event())
        self.assertEqual(first,{'decision':'block','reason':'Read the next original'})
        self.assertEqual(self.invoke(self.stop_event()),{})
        self.assertEqual(self.invoke(self.stop_event(True)),{})
        self.assertEqual(self.todo.read_bytes(),before)

    def test_waiting_task_stops(self):
        self.write_todo('Human needs to decide')
        self.assertEqual(self.invoke(self.stop_event()),{})

    def test_stop_missing_native_identity_does_not_continue(self):
        for field in ('turn_id','stop_hook_active'):
            event=self.stop_event();del event[field]
            self.assertFalse(self.invoke(event)['continue'])

    def test_stop_updates_only_joined_online_open_rooms(self):
        writes=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def reply(self,value):
                body=json.dumps(value).encode();self.send_response(200)
                self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)))
                self.end_headers();self.wfile.write(body)
            def do_GET(self):
                self.reply({'rooms':[{'id':'open','status':'open','presence':'online'},
                    {'id':'closed','status':'closed','presence':'online'}]})
            def do_POST(self):
                writes.append((self.path,json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                self.reply({'ok':True})
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            result=self.invoke(self.stop_event(True),'--cat-url',f'http://127.0.0.1:{server.server_port}')
            self.assertEqual(result,{})
            self.assertEqual(writes,[('/api/rooms/open/members/S010/progress',{'presence':'offline'})])
        finally:
            server.shutdown();server.server_close();worker.join()

    def test_invalid_cli_output_or_timeout_is_not_success(self):
        for value in ('not json','[]','{"ok":false,"missing":[{"kind":"guide"}]}'):
            with patch.object(hook.subprocess,'run',return_value=subprocess.CompletedProcess([],0,value,'')):
                with self.assertRaises(ValueError):hook.call_context(self.install,['read','S010'])
        with patch.object(hook.subprocess,'run',side_effect=subprocess.TimeoutExpired('paos',8)):
            with self.assertRaises(subprocess.TimeoutExpired):hook.call_context(self.install,['read','S010'])

    def test_wrong_context_identity_or_incomplete_document_is_rejected(self):
        good={'ok':True,'schema':'paoe-context/v1','home_id':'S010','reason':'resume','missing':[],
              'documents':[dict(kind='guide',path='guide.md',body='Original',version='1:8')]}
        cases=[{**good,'home_id':'S999'}, {**good,'reason':'startup'},
               {**good,'documents':[dict(kind='guide',path='guide.md',body='Original')]},
               {**good,'missing':[{'kind':'background'}]}]
        for result in cases:
            with patch.dict(os.environ,self.environment,clear=True), \
                 patch.object(hook,'call_context',return_value=result):
                with self.assertRaises(hook.HookProblem):hook.run_hook(self.read_event(),self.install)

    def test_stop_response_must_match_native_turn(self):
        bad={'ok':True,'schema':'paoe-context-stop/v1','event':'other-turn',
             'action':'continue','next_action':'Unrelated work'}
        with patch.dict(os.environ,self.environment,clear=True),patch.object(hook,'call_context',return_value=bad):
            with self.assertRaises(hook.HookProblem):hook.run_hook(self.stop_event(),self.install)

    def test_process_failures_return_explicit_stop_json(self):
        for error in (OSError('fixture unavailable'),subprocess.TimeoutExpired('fixture',8),
                      hook.HookProblem('invalid reply')):
            output=io.BytesIO()
            with patch.object(sys,'argv',['paos_codex_hook.py','--installation-file',str(self.install)]), \
                 patch.object(sys,'stdin',SimpleNamespace(buffer=io.BytesIO(json.dumps(self.read_event()).encode()))), \
                 patch.object(sys,'stdout',SimpleNamespace(buffer=output)), \
                 patch.object(hook,'run_hook',side_effect=error):
                self.assertEqual(hook.main(),0)
            response=json.loads(output.getvalue())
            self.assertFalse(response['continue'])
            self.assertNotIn('decision',response)


if __name__=='__main__':unittest.main()
