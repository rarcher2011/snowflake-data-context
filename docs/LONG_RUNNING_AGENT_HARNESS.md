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

## Agent Behavior

On startup, an agent should:

1. Run the harness.
2. Read `.agent_harness/session_context.md`.
3. Compare the current user request with the recovered next work item.
4. Continue incomplete work when it matches the current request.
5. Ask for clarification when memory, status, and work queue disagree in a task-critical way.

