"""Reader headings must preserve frontmatter and the original execution reference."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from document_reading import add_intro, remove_intro, HUMAN_START, HUMAN_END, AGENT_START


class ReadingHeaderTests(unittest.TestCase):
    def test_original_metadata_and_reference_round_trip_with_both_newlines(self):
        for nl in ('\n', '\r\n'):
            with self.subTest(newline=repr(nl)):
                original = nl.join(['---', 'schema: paos-skill/v1', 'id: example', '---', '',
                                    '# Example', '', '## Existing instructions', '',
                                    '```python', 'print("keep all original code")', '```', ''])
                result = add_intro(original, '这是用途说明。', '先准备原始材料。')
                self.assertTrue(result.startswith(original[:original.index('# Example')]))
                self.assertEqual(remove_intro(result), original)
                self.assertEqual(add_intro(result, '另一段说明', '另一入口'), result)
                self.assertLess(result.index(HUMAN_START), result.index(HUMAN_END))
                self.assertLess(result.index(HUMAN_END), result.index(AGENT_START))
                self.assertIn('## Existing instructions', result[result.index(AGENT_START):])

    def test_incomplete_header_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            add_intro('# Example\n'+HUMAN_START+'\npartial', '说明', '开始')


if __name__ == '__main__':
    unittest.main()
