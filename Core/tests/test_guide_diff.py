"""Small tests for the one Guide operation still exposed by the CLI.

Learning note: a pure read-only function can be tested by checking both its
result and the unchanged bytes of its input files. This uses no Project Vault.
"""
import sys
import tempfile
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CORE / 'code/personal-agent-os/scripts'))
from paos_guide import GuideProblem, build_guide_diff


class GuideDiffTests(unittest.TestCase):
    def test_changed_files_preserve_both_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            canonical = Path(folder) / 'main.md'
            candidate = Path(folder) / 'proposal.md'
            canonical.write_text('# Guide\nold\n', encoding='utf-8')
            candidate.write_text('# Guide\nnew\n', encoding='utf-8')
            before = (canonical.read_bytes(), candidate.read_bytes())
            result = build_guide_diff(candidate, canonical_src=canonical)
            self.assertTrue(result['changed'])
            self.assertIn('-old', result['diff'])
            self.assertIn('+new', result['diff'])
            self.assertIn(str(canonical), result['diff'])
            self.assertEqual(before, (canonical.read_bytes(), candidate.read_bytes()))

    def test_equal_files_have_empty_diff(self):
        with tempfile.TemporaryDirectory() as folder:
            main = Path(folder) / 'main.md'
            copy = Path(folder) / 'copy.md'
            main.write_text('# same\n', encoding='utf-8')
            copy.write_bytes(main.read_bytes())
            result = build_guide_diff(copy, canonical_src=main)
            self.assertFalse(result['changed'])
            self.assertEqual(result['diff'], '')
            self.assertEqual(result['candidate_sha256'], result['canonical_sha256'])

    def test_missing_candidate_returns_explicit_error(self):
        with tempfile.TemporaryDirectory() as folder:
            main = Path(folder) / 'main.md'
            main.write_text('# exists\n', encoding='utf-8')
            with self.assertRaises(GuideProblem) as error:
                build_guide_diff(Path(folder) / 'missing.md', canonical_src=main)
            self.assertEqual(error.exception.code, 'guide_candidate_missing')


if __name__ == '__main__':
    unittest.main()
