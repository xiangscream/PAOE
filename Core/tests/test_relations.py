"""Explicit relation evidence, derived backlinks and a bounded cyclic walk."""

from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "code/personal-agent-os/scripts"
sys.path.insert(0, str(SCRIPTS))
from paos_relations import related


class RelationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.topics = self.root / "Topics"
        self.topics.mkdir()
        self.a, self.b = self.topics / "LRC.md", self.topics / "Reachy.md"
        self.a.write_text("# LRC\n\nHuman批注：不要改此段\n\n## 相关经历\n"
                          "- [Reachy](Reachy.md#接口) — 可借鉴；分开反馈、感知和执行。来源：[Human原话](../Sessions/source.md)。归属：Human明示。\n",
                          encoding="utf-8")
        self.b.write_text("# Reachy\n\n## 相关经历\n- [LRC](LRC.md) — Agent建议的探索联系；原作者待核。\n", encoding="utf-8")

    def test_cycle_backlink_evidence_and_human_edits_are_preserved(self):
        before = self.a.read_bytes()
        got = related(self.root, str(self.b), depth=3)
        self.assertEqual(len(got["nodes"]), 2)
        edge = next(e for e in got["relations"] if e["source"] == str(self.a))
        self.assertIn("Human明示", edge["explanation"])
        self.assertEqual(edge["sources"][0]["label"], "Human原话")
        self.assertTrue(edge["target"].endswith("Reachy.md#接口"))
        self.assertEqual(self.a.read_bytes(), before)
        self.assertEqual(got["writes"], [])

    def test_budget_and_unreadable_relation_are_visible(self):
        self.a.write_text(self.a.read_text(encoding="utf-8") + "- missing named target\n", encoding="utf-8")
        got = related(self.root, str(self.a), depth=2, limit=1)
        self.assertTrue(got["truncated"])
        self.assertEqual(len(got["nodes"]), 1)
        self.assertEqual(len(got["missing"]), 1)
        self.assertEqual(got["missing"][0]["source"], str(self.a))

    def test_code_examples_do_not_become_relations(self):
        self.a.write_text("# LRC\n```md\n## 相关经历\n- [example](fake.md) — example\n```\n", encoding="utf-8")
        self.assertFalse(any(edge["label"] == "example"
                             for edge in related(self.root, str(self.a))["relations"]))

    def test_insights_and_spaces_in_destinations(self):
        folder = self.root / "心得"
        folder.mkdir()
        tip = folder / "my tip.md"
        tip.write_text("# Tip\n## 相关经历\n- [LRC](<../Topics/LRC.md>) — 修正了；来源是当前正文。\n", encoding="utf-8")
        got = related(self.root, str(self.a), depth=1)
        self.assertIn(str(tip), [n["locator"] for n in got["nodes"]])


if __name__ == "__main__":
    unittest.main()
