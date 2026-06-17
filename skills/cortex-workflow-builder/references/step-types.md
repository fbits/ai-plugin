# Cortex step types — full reference

Each step is `{ "id": string, "type": string, "config": object, "output"?: "final" }`. This file documents every `config` field per type, runtime defaults, and the **shape of the value the step produces** (which matters when downstream steps read it via `{{steps.<id>...}}` — see `templating-and-edges.md`).

For the server-current step types and their required config, call `get_step_types` over MCP (see the `cortex-workflow-mcp` skill); this file is the offline reference.

---

## llm — call a language model

```json
{
  "id": "extract",
  "type": "llm",
  "config": {
    "model": "Standard",
    "systemPrompt": "You extract structured data.",
    "userPrompt": "Input: {{input.message}}",
    "responseFormat": "json",
    "outputSchema": { "type": "object", "required": ["intent"], "properties": { "intent": { "type": "string" } } },
    "useConversationContext": true
  }
}
```

| field | type | required | default | notes |
|-------|------|----------|---------|-------|
| `model` | string | **yes (runtime)** | — | The schema does not list it as required, but the parser throws if it's missing. See model resolution below. |
| `userPrompt` | string | yes | — | Template-interpolated. |
| `systemPrompt` | string | no | `""` | Template-interpolated. |
| `responseFormat` | `"text"` \| `"json"` | no | `"text"` | `json` forces the model to emit JSON. |
| `outputSchema` | JSON Schema object | no | none | Only meaningful when `responseFormat: "json"`. The model is constrained to it AND the output is validated against it at runtime — a mismatch throws and fails the step. |
| `useConversationContext` | boolean | no | `false` | When true, prior conversation turns (`{{conversation.history}}`) are injected as chat messages before the user prompt. |

**`provider` is NOT a recognized field.** The example payloads floating around include `"provider": "cortex"`; the parser never reads it. Routing is decided entirely by `model`.

**Model resolution:**
- Tier names `Light`, `Standard`, `Advanced` (case-insensitive) → resolved to the platform's managed models via the Cortex chat client.
- `cortex` → also routed through the Cortex chat client.
- Any other string → treated as a concrete model id and sent to the generic chat client factory as-is.

**Output shape** — the step output is always:
```json
{ "content": <result>, "inputTokens": <int>, "outputTokens": <int> }
```
- `responseFormat: "json"` → `content` is the parsed JSON object/array.
- `responseFormat: "text"` → `content` is `{ "text": "<the model's text>" }`.

So to read a JSON field downstream you can write `{{steps.extract.intent}}` (a fallback digs into `content` for you) and for text `{{steps.extract.text}}`. Details and edge cases in `templating-and-edges.md`.

**Failure modes:** invalid JSON from the model, or output that fails `outputSchema` validation, throws and fails the step (route onward with `condition: "error"` if you want to recover).

---

## result — terminal step that emits the Structured Result envelope

```json
{
  "id": "result-1",
  "type": "result",
  "output": "final",
  "config": {
    "model": "Standard",
    "systemPrompt": "",
    "userPrompt": "{{steps.format.content.text}}",
    "useConversationContext": false
  }
}
```

A `result` step is a specialized `llm` step meant to be the **final** step of a workflow. It calls a model exactly like `llm`, but it **forces** `responseFormat: "json"` against a single fixed schema (the Structured Result envelope) and validates the model's output against it. You cannot change the envelope shape — only the prompts and model. Use it (instead of a plain `llm` or `passthrough`) when the workflow's consumer expects the standard envelope (Asgard BFF / chat render it directly).

| field | type | required | default | notes |
|-------|------|----------|---------|-------|
| `model` | string | **yes (runtime)** | — | Same resolution as `llm` (tier name, `cortex`, or a concrete id). Parser throws if missing. |
| `userPrompt` | string | **yes** | — | Template-interpolated. Parser throws if missing. |
| `systemPrompt` | string | no | `""` | Template-interpolated. |
| `useConversationContext` | boolean | no | `false` | Same behavior as `llm`. |

`responseFormat` and `outputSchema` are **not** read — the envelope schema is fixed. `provider` is ignored, same as `llm`.

**The fixed envelope** the model is constrained to (and validated against):
```json
{
  "title": "string (required)",
  "content": "string (required)",
  "fields":  [ { "title": "string", "content": "string" } ],
  "actions": [ { "label": "string", "kind": "string", "target": "string|null", "payload": "object|null" } ]
}
```
`additionalProperties` is false at every level — the model must emit exactly these keys. `title` and `content` are required; `fields` and `actions` are optional arrays.

**Output shape** — unlike `llm`, the step output is the validated envelope **directly** (no `content` wrapper):
```json
{ "title": "...", "content": "...", "fields": [...], "actions": [...] }
```
So a downstream/template reference reads `{{steps.result-1.title}}`, `{{steps.result-1.content}}`, etc. — there is no `content.text` nesting like a text `llm` step. (A `result` step is almost always the `final` step, so you rarely read from it downstream.)

**Failure modes:** the model returning invalid JSON, or JSON that violates the envelope schema, throws and fails the step. Because it's typically the terminal step, ensure its `userPrompt` is never empty on a path that reaches it (e.g. when an upstream step is skipped on an error branch its `{{steps.x...}}` resolves to `""`) — an empty prompt tends to yield output that fails envelope validation. Funnel the relevant upstream outputs into `userPrompt` so it always has content to summarize.

---

## http — call an HTTP API

```json
{
  "id": "quote",
  "type": "http",
  "config": {
    "method": "POST",
    "url": "https://api.example.com/quotes",
    "headers": { "Content-Type": "application/json" },
    "queryParams": { "verbose": "true" },
    "body": { "cep": "{{steps.extract.cep}}", "items": "{{steps.extract.items}}" },
    "timeoutSeconds": 60
  }
}
```

| field | type | required | default | notes |
|-------|------|----------|---------|-------|
| `url` | string | yes | — | Template-interpolated (you can build it from inputs/outputs). |
| `method` | string | no | `"GET"` | |
| `headers` | object (string→string) | no | none | Values are template-interpolated. |
| `queryParams` | object (string→string) | no | none | Values are template-interpolated and appended to the URL. |
| `body` | any JSON | no | none | Deeply template-interpolated. A `{{steps.x.field}}` that resolves to a JSON array/object is substituted as that structure, not a string. |
| `timeoutSeconds` | integer ≥ 1 | no | `30` | |

**Output shape:**
```json
{ "body": <parsed JSON or raw string>, "statusCode": <int>, "headers": <object>, "isError": <bool> }
```

**Error semantics:** a response status ≥ 400 marks the step as an error, so an edge with `condition: "error"` will fire. Use this to route failures to a recovery/formatting step instead of letting the run halt.

---

## branch — route to one of several steps

```json
{
  "id": "route_by_type",
  "type": "branch",
  "config": {
    "on": "{{steps.extract.tipo}}",
    "cases": { "Products": "by_products", "Cart": "by_cart", "Order": "by_order" },
    "default": "unknown_type"
  }
}
```

| field | type | required | notes |
|-------|------|----------|-------|
| `on` | string | yes | Template resolved to a string, then matched against `cases` keys by exact string equality. |
| `cases` | object (string→string) | yes | Map of **case value → target step id**. |
| `default` | string | no | Target step id used when no case matches. If omitted and nothing matches, the step errors. |

A branch **does not transform data** — it only decides which step runs next. You must also add an **edge per case** carrying control to the target (see branch routing in `templating-and-edges.md`):
```json
{ "from": "route_by_type", "to": "by_products", "condition": "branch:Products" }
```

**Output shape:** `{ "value": "<resolved on>", "target": "<chosen step id>" }`.

---

## constant — emit a fixed value

```json
{ "id": "fallback_msg", "type": "constant", "config": { "value": "Sorry, I couldn't understand that." } }
```

| field | type | required | notes |
|-------|------|----------|-------|
| `value` | any JSON | yes | Emitted verbatim. **No template interpolation** — use `passthrough` if you need `{{...}}`. |

The output is the `value` itself.

---

## passthrough — pass or merge a templated string

```json
{ "id": "out", "type": "passthrough", "config": { "transform": "identity", "value": "{{steps.format.text}}" } }
```

| field | type | required | notes |
|-------|------|----------|-------|
| `transform` | string | yes | Name of a registered transform. Built-in: `"identity"` (returns input unchanged). |
| `value` | string | no | A **string** template, interpolated before the transform runs. Must be a string — non-string literals belong in a `constant`. |

Use passthrough to (a) surface an upstream value as the final output, or (b) **funnel** several mutually-exclusive branch outputs into one string. Because un-taken `{{steps.x}}` references resolve to empty strings, concatenating them yields whichever branch actually ran:
```json
{ "id": "final_out", "type": "passthrough",
  "config": { "transform": "identity",
              "value": "{{steps.missing_data}}{{steps.unknown_type}}{{steps.format.text}}" },
  "output": "final" }
```

---

## function — call a registered server-side function

```json
{ "id": "lookup", "type": "function", "config": { "name": "geocode", "version": "1.0", "payload": { "cep": "{{steps.extract.cep}}" } } }
```

Advanced and rarely needed for new authoring. The function must be registered in the engine's `IWorkflowFunctionRegistry`; its declared input/output JSON schemas are validated at runtime.

**Schema/parser mismatch to be aware of:** the JSON meta-schema marks the required config keys as `function` and `version`, but the runtime parser reads `name` and `version`. To clear both gates today, the safest move is to validate the workflow (via `validate_workflow` over MCP or the bundled validator) and confirm the registered function's exact keys before shipping a function step. Prefer `http` or `llm` unless a registered function is specifically required.
