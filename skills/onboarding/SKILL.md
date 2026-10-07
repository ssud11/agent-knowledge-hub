---
name: onboarding
description: >-
  Use right after installing the agent-knowledge-hub plugin, or to set up, move or re-check where
  documentation mirrors are kept, and prefer this over creating mirror-dir.txt or sites.json by hand.
  It saves the folder choice, seeds the Gemini entry, and proves the setup with a small test fetch
  instead of claiming success.
when_to_use: >-
  Trigger: "set up the knowledge hub", "onboard", "first run", "where are the docs mirrored", "change
  the mirror folder", "check the hub works". Run once per install; safe to run again.
allowed-tools: Bash, Read
argument-hint: "[mirror folder]"
---

# onboarding: choose the mirror folder, seed the sites file, prove it works

Requested folder (may be empty): $ARGUMENTS

The mirror folder holds the downloaded documentation pages. It must live outside the plugin folder,
because an update replaces that folder. The choice is saved in the plugin's data folder, which an
update keeps: `${CLAUDE_PLUGIN_DATA}`.

## Steps

1. Pick the folder.
   - If the user already named one (in the request or the argument above), use it.
   - Otherwise ask where to keep the mirrors and suggest `~/agent-knowledge-hub-mirror` (a folder in
     the home directory). Wait for the answer. An empty or "default" answer means the suggestion.
   - If no one can be asked (a non-interactive run) and no folder was given, use the suggestion and
     say that you did.
   - Never pick a folder inside the plugin folder (`${CLAUDE_PLUGIN_ROOT}`).
2. Run the helper once. It saves the choice as `mirror-dir.txt`, seeds `sites.json` with the Gemini
   entry (an existing file keeps its other entries and gets Gemini added if missing), then does the
   dry run. Omit `--mirror-dir` to take the home-folder default.

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/onboard.py" --data-dir "${CLAUDE_PLUGIN_DATA}" --mirror-dir "<folder>"
   ```

   (On Windows use `py -3` or `python`; Python 3.10 or later is needed. Quote the folder if it has spaces.)
3. Read the helper's output and report it as it is.
   - The dry run fetches the first few pages of each site into a throwaway folder, never the real
     mirror, then checks that real markdown pages landed. The last line says `DRY RUN PASSED` or
     `DRY RUN FAILED`.
   - On `DRY RUN FAILED`, say plainly that setup is not verified, quote the reason, and suggest the
     likely cause (no network, the site's address changed, a proxy). Do not call setup done.
     The choice is still saved, so running this skill again after fixing the cause is enough.
4. On a pass, tell the user the saved folder and that the full mirror is not downloaded yet. The
   command that downloads it (a few minutes for the Gemini docs) is:

   ```
   python "${CLAUDE_PLUGIN_ROOT}/fetchers/llms_txt_fetcher.py" --data-dir "${CLAUDE_PLUGIN_DATA}"
   ```

   Run it only if the user asks. After it, the read-the-docs skill answers from that folder; it reads
   `mirror-dir.txt` on its own.

## Rules

- Do not report success unless the helper printed `DRY RUN PASSED` in this run.
- Do not delete or overwrite an existing mirror folder. The helper only writes `mirror-dir.txt` and
  `sites.json` in the data folder.
- To check what was saved, Read `${CLAUDE_PLUGIN_DATA}/mirror-dir.txt` and `sites.json`.
