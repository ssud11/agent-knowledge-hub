---
type: Concept
title: The function calling loop
description: The four moves of Gemini function calling and which side runs the code.
tags: [gemini, function-calling]
status: stable
generated: { by: teach/1.3.1, at: 2026-10-07T12:00:00Z }
sources:
  - id: fc-page
    resource: ~/agent-knowledge-hub-mirror/gemini-api/docs/function-calling.md
    title: Function calling with the Gemini API (local mirror copy)
---

# Summary

Function calling lets the model connect to your tools and APIs. Instead of
answering in text, the model decides when to call one of your functions and
supplies the arguments.[^fc-page]

# The four moves

1. **Declare.** Describe your function to the model: name, purpose, parameters.
2. **Ask.** Send the user's prompt together with that declaration.
3. **Run.** The model returns a function call (name and arguments). The model
   does not run the function; your code does.
4. **Return.** Send the result back, and the model writes the final answer.[^fc-page]

The loop can repeat over several turns, and the model can ask for several
functions at once (parallel) or one after another (compositional).[^fc-page]

Stage line: "The model doesn't call your code. It asks you to call your code,
then reads the answer."

See the code in [the find_session snippet](/find-session-snippet.md).

[^fc-page]: Function calling with the Gemini API, section "How function calling works"
