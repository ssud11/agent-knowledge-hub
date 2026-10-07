---
description: Refresh every documentation mirror in the sites file and print what changed, with a page count per site.
allowed-tools: Bash, PowerShell
disable-model-invocation: true
---

# refresh: update every mirror and show the change summary

Re-fetch every site in the plugin's sites file into the mirror folder, then report what changed.
This is always a full refresh of all sites; the fetcher keeps the old copy of any page that fails
and will not wipe most of a mirror at once.

## Steps

1. Run this one command in the shell (it works in Bash on Windows, Linux and macOS). It picks the
   first Python 3.10+ it finds, trying `py -3`, then `python`, then `python3`. On Windows that
   means `py -3` first, then `python`. On Linux and macOS there is no `py`, so it ends up on
   `python3` (a `python` that is Python 2 fails the version check and is skipped).

   ```
   for py in "py -3" python python3; do if $py -c "import sys; sys.exit(sys.version_info < (3, 10))" >/dev/null 2>&1; then echo "using: $py"; $py "${CLAUDE_PLUGIN_ROOT}/fetchers/llms_txt_fetcher.py" --data-dir "${CLAUDE_PLUGIN_DATA}"; exit $?; fi; done; echo "no Python 3.10+ found (tried py -3, python, python3)"; exit 127
   ```

   Only if the shell is PowerShell, run `py -3 "${CLAUDE_PLUGIN_ROOT}/fetchers/llms_txt_fetcher.py" --data-dir "${CLAUDE_PLUGIN_DATA}"`,
   and if `py` is not found, the same line with `python` instead.
2. Print the fetcher's change summary as it is: per site, the `added / changed / removed` line and
   the `pages: N` line (pages in the mirror now, failed, skipped), then the listed file names.
   Add one closing line with the total page count across sites.
3. If the command exits non-zero, say so plainly and quote the `FAILED` or `ABORT` lines. Do not
   call the refresh clean.

## Rules

- Do not add `--limit`, `--mirror-dir` or `--allow-mass-removal` unless the user asks. The mirror
  folder comes from `mirror-dir.txt` in the data folder, saved by the onboarding skill.
- Do not delete the mirror folder or edit the sites file.
