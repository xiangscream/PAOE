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
from paos_agent_numbers import NumbersProblem
from paos_contact import _team_heading_home
from paos_registry import ProjectRegistry
from paos_team_overview import MARKER, main, render_overview


class TeamOverviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "项目 with space's"
        self.home = self.project / 'Workstations/3002-s001'
        self.home.mkdir(parents=True)
        (self.project / 'INDEX.md').write_text('# 示例 Project\n', encoding='utf-8')
        self.team = self.project / 'TEAM.md'
        self.team.write_text('## 当前成员\n### 3002-s001\n- 职责/专长：原职责\n'
                             '- Harness：OpenCode2（TEAM）\n'
                             '### 3002-s999\n- 职责/专长：未登记成员\n', encoding='utf-8')
        (self.home / 'ENTRY.md').write_text('- Harness：ENTRY-ONLY\n', encoding='utf-8')
        (self.home / 'contact.py').write_text('raise Exception("Never execute")', encoding='utf-8')
        registry = self.root / 'data/project-registry/projects'
        registry.mkdir(parents=True)
        (registry / '3002.json').write_text(json.dumps({
            'schema': 'paos-project-registry/v1', 'id': '3002',
            'root_path': str(self.project), 'homes': ['3002-s001'],
            'coordinator_home_id': '3002-s001'}), encoding='utf-8')
        self.numbers = self.root / 'numbers.json'
        self.numbers.write_text('{"3002-s001": "S040", "rooter-001": "S035"}', encoding='utf-8')
        self.install = self.root / 'installation.json'
        self.rooter = self.root / 'Rooter'
        self.rooter.mkdir()
        (self.rooter / 'ENTRY.md').write_text('- Harness：Codex；状态见联系入口。\n', encoding='utf-8')
        self.install.write_text(json.dumps({'schema': 'paos-installation/v1',
            'source_root': str(SCRIPTS.parent), 'data_root': str(self.root / 'data'),
            'library_roots_config': str(self.root / 'roots.json'),
            'agent_numbers_config': str(self.numbers),
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

    def test_staff_links_use_the_installation_mapping(self):
        numbers = self.root / 'numbers.json'
        numbers.write_text('{"3002-s001": "S040", "rooter-001": "S035"}', encoding='utf-8')
        install = json.loads(self.install.read_text(encoding='utf-8'))
        install['agent_numbers_config'] = str(numbers)
        self.install.write_text(json.dumps(install), encoding='utf-8')
        self.team.write_text(
            '## 当前成员\n### S040\n- 职责/专长：原职责\n'
            '- Harness：OpenCode2（TEAM）\n', encoding='utf-8')
        text = render_overview(self.install, self.output)
        self.assertIn(f'| [S040](<{(self.home / "ENTRY.md").resolve().as_uri()}>)', text)
        self.assertIn(f'[待办](<{(self.home / "TODO.md").resolve().as_uri()}>)', text)
        self.assertNotIn('[命令]', text)
        self.assertNotIn('### S040', text)
        self.assertIn('原职责', text)
        self.assertNotIn('| 3002-s001 |', text)

    def test_duplicate_staff_mapping_is_an_explicit_ambiguity(self):
        with self.assertRaises(NumbersProblem) as raised:
            _team_heading_home(
                'S040', {'1001-s001', '1001-s002'},
                {'1001-s001': 'S040', '1001-s002': 'S040'})
        self.assertEqual(raised.exception.code, 'staff_number_ambiguous')

    def test_migrated_home_is_linked_from_the_original_staff_mapping(self):
        record_path = self.root / 'data/project-registry/projects/3002.json'
        record = ProjectRegistry(self.install).read_record('3002')
        record['homes'] = ['S040']
        record['coordinator_home_id'] = 'S040'
        record_path.write_text(json.dumps(record), encoding='utf-8')
        migrated = self.home.rename(self.home.with_name('S040'))
        self.team.write_text(
            '## 当前成员\n### S040\n- 职责/专长：原职责\n'
            '- Harness：OpenCode2（TEAM）\n', encoding='utf-8')

        text = render_overview(self.install, self.output)

        self.assertIn(f'| [S040](<{(migrated / "ENTRY.md").resolve().as_uri()}>) | 原职责 | OpenCode2（TEAM） |', text)
        self.assertIn(f'[待办](<{(migrated / "TODO.md").resolve().as_uri()}>)', text)
        self.assertNotIn('3002-s001', text)

    def test_missing_staff_registry_fails_instead_of_falling_back_to_home(self):
        self.numbers.unlink()
        with self.assertRaisesRegex(ValueError, '员工号登记不可用'):
            render_overview(self.install, self.output)

    def test_manual_contact_and_pause_follow_explicit_source_facts(self):
        self.team.write_text('## 当前成员\n### S040\n- 职责：原职责\n- Harness：DSH web\n', encoding='utf-8')
        (self.home / 'contact.py').unlink()
        text = render_overview(self.install, self.output)
        self.assertIn('| DSH web |', text)
        self.assertNotIn('DSH web · 人工联系', text)
        with self.team.open('a', encoding='utf-8') as stream:
            stream.write('- 成员状态：暂停保留；人工联系。\n')
        self.assertIn('| DSH web · 暂停 · 人工联系 |', render_overview(self.install, self.output))
        self.team.write_text(self.team.read_text(encoding='utf-8').replace('暂停保留；人工联系。', '在队。'),
                             encoding='utf-8')
        (self.home / 'ENTRY.md').write_text('- 你的人工联系入口：在原会话提示读信。\n', encoding='utf-8')
        self.assertIn('| DSH web · 人工联系 |', render_overview(self.install, self.output))

    def test_registry_navigation_and_one_shared_wake_example(self):
        text = render_overview(self.install, self.output)
        self.assertIn(MARKER, text)
        self.assertNotIn('3002-s999', text)
        self.assertIn('[联系方法](#外部唤醒) · [示例 Project](#示例-project) · [Rooter](#安装级支持)', text)
        self.assertIn('## 示例 Project\n', text)
        self.assertIn('| 员工 | 职责 | 运行端 | 当前工作 |', text)
        self.assertIn(f'| [S035](<{(self.rooter / "ENTRY.md").resolve().as_uri()}>)', text)
        self.assertIn('| Codex |', text)
        self.assertIn('项目参数填 `rooter`，员工号填 `S035`', text)
        self.assertEqual(text.count('paos wake trigger '), 1)
        self.assertIn('paos wake trigger <接收方项目号> <员工号> --prompt', text)
        self.assertIn('[成员留信](Guide/ops-entry.md#联系同事与-rooter)', text)
        self.assertIn('[外部协作者留信](Guide/ops-entry.md#外部-agent-临时协作)', text)
        self.assertIn('[本机 CLI 入口](Guide/ops-entry.md#操作与参考)', text)
        self.assertIn('OpenCode2（TEAM）', text)
        self.assertNotIn('ENTRY-ONLY', text)
        self.assertNotIn('contact.py', text)
        self.assertNotIn('notices/dsh.py', text)
        self.assertNotIn('在线；', text)
        self.team.write_text('## 当前成员\n### 3002-s001\n- 职责：新职责\n', encoding='utf-8')
        missing_harness = render_overview(self.install, self.output)
        self.assertIn('未注明，读 TEAM', missing_harness)
        self.assertNotIn('ENTRY-ONLY', missing_harness)
        self.team.unlink()
        missing = render_overview(self.install, self.output)
        self.assertIn('TEAM 原件缺失', missing)
        self.assertIn(f'| [S040](<{(self.home / "ENTRY.md").resolve().as_uri()}>)', missing)

    def test_relative_team_links_are_relocated_from_team_source(self):
        works = self.project / 'Works/source'
        works.mkdir(parents=True)
        tools = works / 'TOOLS-QUICKSTART.md'
        tools.write_text('# Tools\n', encoding='utf-8')
        evidence = works / 'RESULT-S002.md'
        evidence.write_text('# Result\n', encoding='utf-8')
        absolute = (self.project / 'absolute.md').resolve().as_uri()
        self.team.write_text(
            '## 当前成员\n### 3002-s001\n'
            '- 职责/专长：维护[工具 速查](Works/source/TOOLS-QUICKSTART.md#usage)，'
            f'并保留[远端](https://example.com/a#b)和[绝对](<{absolute}>)。\n'
            '- Harness：来源为[工位 ENTRY](Workstations/3002-s001/ENTRY.md)及'
            '[证据](<Works/source/RESULT-S002.md#result> "证据标题")。\n',
            encoding='utf-8')
        before = self.team.read_bytes()

        text = render_overview(self.install, self.output)

        self.assertEqual(self.team.read_bytes(), before)
        self.assertIn(
            f'[工具 速查](<{tools.resolve().as_uri()}#usage>)', text)
        self.assertIn(
            f'[工位 ENTRY](<{(self.home / "ENTRY.md").resolve().as_uri()}>)', text)
        self.assertIn(
            f'[证据](<{evidence.resolve().as_uri()}#result> "证据标题")', text)
        self.assertIn('[远端](https://example.com/a#b)', text)
        self.assertIn(f'[绝对](<{absolute}>)', text)

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
