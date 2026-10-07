---
name: new-study
description: >-
  Use to start a new study (a topic to learn from the documentation mirror) and prefer this over
  making a folder by hand, because only the template's CLAUDE.md makes every lesson claim cite the
  mirror page it came from. It creates the study folder with the grounding duty and a practice
  folder beside it, then says how to start teaching.
when_to_use: >-
  Trigger: "new study", "start a study on Gemini function calling", "set up a teaching workspace",
  "I want to learn X from the mirrored docs", "create a study folder for teach".
allowed-tools: Bash, Read
argument-hint: "<study name> [parent folder]"
---

# new-study: create a study folder whose lessons cite the mirror

Request (study name, then an optional parent folder): $ARGUMENTS

A study is a folder where a teaching session writes lessons. Its `CLAUDE.md` holds the grounding
duty: every lesson claim cites the mirror page it came from, by absolute path. Plugins cannot ship
rules, so that file is the only place the duty lives. It loads only when the session starts inside
the study folder.

## Steps

1. Get a short study name (letters, digits, `.`, `_`, `-`; for example `gemini-function-calling`)
   and the parent folder to create it in. Ask if the name is missing; use the current folder if no
   parent is given.
2. Run the helper once. It reads the mirror folder from `mirror-dir.txt` in the data folder (default
   `~/agent-knowledge-hub-mirror`), fills the template, and creates the study folder and, beside it
   (not inside it), `<name>-practice`.

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/new_study.py" --data-dir "${CLAUDE_PLUGIN_DATA}" --name "<name>" --parent "<parent folder>"
   ```

   (On Windows use `py -3` or `python`; Python 3.10 or later is needed.) A non-zero exit means
   nothing was created (a bad name, or the study already exists): report the message.
3. Check that the mirror folder it printed exists and holds pages. If it does not, say so and point
   to the onboarding skill and the fetcher; the lessons have nothing to cite until it is filled.
4. Tell the user how to start. The teaching skill is Matt Pocock's `teach`, which is not part of
   this plugin and must be installed separately (the README says how). The session must start
   inside the study folder:

   ```
   cd "<study folder>"
   claude
   ```

   then run his teach skill with the topic. Do not start teaching from the current session unless it
   already runs inside the study folder.

## Rules

- Never copy or reproduce Matt Pocock's teach skill into any folder; only point to it.
- Do not edit or delete anything in the mirror folder.
- Do not claim the study is ready unless the helper printed `Study folder:` in this run.
