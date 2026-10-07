"""Contract tests for skills/onboarding/SKILL.md."""
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "onboarding" / "SKILL.md"


def parts():
    text = SKILL.read_text(encoding="utf-8")
    _, fm, body = re.split(r"^---\s*$", text, maxsplit=2, flags=re.MULTILINE)
    return fm, body


class OnboardingSkill(unittest.TestCase):
    def test_frontmatter(self):
        fm, _ = parts()
        self.assertRegex(fm, r"(?m)^name: onboarding\s*$")
        desc = re.search(r"description: >-\n((?:  .*\n?)+)", fm)
        self.assertIsNotNone(desc)
        self.assertLessEqual(len(" ".join(l.strip() for l in desc.group(1).splitlines())), 1024)

    def test_body_wires_helper_and_data_folder(self):
        _, body = parts()
        for needle in ("scripts/onboard.py", "${CLAUDE_PLUGIN_DATA}", "${CLAUDE_PLUGIN_ROOT}",
                       "agent-knowledge-hub-mirror", "DRY RUN PASSED", "DRY RUN FAILED"):
            self.assertIn(needle, body)

    def test_refuses_to_claim_success_without_passing_dry_run(self):
        _, body = parts()
        self.assertRegex(body, r"(?i)do not report success unless")


if __name__ == "__main__":
    unittest.main()
