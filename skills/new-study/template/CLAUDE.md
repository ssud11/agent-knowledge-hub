# Study: {{STUDY_NAME}}

This folder is a teaching workspace. A session for it must start with this folder as the
working directory, so that this file loads.

## Grounding duty

Every claim in a lesson, reference sheet or learning record comes from a page of the local
documentation mirror, and cites that page.

- The mirror folder is `{{MIRROR_DIR}}` (read only: never write, move or delete anything there).
- Find the page first: read the `INDEX.md` in the site folder (for example `gemini-api/INDEX.md`) or search the mirror, then read the page itself.
  Do not teach from memory. If the mirror has no page for a claim, drop the claim or mark it
  "not in the mirror".
- Cite each claim with the page's absolute path in the mirror, written in full (for example
  `{{MIRROR_DIR}}/<site>/<page>.md`), so the reader can open it. Put the path next to the claim it
  supports, not only in a list at the end.
- Cite only files you have opened in this session. Never invent or shorten a path.
- Before finishing a lesson, check that every cited path exists, and fix any that does not.

## Folders

- Lessons, references and learning records stay inside this folder (`lessons/`, `reference/`,
  `learning-records/`).
- Practice work (exercises, scratch code, files the learner edits) goes in the practice folder
  `{{PRACTICE_DIR}}`, which sits beside this folder, never inside it.

## Mission

See `MISSION.md`. Ground every lesson in it.
