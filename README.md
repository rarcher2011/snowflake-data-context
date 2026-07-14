# OpenAI Snowflake Agent Context

Python extension helpers for enriching OpenAI SDK coding-agent workflows with Snowflake table descriptions, schema metadata, relationship hints, and governance context.

The package is intended to make Snowflake metadata easy to retrieve, compact, cache, and attach to OpenAI model/tool calls so coding agents can generate safer SQL, understand warehouse structure, and reason about existing analytical assets.

## Planned Capabilities

- Discover Snowflake databases, schemas, tables, views, columns, comments, tags, policies, grants, and freshness signals.
- Convert Snowflake metadata into concise agent-ready context blocks.
- Provide extension-style helpers around the official `openai` Python SDK without forking it.
- Support explicit table selection, semantic search over metadata, and token-budgeted context packing.
- Offer safe defaults for credential handling, query limits, caching, and governance-aware redaction.

See [docs/ARCHITECTURE_TECH_SPEC.md](docs/ARCHITECTURE_TECH_SPEC.md) for the implementation plan and technical specification.

## Long-Running Agent Harness

This repository includes a file-based startup harness for long-running coding agents and analysis sessions. It recovers the latest memory file, status JSON, and configured work queue, then writes a compact session context file for the next agent context window.

See [docs/LONG_RUNNING_AGENT_HARNESS.md](docs/LONG_RUNNING_AGENT_HARNESS.md) for usage and file formats.

## Status

Design scaffold only. Implementation is intentionally not complete yet.
