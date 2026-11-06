import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'code/personal-agent-os/scripts'
sys.path.insert(0, str(SCRIPTS))
from paos_team_overview import MARKER, main, render_overview


class TeamOverviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "项目 with space's"
        self.home = self.project / 'Workstations/3002-s001'
        self.home.mkdir(parents=True)
        self.team = self.project / 'TEAM.md'
        self.team.write_text('## 当前成员\n### 3002-s001\n- 职责/专长：原职责\n'
                             '### 3002-s999\n- 职责/专长：未登记成员\n', encoding='utf-8')
        (self.home / 'ENTRY.md').write_text('- Harness：OpenCode2\n', encoding='utf-8')
        (self.home / 'contact.py').write_text('raise Exception("Never execute")', encoding='utf-8')
        registry = self.root / 'data/project-registry/projects'
        registry.mkdir(parents=True)
        (registry / '3002.json').write_text(json.dumps({
            'schema': 'paos-project-registry/v1', 'id': '3002',
            'root_path': str(self.project), 'homes': ['3002-s001'],
            'coordinator_home_id': '3002-s001'}), encoding='utf-8')
        self.install = self.root / 'installation.json'
        self.install.write_text(json.dumps({'schema': 'paos-installation/v1',
            'source_root': str(SCRIPTS.parent), 'data_root': str(self.root / 'data'),
            'library_roots_config': str(self.root / 'roots.json'),
            'rooter_home': str(self.root / 'Rooter')}), encoding='utf-8')
        self.output = self.root / 'PROJECTS.md'
        self.args = ['--installation-file', str(self.install), '--output', str(self.output)]

    def call(self, mode):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(self.args + [mode])

    def test_source_changes_invalidate_then_regenerate_and_noop_preserves_bytes(self):
        self.assertEqual(self.call('--write'), 0)
        self.assertEqual(self.call('--check'), 0)
        before = self.output.stat().st_mtime_ns
        self.assertEqual(self.call('--write'), 0)
        self.assertEqual(self.output.stat().st_mtime_ns, before)
        self.team.write_text(self.team.read_text(encoding='utf-8').replace('原职责', '新职责'), encoding='utf-8')
        original = self.output.read_bytes()
        self.assertEqual(self.call('--check'), 1)
        self.assertEqual(self.output.read_bytes(), original)
        self.assertEqual(self.call('--write'), 0)
        self.assertIn('新职责', self.output.read_text(encoding='utf-8'))
        self.assertEqual(self.call('--check'), 0)

    def test_registry_isolation_rooter_and_literal_wake_path(self):
        text = render_overview(self.install, self.output)
        self.assertIn(MARKER, text)
        self.assertNotIn('3002-s999', text)
        self.assertIn('安装级支持', text)
        self.assertIn("space''s", text)
        self.assertIn('OpenCode2', text)
        self.assertIn('[命令](#3002-s001)', text)
        self.assertIn('### 3002-s001', text)
        self.assertNotIn('在线；', text)
        self.team.unlink()
        missing = render_overview(self.install, self.output)
        self.assertIn('TEAM 原件缺失', missing)
        self.assertIn('3002-s001', missing)

    def test_human_page_and_invalid_registration_are_never_overwritten(self):
        self.output.write_text('人工内容', encoding='utf-8')
        self.assertEqual(self.call('--write'), 2)
        self.assertEqual(self.output.read_text(encoding='utf-8'), '人工内容')
        record = self.root / 'data/project-registry/projects/3002.json'
        record.write_text('{}', encoding='utf-8')
        self.assertEqual(self.call('--write'), 2)
        self.assertEqual(self.output.read_text(encoding='utf-8'), '人工内容')

    def test_concurrent_output_edit_is_kept(self):
        self.assertEqual(self.call('--write'), 0)
        self.team.write_text('## 当前成员\n### 3002-s001\n- 职责：新职责\n', encoding='utf-8')
        read_text = Path.read_text
        calls = 0

        def changing_read(path, *args, **kwargs):
            nonlocal calls
            if path == self.output:
                calls += 1
                if calls == 2:
                    path.write_text('并发编辑', encoding='utf-8')
            return read_text(path, *args, **kwargs)

        with patch.object(Path, 'read_text', changing_read):
            self.assertEqual(self.call('--write'), 2)
        self.assertEqual(self.output.read_text(encoding='utf-8'), '并发编辑')
        self.assertEqual(list(self.root.glob('.team-*.tmp')), [])

    def test_symlink_output_is_not_replaced(self):
        target = self.root / 'target.md'
        target.write_text(MARKER + '\n人工保留', encoding='utf-8')
        try:
            self.output.symlink_to(target)
        except OSError:
            self.skipTest('File symlinks unavailable for this Windows user')
        self.assertEqual(self.call('--write'), 2)
        self.assertTrue(self.output.is_symlink())
        self.assertEqual(target.read_text(encoding='utf-8'), MARKER + '\n人工保留')


if __name__ == '__main__':
    unittest.main()
