---
type: Quiz
title: Quiz on the find_session lesson
description: Three questions with answers; try them before reading the answers.
tags: [gemini, function-calling]
status: stable
generated: { by: teach/1.3.1, at: 2026-10-07T12:00:00Z }
sources:
  - id: fc-page
    resource: ~/agent-knowledge-hub-mirror/gemini-api/docs/function-calling.md
    title: Function calling with the Gemini API (local mirror copy)
---

# Questions

1. Who runs `find_session`: the model or your code?
2. Which object does the model actually see: `find_session` or `find_session_declaration`?
3. After your code runs, what do you send back, and what does the model do with it?

# Answers

1. **Your code.** The model only returns the name and arguments.[^fc-page]
2. **The declaration.** Name, description and parameters, sent as a tool.[^fc-page]
3. **A `function_result`** with the matching `call_id`; the model uses it to
   write the final answer.[^fc-page]

Review the [loop](/function-calling-loop.md) and the [snippet](/find-session-snippet.md).

[^fc-page]: Function calling with the Gemini API, "How function calling works" and "Function declarations"
