# Long-Running Agent Harness

The long-running agent harness gives coding agents a repeatable startup routine for recovering context across sessions. It is intentionally file-based so it works with local agents, CI jobs, and hosted coding assistants without requiring a service.

For the broader SMB analytics goal, the harness is the continuity layer for work that cannot fit into one prompt or one analyst session. It should eventually preserve discovery findings, unresolved data gaps, transformation candidates, sampled tables, monitoring snapshots, and human-readable progress updates.

## Goals

- Recover the latest memory from prior agent runs.
- Load the last explicit status file.
- Locate the configured work queue.
- Detect incomplete work and inconsistent state.
- Write a compact context bundle for the next agent context window.
- Preserve active analysis goals and unresolved analytics findings.
- Help future runs distinguish new, persistent, and resolved data gaps.

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
progress = "gdoc://google-doc-id-for-human-readable-progress"

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

If a Snowflake sampling run created a destination sample table, include that table in status so later startup summaries and generated session context point agents at the sample instead of the original source:

```json
{
  "work_id": "WORK-7",
  "status": "in_progress",
  "source_table": "ANALYTICS.PUBLIC.ORDERS",
  "sampled_table": "ANALYTICS.PUBLIC.ORDERS_SAMPLE"
}
```

The harness also recognizes `sampled_table_identifier`, `destination_table`, and `destination_location` for compatibility with sampling method result payloads.

Future status files should also support SMB analytics operating state:

```json
{
  "work_id": "WORK-12",
  "status": "in_progress",
  "analysis_goal": "Assess sales reporting readiness",
  "active_domain": "sales",
  "unresolved_data_gaps": [
    {
      "id": "GAP-1",
      "severity": "high",
      "category": "missing_description",
      "table": "ANALYTICS.PUBLIC.ORDERS",
      "recommendation": "Add table grain and business usage notes."
    }
  ],
  "transformation_candidates": [
    {
      "id": "TX-1",
      "table": "ANALYTICS.PUBLIC.ORDERS",
      "recommendation": "Create a reviewed sales order reporting view."
    }
  ],
  "monitoring_snapshot": {
    "generated_at": "2026-07-25T12:00:00Z",
    "new_gaps": 2,
    "persistent_gaps": 5,
    "resolved_gaps": 1
  }
}
```

These fields are target-state documentation. They should guide future implementation without implying the current harness already validates every shape.

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
uv run scripts/start_agent_harness.py
```

Or use the installed console entrypoint:

```bash
snowflake-agent-harness-start
```

For machine-readable output:

```bash
uv run scripts/start_agent_harness.py --json
```

## Cloud Readers

The harness keeps cloud SDK dependencies optional. Install them only for runners that need remote memory or config:

```bash
uv sync --extra cloud
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

## Human-Readable Progress Updates

Configure `locations.progress` with a Google Doc URI when agents should append human-readable status updates as work progresses:

```toml
[locations]
progress = "gdoc://google-doc-id-for-human-readable-progress"
```

Use `publish_progress_update` with a Google Docs progress writer:

```python
from openai_snowflake_agent_context.agent_harness import (
    HarnessProgressUpdate,
    load_harness_config,
    publish_progress_update,
)
from openai_snowflake_agent_context.agent_harness_cloud import build_google_docs_text_store
from openai_snowflake_agent_context.agent_harness_locations import LocationReaders

config = load_harness_config("agent_harness.toml")
docs = build_google_docs_text_store(authenticated_docs_service)

publish_progress_update(
    config,
    HarnessProgressUpdate(
        work_id="WORK-7",
        status="in_progress",
        message="Pulled metadata for 42 tables and started description quality scoring.",
        details=("11 columns are missing descriptions.", "6 descriptions are too generic."),
    ),
    readers=LocationReaders(google_docs_progress=docs),
)
```

Progress updates are append-only and intended for human readers. They do not replace structured memory or status files.

## Agent Behavior

On startup, an agent should:

1. Run the harness.
2. Read `.agent_harness/session_context.md`.
3. Compare the current user request with the recovered next work item.
4. Continue incomplete work when it matches the current request.
5. Ask for clarification when memory, status, and work queue disagree in a task-critical way.
6. Prefer existing sampled tables when status declares one.
7. Carry forward unresolved data gaps and transformation candidates rather than rediscovering them from scratch.
8. Report progress in human-readable language when findings change, work completes, or new blockers appear.
