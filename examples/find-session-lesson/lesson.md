# Lesson 1: Function calling, explained with `find_session`

*About 5 minutes. Goal: you can explain the Gemini function calling loop on stage, using a DevFest schedule example.*

---

## 1. The loop in plain words

Function calling lets the model connect to your tools and APIs. Instead of answering in text, the model decides when to call one of your functions and supplies the arguments.
*Source: `~/agent-knowledge-hub-mirror/gemini-api/docs/function-calling.md` (intro)*

The loop has four moves:

1. **Declare.** You describe your function to the model: its name, its purpose, its parameters.
2. **Ask.** You send the user's prompt together with that declaration.
3. **Run.** The model returns a function call (a name and arguments). **The model does not run the function itself.** Your code does.
4. **Return.** You send the result back, and the model writes the final, user-friendly answer.

*Source: `~/agent-knowledge-hub-mirror/gemini-api/docs/function-calling.md` (section "How function calling works")*

The loop can repeat over several turns. The model can also ask for several functions in one turn (parallel) or one after another (compositional).
*Source: `~/agent-knowledge-hub-mirror/gemini-api/docs/function-calling.md` (section "How function calling works")*

> **Stage line:** "The model doesn't call your code. It asks *you* to call your code, then reads the answer."

---

## 2. The DevFest snippet

> Shown for explanation only. Not run in this lesson.

The calls below follow the Interactions API pattern on the mirror page: `client.interactions.create(...)`, a `function_call` step, then a `function_result` sent back.
*Source: `~/agent-knowledge-hub-mirror/gemini-api/docs/function-calling.md` (Steps 1 to 4)*

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

### What to point at on stage

- **Two halves.** `find_session` is ordinary Python the model never sees. `find_session_declaration` is the description the model does see. A declaration has `type` (`"function"`), `name`, `description` and `parameters` (with `type`, `properties`, `required`).
  *Source: `~/agent-knowledge-hub-mirror/gemini-api/docs/function-calling.md` (section "Function declarations")*
- **The description does the work.** The page's best practices: clear, specific descriptions, descriptive names without spaces, and specific types.
  *Source: `~/agent-knowledge-hub-mirror/gemini-api/docs/function-calling.md` (section "Best practices")*
- **`**fc_step.arguments`** unpacks the model's arguments into your function, the same way the page's `set_light_values` example does.
  *Source: `~/agent-knowledge-hub-mirror/gemini-api/docs/function-calling.md` (Step 3)*
- **`call_id` and `previous_interaction_id`** tie your result to the call the model made and to the earlier turn.
  *Source: `~/agent-knowledge-hub-mirror/gemini-api/docs/function-calling.md` (Step 4)*
- **Check before running.** Best practice is to validate function calls before you execute them. That is why the snippet checks `fc_step.name` first.
  *Source: `~/agent-knowledge-hub-mirror/gemini-api/docs/function-calling.md` (section "Best practices")*
- **Bonus if asked:** by default (`auto`) the model decides whether to call a function or answer directly. `any` forces a call and `none` forbids one.
  *Source: `~/agent-knowledge-hub-mirror/gemini-api/docs/function-calling.md` (section "Function calling modes")*

---

## 3. Quiz (answer from memory first)

1. Who runs `find_session`: the model or your code?
2. Which object does the model actually see: `find_session` or `find_session_declaration`?
3. After your code runs, what do you send back, and what does the model do with it?

Primary source to read next: the live version of the mirror page, https://ai.google.dev/gemini-api/docs/function-calling
*Mirror copy: `~/agent-knowledge-hub-mirror/gemini-api/docs/function-calling.md`*

Stuck on anything? Ask your teacher agent a follow-up question.

### Answers

1. **Your code.** The model only returns the function name and arguments; your application executes it.
   *`~/agent-knowledge-hub-mirror/gemini-api/docs/function-calling.md` ("How function calling works")*
2. **The declaration**: name, description and parameters, sent as a tool.
   *`~/agent-knowledge-hub-mirror/gemini-api/docs/function-calling.md` ("Function declarations")*
3. **A `function_result`** with the matching `call_id`. The model uses it to write the final, user-friendly answer.
   *`~/agent-knowledge-hub-mirror/gemini-api/docs/function-calling.md` ("How function calling works", Step 4)*
