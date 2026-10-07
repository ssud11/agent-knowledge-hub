"""Review fixes for tickets 05 to 10 (fetcher, new_study, onboard)."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fetchers import llms_txt_fetcher as f
from scripts import new_study, onboard

ROOT = Path(__file__).resolve().parent.parent
FETCHER = ROOT / "fetchers" / "llms_txt_fetcher.py"
ONBOARD = ROOT / "scripts" / "onboard.py"
BOM = "\ufeff"


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.data = self.base / "data"
        self.data.mkdir()
        self.mirror = self.base / "mirror"

    def tearDown(self):
        self.tmp.cleanup()

    def write_sites(self, *entries):
        (self.data / "sites.json").write_text(json.dumps({"sites": list(entries)}),
                                              encoding="utf-8")

    def cli(self, *extra):
        return subprocess.run([sys.executable, str(FETCHER), "--data-dir", str(self.data),
                               "--mirror-dir", str(self.mirror), *extra],
                              capture_output=True, text=True)


class RootPageVsIndex(unittest.TestCase):
    def test_root_page_does_not_collide_with_index_md_case_insensitively(self):
        urls = ["https://h/g/", "https://h/g/INDEX.md.txt", "https://h/g/x.md.txt"]
        m = f.local_paths(urls, "https://h/g/docs/llms.txt")
        lowered = [v.lower() for v in m.values()]
        self.assertEqual(len(set(lowered)), 3)
        self.assertNotIn("index.md", lowered)
        self.assertEqual(m[urls[0]], "index-2.md")

    def test_changes_slug_is_reserved_too(self):
        m = f.local_paths(["https://h/g/docs/CHANGES.md.txt"], "https://h/g/docs/llms.txt")
        self.assertNotEqual(list(m.values())[0].lower(), "changes.md")


class MirrorDirHelper(Tmp):
    def test_bom_file_is_clean_in_all_three_callers(self):
        (self.data / "mirror-dir.txt").write_text(BOM + str(self.mirror) + "\n",
                                                  encoding="utf-8")
        want = str(self.mirror)
        self.assertEqual(f.resolve_mirror_dir(str(self.data), None), want)
        study, _ = new_study.create(str(self.data), "s", str(self.base / "p"))
        text = (Path(study) / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(want, text)
        self.assertNotIn(BOM, text)
        self.assertEqual(onboard.saved_mirror_dir(str(self.data)), want)

    def test_tilde_is_expanded_and_default_shared(self):
        (self.data / "mirror-dir.txt").write_text("~/some-mirror\n", encoding="utf-8")
        want = os.path.abspath(os.path.join(os.path.expanduser("~"), "some-mirror"))
        self.assertEqual(f.resolve_mirror_dir(str(self.data), None), want)
        self.assertEqual(new_study.mirror_dir(str(self.data)), want)
        empty = self.base / "empty"
        empty.mkdir()
        self.assertEqual(onboard.default_mirror_dir(), f.resolve_mirror_dir(str(empty), None))


class SiteNames(Tmp):
    def test_escaping_names_fail_plainly_and_write_nothing(self):
        for bad in ("..\\x", "../x", "C:", "C" + ":\\evil","/abs", "a/b", ""):
            self.write_sites({"name": bad, "llms_txt": "http://invalid.invalid/llms.txt"})
            p = self.cli()
            self.assertNotEqual(p.returncode, 0, bad)
            self.assertIn("invalid site name", p.stdout + p.stderr, bad)
        self.assertFalse(self.mirror.exists())
        self.assertFalse((self.base / "x").exists())

    def test_bad_name_does_not_stop_other_sites_from_being_reported(self):
        self.write_sites({"name": "../x", "fetcher": "fetchers/a.py"},
                         {"name": "ok", "fetcher": "fetchers/missing.py"})
        p = self.cli()
        self.assertIn("invalid site name", p.stdout)
        self.assertIn("[ok]", p.stdout)


class LimitArg(Tmp):
    def test_limit_below_one_rejected_by_both_clis(self):
        self.write_sites()
        for v in ("0", "-1", "x"):
            p = self.cli("--limit", v)
            self.assertEqual(p.returncode, 2, v)
            self.assertIn("--limit", p.stderr)
            q = subprocess.run([sys.executable, str(ONBOARD), "--data-dir", str(self.data),
                                "--limit", v], capture_output=True, text=True)
            self.assertEqual(q.returncode, 2, v)

    def test_positive_limit_still_accepted(self):
        self.write_sites({"name": "w", "fetcher": "fetchers/none.py"})
        self.assertEqual(self.cli("--limit", "1").returncode, 1)  # fails on missing script only


class CustomFetcherRules(Tmp):
    def test_hung_fetcher_times_out_and_fails_that_site(self):
        (self.data / "fetchers").mkdir()
        (self.data / "fetchers" / "hang.py").write_text("import time\ntime.sleep(60)\n")
        with mock.patch.object(f, "CUSTOM_FETCHER_TIMEOUT", 1):
            ok, lines = f.run_custom({"name": "h", "fetcher": "fetchers/hang.py"},
                                     str(self.data), str(self.mirror), 0, 5, None)
        self.assertFalse(ok)
        self.assertIn("timed out", "\n".join(lines))

    def test_fetcher_outside_fetchers_folder_rejected(self):
        (self.data / "custom").mkdir()
        (self.data / "custom" / "x.py").write_text("print('hi')\n")
        ok, lines = f.run_custom({"name": "t", "fetcher": "custom/x.py"},
                                 str(self.data), str(self.mirror), 0, 5, None)
        self.assertFalse(ok)
        self.assertIn("must live under fetchers/", "\n".join(lines))


class OnboardCheckOnly(Tmp):
    def run_check(self):
        return subprocess.run([sys.executable, str(ONBOARD), "--data-dir", str(self.data),
                               "--check-only"], capture_output=True, text=True)

    def test_missing_sites_json_is_one_plain_line(self):
        p = self.run_check()
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("Traceback", p.stderr + p.stdout)
        self.assertIn("sites.json", p.stdout + p.stderr)

    def test_corrupt_sites_json_is_one_plain_line(self):
        (self.data / "sites.json").write_text("{not json", encoding="utf-8")
        p = self.run_check()
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("Traceback", p.stderr + p.stdout)
        self.assertIn("sites.json", p.stdout + p.stderr)


class NewStudyCleanup(Tmp):
    def test_failure_midway_cleans_up_and_retry_works(self):
        parent = self.base / "studies"
        real = open

        def boom(path, *a, **k):
            mode = a[0] if a else k.get("mode", "r")
            if str(path).endswith("MISSION.md") and "w" in mode:
                raise PermissionError("denied")
            return real(path, *a, **k)

        with mock.patch("builtins.open", boom):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = new_study.main(["--data-dir", str(self.data), "--name", "s",
                                       "--parent", str(parent)])
        self.assertEqual(code, 1)
        self.assertIn("ERROR", err.getvalue())
        self.assertFalse((parent / "s").exists())
        self.assertFalse((parent / "s-practice").exists())
        self.assertEqual(new_study.main(["--data-dir", str(self.data), "--name", "s",
                                         "--parent", str(parent)]), 0)

    def test_preexisting_folders_are_not_removed_on_refusal(self):
        parent = self.base / "studies"
        (parent / "s").mkdir(parents=True)
        (parent / "s" / "mine.txt").write_text("keep")
        with self.assertRaises(FileExistsError):
            new_study.create(str(self.data), "s", str(parent))
        self.assertTrue((parent / "s" / "mine.txt").exists())


class SkillText(unittest.TestCase):
    def text(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_no_bare_python_commands_in_skills(self):
        for name in ("onboarding", "add-docs", "new-study", "read-the-docs"):
            body = self.text("skills/%s/SKILL.md" % name)
            self.assertIn("python3", body, name)
            self.assertNotRegex(body, r'(?m)^\s*python "', name)

    def test_refresh_allows_powershell(self):
        head = self.text("commands/refresh.md").split("---")[1]
        self.assertRegex(head, r"allowed-tools:.*PowerShell")

    def test_read_the_docs_glob_fallback_and_read_before_cite(self):
        body = self.text("skills/read-the-docs/SKILL.md")
        self.assertIn("<mirror>/*`", body)
        self.assertIn("gemini-api/INDEX.md", body)
        self.assertIn("A Grep hit is a pointer,\n   never a citation", body)

    def test_add_docs_requires_fetchers_folder(self):
        self.assertIn("under `fetchers/`", self.text("skills/add-docs/SKILL.md"))

    def test_example_links_operator_okf_url(self):
        body = self.text("examples/find-session-lesson/README.md")
        self.assertIn("GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md", body)
        self.assertNotIn("open-knowledge-format", body)


if __name__ == "__main__":
    unittest.main()
