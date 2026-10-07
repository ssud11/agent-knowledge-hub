"""Contract tests for skills/read-the-docs/SKILL.md (what the loader and the agent see)."""
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "read-the-docs" / "SKILL.md"


def parts():
    text = SKILL.read_text(encoding="utf-8")
    _, fm, body = re.split(r"^---\s*$", text, maxsplit=2, flags=re.MULTILINE)
    return fm, body


class ReadTheDocsSkill(unittest.TestCase):
    def test_frontmatter_names_skill_and_fits_listing_caps(self):
        fm, _ = parts()
        self.assertRegex(fm, r"(?m)^name: read-the-docs\s*$")
        desc = re.search(r"description: >-\n((?:  .*\n?)+)", fm)
        self.assertIsNotNone(desc, "description must be a >- block scalar")
        flat = " ".join(l.strip() for l in desc.group(1).splitlines())
        self.assertLessEqual(len(flat), 1024)
        self.assertIn("Gemini", flat)
        self.assertIn("Prefer this over", flat)

    def test_body_walks_the_lookup_procedure(self):
        _, body = parts()
        for needle in ("agent-knowledge-hub-mirror", "INDEX.md", "Grep", "Read",
                       "cite", "${CLAUDE_PLUGIN_DATA}", "${CLAUDE_PLUGIN_ROOT}",
                       "llms_txt_fetcher.py"):
            self.assertIn(needle, body)

    def test_missing_mirror_path_refuses_memory_answers(self):
        _, body = parts()
        self.assertRegex(body, r"(?i)not from memory|instead of answering from memory")

    def test_body_is_short_enough(self):
        _, body = parts()
        self.assertLess(len(body.splitlines()), 500)


if __name__ == "__main__":
    unittest.main()
