"""Onboarding helper: save choice, seed sites.json, dry run (real local HTTP server)."""
import json
import os
import tempfile
import threading
import unittest
from http.server import HTTPServer

from scripts import onboard
from tests.test_llms_txt_fetcher import LOOPBACK, _Handler


class OnboardTest(unittest.TestCase):
    def setUp(self):
        self.srv = HTTPServer((LOOPBACK, 0), _Handler)
        base = "http://%s:%d" % (LOOPBACK, self.srv.server_port)
        self.srv.routes = {
            "/g/docs/llms.txt": (200, "# S\n- [A](%s/g/docs/a.md.txt): a\n- [B](%s/g/docs/b.md.txt): b\n"
                                 % (base, base)),
            "/g/docs/a.md.txt": (200, "# A\nreal markdown"),
            "/g/docs/b.md.txt": (200, "# B\nmore"),
        }
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = base
        self.url = base + "/g/docs/llms.txt"
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "data")
        self.mirror = os.path.join(self.tmp.name, "my mirror")

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def sites(self):
        with open(os.path.join(self.data, "sites.json"), encoding="utf-8") as fh:
            return json.load(fh)["sites"]

    def test_fresh_setup_saves_choice_and_keeps_gemini(self):
        ok, lines = onboard.run(self.data, self.mirror, dry_run_url=self.url)
        self.assertTrue(ok, lines)
        with open(os.path.join(self.data, "mirror-dir.txt"), encoding="utf-8") as fh:
            self.assertEqual(fh.read().strip(), self.mirror)
        self.assertIn("gemini-api", [s["name"] for s in self.sites()])

    def test_existing_sites_kept_and_gemini_added_when_missing(self):
        os.makedirs(self.data)
        with open(os.path.join(self.data, "sites.json"), "w") as fh:
            json.dump({"sites": [{"name": "other", "title": "O", "llms_txt": "http://x/llms.txt"}]}, fh)
        onboard.run(self.data, self.mirror, dry_run_url=self.url)
        self.assertEqual([s["name"] for s in self.sites()], ["other", "gemini-api"])

    def test_dry_run_does_not_touch_real_mirror(self):
        onboard.run(self.data, self.mirror, dry_run_url=self.url)
        self.assertFalse(os.path.exists(self.mirror))

    def test_dry_run_reports_pages_landed(self):
        ok, lines = onboard.run(self.data, self.mirror, dry_run_url=self.url)
        self.assertTrue(ok)
        self.assertRegex("\n".join(lines), r"DRY RUN PASSED: 2 markdown page")

    def test_unreachable_url_reports_failure_plainly(self):
        ok, lines = onboard.run(self.data, self.mirror,
                                dry_run_url="http://%s:1/llms.txt" % LOOPBACK)
        self.assertFalse(ok)
        self.assertIn("DRY RUN FAILED", "\n".join(lines))

    def test_html_instead_of_markdown_fails(self):
        self.srv.routes["/g/docs/a.md.txt"] = (200, "<!doctype html><html></html>")
        self.srv.routes["/g/docs/b.md.txt"] = (200, "<html>x</html>")
        ok, lines = onboard.run(self.data, self.mirror, dry_run_url=self.url)
        self.assertFalse(ok)

    def test_choice_still_saved_when_dry_run_fails(self):
        onboard.run(self.data, self.mirror, dry_run_url="http://%s:1/llms.txt" % LOOPBACK)
        self.assertTrue(os.path.exists(os.path.join(self.data, "mirror-dir.txt")))


if __name__ == "__main__":
    unittest.main()
