"""Release integrity and Windows install/upgrade checks in disposable directories."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def run(command, cwd=ROOT, env=None, ok=True):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, encoding='utf-8', timeout=90)
    if ok and result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
            for p in root.rglob('*')}


class SystemReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='paoe-system-contract-')
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)

    def build(self, output):
        result = run([sys.executable, '-X', 'utf8', '-B', str(ROOT/'release.py'),
                      'build', '--ref', 'HEAD', '--output', str(output)])
        return json.loads(result.stdout)

    def test_committed_source_builds_identically_and_detects_tampering(self):
        first = self.build(self.temp/'first'); second = self.build(self.temp/'second')
        self.assertEqual(first['sha256'], second['sha256'])
        good = Path(first['archive'])
        result = run([sys.executable,'-B',str(ROOT/'release.py'),'verify',str(good)])
        self.assertTrue(json.loads(result.stdout)['ok'])
        altered = self.temp/'tampered.zip'
        with zipfile.ZipFile(good) as source, zipfile.ZipFile(altered,'w') as target:
            for member in source.infolist():
                data = source.read(member.filename)
                if member.filename.endswith('/HOME.md'):
                    data += b'\nnot the committed content\n'
                target.writestr(member,data)
        result = run([sys.executable,'-B',str(ROOT/'release.py'),'verify',str(altered)],ok=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('checksum mismatch',result.stderr)

    def test_dirty_source_is_rejected_before_output(self):
        clone = self.temp/'dirty-source'
        run(['git','clone','--quiet','--no-hardlinks',str(ROOT),str(clone)])
        (clone/'HOME.md').write_bytes((clone/'HOME.md').read_bytes()+b'\nHuman edit\n')
        output = self.temp/'must-not-be-created'
        result = run([sys.executable,'-B',str(clone/'release.py'),'build','--ref','HEAD','--output',str(output)],cwd=clone,ok=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('dirty',result.stderr)
        self.assertFalse(output.exists())

    def test_machine_scan_covers_core_and_neutral_projects(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('release_under_test', ROOT/'release.py')
        release = importlib.util.module_from_spec(spec); spec.loader.exec_module(release)
        for name in ('Core/README.md','Guide/README.md','PROJECTS.md'):
            for value in ('X:' + r'\Users\Someone\private', 'Z:' + '/Projects/Real', '/home/' + 'someone/project'):
                with self.subTest(name=name,value=value), self.assertRaises(ValueError):
                    release.scan_machine_paths(name,value.encode())
        release.scan_machine_paths('Core/tests/test_stage1_entry.py',('C:'+'/Users/' + 'remo').encode())
        with self.assertRaises(ValueError):
            release.scan_machine_paths('Core/README.md',('C:'+'/Users/' + 'remo').encode())
        with self.assertRaises(ValueError):
            release.scan_machine_paths('PROJECTS.md',b'1999-s001')

    def test_output_inside_checkout_is_rejected(self):
        result = run([sys.executable,'-B',str(ROOT/'release.py'),'build','--ref','HEAD',
                      '--output',str(ROOT/'must-not-be-created')],ok=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('outside the source checkout',result.stderr)
        self.assertFalse((ROOT/'must-not-be-created').exists())

    def installation(self):
        system = self.temp/'fresh system'
        for directory in ('Core','Guide','Project-Template','rooter'):
            shutil.copytree(ROOT/directory,system/directory,
                ignore=shutil.ignore_patterns('.git','__pycache__','node_modules','local','data'))
        for name in ('PROJECTS.md','RESOURCES.md'):
            shutil.copyfile(ROOT/name,system/name)
        core = system/'Core'; config = core/'config/local/installation.json'
        env = {**os.environ,'PAOS_INSTALLATION_FILE':str(config),
               'PAOS_LIBRARY_ROOTS_CONFIG':str(core/'config/local/library-roots.json'),
               'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'}
        cli = core/'code/personal-agent-os/scripts/paos.py'
        prefix = [sys.executable,'-X','utf8','-B',str(cli),'--installation-file',str(config),'--json']
        workflow = self.temp/'external libraries/workflow'; skill = self.temp/'external libraries/skill'
        for kind,path in [('workflow',workflow),('skill',skill)]:
            run(prefix+['library','init',kind,'--root',str(path)],cwd=system,env=env)
        external = snapshot(self.temp/'external libraries')
        portable = [sys.executable,'-X','utf8','-B',str(core/'portable.py')]
        run(portable+['plan'],cwd=self.temp,env=env)
        run(portable+['init','--workflow-root',str(workflow),'--skill-root',str(skill)],cwd=self.temp,env=env)
        return system,core,config,env,prefix,portable,external

    def test_fresh_install_has_no_fake_home_and_reinit_preserves_bytes(self):
        system,core,config,env,prefix,portable,external = self.installation()
        data = json.loads(config.read_text('utf-8'))
        self.assertEqual(Path(data['source_root']),core/'code/personal-agent-os')
        self.assertEqual(Path(data['data_root']),core/'data')
        self.assertEqual(data['rooter_home'],'')
        self.assertFalse((core/'data/project-registry').exists())
        self.assertFalse((system/'rooter/ENTRY.md').exists())
        self.assertFalse((system/'rooter/TODO.md').exists())
        self.assertTrue(json.loads(run(portable+['doctor'],cwd=self.temp,env=env).stdout)['configuration_ok'])
        self.assertTrue(json.loads(run(prefix+['health'],cwd=self.temp,env=env).stdout)['ok'])
        before = snapshot(core/'config/local')
        run(portable+['init'],cwd=self.temp,env=env)
        self.assertEqual(before,snapshot(core/'config/local'))
        self.assertEqual(external,snapshot(self.temp/'external libraries'))
        check = core/'code/personal-agent-os/scripts/paos_template_check.py'
        run([sys.executable,'-X','utf8','-B',str(check),'--system-root',str(system),
             '--installation-file',str(config),'--templates-only'],cwd=self.temp,env=env)

    def test_existing_registry_homes_libraries_and_stop_survive_repointing(self):
        system,core,config,env,prefix,portable,external = self.installation()
        legacy = self.temp/'existing machine'; data = legacy/'data'
        project = legacy/'Project'; home = project/'Workstations/1999-s001'; rooter = legacy/'rooter'
        for path in (home,rooter,data/'project-registry/projects'):
            path.mkdir(parents=True)
        scripts = core/'code/personal-agent-os/scripts'; sys.path.insert(0,str(scripts))
        from paos_todo import render_todo
        (home/'ENTRY.md').write_text('# Original project identity\n','utf-8')
        (home/'TODO.md').write_text(render_todo(home_kind='project_agent',home_id='1999-s001',
            project_id='1999',objective='Original ongoing work',next_action='Continue original work'),'utf-8')
        (rooter/'ENTRY.md').write_text('# Original Rooter identity\n','utf-8')
        (rooter/'TODO.md').write_text(render_todo(home_kind='rooter',home_id='rooter-001',
            project_id='',objective='Keep existing machine',next_action='Read original input'),'utf-8')
        (rooter/'STOP').write_text('paused by owner\n','utf-8')
        (rooter/'private-data').mkdir(); (rooter/'private-data/owner.txt').write_text('existing binding marker\n','utf-8')
        (home/'mailbox').mkdir(); (home/'mailbox/original.md').write_text('Original durable input\n','utf-8')
        (data/'project-registry/projects/1999.json').write_text(json.dumps({
            'schema':'paos-project-registry/v1','id':'1999','root_path':str(project),
            'homes':['1999-s001'],'coordinator_home_id':'1999-s001'}),'utf-8')
        before = snapshot(legacy)
        run(prefix+['install','configure','--source-root',str(core/'code/personal-agent-os'),
            '--data-root',str(data),'--library-roots-config',str(core/'config/local/library-roots.json'),
            '--rooter-home',str(rooter)],cwd=self.temp,env=env)
        self.assertTrue(json.loads(run(portable+['doctor'],cwd=self.temp,env=env).stdout)['configuration_ok'])
        run(portable+['init'],cwd=self.temp,env=env)
        result = json.loads(run(prefix+['workstation','show','1999','1999-s001'],cwd=self.temp,env=env).stdout)
        self.assertTrue(result['ok'])
        self.assertEqual(before,snapshot(legacy))
        self.assertEqual(external,snapshot(self.temp/'external libraries'))


if __name__ == '__main__':
    unittest.main()
