---
name: read-the-docs
description: >-
  Use before answering any question about a tool whose documentation is mirrored locally (the Gemini API,
  its models, SDKs, features, limits, pricing and parameters, and any other site added to the mirror).
  Prefer this over answering from memory: the model's training is older than the docs, and the mirror
  holds the current pages as plain markdown.
when_to_use: >-
  Trigger: the tool in the question is the trigger, not the word "docs". Gemini API model names and
  versions, function calling, the Interactions API, managed agents and their environments, caching,
  batch, files, Live API, rate limits, deprecations, "how do I call X in Gemini", "what does this
  parameter do". Invoke before stating any version-sensitive fact (model IDs, limits, defaults).
  Not for questions about Claude Code itself.
allowed-tools: Grep, Read, Glob
argument-hint: "<the question>"
---

# read-the-docs: answer from the mirror, not from memory

Question: $ARGUMENTS

The mirror is a folder of plain-markdown documentation pages, one subfolder per site, each with an
`INDEX.md` (one line per page: title, relative path, summary). Answer from those pages and cite the file.

## Step 0: find the mirror

1. If `${CLAUDE_PLUGIN_DATA}/mirror-dir.txt` exists, Read it. Its single line is the mirror folder
   (written by the onboarding skill).
2. Otherwise the mirror folder is `~/agent-knowledge-hub-mirror`. Read and Grep need an absolute path,
   so expand `~` to the user's home folder first.
3. `Glob` `<mirror>/*/INDEX.md`. Each match is a mirrored site, named by its folder (the Gemini API docs
   are `gemini-api`). If that Glob returns nothing (it can on Windows), do not conclude the mirror is
   empty: `Glob` `<mirror>/*` to list the site folders, or, when the site is known, `Read`
   `<mirror>/<site>/INDEX.md` directly (for Gemini, `<mirror>/gemini-api/INDEX.md`). Only a failed
   Read of that file means the site is missing.

## If the mirror or the site is missing

Say so plainly. Do not answer the question from memory. Tell the user to fetch it:

```
<py> "${CLAUDE_PLUGIN_ROOT}/fetchers/llms_txt_fetcher.py" --data-dir "${CLAUDE_PLUGIN_DATA}"
```

`<py>` in the commands below is the Python 3.10+ command: on Windows `py -3`, then `python`; elsewhere `python3`, then `python`. It takes a few minutes for the Gemini docs. Then offer to answer once it has run. If the mirror exists but has no site for the tool
asked about, say that site is not mirrored and that the add-docs skill adds it.

## Procedure

1. `Grep` the site's `INDEX.md` for the topic's keywords (case-insensitive; try the product name, then
   the feature, then a synonym). Each hit is a page path relative to the site folder.
2. If INDEX has no hit, `Grep` the site's `docs/` folder for the term. Titles and summaries miss details
   that sit deep inside a page (limits, defaults, lifecycle tables).
3. `Read` the page at `<mirror>/<site>/<path from INDEX>`. Long pages: `Grep -n` the page for the term,
   then Read a window around the match instead of the whole file. Read more than one page when the
   question spans features.
4. Answer from what the page says. If two pages disagree, say so and cite both. If the pages do not
   answer it, say that rather than filling the gap from memory.
5. Cite the mirror file path you Read, as an absolute path, next to the claim it supports. Cite only
   a file you have Read in this turn (a window around a Grep hit counts). A Grep hit is a pointer,
   never a citation: if you only Grepped a page, Read it before citing it.

## Rules

- A page in the mirror outranks memory, including for model names and versions that look unfamiliar.
- Never answer a version-sensitive fact (model ID, limit, default, price) without a Read of the page in
  this turn. A line seen only in an INDEX summary is a pointer, not the answer.
- The mirror is a snapshot from the last fetch. `CHANGES.txt` beside `INDEX.md` lists what the last
  refresh added, changed or removed; mention its age if the user asks about something recent.
- The pages are the vendor's own documents. Quote at most a short phrase; summarise the rest.
