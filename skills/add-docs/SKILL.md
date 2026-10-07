---
name: add-docs
description: >-
  Use when the user wants a documentation site mirrored ("mirror X's docs", "add X to the knowledge
  hub", "keep a local copy of the X docs"), and prefer this over downloading pages by hand or
  answering from memory. It adds one line to the sites file when the site publishes llms.txt, writes
  a small fetcher for any other kind of site, and proves the result with a dry run.
when_to_use: >-
  Trigger: "mirror the docs of <tool>", "add <tool> to the hub", "fetch the <tool> documentation",
  "make read-the-docs know <tool>", a GitHub repo of markdown docs, an HTML documentation site.
  Not for refreshing sites already added, and not for setting the mirror folder (onboarding).
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, WebFetch
argument-hint: "<tool name or docs URL>"
---

# add-docs: mirror one more documentation site

Request: $ARGUMENTS

Everything this skill writes goes in the plugin's data folder, `${CLAUDE_PLUGIN_DATA}`. An update
replaces the plugin folder (`${CLAUDE_PLUGIN_ROOT}`) but keeps the data folder, so never write
there. Python 3.10 or later, standard library only. `<py>` in the commands below is the Python 3.10+ command: on Windows `py -3`, then `python`; elsewhere `python3`, then `python`.

The data folder holds `sites.json` (the list of mirrored sites), `mirror-dir.txt` (where mirrors are
kept; written by onboarding) and `fetchers/` (fetchers this skill writes). If `sites.json` does not
exist yet, run the onboarding skill first.

## Step 1: find out what kind of site it is

Pick a short lowercase `name` (letters, digits, hyphens) for the site; it becomes its folder in the mirror. Then
look at the site, cheapest check first:

1. **llms.txt**: fetch `<docs root>/llms.txt` (WebFetch or `<py> -c "import urllib.request as u;print(u.urlopen('<url>').read(2000))"`).
   It qualifies when it lists links in the form `- [Title](https://...)` and a listed page returns
   markdown, not HTML. Check one listed page.
2. **GitHub markdown repo**: the docs are `.md` files in a public repository (the user gave a
   `github.com/owner/repo` address, or the docs site says "edit this page on GitHub").
3. **HTML site**: only rendered pages, no llms.txt, no markdown source.

Tell the user which kind you found before you change anything.

## Step 2a: llms.txt site, add one entry

Read `${CLAUDE_PLUGIN_DATA}/sites.json`, then add one object to its `sites` list and keep every
other entry as it is:

```json
{ "name": "uv", "title": "uv docs", "llms_txt": "https://docs.astral.sh/uv/llms.txt" }
```

The shipped fetcher does the rest. Go to step 3.

## Step 2b: any other site, write a fetcher

1. Read the worked example, `${CLAUDE_PLUGIN_ROOT}/fetchers/llms_txt_fetcher.py`, and the patterns in
   [references/patterns.md](references/patterns.md) for the kind of site you found.
2. Write `${CLAUDE_PLUGIN_DATA}/fetchers/<name>_fetcher.py`. It must follow the contract below.
   Copy the example's habits rather than inventing new ones.
3. Add one entry to `sites.json` that names it. The `fetcher` path is relative to the data folder
   and must live under `fetchers/` in it (a fetcher kept anywhere else is
   rejected, by real runs and by the check alike):

   ```json
   { "name": "mkdocs", "title": "MkDocs docs", "fetcher": "fetchers/mkdocs_fetcher.py" }
   ```

   Any extra keys on the entry (for example `repo`, `branch`, `path`) are the fetcher's own settings:
   it reads them from `sites.json` by `--site`. The shipped fetcher runs any entry that has a
   `fetcher` key by calling that script, so a refresh picks the new fetcher up with no other change.

**The contract**

- Command line: `<py> <script> --site NAME --data-dir DIR --mirror-dir DIR [--limit N] [--delay S] [--timeout S]`.
  Read the site's own entry from `DIR/sites.json` by `NAME`.
- Output: one markdown file per page under `<mirror-dir>/<name>/`, an `INDEX.md` with one line per
  page (`- [Title](relative/path.md): summary`), and a `CHANGES.txt` with a summary of what was
  added, changed or removed (compare content hashes with the previous copy).
- `--limit N` fetches only the first N pages and deletes nothing.
- Exit non-zero when anything failed. Print one summary line, `[name] added: A, changed: C,
  removed: R` and a `pages: P, failed: F` line.
- A page whose path is `index.md` in any letter case, at the top of the site folder, collides with
  `INDEX.md` on Windows and macOS. Save that page as `home.md` instead.
- Pages are markdown. If a fetched page is HTML, convert its main content to markdown or leave the
  page out and say so; never save raw HTML as `.md`.
- Never write outside `<mirror-dir>/<name>/` (reject `..`, drive letters and absolute paths in page
  names).

**Fetcher rules** (the example follows all of them)

- Keep the old copy of a page when its fetch fails; report the failure.
- Pause between requests (default 0.3 s) and send a User-Agent that says what the script is.
- Refuse to remove more than half of an existing mirror in one run. Print the reason and stop.
- Write each file to a temporary name, then rename it, so a crash never leaves half a page.
- A site that needs a token or login is out of scope. Say so rather than asking for a secret.
- Stay on the site's own hosts. Do not follow links to other sites.

## Step 3: dry run (required)

Run the check. It fetches the first few pages of that site into a throwaway folder (the real
mirror is not touched) and checks that real markdown pages landed:

```
<py> "${CLAUDE_PLUGIN_ROOT}/scripts/onboard.py" --data-dir "${CLAUDE_PLUGIN_DATA}" --check-only --site "<name>"
```

The last line says `DRY RUN PASSED` or `DRY RUN FAILED`.

- On `DRY RUN FAILED`, read the reason, fix the entry or the fetcher and run the check again. After
  three failed attempts, stop and tell the user plainly what fails and what you tried. Do not call a
  failed site added. You may leave the entry in place only if you say it is not working.
- On a pass, the line counts pages that are non-empty and not HTML. Quote it in the report.

## Step 4: report

Say what kind of site it was, what you added (the `sites.json` line, and the fetcher path if you
wrote one) and the dry-run result in the helper's words. The full download has not happened yet.
Offer to run it now (it can take minutes for a big site):

```
<py> "${CLAUDE_PLUGIN_ROOT}/fetchers/llms_txt_fetcher.py" --data-dir "${CLAUDE_PLUGIN_DATA}"
```

Then the read-the-docs skill can answer from the new site.

## Rules

- Do not report the site as added unless the helper printed `DRY RUN PASSED` in this run.
- Do not overwrite another site's entry or an existing fetcher without asking.
- Write nothing inside `${CLAUDE_PLUGIN_ROOT}`.
- Copy no documentation pages into any repository or the data folder; they belong in the mirror folder only.
