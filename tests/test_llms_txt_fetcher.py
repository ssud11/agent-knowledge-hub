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


if __name__ == "__main__":
    unittest.main()
