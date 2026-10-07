"""Contract tests for skills/new-study/SKILL.md and its template."""
import re
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "skills" / "new-study"


def parts():
    text = (BASE / "SKILL.md").read_text(encoding="utf-8")
    _, fm, body = re.split(r"^---\s*$", text, maxsplit=2, flags=re.MULTILINE)
    return fm, body


class NewStudySkill(unittest.TestCase):
    def test_frontmatter(self):
        fm, _ = parts()
        self.assertRegex(fm, r"(?m)^name: new-study\s*$")
        desc = re.search(r"description: >-\n((?:  .*\n?)+)", fm)
        self.assertIsNotNone(desc)
        self.assertLessEqual(len(" ".join(l.strip() for l in desc.group(1).splitlines())), 1024)

    def test_body_wires_helper_and_never_copies_teach(self):
        _, body = parts()
        for needle in ("scripts/new_study.py", "${CLAUDE_PLUGIN_DATA}", "${CLAUDE_PLUGIN_ROOT}",
                       "Study folder:", "beside"):
            self.assertIn(needle, body)
        self.assertRegex(body, r"(?i)never copy")

    def test_template_carries_grounding_duty(self):
        text = (BASE / "template" / "CLAUDE.md").read_text(encoding="utf-8")
        for needle in ("{{MIRROR_DIR}}", "{{PRACTICE_DIR}}", "absolute path"):
            self.assertIn(needle, text)
        self.assertRegex(text, r"(?i)cites? ")


if __name__ == "__main__":
    unittest.main()
