# Long-Running Agent Harness

The long-running agent harness gives coding agents a repeatable startup routine for recovering context across sessions. It is intentionally file-based so it works with local agents, CI jobs, and hosted coding assistants without requiring a service.

## Goals

- Recover the latest memory from prior agent runs.
- Load the last explicit status file.
- Locate the configured work queue.
- Detect incomplete work and inconsistent state.
- Write a compact context bundle for the next agent context window.

## Files

- `agent_harness.toml`: repository and path configuration.
- `.agent_harness/memory/`: memory files from previous agents.
- `.agent_harness/status.json`: last known status from the previous run.
- `.agent_harness/work.md`: source of requested work.
- `.agent_harness/session_context.md`: generated startup context for the active run.

The `.agent_harness/` directory is not required to exist before startup. Missing files are reported as warnings so an agent can decide whether to continue or ask for input.

Remote S3, Google Cloud Storage, and Google Docs locations can also be configured for memory, status, work, or config handoff. Remote integrations are optional and require callers to provide authenticated clients.

## Configuration

```toml
[repo]
path = "."

[paths]
memory_dir = ".agent_harness/memory"
status_file = ".agent_harness/status.json"
work_file = ".agent_harness/work.md"
session_context_file = ".agent_harness/session_context.md"
```

Optional remote locations:

```toml
[locations]
memory = "s3://my-agent-state/memory/"
status = "gs://my-agent-state/status.json"
work = "gdoc://google-doc-id-for-work-queue"

[locations.config]
backend = "google_doc"
uri = "https://docs.google.com/document/d/google-doc-id/edit"
description = "Shared bootstrap configuration for long-running agents"
```

Supported location forms:

- `s3://bucket/key-or-prefix`
- `gs://bucket/key-or-prefix`
- `gdoc://document-id`
- `google-doc://document-id`
- `https://docs.google.com/document/d/<document-id>/edit`
- local relative or absolute paths

When a remote memory location points to an object-store prefix, the newest text object by update timestamp is selected. Text objects are files ending in `.md`, `.txt`, or `.json`.

## Memory Format

Memory files can be Markdown or text. The harness reads simple labeled fields:

```markdown
summary: Snowflake query-builder tests started
status: in_progress
work_id: WORK-7

Notes from the prior run can continue below.
```

## Status Format

The status file is JSON:

```json
{
  "work_id": "WORK-7",
  "status": "in_progress",
  "summary": "Query builder tests are drafted, implementation pending."
}
```

## Work Queue Format

The default work file is Markdown. The first unchecked task is treated as the next work item:

```markdown
- [x] WORK-6: Add formatter tests
- [ ] WORK-7: Add Snowflake query-builder tests
- [ ] WORK-8: Implement Snowflake query builders
```

JSON work files are also supported when configured with a `.json` suffix.

## Startup

Run the startup script:

```bash
.venv/bin/python scripts/start_agent_harness.py
```

Or use the installed console entrypoint:

```bash
snowflake-agent-harness-start
```

For machine-readable output:

```bash
.venv/bin/python scripts/start_agent_harness.py --json
```

## Cloud Readers

The harness keeps cloud SDK dependencies optional. Install them only for runners that need remote memory or config:

```bash
.venv/bin/python -m pip install -e '.[cloud]'
```

The core harness accepts reader adapters:

```python
from openai_snowflake_agent_context.agent_harness import initialize_agent_session
from openai_snowflake_agent_context.agent_harness_cloud import (
    build_boto3_s3_text_store,
    build_google_cloud_storage_text_store,
    build_google_docs_text_store,
)
from openai_snowflake_agent_context.agent_harness_locations import LocationReaders

readers = LocationReaders(
    s3=build_boto3_s3_text_store(),
    gcs=build_google_cloud_storage_text_store(),
    google_docs=build_google_docs_text_store(authenticated_docs_service),
)

report = initialize_agent_session("agent_harness.toml", readers=readers)
```

Remote readers are read-only in the current harness. Agents should still write the generated session context locally and let a supervising workflow decide whether to persist updated memory or status back to remote storage.

## Agent Behavior

On startup, an agent should:

1. Run the harness.
2. Read `.agent_harness/session_context.md`.
3. Compare the current user request with the recovered next work item.
4. Continue incomplete work when it matches the current request.
5. Ask for clarification when memory, status, and work queue disagree in a task-critical way.
