#!/usr/bin/env python3
"""Fail if the repo contains anything on the never list.

Scans git-tracked files plus untracked, non-ignored files. Prints
file:line and the pattern NAME, never the matched text.

Layer 1: generic regexes below.
Layer 2: optional private terms, read from the file named by the
AKH_SCRUB_TERMS_FILE env var (one term per line, '#' comments, 're:'
prefix for a regex, otherwise a case-insensitive literal).

A line carrying the marker "scrub: allow" is skipped (files only).
Files are decoded as UTF-8, UTF-16 (BOM) or, failing that, with replacement
characters; only binary files (NUL bytes) are skipped, and listed by name.
Commit metadata (author/committer name and email, message) of unpushed commits
is scanned with the same patterns; noreply addresses are allowed. Range: commits
not on the upstream, all of HEAD without one, or <ref>..HEAD with --since-ref.
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


def decode_bytes(data):
    """Return text, or None for binary content. Never raises on bad bytes."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        if b"\0" in data:
            return None
        return data.decode("utf-8", errors="replace")


def scan_text(label, text, terms, hits, allow_marker=True):
    for i, line in enumerate(text.splitlines(), 1):
        if allow_marker and ALLOW_MARKER in line:
            continue
        for pname, rx in COMPILED:
            if rx.search(line):
                hits.append("%s:%d: %s" % (label, i, pname))
                break
        for n, rx in enumerate(terms, 1):
            if rx.search(line):
                hits.append("%s:%d: private-term #%d" % (label, i, n))


def scan(root, terms, skipped=None):
    hits = []
    if skipped is None:
        skipped = []
    for name in list_files(root):
        for h in path_hits(name):
            hits.append("%s:0: %s" % (name, h))
        try:
            data = (root / name).read_bytes()
        except OSError:
            skipped.append("%s (unreadable)" % name)
            continue
        text = decode_bytes(data)
        if text is None:
            skipped.append("%s (binary)" % name)
            continue
        if name.replace("\\", "/").endswith("SKILL.md") and re.search(
                r"(?m)^name:\s*teach\s*$", text):
            hits.append("%s:1: teach-skill" % name)
        scan_text(name, text, terms, hits)
    return hits


NOREPLY_RE = re.compile(r"(?i)\bnoreply@[\w.-]+")
COMMIT_FIELDS = ("author-name", "author-email", "committer-name",
                 "committer-email", "message")


def git_out(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True)


def commit_range(root, since_ref):
    """Return the rev-range to scan, or None when there are no commits."""
    if git_out(root, "rev-parse", "--verify", "-q", "HEAD").returncode != 0:
        return None
    if since_ref:
        if git_out(root, "rev-parse", "--verify", "-q",
                   since_ref + "^{commit}").returncode != 0:
            raise ValueError("unknown --since-ref")
        return since_ref + "..HEAD"
    if git_out(root, "rev-parse", "--verify", "-q", "@{u}").returncode == 0:
        return "@{u}..HEAD"
    return "HEAD"


def scan_commits(root, terms, since_ref=None):
    """Scan author/committer name+email and message of unpushed commits."""
    rng = commit_range(root, since_ref)
    if rng is None:
        return []
    out = git_out(root, "log", "--format=%h%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%B%x1e",
                  rng).stdout.decode("utf-8", "replace")
    hits = []
    for rec in out.split("\x1e"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        parts = rec.split("\x1f", 5)
        if len(parts) != 6:
            continue
        for field, value in zip(COMMIT_FIELDS, parts[1:]):
            text = NOREPLY_RE.sub("", value)
            sub = []
            scan_text("commit %s:%s" % (parts[0], field), text, terms, sub,
                      allow_marker=False)
            hits.extend(sub)
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--since-ref", default=None,
                    help="scan commit metadata in <ref>..HEAD (default: commits "
                         "not on the upstream, or all of HEAD when none)")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    terms = load_terms()
    skipped = []
    try:
        hits = scan(root, terms, skipped)
        hits += scan_commits(root, terms, args.since_ref)
    except ValueError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    except (subprocess.CalledProcessError, OSError):
        print("error: could not list files (is this a git repo?)", file=sys.stderr)
        return 2
    for s in skipped:
        print("skipped: %s" % s)
    for h in hits:
        print(h)
    if hits:
        print("scrub: FAIL (%d hit(s))" % len(hits))
        return 1
    print("scrub: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
