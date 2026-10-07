"""Behavior tests for scripts/scrub.py, driven through its CLI.

Fixture strings that would trip the scrubber are built at runtime so this
file itself stays clean.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRUB = Path(__file__).resolve().parent.parent / "scripts" / "scrub.py"

FAKE_IP = "203.0." + "113.7"
TS_IP = "100." + "100.1.2"
LAN_IP = "192." + "168.1.5"
FAKE_EMAIL = "someone" + "@" + "example.org"
NOREPLY = "12345+user" + "@users.noreply." + "github.com"
WIN_PATH = "D" + ":" + "\\" + "stuff"
COWORK = "cowork" + " projects"
SECRET = "gh" + "p_" + "A" * 36
SCHED = "sys" + "temd timer"
WINSCHED = "sch" + "tasks /create"


class ScrubCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.git("init", "-q")
        self.addCleanup(self._tmp.cleanup)

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True,
                       capture_output=True)

    def write(self, name, text, track=True):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        if track:
            self.git("add", name)
        return p

    def run_scrub(self, terms=None, env_extra=None):
        env = {k: v for k, v in os.environ.items()
               if k != "AKH_SCRUB_TERMS_FILE"}
        if terms is not None:
            env["AKH_SCRUB_TERMS_FILE"] = str(terms)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [sys.executable, str(SCRUB), "--root", str(self.root)],
            capture_output=True, text=True, env=env)

    def assert_hit(self, text, name=None, filename="a.txt"):
        self.write(filename, "line one\n" + text + "\n")
        r = self.run_scrub()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(filename + ":2", r.stdout)
        if name:
            self.assertIn(name, r.stdout)
        self.assertNotIn(text.strip(), r.stdout + r.stderr)


class GenericPatterns(ScrubCase):
    def test_clean_tree_passes(self):
        self.write("a.txt", "hello world\nversion 0.1.0\n")
        r = self.run_scrub()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_ipv4_fails(self):
        self.assert_hit("host " + FAKE_IP, "ipv4")

    def test_tailscale_cgnat_fails(self):
        self.assert_hit("node " + TS_IP, "tailscale-ip")

    def test_lan_ip_fails(self):
        self.assert_hit("router " + LAN_IP, "lan-ip")

    def test_email_fails(self):
        self.assert_hit("mail " + FAKE_EMAIL, "email")

    def test_github_noreply_email_allowed(self):
        self.write("a.txt", "by " + NOREPLY + "\n")
        self.assertEqual(self.run_scrub().returncode, 0)

    def test_windows_path_fails(self):
        self.assert_hit("path " + WIN_PATH, "windows-path")

    def test_cowork_projects_fails(self):
        self.assert_hit("see " + COWORK.upper(), "cowork-projects")

    def test_secret_shape_fails(self):
        self.assert_hit("token " + SECRET, "secret")

    def test_scheduler_setup_fails(self):
        self.assert_hit("use " + SCHED, "scheduler")
        self.assert_hit("run " + WINSCHED, "scheduler", filename="b.txt")

    def test_google_page_file_fails(self):
        self.write("docs/page.md.txt", "x\n")
        r = self.run_scrub()
        self.assertEqual(r.returncode, 1)
        self.assertIn("page.md.txt", r.stdout)
        self.assertIn("google-page-file", r.stdout)

    def test_copied_teach_skill_fails(self):
        self.write("skills/x/SKILL.md", "---\nname: teach\n---\nbody\n")
        r = self.run_scrub()
        self.assertEqual(r.returncode, 1)
        self.assertIn("teach-skill", r.stdout)

    def test_untracked_unignored_file_scanned(self):
        self.write("u.txt", "ip " + FAKE_IP + "\n", track=False)
        self.assertEqual(self.run_scrub().returncode, 1)

    def test_ignored_file_not_scanned(self):
        self.write(".gitignore", "secret.txt\n")
        self.write("secret.txt", "ip " + FAKE_IP + "\n", track=False)
        self.assertEqual(self.run_scrub().returncode, 0)

    def test_inline_allow_marker(self):
        self.write("a.txt", "ip " + FAKE_IP + "  scrub" + ": allow\n")
        self.assertEqual(self.run_scrub().returncode, 0)


class PrivateTerms(ScrubCase):
    def test_private_term_fails_without_echo(self):
        term = "zq" + "xjunk"
        tf = self.root.parent / (self.root.name + "-terms.txt")
        tf.write_text("# comment\n" + term + "\n", encoding="utf-8")
        self.addCleanup(tf.unlink)
        self.write("a.txt", "has " + term.upper() + " inside\n")
        r = self.run_scrub(terms=tf)
        self.assertEqual(r.returncode, 1)
        self.assertIn("a.txt:1", r.stdout)
        self.assertIn("private-term", r.stdout)
        self.assertNotIn(term, (r.stdout + r.stderr).lower())

    def test_unset_env_passes_with_note(self):
        self.write("a.txt", "fine\n")
        r = self.run_scrub()
        self.assertEqual(r.returncode, 0)
        self.assertIn("generic checks only", r.stdout + r.stderr)

    def test_unreadable_terms_file_exits_2(self):
        self.write("a.txt", "fine\n")
        r = self.run_scrub(terms=self.root / "nope.txt")
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
