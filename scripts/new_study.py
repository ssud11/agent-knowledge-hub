#!/usr/bin/env python3
"""Create a study folder from the template shipped with the plugin.

Usage:
  python scripts/new_study.py --data-dir DIR --name NAME [--parent DIR]

Creates <parent>/<NAME>/ from skills/new-study/template/ (placeholders filled in) and an empty
practice folder <parent>/<NAME>-practice/ beside it. The mirror folder written into the study's
CLAUDE.md is the one line of <data-dir>/mirror-dir.txt, else ~/agent-knowledge-hub-mirror.
Refuses to touch an existing study. Standard library only.
"""
import argparse
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fetchers.llms_txt_fetcher import read_mirror_dir  # noqa: E402  (the one shared helper)
TEMPLATE = os.path.join(ROOT, "skills", "new-study", "template")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def mirror_dir(data_dir):
    return read_mirror_dir(data_dir)


def create(data_dir, name, parent=None):
    if not NAME_RE.match(name or "") or name.endswith("."):
        raise ValueError("study name must be letters, digits, '.', '_' or '-': %r" % name)
    parent = os.path.abspath(parent or os.getcwd())
    study = os.path.join(parent, name)
    practice = os.path.join(parent, name + "-practice")
    if os.path.exists(study) or os.path.exists(practice):
        raise FileExistsError("study or practice folder already exists: %s" % study)
    values = {"{{STUDY_NAME}}": name, "{{MIRROR_DIR}}": mirror_dir(data_dir),
              "{{PRACTICE_DIR}}": practice}
    made = []
    try:
        os.makedirs(practice)
        made.append(practice)
        for dp, _, files in os.walk(TEMPLATE):
            dest_dir = os.path.join(study, os.path.relpath(dp, TEMPLATE))
            if not os.path.isdir(study):
                made.append(study)
            os.makedirs(dest_dir, exist_ok=True)
            for fn in files:
                with open(os.path.join(dp, fn), encoding="utf-8") as fh:
                    text = fh.read()
                for key, val in values.items():
                    text = text.replace(key, val)
                with open(os.path.join(dest_dir, fn), "w", encoding="utf-8",
                          newline="\n") as fh:
                    fh.write(text)
    except BaseException:
        for path in made:  # only what this run created (both paths were absent at the start)
            shutil.rmtree(path, ignore_errors=True)
        raise
    return study, practice


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--parent")
    args = ap.parse_args(argv)
    try:
        study, practice = create(args.data_dir, args.name, args.parent)
    except (ValueError, FileExistsError, OSError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1
    print("Study folder: %s" % study)
    print("Practice folder: %s" % practice)
    print("Mirror folder: %s" % mirror_dir(args.data_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
