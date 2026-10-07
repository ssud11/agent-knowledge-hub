#!/usr/bin/env python3
"""Mirror documentation sites that publish an llms.txt index.

Usage:
  python fetchers/llms_txt_fetcher.py --data-dir DIR [--mirror-dir DIR]
      [--delay SECONDS] [--timeout SECONDS] [--allow-mass-removal]

DIR (--data-dir) holds sites.json (seeded from the repo template if missing).
Pages are written to <mirror-dir>/<site>/, with INDEX.md and CHANGES.txt.
Standard library only.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "agent-knowledge-hub-fetcher/0.1 (documentation mirror; stdlib urllib)"
LINK_RE = re.compile(
    r"^\s*-\s+(?:\[(?P<title>.*?)\])?\((?P<url>https?://\S+?)\)(?::\s*(?P<desc>.*))?$")
RESERVED = {"INDEX.md"}
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
        parts = [s for s in p.split("/") if s not in ("", ".", "..")]
        slugs[u] = "/".join(parts) or "index"
    allslugs = set(slugs.values())
    out = {}
    for u, s in slugs.items():
        if any(o.startswith(s + "/") for o in allslugs):
            out[u] = s + "/index.md"
        else:
            out[u] = s + ".md"
    return out


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


def _atomic_write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def mirror_site(site, mirror_dir, delay, timeout, allow_mass_removal):
    name = site["name"]
    root = os.path.join(mirror_dir, name)
    lines = []

    def say(s):
        lines.append(s)

    try:
        text = http_get(site["llms_txt"], timeout).decode("utf-8")
    except Exception as e:
        say("[%s] ABORT: could not fetch llms.txt (%s); mirror untouched" % (name, e))
        return False, lines
    entries = parse_llms_txt(text)
    if not entries:
        say("[%s] ABORT: llms.txt listed no links; mirror untouched" % name)
        return False, lines
    paths = local_paths([e["url"] for e in entries], site["llms_txt"])
    seen, uniq = set(), []
    for e in entries:
        if e["url"] not in seen:
            seen.add(e["url"])
            uniq.append(e)
    entries = uniq
    wanted = {paths[e["url"]] for e in entries}
    existing = _scan(root) if os.path.isdir(root) else {}
    gone = sorted(set(existing) - wanted)
    if existing and len(gone) * 2 > len(existing) and not allow_mass_removal:
        say("[%s] ABORT: %d of %d existing pages would be removed; no changes made "
            "(use --allow-mass-removal to override)" % (name, len(gone), len(existing)))
        return False, lines

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
        dest = os.path.join(root, *rel.split("/"))
        if rel not in existing:
            added.append(rel)
        elif existing[rel] != sha(body):
            changed.append(rel)
        else:
            continue
        _atomic_write(dest, body)

    for rel in gone:
        os.remove(os.path.join(root, *rel.split("/")))
    for dp, dn, fn in os.walk(root, topdown=False):
        if dp != root and not os.listdir(dp):
            os.rmdir(dp)

    idx = ["# %s index" % site.get("title", name), ""]
    for e in entries:
        rel = paths[e["url"]]
        title = e["title"] or rel.rsplit("/", 1)[-1][:-3]
        idx.append("- [%s](%s): %s" % (title, rel, e["desc"]))
    _atomic_write(os.path.join(root, "INDEX.md"), ("\n".join(idx) + "\n").encode("utf-8"))

    pages = len(_scan(root))
    say("[%s] added: %d, changed: %d, removed: %d" % (name, len(added), len(changed), len(gone)))
    say("[%s] pages: %d, failed: %d" % (name, pages, len(failed)))
    for label, items in (("added", added), ("changed", changed), ("removed", gone)):
        for rel in items:
            say("  %s %s" % (label, rel))
    for rel, why in failed:
        say("  FAILED %s (old copy kept if present): %s" % (rel, why))
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    _atomic_write(os.path.join(root, "CHANGES.txt"),
                  ("run: %s\n" % stamp + "\n".join(lines) + "\n").encode("utf-8"))
    return True, lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=os.environ.get("CLAUDE_PLUGIN_DATA"),
                    help="folder holding sites.json (fallback: $CLAUDE_PLUGIN_DATA)")
    ap.add_argument("--mirror-dir",
                    default=os.path.join(os.path.expanduser("~"), "agent-knowledge-hub-mirror"))
    ap.add_argument("--delay", type=float, default=0.3, help="seconds between requests")
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--allow-mass-removal", action="store_true")
    a = ap.parse_args(argv)
    if not a.data_dir:
        ap.error("--data-dir is required (or set CLAUDE_PLUGIN_DATA)")
    with open(seed_sites_json(a.data_dir), encoding="utf-8") as fh:
        sites = json.load(fh)["sites"]
    ok_all = True
    for site in sites:
        ok, lines = mirror_site(site, a.mirror_dir, a.delay, a.timeout, a.allow_mass_removal)
        print("\n".join(lines))
        ok_all = ok_all and ok
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
