"""Contract tests for skills/add-docs/SKILL.md."""
import re
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "add-docs"
SKILL = SKILL_DIR / "SKILL.md"


def parts():
    text = SKILL.read_text(encoding="utf-8")
    _, fm, body = re.split(r"^---\s*$", text, maxsplit=2, flags=re.MULTILINE)
    return fm, body


class AddDocsSkill(unittest.TestCase):
    def test_frontmatter(self):
        fm, _ = parts()
        self.assertRegex(fm, r"(?m)^name: add-docs\s*$")
        desc = re.search(r"description: >-\n((?:  .*\n?)+)", fm)
        self.assertIsNotNone(desc)
        self.assertLessEqual(len(" ".join(l.strip() for l in desc.group(1).splitlines())), 1024)

    def test_body_wires_both_paths_and_dry_run(self):
        _, body = parts()
        for needle in ("llms_txt_fetcher.py", "${CLAUDE_PLUGIN_DATA}", "${CLAUDE_PLUGIN_ROOT}",
                       "sites.json", "fetchers/", "--check-only", "DRY RUN PASSED",
                       "DRY RUN FAILED", "references/patterns.md"):
            self.assertIn(needle, body)

    def test_never_writes_into_plugin_folder_and_reports_failure(self):
        _, body = parts()
        self.assertRegex(body, r"(?i)write nothing inside `\$\{CLAUDE_PLUGIN_ROOT\}`")
        self.assertRegex(body, r"(?i)do not report the site as added unless")

    def test_patterns_reference_covers_three_kinds(self):
        text = (SKILL_DIR / "references" / "patterns.md").read_text(encoding="utf-8")
        for heading in ("llms.txt site", "GitHub markdown repo", "HTML site"):
            self.assertIn(heading, text)

    def test_no_host_details(self):
        text = SKILL.read_text(encoding="utf-8") + (SKILL_DIR / "references" / "patterns.md").read_text(encoding="utf-8")
        for bad in ("system" + "d", "sync" + "thing", "tail" + "scale", "cron" + "tab", "sch" + "tasks"):
            self.assertNotIn(bad, text.lower())


if __name__ == "__main__":
    unittest.main()
