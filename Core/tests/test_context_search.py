import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "code/personal-agent-os/scripts"
sys.path.insert(0, str(SCRIPTS))
from paos_context_search import QmdUnavailable, search_context
from paos_installation import load_installation_descriptor, write_installation_descriptor
from paos_registry import ProjectRegistry


class OriginalSearchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.project = root / "project"
        self.project.mkdir()
        self.install = root / "installation.json"
        write_installation_descriptor(self.install, source_root=str(SCRIPTS.parent), data_root=str(root/"data"),
                                      library_roots_config=str(root/"libraries.json"))
        ProjectRegistry(self.install).register("3997", root_path=str(self.project), homes=["S841"],
                                              coordinator_home_id="S841")
        self.descriptor = load_installation_descriptor(self.install)
        self.args = SimpleNamespace(query="公开资料", scope=["project", "experience"], mode="hybrid",
                                    limit=5, project=None)
        self.home = {"project_id": "3997"}

    def search(self, result_by_collection):
        def query(launcher, collection, query, mode, limit):
            result = result_by_collection[collection]
            if isinstance(result, QmdUnavailable):
                raise result
            return result

        with patch("paos_context_search.query_qmd", side_effect=query):
            return search_context(self.args, self.home, self.install, self.descriptor)

    def test_sections_merge_across_hits_and_explicit_date_comes_from_the_original(self):
        source = self.project / "memo.md"
        source.write_text("---\ndate: 2026-07-01\ndescription: A decision\n---\n# Memo", encoding="utf-8")
        def hit(line):
            return {"file": str(source), "title": "Memo", "line": line, "snippet": f"Excerpt at {line}"}
        answer = self.search({"project-3997": [hit(2), hit(5)], "exm": []})
        self.assertTrue(answer["ok"])
        self.assertEqual(len(answer["results"]), 1)
        entry = answer["results"][0]
        self.assertEqual([row["line"] for row in entry["sections"]], [2, 5])
        self.assertEqual((entry["date"], entry["description"], entry["status"]), ("2026-07-01", "A decision", None))

    def test_failed_collection_does_not_erase_or_misrepresent_other_results(self):
        answer = self.search({"project-3997": QmdUnavailable("collection not found"),
                              "exm": [{"file": "qmd://exm/Daily/former.md", "title": "Moved"}]})
        self.assertFalse(answer["ok"])
        self.assertEqual(answer["coverage"][0]["reason"], "collection not found")
        self.assertEqual(answer["results"][0]["availability"], "index_only")
        self.assertIsNone(answer["results"][0]["date"])

    def test_wrong_project_is_reported_and_archived_file_is_labelled(self):
        outside = self.project.parent / "elsewhere.md"
        outside.write_text("unrelated", encoding="utf-8")
        answer = self.search({"project-3997": [{"file": str(outside)}], "exm": []})
        self.assertFalse(answer["ok"])
        self.assertEqual(answer["results"], [])
        archived = self.project / "Archive" / "old.md"
        archived.parent.mkdir()
        archived.write_text("# Historical", encoding="utf-8")
        answer = self.search({"project-3997": [{"file": str(archived)}], "exm": []})
        self.assertEqual(answer["results"][0]["status"], "historical")

    def test_unregistered_methods_are_reported_as_incomplete(self):
        self.args.scope = ["methods"]
        answer = self.search({})
        self.assertFalse(answer["ok"])
        self.assertEqual(answer["coverage"][0]["source"], "method-catalog")

    def test_experience_archive_is_relative_to_its_registered_collection(self):
        self.args.scope = ["experience"]
        root = self.project.parent / "Archive" / "Experience"
        archived = root / "Archive" / "prior.md"
        active = root / "Topics" / "active.md"
        for file in (archived, active):
            file.parent.mkdir(parents=True)
            file.write_text("# A source", encoding="utf-8")
        rows = [{"file": str(archived)}, {"file": str(active)},
                {"file": "qmd://exm/Archive/moved.md"}]
        with patch("paos_context_search._run_qmd", return_value=f"Collection: exm\n  Path: {root}\n"):
            result = self.search({"exm": rows})
        self.assertTrue(result["ok"])
        self.assertEqual([v["status"] for v in result["results"]], ["historical", None, None])
        self.assertEqual(result["results"][-1]["availability"], "index_only")
        active.write_text("---\nstatus: adopted\n---\n# Source", encoding="utf-8")
        with patch("paos_context_search.qmd_collection_root", return_value=root):
            result = self.search({"exm": [{"file": str(active)}]})
            self.assertEqual(result["results"][0]["status"], "adopted")
            invalid = self.search({"exm": [{"file": str(self.project / "other.md")}]})
            self.assertFalse(invalid["ok"])
