"""Common AGENTS section sync: disposable registry, no real project mutations."""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_headless

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'code' / 'personal-agent-os' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import paos_agents_common as sync


class AgentsCommonTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_headless.HeadlessTests(methodName='runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.fixture.vault.mkdir(parents=True, exist_ok=True)
        self.source_v1 = self.fixture.root / 'source-v1.md'
        self.source_v2 = self.fixture.root / 'source-v2.md'
        self.source_v1.write_text('''# Template\n<!-- paoe:common:start -->\n## Guide\n\nOld rule.\n<!-- paoe:common:end -->\n## Project\n''', encoding='utf-8')
        self.source_v2.write_text('''# Template\n<!-- paoe:common:start -->\n## Guide\n\nNew rule.\n<!-- paoe:common:end -->\n## Project\n''', encoding='utf-8')
        self.target = self.fixture.vault / 'AGENTS.md'
        self.local = '## 项目约定\n\nHuman 专项编辑；需要保留。\n'
        self.write_target(self.source_v1)

    def write_target(self, source: Path, *, newline='\n'):
        block = sync.source_block(source)
        content = '# Project 3002\n' + sync.START + '\n' + sync.managed_section(block) + sync.END + '\n' + self.local
        self.target.write_bytes(content.replace('\n', newline).encode('utf-8'))

    def call(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sync.main(['--installation-file', str(self.fixture.install),
                              '--template', str(self.source_v2), '--project', '3002', *args])
        return code, out.getvalue(), err.getvalue()

    def test_check_stale_diff_then_apply_preserves_human_bytes(self):
        before = self.target.read_bytes()
        code, out, _ = self.call('--check')
        self.assertEqual(code, 1)
        self.assertIn('stale', out)
        self.assertEqual(self.target.read_bytes(), before)
        code, out, _ = self.call('--diff')
        self.assertEqual(code, 1)
        self.assertIn('+New rule.', out)
        self.assertEqual(self.target.read_bytes(), before)
        code, out, _ = self.call('--apply')
        self.assertEqual(code, 0)
        self.assertIn('updated: 3002', out)
        text = self.target.read_text(encoding='utf-8')
        self.assertIn(self.local, text)
        self.assertIn('New rule.', text)
        self.assertNotIn('Old rule.', text)
        self.assertEqual(self.call('--check')[0], 0)
        self.assertEqual(self.target.read_text(encoding='utf-8'), text)

    def test_newly_copied_template_is_sealed_only_if_public_text_matches(self):
        new_source = sync.source_block(self.source_v2)
        content = '# Project 3002\n' + sync.START + '\n' + new_source.body + sync.END + '\n' + self.local
        self.target.write_text(content, encoding='utf-8')
        self.assertEqual(self.call('--apply')[0], 0)
        self.assertEqual(self.call('--check')[0], 0)
        self.assertIn(self.local, self.target.read_text(encoding='utf-8'))
        self.target.write_text(content.replace('New rule.', 'Edited by Human.'), encoding='utf-8')
        before = self.target.read_bytes()
        rc, stdout, _ = self.call('--apply')
        self.assertEqual(rc, 1)
        self.assertIn('conflict', stdout)
        self.assertEqual(self.target.read_bytes(), before)

    def test_manual_change_inside_common_is_conflict_without_overwrite(self):
        self.target.write_text(self.target.read_text(encoding='utf-8').replace('Old rule.', 'Edited by Human.'),encoding='utf-8')
        before = self.target.read_bytes()
        code, out, _ = self.call('--apply')
        self.assertEqual(code, 1)
        self.assertIn('conflict', out)
        self.assertEqual(self.target.read_bytes(), before)

    def test_unmanaged_project_agents_does_not_get_replaced(self):
        self.target.write_text('Human 专属 AGENTS\n', encoding='utf-8')
        before = self.target.read_bytes()
        code, out, _ = self.call('--apply')
        self.assertEqual(code, 1)
        self.assertIn('conflict', out)
        self.assertEqual(self.target.read_bytes(), before)

    def test_crlf_preserves_human_content_and_line_endings(self):
        self.write_target(self.source_v1, newline='\r\n')
        self.assertEqual(self.call('--apply')[0], 0)
        data = self.target.read_bytes()
        self.assertNotIn(b'\n', data.replace(b'\r\n', b''))
        self.assertIn(self.local.replace('\n', '\r\n').encode('utf-8'), data)
        self.assertEqual(self.call('--check')[0], 0)

    def test_missing_is_unavailable_not_created(self):
        self.target.unlink()
        code, out, _ = self.call('--apply')
        self.assertEqual(code, 1)
        self.assertIn('unavailable', out)
        self.assertFalse(self.target.exists())

    def test_symlink_is_unavailable_not_replaced(self):
        self.target.unlink()
        try:
            self.target.symlink_to(self.source_v1)
        except OSError as exc:
            if getattr(exc, 'winerror', None) == 1314:
                self.skipTest('File symlinks unavailable for this Windows user')
            raise
        code, out, _ = self.call('--apply')
        self.assertEqual(code, 1)
        self.assertIn('unavailable', out)
        self.assertTrue(self.target.is_symlink())

    def test_scope_requires_explicit_registry_project(self):
        before = self.target.read_bytes()
        self.assertEqual(sync.main(['--template', str(self.source_v2), '--installation-file',
                                    str(self.fixture.install), '--apply']), 2)
        self.assertEqual(sync.main(['--template', str(self.source_v2), '--installation-file',
                                    str(self.fixture.install), '--project', '2001', '--apply']), 2)
        self.assertEqual(self.target.read_bytes(), before)

    def test_print_block_is_available_for_manual_first_adoption(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = sync.main(['--template', str(self.source_v2), '--print-block'])
        self.assertEqual(code, 0)
        self.assertIn(sync.START, out.getvalue())
        self.assertIn(sync.END, out.getvalue())
        self.assertIn('source-sha256', out.getvalue())

    def test_changed_target_before_atomic_publish_fails(self):
        status = sync.inspect_target('3002', self.target, sync.source_block(self.source_v2))
        self.assertEqual(status.status, 'stale')
        self.target.write_text(self.target.read_text(encoding='utf-8')+'\nnew Human note\n', encoding='utf-8')
        before = self.target.read_bytes()
        with self.assertRaises(sync.CommonError):
            sync._atomic_update(status)
        self.assertEqual(self.target.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
