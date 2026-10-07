---
type: Code Example
title: The find_session snippet
description: A DevFest schedule lookup as a Gemini function; shown for explanation, never run.
tags: [gemini, function-calling, python]
status: stable
generated: { by: teach/1.3.1, at: 2026-10-07T12:00:00Z }
sources:
  - id: fc-page
    resource: ~/agent-knowledge-hub-mirror/gemini-api/docs/function-calling.md
    title: Function calling with the Gemini API (local mirror copy)
---

> Shown for explanation only. Not run.

The calls follow the Interactions API pattern on the mirror page:
`client.interactions.create(...)`, a `function_call` step, then a
`function_result` sent back.[^fc-page]

# Examples

```python
import json
from google import genai

# Your real code: a tiny in-code schedule
SCHEDULE = {
    "09:00": "Keynote: What's new in Gemini",
    "10:30": "Builder Showcase: Agents in Python",
    "13:00": "Lightning talks",
}

def find_session(time: str) -> dict:
    """Return the DevFest session at a given time."""
    return {"time": time, "session": SCHEDULE.get(time, "No session at that time")}

# What the model sees: the declaration, not the code
find_session_declaration = {
    "type": "function",
    "name": "find_session",
    "description": "Finds the DevFest Sydney session scheduled at a given start time.",
    "parameters": {
        "type": "object",
        "properties": {
            "time": {"type": "string", "description": "Start time, 24-hour, e.g. '10:30'"},
        },
        "required": ["time"],
    },
}

client = genai.Client()

# Steps 1 and 2: declare and ask
interaction = client.interactions.create(
    model="gemini-3.8-flash",
    input="What's on at 10:30?",
    tools=[find_session_declaration],
)

# Step 3: the model returned a call; YOUR code runs it
fc_step = next(s for s in interaction.steps if s.type == "function_call")
if fc_step.name == "find_session":
    result = find_session(**fc_step.arguments)

# Step 4: send the result back; the model writes the answer
final = client.interactions.create(
    model="gemini-3.8-flash",
    input=[{
        "type": "function_result",
        "name": fc_step.name,
        "call_id": fc_step.id,
        "result": [{"type": "text", "text": json.dumps(result)}],
    }],
    tools=[find_session_declaration],
    previous_interaction_id=interaction.id,
)
print(final.output_text)
```

# What to point at on stage

- **Two halves.** `find_session` is ordinary Python the model never sees.
  `find_session_declaration` is what it sees: `type`, `name`, `description`,
  `parameters`.[^fc-page]
- **The description does the work.** Best practice: clear, specific
  descriptions, descriptive names without spaces, specific types.[^fc-page]
- **Check before running.** Validate the function call before executing it,
  which is why the snippet tests `fc_step.name` first.[^fc-page]
- **Modes.** By default (`auto`) the model chooses between a call and a direct
  answer; `any` forces a call; `none` forbids one.[^fc-page]

Background: [the function calling loop](/function-calling-loop.md).

[^fc-page]: Function calling with the Gemini API, sections "Function declarations", "Best practices", "Function calling modes" and Steps 1 to 4
