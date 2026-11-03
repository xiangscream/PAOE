"""System Vault navigation: domain files remain authoritative and untouched."""
from pathlib import Path
import contextlib
import hashlib
import io
import json
import re
import sys
import unittest
from urllib.parse import unquote, urlparse, parse_qs

import test_headless

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import system_vault as sv


class SystemVaultTests(unittest.TestCase):
    def setUp(self):
        self.f = test_headless.HeadlessTests(methodName='runTest')
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.output = self.f.root / '系统 阅读库'

    def state(self):
        return sv.inspect_installation(self.f.install)

    def test_create_is_additive_and_contains_no_private_home_content(self):
        secret = self.f.rooter / 'contact.json'
        secret.write_text('{"token":"DO_NOT_EXPORT_PRIVATE_SENTINEL"}', encoding='utf-8')
        before = {p: p.read_bytes() for p in self.f.root.rglob('*') if p.is_file()}
        state = self.state()
        plan = sv.write_vault(state, self.output)
        self.assertFalse(self.output.exists())
        self.assertFalse(plan['domain_writes'])
        sv.write_vault(state, self.output, apply=True)
        combined = '\n'.join(p.read_text(encoding='utf-8') for p in self.output.rglob('*.md'))
        self.assertNotIn('DO_NOT_EXPORT_PRIVATE_SENTINEL', combined)
        self.assertIn('3002-s001', combined)
        self.assertIn(str(self.f.libconfig), combined)
        self.assertNotIn('schema: paos-todo/v4', combined)
        self.assertNotIn('# Pinned', combined)
        self.assertIn('Obsidian候选', combined)
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw, str(path))
        for path in self.f.root.rglob('*'):
            if path.is_file() and path not in before:
                self.assertTrue(path.is_relative_to(self.output), str(path))

    def test_repeated_apply_and_refresh_preserve_human_pages(self):
        sv.write_vault(self.state(), self.output, apply=True)
        home = self.output / 'HOME.md'
        home.write_text(home.read_text(encoding='utf-8') + '\n人工笔记，必须保留。\n', encoding='utf-8')
        before = {p: p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        result = sv.write_vault(self.state(), self.output, apply=True)
        self.assertEqual(result['files'], [])
        self.assertEqual(before, {p: p.read_bytes() for p in self.output.rglob('*') if p.is_file()})
        sv.write_vault(self.state(), self.output, apply=True, refresh=True)
        self.assertEqual(home.read_bytes(), before[home])

    def test_modified_snapshot_and_existing_user_directory_are_not_overwritten(self):
        self.output.mkdir()
        (self.output / 'HOME.md').write_text('用户原件', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '不覆盖'):
            sv.write_vault(self.state(), self.output, apply=True)
        self.assertEqual((self.output / 'HOME.md').read_text(encoding='utf-8'), '用户原件')
        target = self.f.root / '另一新库'
        sv.write_vault(self.state(), target, apply=True)
        project_index = target / 'Projects/PROJECT-INDEX.md'
        project_index.write_text(project_index.read_text(encoding='utf-8') + '\n人工补充\n', encoding='utf-8')
        before = {p: p.read_bytes() for p in target.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(ValueError, '人工修改'):
            sv.write_vault(self.state(), target, apply=True, refresh=True)
        self.assertEqual(before, {p: p.read_bytes() for p in target.rglob('*') if p.is_file()})
        with self.assertRaisesRegex(ValueError, '重叠'):
            sv.write_vault(self.state(), self.f.vault / 'System', apply=True)

    def test_two_absolute_roots_and_missing_project_root_preserve_registry_and_cli(self):
        other = self.f.root / 'E挂载根' / '项目1001'
        self.f.make_home(other / 'Workstations/1001-s001', '1001-s001', '1001')
        self.f.call('project', 'register', '1001', '--root', str(other), '--coordinator', '1001-s001')
        record = self.f.records / '1001.json'
        original = record.read_bytes()
        state = self.state()
        self.assertEqual({p['id'] for p in state['projects']}, {'1001', '3002'})
        self.assertTrue(all(p['available'] for p in state['projects']))
        self.assertEqual(Path(self.f.call('project', 'show', '1001')[1]['project']['root_path']), other)
        offline = other.with_name('项目1001-offline')
        self.assertTrue(other.resolve().is_relative_to(self.f.root))
        self.assertTrue(offline.resolve().is_relative_to(self.f.root))
        other.rename(offline)
        missing = next(p for p in self.state()['projects'] if p['id'] == '1001')
        self.assertFalse(missing['available'])
        self.assertEqual(Path(missing['root_path']), other)
        self.f.call('project', 'show', '1001')
        sv.write_vault(self.state(), self.output, apply=True)
        self.assertIn('Unavailable', (self.output / 'Projects/PROJECT-INDEX.md').read_text(encoding='utf-8'))
        self.assertEqual(record.read_bytes(), original)
        self.assertFalse(other.exists())

    def test_uri_escaping_and_all_internal_navigation_targets(self):
        source = self.f.vault / '入口 #1 & 阅读.md'
        source.write_text('原件', encoding='utf-8')
        rendered = sv.link(source, '打开', obsidian=True)
        uri = re.search(r'\]\((obsidian:[^)]+)\)', rendered).group(1)
        self.assertEqual(Path(parse_qs(urlparse(uri).query)['path'][0]), source)
        self.assertIn('%23', uri)
        self.assertIn('%26', uri)
        self.assertIn('%20', uri)
        sv.write_vault(self.state(), self.output, apply=True)
        for page in self.output.rglob('*.md'):
            for target in re.findall(r'\[\[([^]|]+)', page.read_text(encoding='utf-8')):
                name = target.split('#', 1)[0]
                candidates = [self.output / (name + '.md'), page.parent / (name + '.md')]
                self.assertTrue(any(p.is_file() for p in candidates), (page, name))

    def test_invalid_installation_has_structured_error_and_creates_nothing(self):
        self.f.install.write_text('{invalid JSON', encoding='utf-8')
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            code = sv.main(['--installation-file', str(self.f.install), '--output', str(self.output), '--apply'])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(error.getvalue())['error_code'], 'installation_descriptor_invalid')
        self.assertFalse(self.output.exists())

    def test_unavailable_registry_cannot_replace_existing_snapshot_with_zero_projects(self):
        sv.write_vault(self.state(), self.output, apply=True)
        original_pages = {p: p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        original_record = self.f.record.read_bytes()
        arguments = ['--installation-file', str(self.f.install), '--output', str(self.output),
                     '--apply', '--refresh-snapshots']
        for source, expected_code in ((self.f.data, 'registry_unavailable'),
                                       (self.f.records, 'registry_uninitialized')):
            offline = source.with_name(source.name + '-offline')
            self.assertTrue(source.resolve().is_relative_to(self.f.root))
            self.assertTrue(offline.resolve().is_relative_to(self.f.root))
            source.rename(offline)
            try:
                error = io.StringIO()
                with contextlib.redirect_stderr(error):
                    self.assertEqual(sv.main(arguments), 1)
                self.assertEqual(json.loads(error.getvalue())['error_code'], expected_code)
                self.assertEqual(original_pages, {p: p.read_bytes() for p in self.output.rglob('*') if p.is_file()})
            finally:
                offline.rename(source)
        self.assertEqual(self.f.record.read_bytes(), original_record)
        # An accessible, initialized, genuinely empty Registry is different.
        offline = self.f.records.with_name('projects-saved')
        self.assertTrue(offline.resolve().is_relative_to(self.f.root))
        self.f.records.rename(offline)
        self.f.records.mkdir()
        try:
            state = self.state()
            self.assertEqual(state['projects'], [])
            text = sv.rendered_snapshots(state)['Projects/PROJECT-INDEX.md']
            self.assertIn('Registry根已确认可读', text)
            self.assertIn('0 条登记', text)
        finally:
            self.f.records.rmdir()  # Exactly the empty temporary fixture above.
            offline.rename(self.f.records)
        self.assertEqual(self.f.record.read_bytes(), original_record)


if __name__ == '__main__':
    unittest.main()
