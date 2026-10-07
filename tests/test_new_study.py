"""new-study helper: creates a study folder from the shipped template, practice folder beside it."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import new_study

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "new_study.py"


class NewStudyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.data = self.base / "data"
        self.data.mkdir()
        self.mirror = self.base / "my mirror"
        (self.data / "mirror-dir.txt").write_text(str(self.mirror) + "\n", encoding="utf-8")
        self.parent = self.base / "studies"

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_study_with_grounding_and_practice_beside_it(self):
        study, practice = new_study.create(str(self.data), "gemini-fc", str(self.parent))
        study, practice = Path(study), Path(practice)
        self.assertEqual(study, self.parent / "gemini-fc")
        self.assertEqual(practice.parent, study.parent)          # beside, not inside
        self.assertTrue(practice.is_dir())
        self.assertFalse(str(practice).startswith(str(study) + os.sep))
        claude_md = (study / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(str(self.mirror), claude_md)               # absolute mirror path from mirror-dir.txt
        self.assertRegex(claude_md, r"(?i)cite")
        self.assertIn(str(practice), claude_md)
        self.assertNotIn("{{", claude_md)                         # every placeholder filled

    def test_default_mirror_when_no_mirror_dir_file(self):
        empty = self.base / "empty-data"
        empty.mkdir()
        study, _ = new_study.create(str(empty), "s", str(self.parent))
        text = (Path(study) / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(os.path.join(os.path.expanduser("~"), "agent-knowledge-hub-mirror"), text)

    def test_refuses_existing_study(self):
        new_study.create(str(self.data), "s", str(self.parent))
        with self.assertRaises(FileExistsError):
            new_study.create(str(self.data), "s", str(self.parent))

    def test_rejects_unsafe_names(self):
        for bad in ("", "a/b", "..", "a b;c"):
            with self.assertRaises(ValueError):
                new_study.create(str(self.data), bad, str(self.parent))

    def test_cli_exit_codes(self):
        cmd = [sys.executable, str(SCRIPT), "--data-dir", str(self.data), "--name", "cli-s",
               "--parent", str(self.parent)]
        ok = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn(str(self.parent / "cli-s"), ok.stdout)
        again = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(again.returncode, 0)


if __name__ == "__main__":
    unittest.main()
