# Templating and edges

Two things trip up almost every workflow author: (1) reading the right value out of an upstream step, and (2) wiring branch/error control flow. This file covers both precisely. It is the offline reference for templating and edge rules; for the server-current schema and step types, fetch `get_workflow_schema` / `get_step_types` over MCP (see the `cortex-workflow-mcp` skill).

## Template interpolation — `{{ ... }}`

Any string field in a step's config (urls, headers, query params, prompts, http body values, passthrough value) is scanned for `{{ expression }}` tokens and substituted before the step runs. `constant.value` is the exception — it is **never** interpolated.

Recognized expressions:

| expression | resolves to |
|------------|-------------|
| `{{input.foo}}` | field `foo` of the workflow input. Supports dot paths and array indexes: `{{input.user.name}}`, `{{input.items[0].id}}`. |
| `{{steps.<id>}}` | the **entire output** of step `<id>`. |
| `{{steps.<id>.output}}` | same as above (explicit form). |
| `{{steps.<id>.<path>}}` | a field inside step `<id>`'s output, via dot/index path. **Plus an LLM/HTTP fallback — see below.** |
| `{{conversation.history}}` | array of prior turns: `[{ "role", "content" }, ...]`. Empty `[]` if none. |
| `{{conversation.previousRunId}}` | the previous run's id as a string, or `""`. |

Resolution details that matter:
- An unresolved expression becomes an **empty string**, not an error. This is what makes the funnel pattern work, but it also means a typo'd path silently yields `""` — double-check paths.
- When a `{{...}}` token is the whole value and resolves to a JSON object/array, it is substituted **as that structure** (e.g. an `http` `body` field can carry a full array). When embedded in surrounding text, it's stringified.
- Booleans stringify as `true`/`false`, numbers as their literal form.

### The LLM/HTTP nesting fallback (read this)

LLM and HTTP steps don't put their useful data at the top level — they nest it:
- `llm` output: `{ "content": <...>, "inputTokens", "outputTokens" }`
- `http` output: `{ "body": <...>, "statusCode", "headers", "isError" }`

When you write `{{steps.<id>.<field>}}` and `<field>` isn't found at the top level, the resolver **automatically retries inside `content`**. So for an LLM step that returned JSON `{ "Status": "Complete" }`:
- `{{steps.extract.Status}}` → works (fallback finds it in `content`).
- `{{steps.extract.content.Status}}` → also works (explicit).

For a **text** LLM step (`content` is `{ "text": "..." }`):
- `{{steps.format.text}}` → works (fallback into `content.text`).

The fallback only applies to `content`, and only one level. It does **not** apply to HTTP's `body`. To read an HTTP response field, be explicit:
- `{{steps.quote.body.price}}`, `{{steps.quote.statusCode}}`.

When in doubt, reference the whole output (`{{steps.<id>}}`) and let a downstream LLM parse it — that's exactly what the worked example does when formatting quote results.

**`result` steps are the exception to the `content` nesting.** A `result` step emits the validated Structured Result envelope **directly** at the top level, so you read `{{steps.<id>.title}}` / `{{steps.<id>.content}}` (here `content` is the envelope's body string, not the `llm` wrapper). There is no `content.text`. A `result` step is almost always the `final` step, though, so you rarely template off it.

## Edges and control flow

Edges are `{ "from": <stepId>, "to": <stepId>, "condition"?: <string> }`. They define which step(s) run after a given step. There are exactly three condition forms:

| `condition` | fires when |
|-------------|-----------|
| omitted or `"success"` | the `from` step completed without marking itself an error. |
| `"error"` | the `from` step marked itself an error (e.g. an `http` step that got status ≥ 400). |
| `"branch:<caseKey>"` | the `from` step is a `branch` and it routed to this edge's `to` target. |

Any other condition string is rejected at parse time.

### Wiring a branch correctly

A `branch` step needs **two coordinated pieces**: its `cases` map AND an edge per case. The branch executor resolves `on`, looks up the matching `cases` key, and records the **target step id** (the case's value). An edge fires when its `to` equals that recorded target. So:

```json
// step
{ "id": "route", "type": "branch",
  "config": { "on": "{{steps.extract.tipo}}",
              "cases": { "Products": "by_products", "Cart": "by_cart" },
              "default": "unknown" } }

// edges — one per case, plus the default
{ "from": "route", "to": "by_products", "condition": "branch:Products" }
{ "from": "route", "to": "by_cart",     "condition": "branch:Cart" }
{ "from": "route", "to": "unknown",     "condition": "branch:default" }
```

Rules:
- Each `cases` **value** is a step id and must match the `to` of its edge.
- The `<caseKey>` in `branch:<caseKey>` conventionally matches the `cases` key (use `branch:default` for the default route). The routing decision is "did the branch target this `to`", so keep the labels aligned to stay readable.
- A case with no corresponding edge means the branch picks a target that no edge carries control to — the run stalls. Always pair them.
- Branches can chain: route by one value, then the chosen step is itself another `branch`.

### Error fan-in

To make a step's success and failure both continue to the same next step, add two edges:
```json
{ "from": "quote", "to": "format", "condition": "success" }
{ "from": "quote", "to": "format", "condition": "error" }
```
This lets a formatting/LLM step handle both the data and the error payload (the failed step's output is still available via `{{steps.quote}}`). The worked example uses this so one formatter handles all three API calls' results and errors.

### The final step

Exactly one step carries `"output": "final"`; its output is the workflow's result. Edges must lead there along every reachable path, or some inputs produce no output. A common terminal pattern is a `passthrough` that funnels all branch outcomes into one string (see the funnel pattern in `step-types.md`).
