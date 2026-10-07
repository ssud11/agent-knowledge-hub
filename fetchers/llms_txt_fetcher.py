#!/usr/bin/env python3
"""Mirror documentation sites that publish an llms.txt index.

Usage:
  python fetchers/llms_txt_fetcher.py --data-dir DIR [--mirror-dir DIR]
      [--delay SECONDS] [--timeout SECONDS] [--allow-mass-removal] [--limit N]

DIR (--data-dir) holds sites.json (seeded from the repo template if missing).
--mirror-dir defaults to the first line of <data-dir>/mirror-dir.txt when that
file exists, else ~/agent-knowledge-hub-mirror.
Pages are written to <mirror-dir>/<site>/, with INDEX.md and CHANGES.txt.
Pages on a different host than the llms.txt are skipped (reported, not failed).
--limit N fetches only the first N pages of each site and deletes nothing
(used by onboarding's dry run; point it at a throwaway --mirror-dir).
A sites entry with a "fetcher" key (a script path relative to DIR, e.g. "fetchers/x.py") is
not an llms.txt site: it is run as
  python <DIR>/<fetcher> --site NAME --data-dir DIR --mirror-dir DIR --limit N --delay S --timeout S
and must write pages to <mirror-dir>/NAME/ and exit non-zero on failure (see the add-docs skill).
Exit code is non-zero if any site aborted or any page failed to fetch.
Standard library only.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "agent-knowledge-hub-fetcher/0.1 (documentation mirror; stdlib urllib)"
LINK_RE = re.compile(
    r"^\s*-\s+(?:\[(?P<title>.*?)\])?\((?P<url>https?://\S+?)\)(?::\s*(?P<desc>.*))?$")
SEP_RE = re.compile(r"[/\\]")
RESERVED = {"INDEX.md"}
SITE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
CUSTOM_FETCHER_DIR = "fetchers"
CUSTOM_FETCHER_TIMEOUT = 30 * 60  # seconds a written fetcher may run per site
TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "sites.json")


def parse_llms_txt(text):
    out = []
    for line in text.splitlines():
        m = LINK_RE.match(line)
        if m:
            out.append({"title": (m.group("title") or "").strip(),
                        "url": m.group("url"),
                        "desc": (m.group("desc") or "").strip()})
    return out


def local_paths(urls, llms_url):
    """Map page URLs to safe relative mirror paths (forward slashes)."""
    first = urllib.parse.urlparse(llms_url).path.strip("/").split("/")[0]
    prefix = "/" + first + "/" if first else "/"
    slugs = {}
    for u in urls:
        p = urllib.parse.unquote(urllib.parse.urlparse(u).path)
        if p.startswith(prefix):
            p = p[len(prefix):]
        p = p.lstrip("/")
        for suf in (".md.txt", ".md", ".txt"):
            if p.endswith(suf):
                p = p[:-len(suf)]
                break
        parts = [s for s in SEP_RE.split(p)
                 if s not in ("", ".", "..") and ":" not in s]
        slugs[u] = "/".join(parts) or "index"
    allslugs = set(slugs.values())
    out = {}
    used = {r.lower() for r in RESERVED}  # INDEX.md is ours, even on case-insensitive disks
    for u, s in slugs.items():
        if any(o.startswith(s + "/") for o in allslugs):
            rel = s + "/index.md"
        else:
            rel = s + ".md"
        n = 1
        base = rel[:-3]
        while rel.lower() in used:
            n += 1
            rel = "%s-%d.md" % (base, n)
        used.add(rel.lower())
        out[u] = rel
    return out


def safe_join(root, rel):
    """Join rel under root; raise ValueError if the result leaves root."""
    rroot = os.path.realpath(root)
    full = os.path.realpath(os.path.join(rroot, *SEP_RE.split(rel)))
    if full != rroot and not full.startswith(rroot + os.sep):
        raise ValueError("path escapes site folder: %r" % rel)
    return full


def default_mirror_dir():
    return os.path.join(os.path.expanduser("~"), "agent-knowledge-hub-mirror")


def read_mirror_dir(data_dir):
    """The one place that resolves the saved mirror folder.

    First line of <data_dir>/mirror-dir.txt (BOM tolerated), stripped, ~ expanded, made
    absolute; else the default folder.
    """
    try:
        with open(os.path.join(data_dir, "mirror-dir.txt"), encoding="utf-8-sig") as fh:
            first = fh.readline().strip()
        if first:
            return os.path.abspath(os.path.expanduser(first))
    except OSError:
        pass
    return default_mirror_dir()


def resolve_mirror_dir(data_dir, explicit):
    return explicit if explicit else read_mirror_dir(data_dir)


def positive_int(text):
    try:
        n = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a whole number of 1 or more: %r" % text)
    if n < 1:
        raise argparse.ArgumentTypeError("must be 1 or more: %r" % text)
    return n


def sha(data):
    return hashlib.sha256(data).hexdigest()


def http_get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def seed_sites_json(data_dir):
    os.makedirs(data_dir, exist_ok=True)
    dest = os.path.join(data_dir, "sites.json")
    if not os.path.exists(dest):
        shutil.copyfile(TEMPLATE, dest)
    return dest


def _scan(root):
    found = {}
    for dp, _, files in os.walk(root):
        for fn in files:
            rel = os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, "/")
            if rel.endswith(".md") and rel not in RESERVED:
                with open(os.path.join(dp, fn), "rb") as fh:
                    found[rel] = sha(fh.read())
    return found


def _atomic_write(path, data, root=None):
    if root is not None:
        path = safe_join(root, os.path.relpath(path, root))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def mirror_site(site, mirror_dir, delay, timeout, allow_mass_removal, limit=None):
    name = site["name"]
    root = os.path.join(mirror_dir, name)
    lines = []

    def say(s):
        lines.append(s)

    def abort(msg):
        say(msg)
        if os.path.isdir(root):
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            _atomic_write(os.path.join(root, "CHANGES.txt"),
                          ("run: %s\n" % stamp + "\n".join(lines) + "\n").encode("utf-8"),
                          root)
        return False, lines

    try:
        text = http_get(site["llms_txt"], timeout).decode("utf-8")
    except Exception as e:
        return abort("[%s] ABORT: could not fetch llms.txt (%s); mirror untouched" % (name, e))
    entries = parse_llms_txt(text)
    if not entries:
        return abort("[%s] ABORT: llms.txt listed no links; mirror untouched" % name)
    host = urllib.parse.urlparse(site["llms_txt"]).netloc.lower()
    seen, uniq, skipped = set(), [], []
    for e in entries:
        if e["url"] in seen:
            continue
        seen.add(e["url"])
        if urllib.parse.urlparse(e["url"]).netloc.lower() != host:
            skipped.append(e["url"])
        else:
            uniq.append(e)
    entries = uniq[:limit] if limit else uniq
    paths = local_paths([e["url"] for e in entries], site["llms_txt"])
    wanted = {paths[e["url"]] for e in entries}
    existing = _scan(root) if os.path.isdir(root) else {}
    gone = [] if limit else sorted(set(existing) - wanted)
    if existing and len(gone) * 2 > len(existing) and not allow_mass_removal:
        return abort("[%s] ABORT: %d of %d existing pages would be removed; no changes made "
                     "(use --allow-mass-removal to override)" % (name, len(gone), len(existing)))

    added, changed, failed = [], [], []
    for i, e in enumerate(entries):
        rel = paths[e["url"]]
        if i and delay:
            time.sleep(delay)
        try:
            body = http_get(e["url"], timeout)
            if not body.strip():
                raise ValueError("empty body")
        except Exception as ex:
            failed.append((rel, str(ex)))
            continue
        try:
            dest = safe_join(root, rel)
        except ValueError as ex:
            failed.append((rel, str(ex)))
            continue
        if rel not in existing:
            added.append(rel)
        elif existing[rel] != sha(body):
            changed.append(rel)
        else:
            continue
        _atomic_write(dest, body, root)

    for rel in gone:
        os.remove(safe_join(root, rel))
    for dp, dn, fn in os.walk(root, topdown=False):
        if dp != root and not os.listdir(dp):
            os.rmdir(dp)

    idx = ["# %s index" % site.get("title", name), ""]
    for e in entries:
        rel = paths[e["url"]]
        title = e["title"] or rel.rsplit("/", 1)[-1][:-3]
        idx.append("- [%s](%s): %s" % (title, rel, e["desc"]))
    _atomic_write(os.path.join(root, "INDEX.md"), ("\n".join(idx) + "\n").encode("utf-8"),
                  root)

    pages = len(_scan(root))
    say("[%s] added: %d, changed: %d, removed: %d" % (name, len(added), len(changed), len(gone)))
    say("[%s] pages: %d, failed: %d, skipped: %d" % (name, pages, len(failed), len(skipped)))
    for label, items in (("added", added), ("changed", changed), ("removed", gone)):
        for rel in items:
            say("  %s %s" % (label, rel))
    for url in skipped:
        say("  SKIPPED off-host %s" % url)
    for rel, why in failed:
        say("  FAILED %s (old copy kept if present): %s" % (rel, why))
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    _atomic_write(os.path.join(root, "CHANGES.txt"),
                  ("run: %s\n" % stamp + "\n".join(lines) + "\n").encode("utf-8"), root)
    return not failed, lines


def run_custom(site, data_dir, mirror_dir, delay, timeout, limit):
    """Run a written fetcher kept in the data folder. Returns (ok, lines)."""
    name = site["name"]
    try:
        script = safe_join(data_dir, site["fetcher"])
    except ValueError:
        return False, ["[%s] ABORT: fetcher path %r is outside the data folder" %
                       (name, site["fetcher"])]
    try:
        inside = safe_join(data_dir, CUSTOM_FETCHER_DIR)
    except ValueError:
        inside = None
    if inside is None or not script.startswith(inside + os.sep):
        return False, ["[%s] ABORT: fetcher %r must live under %s/ in the data folder" %
                       (name, site["fetcher"], CUSTOM_FETCHER_DIR)]
    if not os.path.isfile(script):
        return False, ["[%s] ABORT: fetcher script not found: %s" % (name, script)]
    cmd = [sys.executable, script, "--site", name, "--data-dir", data_dir,
           "--mirror-dir", mirror_dir, "--delay", str(delay), "--timeout", str(timeout)]
    if limit:
        cmd += ["--limit", str(limit)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=CUSTOM_FETCHER_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, ["[%s] FAILED: fetcher timed out after %d seconds" %
                       (name, CUSTOM_FETCHER_TIMEOUT)]
    lines = (proc.stdout + proc.stderr).strip().splitlines()
    if proc.returncode != 0:
        lines.append("[%s] FAILED: fetcher exited with code %d" % (name, proc.returncode))
    return proc.returncode == 0, lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=os.environ.get("CLAUDE_PLUGIN_DATA"),
                    help="folder holding sites.json (fallback: $CLAUDE_PLUGIN_DATA)")
    ap.add_argument("--mirror-dir", default=None,
                    help="default: first line of <data-dir>/mirror-dir.txt, "
                         "else ~/agent-knowledge-hub-mirror")
    ap.add_argument("--delay", type=float, default=0.3, help="seconds between requests")
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--allow-mass-removal", action="store_true")
    ap.add_argument("--limit", type=positive_int, default=None,
                    help="fetch only the first N pages per site; removes nothing")
    a = ap.parse_args(argv)
    if not a.data_dir:
        ap.error("--data-dir is required (or set CLAUDE_PLUGIN_DATA)")
    a.mirror_dir = resolve_mirror_dir(a.data_dir, a.mirror_dir)
    with open(seed_sites_json(a.data_dir), encoding="utf-8") as fh:
        sites = json.load(fh)["sites"]
    ok_all = True
    for site in sites:
        name = site.get("name")
        if not isinstance(name, str) or not SITE_NAME_RE.match(name) or name.endswith("."):
            print("[%s] FAILED: invalid site name (use letters, digits, '.', '_' or '-'); "
                  "site skipped" % (name,))
            ok_all = False
            continue
        if site.get("fetcher"):
            ok, lines = run_custom(site, a.data_dir, a.mirror_dir, a.delay, a.timeout, a.limit)
        else:
            ok, lines = mirror_site(site, a.mirror_dir, a.delay, a.timeout,
                                    a.allow_mass_removal, a.limit)
        print("\n".join(lines))
        ok_all = ok_all and ok
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
