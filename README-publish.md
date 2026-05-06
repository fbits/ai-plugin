# Wake Commerce Plugin

AI-powered development assistance for Wake Commerce Storefront. Agents, skills, workflows, and tools for building headless storefronts, checkout flows, migrations, security audits, performance reviews, and code quality.

## Installation

### Cursor

1. Open Cursor Settings → Plugins
2. Add this directory as a local plugin
3. The plugin loads manifests, skills, agents, and commands

### Claude (Agent Plugins)

1. Add the marketplace if needed: `/plugin marketplace add <marketplace-url>`
2. Install: `/plugin install wake-storefront`
3. Or test locally with a local marketplace: `/plugin marketplace add ./` from the plugin root

## Documentation

For detailed API reference, schemas, and guides:

- **[Wake Commerce Documentation](https://wakecommerce.readme.io/)** — Storefront API, GraphQL schema, checkout, products, search, and more.

---

## Agents

| Agent | Description |
|-------|-------------|
| **wake-storefront-developer** | Wake Commerce Storefront API specialist. Use when building headless storefronts, product pages, search, checkout, cart, or customer flows. |
| **wake-checkout-architect** | Checkout flow design specialist. Use when designing checkout, shipping, payment, or order completion. |
| **wake-migration-specialist** | Reference-to-headless migration specialist. Use when migrating from Wake Storefront templates, porting Queries/*.graphql, or aligning with production patterns. |
| **wake-security-auditor** | Senior security auditor for secure code reviews, threat modeling, OWASP compliance. Covers auth, tokens, injection, data exposure. |
| **wake-qa-expert** | Test design and validation specialist. Use when designing E2E tests, contract tests, or acceptance criteria. |
| **wake-performance-engineer** | Senior performance engineer for architecting for scale and resolving performance issues. Covers GraphQL, caching, Core Web Vitals, load testing. |
| **wake-graphql-architect** | GraphQL design specialist. Use when designing schema usage, queries, fragments, or batching. |
| **wake-code-reviewer** | Code quality specialist. Use when reviewing style, patterns, maintainability, or best practices. |

---

## Workflows (Commands)

| Command | Description |
|---------|-------------|
| **wake-product-page** | Build a product detail page. Load product by productId, resolve variant via attributeSelections, render prices/images/add-to-cart. |
| **wake-search-page** | Build a search page. Call search(query, partnerAccessToken), use productsByOffset for pagination, apply filters and aggregations. |
| **wake-checkout-flow** | Implement full checkout sequence: createCheckout → checkoutCustomerAssociate → checkoutAddressAssociate → shippingQuotes → checkoutSelectShippingQuote → checkoutAddCoupon → paymentMethods → checkoutSelectPaymentMethod → checkoutComplete. |
| **wake-migrate-storefront-query** | Port Wake Storefront reference Queries/*.graphql to headless. Extract root field, args, fragment; generate equivalent headless query. |
| **wake-security-audit** | Security audit. Review token handling, auth, data exposure, OWASP alignment. Uses wake-security-auditor agent. |
| **wake-test-plan** | Generate test plan. Define E2E scenarios, contract tests, acceptance criteria. Uses wake-qa-expert agent. |
| **wake-performance-review** | Performance review. Query optimization, caching, Core Web Vitals. Uses wake-performance-engineer agent and web-performance-audit skill. |
| **wake-query-review** | GraphQL query design review. Schema alignment, fragments, batching. Uses wake-graphql-architect agent. |
| **wake-code-review** | Code quality review. Style, patterns, maintainability. Uses wake-code-reviewer agent. |

---

## Skills

| Skill | Description |
|-------|-------------|
| **wake-storefront-api** | Wake Commerce Storefront API for headless storefronts. Product pages, search, checkout, cart, customer flows. |
| **wake-checkout-flow** | Checkout mutation sequence. createCheckout → checkoutComplete, shipping selection, payment selection. |
| **wake-product-variants** | Variant resolution and add-to-cart. attributeSelections, matrix, selectedVariant, customizations, subscriptionGroups. |
| **wake-storefront-reference-patterns** | Reference to headless mapping. Migrating from Wake Storefront templates, porting Queries/*.graphql, productId vs handle. |
| **wake-hotsite-banners** | Hotsite and landing pages. Landing pages, promotional pages, campaign URLs. |
| **web-performance-audit** | Lighthouse and performance audits. Core Web Vitals (LCP, INP, CLS), accessibility, SEO, best practices. Requires Chrome DevTools MCP. |

---

## Optional MCP Servers

Only `chrome-devtools` is bundled in `.mcp.json` (required by the `web-performance-audit` skill). The servers below are **suggestions** — agents and skills can take advantage of them when present, but this plugin does **not** auto-install them. Add any you want to your own MCP config.

| Server | Suggested for | Install |
|--------|---------------|---------|
| `context7` | `wake-performance-engineer`, `wake-security-auditor` (research, OWASP/CWE lookup) | `npx -y @upstash/context7-mcp` — requires `CONTEXT7_API_KEY` |
| `sequential-thinking` | `wake-performance-engineer`, `wake-security-auditor` (structured reasoning) | `npx -y @modelcontextprotocol/server-sequential-thinking` |
| `github` | repo / issue / PR lookups | `npx -y @modelcontextprotocol/server-github` — requires `GITHUB_PERSONAL_ACCESS_TOKEN` |
| `@playwright/mcp` | E2E browser automation, QA flows | `npx -y @playwright/mcp` *(use the official scoped package — not the unscoped `playwright-mcp`)* |
| `TestSprite` | Test scaffolding | `npx -y testsprite-mcp` |

---

## Tools (Scripts)

| Script | Usage | Purpose |
|--------|-------|---------|
| **wake-graphql-validate.sh** | `./scripts/wake-graphql-validate.sh <query-file>` | Validate GraphQL query: productId (not handle), attributeSelections, partnerAccessToken. |
| **wake-query-from-reference.sh** | `./scripts/wake-query-from-reference.sh <reference-file>` | Extract headless query pattern from Wake Storefront reference. Outputs mapping notes. |
| **wake-checkout-flow-validator.sh** | `./scripts/wake-checkout-flow-validator.sh <file>` | Verify checkout mutations are called in correct order. |

> **Requires a POSIX shell** (bash + `grep`, `awk`, `tr`, `printf`). On Windows, run them under **Git Bash**, **WSL**, or **MSYS2** — they will not run in PowerShell or `cmd.exe`. PowerShell ports are not currently provided.

---

## What's Included

| Component | Path | Purpose |
|-----------|------|---------|
| Cursor manifest | `.cursor-plugin/` | Cursor plugin metadata |
| Claude manifest | `.claude-plugin/` | Claude/Agent Plugins metadata |
| MCP config | `.mcp.json` | Bundled MCP servers (chrome-devtools only — see [Optional MCP Servers](#optional-mcp-servers) for suggestions) |
| Skills | `skills/` | Domain instructions and references |
| Agents | `agents/` | Persona definitions |
| Commands | `commands/` | Slash-command workflows |
| Scripts | `scripts/` | Validation and extraction tools |
| Assets | `assets/` | Logo and marketplace assets |

---

## References

- [Wake Commerce Documentation](https://wakecommerce.readme.io/) — API reference, schemas, guides
- [Agent Skills Specification](https://agentskills.io/specification)
- [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp)
- [Core Web Vitals](https://web.dev/articles/vitals)

## License

MIT
