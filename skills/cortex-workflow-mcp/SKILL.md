---
name: cortex-workflow-mcp
description: 'Create, validate, register, run, and inspect Cortex workflows through the Cortex MCP server tools (validate_workflow, create_workflow, activate_workflow, run_workflow, list/get/cancel runs, get_workflow_schema, get_step_types). Use this when an MCP-capable client is connected to the Cortex API MCP endpoint and the user wants to build, register, activate, run, or manage a workflow via those tools — including "register this workflow on cortex", "run the order-intake workflow", "validate my workflow JSON", "activate version 1.1", or "show me the last failed runs". For writing the workflow JSON itself (schema, step types, templating, edges), defer to the cortex-workflow-builder skill.'
---

# Cortex Workflow MCP

The Cortex API hosts an MCP server (default endpoint `http://api.cortex.fbits.net/mcp`) that exposes the full workflow lifecycle as typed tools. This skill teaches you which tool to call, in what order, and how to react to errors. It is the **operational** counterpart to `cortex-workflow-builder`: that skill teaches you how to *write* the workflow JSON; this one teaches you how to *drive the API* through MCP once you have JSON (or want to inspect what is already there).

The MCP tools are thin wrappers over the same services the REST `/workflows` endpoints use — there is no separate behavior to learn. Anything you could do via REST, you do here by calling a tool.

## Authoring rules live in `cortex-workflow-builder`

Do **not** re-derive the workflow JSON structure here. For the meta-schema, step types, templating, and edge rules, use the `cortex-workflow-builder` skill and its assets:

- `cortex-workflow-builder/assets/workflow-meta-schema.json` — the meta-schema.
- `cortex-workflow-builder/references/step-types.md` — every step type's config and output shape.
- `cortex-workflow-builder/references/templating-and-edges.md` — `{{...}}` templating and edge/branch routing.
- `cortex-workflow-builder/scripts/validate_workflow.py` — offline validator (Gate 1 + Gate 2).

You can also fetch the live rules over MCP without leaving the session: `get_workflow_schema` returns the current meta-schema, and `get_step_types` returns the supported step types and their required config. Prefer these when you want the authoritative, server-current rules.

## The two validation gates (why `validate_workflow` matters)

A workflow must clear both, in order:

1. **JSON meta-schema** — required top-level fields, the step shape, per-type required config.
2. **Semantic / runtime rules the schema does NOT catch:**
   - **Exactly one** step has `"output": "final"` (zero or two is a hard failure).
   - Every `"llm"` step includes a `"model"` (the parser throws without it; the schema marks it optional).
   - Step `id`s are unique; `start` and every edge `from`/`to` reference a real step id.

`validate_workflow` runs both gates server-side without persisting. Always validate before `create_workflow`.

## Lifecycle: the order to call tools

Work in this order. A new definition lands as **`Draft`** and serves no traffic until you **activate** it.

1. **`validate_workflow`** — pass the workflow JSON (as a string). Returns `{ valid, hash, stepCount, estimatedDurationMs, warnings }`. Fix anything it reports before continuing.
2. **`create_workflow`** — pass the same JSON. Persists a `Draft` and returns the stored definition. Idempotent: identical content (same hash) returns the existing definition instead of duplicating.
3. **`activate_workflow`** — pass `name` + `version`. Makes that version the live one. **Until this runs, the workflow does not serve traffic.**
4. **`run_workflow`** (or `run_workflow_version`) — execute it. See "Running" below.
5. **Inspect** — `get_workflow_run`, `list_workflow_runs`, `cancel_workflow_run`.

After you create or activate a version (step 2/3), **offer the chat UI link** so the user can test the LLM behavior interactively without you spending tokens on sync runs — see "Testing in the chat UI" below.

To **read** existing definitions: `list_workflows` (optional `status` filter: `Draft` / `Active` / `Retired`), `get_active_workflow` (by name), `get_workflow_version` (by name + version).

When iterating on a workflow, **bump the `version`** and create + activate the new one — do not try to mutate an activated definition (see the conflict error below).

## Running a workflow

`run_workflow` takes `name`, `input` (a JSON string matching the workflow's `inputSchema`), and:

- **`mode`** — `async` (default) queues the run and returns immediately with a `Queued` run; `sync` executes inline and returns the completed (or failed) run.
- **`context`** — optional JSON object string (channel, user, etc.).
- **`previousRunId`** — optional id of a prior run to continue from (carries conversation context forward).

`run_workflow_version` is identical but pins a specific `version` instead of using the active one.

**Sync runs cost real money and have side effects** (model calls, HTTP calls). Default to `async` unless the user needs the result inline. A sync run that exceeds the inline budget returns a **504-coded** error — re-run in `async` mode and poll with `get_workflow_run`.

## Testing in the chat UI

Whenever the user **changes a workflow and wants to test how the LLM responds**, the fastest loop is the workflow chat UI, not a sync `run_workflow`. After you `create_workflow` (and ideally `activate_workflow`) a version, surface a clickable link so they can chat against that exact version:

```
http://<workflow-ui-host>/workflows/<name>/versions/<version>/chat
```

For example, version `2.17` of `ResponderPerguntaFrete-v2`:

```
http://workflow-ui-hlog.cortex.fbits.net/workflows/ResponderPerguntaFrete-v2/versions/2.17/chat
```

Rules:
- Fill `<name>` and `<version>` with the values returned by `create_workflow` / `get_workflow_version` — don't guess them.
- The UI host is **environment-specific** (e.g. `workflow-ui-hlog.cortex.fbits.net` for homologation). Confirm the host with the user if you don't already know it for their environment; only the `/workflows/<name>/versions/<version>/chat` path is fixed.
- Prefer this link for interactive "does the prompt sound right" testing. Reserve `run_workflow` (especially `mode=sync`) for programmatic checks or when the user explicitly wants the run captured/inspected via `get_workflow_run`.
- Offer the link **proactively** after each new version you register, since each change produces a new version with its own URL.

## The MCP error contract

When an underlying service fails, the tool raises an error whose message is prefixed with the status code in brackets: `[<code>] <message>`. The codes match the REST layer, so you react the same way regardless of transport:

| Code | Meaning | What to do |
|------|---------|------------|
| `[422]` | Validation failed (bad JSON or a broken gate-2 rule) | **Fix the workflow JSON, then re-validate.** Do NOT retry the same payload unchanged — read the message, correct the offending step/edge (e.g. add `model`, fix the single-`final` rule), and call `validate_workflow` again. |
| `[409]` | Same `name`+`version` exists with different content | **Bump the `version`** and create the new version, then activate it. Never try to overwrite an activated definition. |
| `[404]` | Unknown workflow name, version, or run id | Check the name/version with `list_workflows` / `get_active_workflow`, or the run id with `list_workflow_runs`. |
| `[400]` | Bad argument (e.g. invalid `mode`, `status`, pagination, or `previousRunId`) | Correct the argument and retry. |
| `[504]` | Sync run timed out | Re-run in `async` mode and poll `get_workflow_run`. |

A `[422]` on create almost always means you skipped `validate_workflow` or ignored a warning — validate first and the create will succeed.

## Tool catalog (quick reference)

**Authoring** — `validate_workflow`, `create_workflow`, `list_workflows`, `get_active_workflow`, `get_workflow_version`, `activate_workflow`.

**Runs** — `run_workflow`, `run_workflow_version`, `get_workflow_run`, `list_workflow_runs`, `cancel_workflow_run`.

**Reference** — `get_workflow_schema`, `get_step_types`.

## Worked flow

A typical "build and ship a new workflow" session:

1. Author the JSON with `cortex-workflow-builder` (or fetch the rules via `get_workflow_schema` / `get_step_types`).
2. `validate_workflow(workflowJson)` → fix until `valid: true`.
3. `create_workflow(workflowJson, createdBy)` → note the returned `name` / `version` (status `Draft`).
4. `activate_workflow(name, version)` → now live.
5. `run_workflow(name, input, mode="async")` → note the `runId`.
6. `get_workflow_run(runId)` → check `status`, `output`, `error`, and the step trace.
