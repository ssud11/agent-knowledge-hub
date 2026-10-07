"""Checks on examples/find-session-lesson/: the plain lesson and its OKF v0.2 bundle.

Seams: the committed files themselves (what a reader or an OKF consumer opens).
Conformance rules follow section 11 of the OKF v0.2 spec: every non-reserved .md
file has parseable frontmatter with a non-empty `type`; okf_version lives in the
bundle-root index.md.
"""
import re
import unittest
from pathlib import Path

EX = Path(__file__).resolve().parent.parent / "examples" / "find-session-lesson"
BUNDLE = EX / "okf-bundle"
RESERVED = {"index.md", "log.md"}
CITE = re.compile(r"~/agent-knowledge-hub-mirror/[A-Za-z0-9_./-]+?\.md")


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    return m.group(1) if m else None


class PlainLesson(unittest.TestCase):
    def setUp(self):
        self.text = (EX / "lesson.md").read_text(encoding="utf-8")

    def test_covers_function_calling_and_shows_snippet_not_run(self):
        self.assertIn("def find_session(time", self.text)
        self.assertIn("Not run", self.text)
        self.assertIn("function_call", self.text)

    def test_cites_existing_mirror_pages_portably(self):
        cites = set(CITE.findall(self.text))
        self.assertTrue(cites)
        for c in cites:
            self.assertTrue(Path(c).expanduser().is_file(), c)

    def test_no_absolute_machine_paths(self):
        self.assertNotRegex(self.text, r"[A-Za-z]:\\|/Users/|/home/")


class OkfBundle(unittest.TestCase):
    def test_root_index_declares_version_0_2(self):
        fm = frontmatter(BUNDLE / "index.md")
        self.assertIsNotNone(fm)
        self.assertIn('okf_version: "0.2"', fm.splitlines())

    def test_every_concept_has_a_type(self):
        concepts = [p for p in BUNDLE.glob("*.md") if p.name not in RESERVED]
        self.assertGreaterEqual(len(concepts), 3)
        for p in concepts:
            fm = frontmatter(p)
            self.assertIsNotNone(fm, p.name)
            self.assertRegex(fm, r"(?m)^type: \S+", p.name)

    def test_source_resources_exist_and_footnotes_have_ids(self):
        for p in BUNDLE.glob("*.md"):
            if p.name in RESERVED:
                continue
            text = p.read_text(encoding="utf-8")
            for res in CITE.findall(frontmatter(p)):
                self.assertTrue(Path(res).expanduser().is_file(), res)
            for label in re.findall(r"\[\^([\w-]+)\]:", text):
                self.assertIn("id: " + label, frontmatter(p), p.name)


if __name__ == "__main__":
    unittest.main()
