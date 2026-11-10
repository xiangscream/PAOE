"""External mother and dependency checks; only disposable Homes are used."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import test_headless
SCRIPTS = Path(__file__).resolve().parents[1] / 'code/personal-agent-os/scripts'
sys.path.insert(0,str(SCRIPTS))
import paos_template_check as checks
import paos_agents_common as common
from paos_team_overview import render_overview
from paos_workstation import render_fixed_entry, WorkstationProblem
from paos_todo import render_todo


class TemplateSyncTests(unittest.TestCase):
    def setUp(self):
        self.f = test_headless.HeadlessTests(methodName='runTest')
        self.addCleanup(self.f.doCleanups); self.f.setUp()
        (self.f.root/'numbers.json').write_text(json.dumps({'3002-s001':'S001','3002-s002':'S002'}),'utf-8')
        self.system = self.f.root / 'System'
        self.mother = self.system / 'Project-Template'
        station = self.mother / 'Workstations/_workstation';station.mkdir(parents=True)
        (self.mother/'README.md').write_text('# Mother\n','utf-8')
        (self.mother/'AGENTS.md').write_text('# Mother\n'+common.START+'\nRule.\n'+common.END+'\n','utf-8')
        for name in ('INDEX.md','TEAM.md','HISTORY.md'):
            (self.mother/name).write_text('# fixture\n','utf-8')
        self.template = station/'ENTRY.md'
        self.template.write_bytes(self.f.entry_template.read_bytes())
        (station/'TODO.md').write_text(render_todo(home_kind='project_agent',home_id='3002-s099',project_id='3002',objective='fixture',next_action='read'),'utf-8')
        guide = self.system/'Guide';guide.mkdir()
        for name in ('README.md','guide-work-method.md','ops-entry.md'):
            (guide/name).write_text('# Guide\n','utf-8')
        for name in ('HOME.md','SYSTEM.md','RESOURCES.md','MAINTENANCE.md'):
            (self.system/name).write_text('# fixture\n','utf-8')
        source=common.source_block(self.mother/'AGENTS.md')
        (self.f.vault/'AGENTS.md').write_text(common.START+'\n'+common.managed_section(source)+common.END+'\n## Human\nPreserve.\n','utf-8')
        for name in ('INDEX.md','TEAM.md','HISTORY.md'):
            (self.f.vault/name).write_text('# fixture\n','utf-8')
        overview=self.system/'PROJECTS.md';overview.write_text(render_overview(self.f.install,overview),'utf-8')

    def snapshot(self):
        return {str(p.relative_to(self.f.root)):(hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None)
                for p in self.f.root.rglob('*')}

    def new_home(self):
        self.f.call('project','home-add','3002','3002-s003','--expected-fingerprint',hashlib.sha256(self.f.record.read_bytes()).hexdigest())
        return self.f.vault/'Workstations/3002-s003'

    def check(self,*args):
        out=io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(out):
            code=checks.main(['--system-root',str(self.system),'--installation-file',str(self.f.install),*args])
        return code,out.getvalue()

    def test_external_prose_is_used_and_reinit_keeps_existing_human_files(self):
        home=self.new_home()
        self.template.write_text(self.template.read_text('utf-8')+'\nMother revision A.\n','utf-8')
        self.f.call('workstation','init','3002','3002-s003','--entry-template',str(self.template))
        self.assertIn('Mother revision A.',(home/'ENTRY.md').read_text('utf-8'))
        (home/'ENTRY.md').write_text((home/'ENTRY.md').read_text('utf-8')+'Human edit.\n','utf-8')
        before=(home/'ENTRY.md').read_bytes(),(home/'TODO.md').read_bytes()
        self.template.write_text(self.template.read_text('utf-8').replace('revision A','revision B'),'utf-8')
        self.f.call('workstation','init','3002','3002-s003','--entry-template',str(self.template))
        self.assertEqual(before,((home/'ENTRY.md').read_bytes(),(home/'TODO.md').read_bytes()))
        (home/'ENTRY.md').unlink()  # Disposable repair fixture only.
        self.f.call('workstation','init','3002','3002-s003','--entry-template',str(self.template))
        self.assertIn('Mother revision B.',(home/'ENTRY.md').read_text('utf-8'))

    def test_bad_or_missing_mother_fails_before_number_or_directory_writes(self):
        self.new_home()
        original=self.template.read_text('utf-8')
        for body,expected in [(original+'{{unknown}}','workstation_entry_template_invalid'),
                              (original.replace('{{home_id}}',''), 'workstation_entry_template_invalid'),
                              (original+'{{ broken', 'workstation_entry_template_invalid'),
                              (None,'workstation_entry_template_missing')]:
            with self.subTest(expected=expected,body=body):
                if body is None:self.template.unlink()
                else:self.template.write_text(body,'utf-8')
                before=self.snapshot()
                rc,value=self.f.call('workstation','init','3002','3002-s003','--entry-template',str(self.template),ok=False)
                self.assertNotEqual(rc,0);self.assertEqual(value['error_code'],expected)
                self.assertEqual(before,self.snapshot())

    def test_standard_system_inference_uses_the_external_mother(self):
        source=self.system/'Core/code/personal-agent-os';source.mkdir(parents=True)
        text=render_fixed_entry(project={'id':'3002'},session={'id':'3002-s001'},
             workstation_path=self.f.vault/'Workstations/3002-s001',source_root=str(source),installation_file=str(self.f.install))
        self.assertIn('# Fixture 3002-s001',text)
        self.assertNotIn('{{',text)
        with self.assertRaises(WorkstationProblem):
            render_fixed_entry(project={'id':'3002'},session={'id':'3002-s001'},
                workstation_path=self.f.vault/'Workstations/3002-s001',
                source_root=str(self.system/'Core/renamed/source'),installation_file=str(self.f.install))

    def test_relative_project_navigation_needs_no_slots_and_remains_required(self):
        body=self.template.read_text('utf-8')
        for slot, target in [('project_agents_link','../../AGENTS.md'),
                             ('project_index_link','../../INDEX.md')]:
            body=body.replace('{{'+slot+'}}',f'[{slot}]({target})')
        self.template.write_text(body,'utf-8')
        home=self.new_home()
        self.f.call('workstation','init','3002','3002-s003','--entry-template',str(self.template))
        rendered=(home/'ENTRY.md').read_text('utf-8')
        self.assertIn('](../../AGENTS.md)',rendered)
        self.assertIn('](../../INDEX.md)',rendered)
        for target in ('../../AGENTS.md','../../INDEX.md'):
            with self.subTest(target=target):
                self.template.write_text(body.replace(target,'../../missing.md'),'utf-8')
                before=self.snapshot()
                rc,value=self.f.call('workstation','init','3002','3002-s003','--entry-template',str(self.template),ok=False)
                self.assertNotEqual(rc,0)
                self.assertEqual(value['error_code'],'workstation_entry_template_invalid')
                self.assertEqual(before,self.snapshot())

    def test_full_check_is_read_only_and_reports_stale_derived_files(self):
        before=self.snapshot()
        code,out=self.check();self.assertEqual(code,0,out);self.assertEqual(before,self.snapshot())
        (self.mother/'AGENTS.md').write_text((self.mother/'AGENTS.md').read_text('utf-8').replace('Rule.','Updated.'),'utf-8')
        (self.system/'PROJECTS.md').write_text((self.system/'PROJECTS.md').read_text('utf-8')+'stale\n','utf-8')
        before=self.snapshot();code,out=self.check()
        self.assertEqual(code,1,out);self.assertIn('stale',out);self.assertIn('聚合已过期',out)
        self.assertEqual(before,self.snapshot())

    def test_links_anchors_retired_locators_and_reverse_links(self):
        target=self.system/'Guide/目标.md';target.write_text('# 目标\n## 同名\n## 同名\n','utf-8')
        source=self.system/'Guide/ref.md';source.write_text('[ok](目标.md#同名-1)\n[bad](目标.md#不存在)\n[missing](gone.md)\nold/place\n```text\nold/place\n[x](fake.md)\n```\n','utf-8')
        before=self.snapshot();code,out=self.check('--retired-locator','old/place','--changed',str(target))
        self.assertEqual(code,1);self.assertIn('锚点缺失',out);self.assertIn('gone.md',out)
        self.assertNotIn('fake.md',out);self.assertIn('引用方',out)
        self.assertEqual(out.count('退役定位 old/place'),1)
        self.assertEqual(before,self.snapshot())

    def test_history_mother_is_part_of_initialization_check(self):
        (self.mother/'HISTORY.md').unlink()
        code,out=self.check('--templates-only')
        self.assertNotEqual(code,0,out)
        self.assertIn('HISTORY.md',out)

    def test_registered_project_history_is_checked_read_only(self):
        (self.f.vault/'HISTORY.md').unlink()
        before=self.snapshot()
        code,out=self.check()
        self.assertNotEqual(code,0,out)
        self.assertIn('HISTORY.md',out)
        self.assertEqual(before,self.snapshot())

    def test_todo_mother_is_checked_with_the_real_v4_parser(self):
        p=self.mother/'Workstations/_workstation/TODO.md'
        p.write_text(p.read_text('utf-8').replace('# Current','# Broken'),'utf-8')
        code,out=self.check('--templates-only')
        self.assertEqual(code,1,out);self.assertIn('母版展开失败',out)


if __name__=='__main__':unittest.main()
