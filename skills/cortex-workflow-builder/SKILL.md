---
name: cortex-workflow-builder
description: 'Author, validate, and register Cortex workflow definitions (the v2 JSON graph of steps + edges run by the Cortex.Workflows engine). Use this whenever the user wants to build, design, write, edit, or fix a Cortex workflow — including phrases like "create a workflow on cortex", "add a step", "wire up an LLM/HTTP/branch step", "extract intent and call an API", or when they paste a workflow JSON and ask you to change or debug it. Also use when generating the JSON to POST to /workflows/. Trigger even if the user does not say the word "workflow" but is clearly describing a multi-step LLM/HTTP/branching pipeline meant to run on Cortex.'
---

# Cortex Workflow Builder

Cortex workflows are JSON documents executed by the `Cortex.Workflows` engine (Microsoft Agent Framework under the hood). A workflow is a **directed graph**: a list of `steps` (nodes) connected by `edges`, starting at `start` and ending at the single step marked `"output": "final"`. Your job is to author JSON that is valid against the engine's schema **and** parses cleanly at runtime — these are two separate gates, and the example payloads people hand you sometimes pass one but not the other.

The schema is bundled with this skill at `assets/workflow-meta-schema.json` so you can validate offline. **Always validate against this schema before declaring a workflow done.** When an MCP client is connected to the Cortex API, you can also fetch the server-current rules with `get_workflow_schema` / `get_step_types` (see the `cortex-workflow-mcp` skill) — prefer those if you suspect the bundled copy has drifted from the live engine.

## The authoring workflow

Work through these in order. Don't jump straight to emitting JSON — the graph design is where mistakes happen, and they're cheap to fix on paper and expensive to fix after the user tries to register it.

1. **Clarify the goal and I/O.** What triggers the workflow, what `inputSchema` does it accept (this is a JSON Schema `object`; fields are read via `{{input.x}}`), and what should the final output be (a formatted string? a JSON object)?
2. **Sketch the graph.** List the steps and how control flows between them. Decide branch points up front. Every step except the start needs at least one inbound edge, and exactly one step must produce the final output.
3. **Write the steps.** Pick a type per node (see the quick reference below; full config in `references/step-types.md`). Give each a unique `id`.
4. **Write the edges.** Connect steps with `from`/`to`/`condition`. Get branch routing and error fan-in right (see `references/templating-and-edges.md`).
5. **Wire the templates.** Reference inputs and upstream outputs with `{{...}}`. The single most common bug is reading an LLM result at the wrong path — read `references/templating-and-edges.md` for how LLM/HTTP outputs nest.
6. **Validate** against the bundled schema, then check the runtime-only rules in the "Validation gates" section below.
7. **Register** the workflow if the user wants it live (see "Registering a workflow").

## Top-level shape

```json
{
  "name": "MyWorkflow",
  "version": "1.0",
  "description": "optional",
  "inputSchema": { "type": "object", "required": ["foo"], "properties": { "foo": { "type": "string" } } },
  "start": "first_step",
  "steps": [ /* ... */ ],
  "edges": [ /* ... */ ]
}
```

Required: `name`, `version`, `start`, `steps` (at least one). `edges` is optional (a single-step workflow needs none). `inputSchema`, `description`, `allowedFunctions`, `allowedSecrets` are optional.

## Step quick reference

Every step is `{ "id", "type", "config", "output?" }`. `id` must be unique. `output` is either absent or the literal `"final"` — and exactly one step in the whole workflow must set it. Pick the type:

| type | purpose | required config | key gotcha |
|------|---------|-----------------|------------|
| `llm` | call a model | `userPrompt`, **`model`** | `model` is required at runtime even though the schema doesn't flag it. Output nests under `content` — see templating ref. |
| `result` | terminal step emitting the fixed Structured Result envelope | `userPrompt`, **`model`** | a specialized `llm` for the **final** step: forces JSON into a fixed envelope (`title`/`content`/`fields`/`actions`); you can't change the shape. Output is the envelope **directly** (no `content` wrapper). See ref file. |
| `http` | call an API | `url` | status ≥ 400 marks the step as an error (routes via `condition: "error"`). |
| `branch` | route by a value | `on`, `cases` | doesn't transform data; it picks the next step. Needs matching `branch:<case>` edges. |
| `constant` | emit a fixed value | `value` | `value` can be any JSON. No template interpolation. |
| `passthrough` | pass/merge a templated string | `transform` | `value` must be a **string** template; built-in transform is `"identity"`. |
| `function` | call a registered server function | `name`, `version` | advanced; the function must be registered in the engine. See ref file. |

Full config fields, defaults, and output shapes for each type are in `references/step-types.md` — read it before writing any step type you're not certain about.

## Validation gates

A workflow must clear **both** of these, in this order:

**Gate 1 — JSON Schema** (`assets/workflow-meta-schema.json`, checked at `POST /workflows/`):
- Required top-level fields present; at least one step.
- Each step's `config` satisfies the per-type requirements (e.g. `llm` needs `userPrompt`, `http` needs `url`).
- `output`, when present, equals `"final"`.

**Gate 2 — Semantic + runtime rules** (checked by the validator and the parser; the schema will NOT catch these):
- **Exactly one** step has `"output": "final"`. Zero or two is a hard failure.
- Step `id`s are unique.
- `start` references a real step id.
- Every edge `from`/`to` references a real step id.
- `llm` and `result` steps **must** include `model` (the parser throws without it, even though the schema treats it as optional).
- A `result` step's output is the validated Structured Result envelope; if the model can't produce a valid envelope (e.g. an empty `userPrompt` on a reachable path), the step throws. Keep its prompt non-empty on every path that reaches it.
- `passthrough.value` must be a string (it's read as a string template). Use `constant` if you need a non-string literal.

Run the bundled validator on every workflow before calling it done — it enforces all of Gate 2 and runs Gate 1 too if `jsonschema` is installed:

```bash
python .claude/skills/cortex-workflow-builder/scripts/validate_workflow.py path/to/workflow.json
```

Exit 0 means valid; it prints each error and any warnings (e.g. an ignored `provider` field, or a branch case with no matching edge). If you can't run it, walk Gate 2 manually — those are the rules that bite.

## Registering a workflow

This skill **authors and validates** the JSON; getting it live is a separate, operational job. The preferred path is the **`cortex-workflow-mcp` skill**, which drives the full lifecycle through MCP tools (`validate_workflow` → `create_workflow` → `activate_workflow` → `run_workflow`). Hand the validated JSON off to it once the workflow is clean.

If no MCP client is connected, the same lifecycle is available over the Cortex REST API. The base URL is environment-specific; confirm it with the user rather than guessing.

- **Validate only** (no persistence): `POST /workflows/?validateOnly=true` with the raw workflow JSON as the body. Returns `200` with `{ valid, hash, stepCount, warnings }` or `422` with validation errors.
- **Create**: `POST /workflows/?createdBy=<who>` with the raw JSON. Returns `201` with the stored definition (status `Draft`). `200` if an identical hash already exists (idempotent). `409` if the same name+version exists with a different body.
- **Activate** (make it the live version): `POST /workflows/{name}/activate`.
- **Read**: `GET /workflows/` (list), `GET /workflows/{name}` (active version), `GET /workflows/{name}/versions/{version}`.

A new workflow lands as `Draft`. It only serves traffic after you activate it. When iterating, bump `version` rather than mutating an activated definition.

## Worked example

`assets/example.json` is a complete, validated multi-branch workflow: an LLM extracts intent from a shipping question, a `branch` routes by completeness then by type, three `http` steps call different quote APIs, and a final `llm` formats the answer. The `saida` step shows the **funnel pattern** — concatenating several mutually-exclusive upstream outputs into one `final` string, where the non-taken paths resolve to empty. Study it when building anything with branches.

## Common mistakes to avoid

- Forgetting `model` on an `llm` step (schema passes, runtime throws).
- Adding a `provider` field to `llm` steps expecting it to do something — the engine ignores it; only `model` is read. Use a tier name (`Light`, `Standard`, `Advanced`) or `cortex` to hit the platform models, or a concrete model id for a specific one.
- Reading an LLM/HTTP output at the top level (e.g. `{{steps.x.Status}}`) without understanding it nests under `content`/`body` — it usually still works via a fallback, but read the templating ref so you know when it won't.
- Zero or multiple `"output": "final"` steps.
- A `branch` whose `cases` point to step ids that have no matching `branch:<case>` edge — the branch sets a target but no edge carries control there.
