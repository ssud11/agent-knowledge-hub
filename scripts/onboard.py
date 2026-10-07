#!/usr/bin/env python3
"""Onboarding helper: save the mirror folder, seed sites.json, run a dry run.

Usage:
  python scripts/onboard.py --data-dir DIR [--mirror-dir DIR] [--limit N]
      [--dry-run-url URL]

1. Saves the mirror folder as the one line of <data-dir>/mirror-dir.txt (the fetcher and
   read-the-docs both read it). Default folder: ~/agent-knowledge-hub-mirror.
2. Seeds <data-dir>/sites.json from the repo template, and adds the Gemini entry if an
   existing file lacks it. Other entries are never touched.
3. Dry run: fetches the first N pages (default 3) of every site into a throwaway folder
   (the real mirror is not touched) and checks that real markdown pages landed.
   --dry-run-url replaces every site's llms.txt URL for the dry run only (used to test the
   failure path with an unreachable address).
Exit code 0 only when the dry run passed. The choice is saved even when it fails.
Standard library only.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FETCHER = os.path.join(ROOT, "fetchers", "llms_txt_fetcher.py")
TEMPLATE = os.path.join(ROOT, "sites.json")
GEMINI = "gemini-api"


def default_mirror_dir():
    return os.path.join(os.path.expanduser("~"), "agent-knowledge-hub-mirror")


def save_choice(data_dir, mirror_dir):
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "mirror-dir.txt")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(mirror_dir + "\n")
    return path


def seed_sites(data_dir):
    """Create sites.json from the template, or add the Gemini entry if it is missing."""
    dest = os.path.join(data_dir, "sites.json")
    with open(TEMPLATE, encoding="utf-8") as fh:
        template = json.load(fh)
    if not os.path.exists(dest):
        shutil.copyfile(TEMPLATE, dest)
        return dest, "created from template"
    with open(dest, encoding="utf-8") as fh:
        current = json.load(fh)
    sites = current.setdefault("sites", [])
    if any(s.get("name") == GEMINI for s in sites):
        return dest, "kept (Gemini entry present)"
    sites.extend(s for s in template["sites"] if s["name"] == GEMINI)
    with open(dest, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(current, fh, indent=2)
        fh.write("\n")
    return dest, "Gemini entry added"


def _md_pages(root):
    pages, bad = [], []
    for dp, _, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".md") or fn == "INDEX.md":
                continue
            full = os.path.join(dp, fn)
            with open(full, "rb") as fh:
                head = fh.read(512).lstrip().lower()
            if not head or head.startswith((b"<!doctype", b"<html")):
                bad.append(full)
            else:
                pages.append(full)
    return pages, bad


def dry_run(data_dir, limit=3, dry_run_url=None):
    lines = []
    scratch = tempfile.mkdtemp(prefix="akh-dryrun-")
    try:
        with open(os.path.join(data_dir, "sites.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
        if dry_run_url:
            for s in cfg["sites"]:
                s["llms_txt"] = dry_run_url
        ddir = os.path.join(scratch, "data")
        os.makedirs(ddir)
        with open(os.path.join(ddir, "sites.json"), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        mdir = os.path.join(scratch, "mirror")
        proc = subprocess.run(
            [sys.executable, FETCHER, "--data-dir", ddir, "--mirror-dir", mdir,
             "--limit", str(limit), "--delay", "0", "--timeout", "20"],
            capture_output=True, text=True)
        lines.append("dry run fetch output:")
        lines.extend("  " + l for l in (proc.stdout + proc.stderr).strip().splitlines())
        pages, bad = _md_pages(mdir) if os.path.isdir(mdir) else ([], [])
        problems = []
        if proc.returncode != 0:
            problems.append("fetcher exited with code %d" % proc.returncode)
        if bad:
            problems.append("%d page(s) empty or HTML instead of markdown" % len(bad))
        if not pages:
            problems.append("no markdown pages landed")
        if problems:
            lines.append("DRY RUN FAILED: " + "; ".join(problems))
            return False, lines
        lines.append("DRY RUN PASSED: %d markdown page(s) landed (test copy discarded; "
                     "real mirror untouched)" % len(pages))
        return True, lines
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def run(data_dir, mirror_dir=None, limit=3, dry_run_url=None):
    lines = []
    mirror_dir = os.path.abspath(os.path.expanduser(mirror_dir)) if mirror_dir \
        else default_mirror_dir()
    path = save_choice(data_dir, mirror_dir)
    lines.append("saved mirror folder: %s -> %s" % (mirror_dir, path))
    dest, what = seed_sites(data_dir)
    lines.append("sites file: %s (%s)" % (dest, what))
    ok, dlines = dry_run(data_dir, limit, dry_run_url)
    return ok, lines + dlines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=os.environ.get("CLAUDE_PLUGIN_DATA"))
    ap.add_argument("--mirror-dir", default=None,
                    help="default: ~/agent-knowledge-hub-mirror")
    ap.add_argument("--limit", type=int, default=3, help="pages per site for the dry run")
    ap.add_argument("--dry-run-url", default=None,
                    help="override every site's llms.txt URL for the dry run only")
    a = ap.parse_args(argv)
    if not a.data_dir:
        ap.error("--data-dir is required (or set CLAUDE_PLUGIN_DATA)")
    ok, lines = run(a.data_dir, a.mirror_dir, a.limit, a.dry_run_url)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
