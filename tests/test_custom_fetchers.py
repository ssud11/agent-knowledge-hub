"""A sites entry with a "fetcher" key is run by the shipped fetcher (refresh needs no change)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FETCHER = ROOT / "fetchers" / "llms_txt_fetcher.py"

STUB = '''import argparse, os, sys
ap = argparse.ArgumentParser()
ap.add_argument("--site"); ap.add_argument("--data-dir"); ap.add_argument("--mirror-dir")
ap.add_argument("--limit", type=int); ap.add_argument("--delay"); ap.add_argument("--timeout")
a = ap.parse_args()
d = os.path.join(a.mirror_dir, a.site)
os.makedirs(d, exist_ok=True)
open(os.path.join(d, "page.md"), "w").write("# stub page for %s limit=%s" % (a.site, a.limit))
print("[%s] added: 1, changed: 0, removed: 0" % a.site)
sys.exit(int(os.environ.get("STUB_EXIT", "0")))
'''


class CustomFetcher(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "data")
        self.mirror = os.path.join(self.tmp.name, "mirror")
        os.makedirs(os.path.join(self.data, "fetchers"))
        Path(self.data, "fetchers", "stub.py").write_text(STUB, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def sites(self, entry):
        Path(self.data, "sites.json").write_text(json.dumps({"sites": [entry]}), encoding="utf-8")

    def run_fetcher(self, *extra, env=None):
        e = dict(os.environ, **(env or {}))
        return subprocess.run([sys.executable, str(FETCHER), "--data-dir", self.data,
                               "--mirror-dir", self.mirror, *extra],
                              capture_output=True, text=True, env=e)

    def test_site_with_fetcher_key_runs_that_script(self):
        self.sites({"name": "tool", "fetcher": "fetchers/stub.py"})
        p = self.run_fetcher("--limit", "2")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("[tool] added: 1", p.stdout)
        self.assertEqual(Path(self.mirror, "tool", "page.md").read_text(),
                         "# stub page for tool limit=2")

    def test_failing_custom_fetcher_makes_run_fail(self):
        self.sites({"name": "tool", "fetcher": "fetchers/stub.py"})
        p = self.run_fetcher(env={"STUB_EXIT": "1"})
        self.assertNotEqual(p.returncode, 0)

    def test_missing_script_fails_plainly(self):
        self.sites({"name": "tool", "fetcher": "fetchers/nope.py"})
        p = self.run_fetcher()
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("not found", p.stdout + p.stderr)

    def test_script_outside_data_folder_refused(self):
        self.sites({"name": "tool", "fetcher": "../outside.py"})
        p = self.run_fetcher()
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("outside", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
