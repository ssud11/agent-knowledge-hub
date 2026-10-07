"""Contract tests for commands/refresh.md."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CMD = ROOT / "commands" / "refresh.md"


def parts():
    text = CMD.read_text(encoding="utf-8")
    _, fm, body = re.split(r"^---\s*$", text, maxsplit=2, flags=re.MULTILINE)
    return fm, body


class RefreshCommand(unittest.TestCase):
    def test_frontmatter(self):
        fm, _ = parts()
        self.assertRegex(fm, r"(?m)^description:")
        self.assertNotRegex(fm, r"(?m)^name:")  # commands take their name from the file
        self.assertRegex(fm, r"allowed-tools:.*Bash")

    def test_body_runs_fetcher_with_data_dir(self):
        _, body = parts()
        for needle in ("llms_txt_fetcher.py", '--data-dir "${CLAUDE_PLUGIN_DATA}"',
                       "${CLAUDE_PLUGIN_ROOT}", "py -3", "python3", "python", "pages"):
            self.assertIn(needle, body)

    def test_python_order_is_py3_then_python(self):
        _, body = parts()
        self.assertIn('for py in "py -3" python python3;', body)

    def test_does_not_limit_the_refresh(self):
        _, body = parts()
        self.assertNotIn("--limit", body.split("## Rules")[0])

    def test_readme_uses_prefixed_name(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("/agent-knowledge-hub:refresh", readme)
        self.assertNotRegex(readme, r"(?<![:\w-])/refresh\b")


if __name__ == "__main__":
    unittest.main()
