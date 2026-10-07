#!/usr/bin/env python3
"""Fail if the repo contains anything on the never list.

Scans git-tracked files plus untracked, non-ignored files. Prints
file:line and the pattern NAME, never the matched text.

Layer 1: generic regexes below.
Layer 2: optional private terms, read from the file named by the
AKH_SCRUB_TERMS_FILE env var (one term per line, '#' comments, 're:'
prefix for a regex, otherwise a case-insensitive literal).

A line carrying the marker "scrub: allow" is skipped.
Exit codes: 0 clean, 1 hits, 2 setup error.
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ALLOW_MARKER = "scrub: allow"
OCT = r"(?:25[0-5]|2[0-4]\d|1?\d?\d)"

# Order matters: the first matching pattern name per line is reported.
LINE_PATTERNS = [
    ("tailscale-ip", r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b"),
    ("lan-ip", r"\b192\.168\.\d{1,3}\.\d{1,3}\b"),
    ("lan-ip", r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    ("lan-ip", r"\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b"),
    ("ipv4", r"\b(?:%s\.){3}%s\b" % (OCT, OCT)),
    ("ipv6-private", r"\bfd7a:115c:a1e0:[0-9a-f:]+"),
    ("ipv6-private", r"\bfe80:[0-9a-f:]+"),
    ("tailnet-hostname", r"\b[\w-]+\.ts\.net\b"),
    ("email", r"\b[\w.+-]+@(?!users\.noreply\.github\.com\b)[\w-]+(?:\.[\w-]+)+\b"),
    ("windows-path", r"\b[A-Za-z]:\\"),
    ("windows-path", r"\b[A-Za-z]:/(?:Users|Claude)"),
    ("windows-path", r"[\\]Users[\\][^\\\s]+"),
    ("unix-home-path", r"/home/[a-z_][\w-]*"),
    ("unix-home-path", r"/Users/[A-Za-z][\w.-]*"),
    ("cowork-projects", r"(?i)cowork\s+projects"),
    ("secret", r"\bsk-[A-Za-z0-9_-]{20,}"),
    ("secret", r"\bghp_[A-Za-z0-9]{30,}"),
    ("secret", r"github_pat_"),  # scrub: allow
    ("secret", r"\bAIza[0-9A-Za-z_-]{30,}"),
    ("secret", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("secret", r"\.kdbx\b"),  # scrub: allow
    ("scheduler", r"(?i)\b(?:systemd|schtasks|crontab|Register-ScheduledTask|Task Scheduler)\b|\.timer\b"),  # scrub: allow
]
COMPILED = [(n, re.compile(p)) for n, p in LINE_PATTERNS]


def list_files(root):
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root, capture_output=True, check=True).stdout
    names = sorted({n for n in out.decode("utf-8", "replace").split("\0") if n})
    return [n for n in names if (root / n).is_file()]


def path_hits(name):
    p = name.replace("\\", "/")
    hits = []
    if p.endswith(".md.txt"):
        hits.append("google-page-file")
    if p.startswith("skills/teach/") or "/skills/teach/" in p:
        hits.append("teach-skill")
    return hits


def load_terms():
    path = os.environ.get("AKH_SCRUB_TERMS_FILE")
    if not path:
        print("note: AKH_SCRUB_TERMS_FILE unset, generic checks only")
        return []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        print("error: AKH_SCRUB_TERMS_FILE is set but unreadable", file=sys.stderr)
        sys.exit(2)
    terms = []
    for raw in lines:
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        try:
            rx = re.compile(s[3:]) if s.startswith("re:") else re.compile(re.escape(s), re.I)
        except re.error:
            print("error: bad regex in terms file", file=sys.stderr)
            sys.exit(2)
        terms.append(rx)
    return terms


def scan(root, terms):
    hits = []
    for name in list_files(root):
        for h in path_hits(name):
            hits.append("%s:0: %s" % (name, h))
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if name.replace("\\", "/").endswith("SKILL.md") and re.search(
                r"(?m)^name:\s*teach\s*$", text):
            hits.append("%s:1: teach-skill" % name)
        for i, line in enumerate(text.splitlines(), 1):
            if ALLOW_MARKER in line:
                continue
            for pname, rx in COMPILED:
                if rx.search(line):
                    hits.append("%s:%d: %s" % (name, i, pname))
                    break
            for n, rx in enumerate(terms, 1):
                if rx.search(line):
                    hits.append("%s:%d: private-term #%d" % (name, i, n))
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    root = Path(ap.parse_args().root).resolve()
    terms = load_terms()
    try:
        hits = scan(root, terms)
    except (subprocess.CalledProcessError, OSError):
        print("error: could not list files (is this a git repo?)", file=sys.stderr)
        return 2
    for h in hits:
        print(h)
    if hits:
        print("scrub: FAIL (%d hit(s))" % len(hits))
        return 1
    print("scrub: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
