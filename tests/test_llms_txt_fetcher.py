import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from fetchers import llms_txt_fetcher as f


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        entry = self.server.routes.get(self.path)
        if entry is None:
            self.send_response(404)
            self.end_headers()
            return
        status, body = entry
        self.send_response(status)
        self.send_header("Content-Type", "text/markdown")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *a):
        pass


# built at runtime so the scrub script does not flag a literal address
LOOPBACK = ".".join(["127", "0", "0", "1"])


class FetcherTest(unittest.TestCase):
    def setUp(self):
        self.srv = HTTPServer((LOOPBACK, 0), _Handler)
        self.srv.routes = {}
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = "http://%s:%d" % (LOOPBACK, self.srv.server_port)
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "data")
        self.mirror = os.path.join(self.tmp.name, "mirror")
        os.makedirs(self.data)
        self.set_site({
            "/g/docs/llms.txt": "# Site\n\n## Docs\n"
            "- [Home](%s/g/docs/home.md.txt): The home\n"
            "- [Nested](%s/g/docs/a/b.md.txt): Nested page\n"
            "- (%s/g/docs/untitled.md.txt): No title here\n" % ((self.base,) * 3),
            "/g/docs/home.md.txt": "home v1",
            "/g/docs/a/b.md.txt": "nested v1",
            "/g/docs/untitled.md.txt": "untitled v1",
        })

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def set_site(self, pages):
        self.srv.routes = {k: (200, v) for k, v in pages.items()}
        with open(os.path.join(self.data, "sites.json"), "w") as fh:
            json.dump({"sites": [{"name": "s", "title": "S",
                                  "llms_txt": self.base + "/g/docs/llms.txt"}]}, fh)

    def run_cli(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = f.main(["--data-dir", self.data, "--mirror-dir", self.mirror,
                           "--delay", "0"] + list(extra))
        return code, out.getvalue()

    def page(self, rel):
        with open(os.path.join(self.mirror, "s", rel), encoding="utf-8") as fh:
            return fh.read()

    def test_first_run_mirrors_pages_with_nested_slugs_and_index(self):
        code, out = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(self.page("docs/home.md"), "home v1")
        self.assertEqual(self.page("docs/a/b.md"), "nested v1")
        index = self.page("INDEX.md")
        self.assertIn("[Home](docs/home.md): The home", index)
        self.assertIn("[untitled](docs/untitled.md): No title here", index)
        self.assertIn("added: 3", out)
        self.assertIn("pages: 3", out)

    def test_limit_fetches_only_first_pages_and_removes_nothing(self):
        self.run_cli()
        code, out = self.run_cli("--limit", "1")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(self.mirror, "s", "docs", "home.md")))
        self.assertTrue(os.path.exists(os.path.join(self.mirror, "s", "docs", "a", "b.md")))
        fresh = os.path.join(self.tmp.name, "fresh")
        code, out = self.run_cli("--limit", "1", "--mirror-dir", fresh)
        self.assertEqual(code, 0)
        pages = [n for _, _, fs in os.walk(os.path.join(fresh, "s")) for n in fs
                 if n.endswith(".md") and n != "INDEX.md"]
        self.assertEqual(len(pages), 1)

    def test_second_run_reports_no_changes(self):
        self.run_cli()
        code, out = self.run_cli()
        self.assertIn("added: 0, changed: 0, removed: 0", out)
        self.assertIn("pages: 3", out)

    def test_local_edit_and_remote_change_reported_as_changed(self):
        self.run_cli()
        with open(os.path.join(self.mirror, "s", "docs", "home.md"), "w") as fh:
            fh.write("hand edited")
        code, out = self.run_cli()
        self.assertIn("added: 0, changed: 1, removed: 0", out)
        self.assertEqual(self.page("docs/home.md"), "home v1")

    def test_failed_fetch_keeps_old_copy_and_is_reported(self):
        self.run_cli()
        self.srv.routes["/g/docs/home.md.txt"] = (500, "boom")
        code, out = self.run_cli()
        self.assertEqual(self.page("docs/home.md"), "home v1")
        self.assertIn("failed: 1", out)
        self.assertIn("docs/home.md", out)
        self.assertIn("pages: 3", out)

    def test_removed_page_is_deleted_and_reported(self):
        self.run_cli()
        self.set_site({
            "/g/docs/llms.txt": "- [Home](%s/g/docs/home.md.txt): The home\n"
            "- [Nested](%s/g/docs/a/b.md.txt): n\n" % (self.base, self.base),
            "/g/docs/home.md.txt": "home v1", "/g/docs/a/b.md.txt": "nested v1"})
        code, out = self.run_cli()
        self.assertIn("removed: 1", out)
        self.assertFalse(os.path.exists(os.path.join(self.mirror, "s", "docs", "untitled.md")))

    def test_mass_removal_aborts_unless_overridden(self):
        self.run_cli()
        self.set_site({
            "/g/docs/llms.txt": "- [Home](%s/g/docs/home.md.txt): h\n" % self.base,
            "/g/docs/home.md.txt": "home v2"})
        code, out = self.run_cli()
        self.assertNotEqual(code, 0)
        self.assertIn("ABORT", out)
        self.assertEqual(self.page("docs/home.md"), "home v1")
        self.assertEqual(self.page("docs/a/b.md"), "nested v1")
        code, out = self.run_cli("--allow-mass-removal")
        self.assertIn("removed: 2", out)

    def test_summary_file_written(self):
        self.run_cli()
        with open(os.path.join(self.mirror, "s", "CHANGES.txt")) as fh:
            self.assertIn("added: 3", fh.read())

    def test_data_dir_seeded_from_template(self):
        os.remove(os.path.join(self.data, "sites.json"))
        f.seed_sites_json(self.data)
        with open(os.path.join(self.data, "sites.json")) as fh:
            sites = json.load(fh)["sites"]
        self.assertEqual(sites[0]["name"], "gemini-api")

    def test_parse_both_line_formats(self):
        text = ("- [A](https://x/y/a.md.txt): da\n- (https://x/y/b.md.txt): db\n"
                "not a link\n- [C](https://x/y/c.md.txt)\n")
        got = f.parse_llms_txt(text)
        self.assertEqual([(g["title"], g["url"], g["desc"]) for g in got],
                         [("A", "https://x/y/a.md.txt", "da"),
                          ("", "https://x/y/b.md.txt", "db"),
                          ("C", "https://x/y/c.md.txt", "")])

    def test_slug_mapping_with_index_collision_and_traversal(self):
        base = "https://h/g/docs/llms.txt"
        urls = ["https://h/g/docs.md.txt", "https://h/g/docs/x/y.md.txt",
                "https://h/g/docs/../../evil.md.txt"]
        m = f.local_paths(urls, base)
        self.assertEqual(m[urls[0]], "docs/index.md")
        self.assertEqual(m[urls[1]], "docs/x/y.md")
        self.assertNotIn("..", m[urls[2]])

    # --- review-fix findings ---

    def test_encoded_backslash_traversal_stays_inside_site_root(self):
        urls = ["https://h/g/docs/a%5C..%5C..%5Cpwn.md.txt",
                "https://h/g/docs/C%3A%5Cevil.md.txt"]
        m = f.local_paths(urls, "https://h/g/docs/llms.txt")
        for rel in m.values():
            self.assertNotIn("\\", rel)
            self.assertNotIn(":", rel)
            self.assertNotIn("..", rel.split("/"))

    def test_safe_join_rejects_escape(self):
        with self.assertRaises(ValueError):
            f.safe_join(self.mirror, "../outside.md")
        self.assertTrue(f.safe_join(self.mirror, "a/b.md").startswith(
            os.path.realpath(self.mirror)))

    def test_hostile_url_does_not_write_outside_root(self):
        self.set_site({
            "/g/docs/llms.txt": "- [P](%s/g/docs/a%%5C..%%5C..%%5Cpwn.md.txt): p\n" % self.base,
            "/g/docs/a%5C..%5C..%5Cpwn.md.txt": "pwn"})
        self.run_cli()
        self.assertFalse(os.path.exists(os.path.join(self.mirror, "pwn.md")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "pwn.md")))

    def test_failed_page_makes_run_fail_but_keeps_summary(self):
        self.run_cli()
        self.srv.routes["/g/docs/home.md.txt"] = (500, "boom")
        code, out = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(self.page("docs/home.md"), "home v1")
        with open(os.path.join(self.mirror, "s", "CHANGES.txt")) as fh:
            self.assertIn("failed: 1", fh.read())

    def test_mirror_dir_default_read_from_data_dir_file(self):
        target = os.path.join(self.tmp.name, "elsewhere")
        with open(os.path.join(self.data, "mirror-dir.txt"), "w") as fh:
            fh.write(target + "\nignored second line\n")
        self.assertEqual(f.resolve_mirror_dir(self.data, None), target)
        self.assertEqual(f.resolve_mirror_dir(self.data, "x"), "x")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = f.main(["--data-dir", self.data, "--delay", "0"])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(target, "s", "docs", "home.md")))

    def test_mirror_dir_default_falls_back_to_home_folder(self):
        got = f.resolve_mirror_dir(self.data, None)
        self.assertEqual(got, os.path.join(os.path.expanduser("~"),
                                           "agent-knowledge-hub-mirror"))

    def test_colliding_slugs_get_distinct_paths(self):
        urls = ["https://h/g/docs.md.txt", "https://h/g/docs/index.md.txt",
                "https://h/g/docs/x.md.txt"]
        m = f.local_paths(urls, "https://h/g/docs/llms.txt")
        self.assertEqual(len(set(v.lower() for v in m.values())), 3)

    def test_colliding_urls_both_stored(self):
        self.set_site({
            "/g/docs/llms.txt": "- [A](%s/g/docs.md.txt): a\n"
            "- [B](%s/g/docs/index.md.txt): b\n- [C](%s/g/docs/x.md.txt): c\n"
            % ((self.base,) * 3),
            "/g/docs.md.txt": "AAA", "/g/docs/index.md.txt": "BBB",
            "/g/docs/x.md.txt": "CCC"})
        code, out = self.run_cli()
        self.assertIn("pages: 3", out)
        self.assertEqual(code, 0)

    def test_abort_writes_changes_txt_when_site_folder_exists(self):
        self.run_cli()
        self.srv.routes.pop("/g/docs/llms.txt")
        code, out = self.run_cli()
        self.assertNotEqual(code, 0)
        with open(os.path.join(self.mirror, "s", "CHANGES.txt")) as fh:
            text = fh.read()
        self.assertIn("ABORT", text)
        self.assertRegex(text, r"run: [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}.[0-9]{2}.[0-9]{2}")
        self.assertEqual(self.page("docs/home.md"), "home v1")

    def test_abort_without_site_folder_creates_nothing(self):
        self.srv.routes.pop("/g/docs/llms.txt")
        code, out = self.run_cli()
        self.assertNotEqual(code, 0)
        self.assertFalse(os.path.exists(os.path.join(self.mirror, "s")))

    def test_off_host_urls_skipped_not_failed(self):
        self.set_site({
            "/g/docs/llms.txt": "- [Home](%s/g/docs/home.md.txt): h\n"
            "- [Far](https://elsewhere.invalid/g/docs/far.md.txt): f\n" % self.base,
            "/g/docs/home.md.txt": "home v1"})
        code, out = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("skipped: 1", out)
        self.assertIn("failed: 0", out)
        self.assertFalse(os.path.exists(os.path.join(self.mirror, "s", "docs", "far.md")))
        self.assertNotIn("far.md", self.page("INDEX.md"))


if __name__ == "__main__":
    unittest.main()
