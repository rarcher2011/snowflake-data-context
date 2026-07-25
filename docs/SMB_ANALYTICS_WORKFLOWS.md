# SMB Analytics Workflows

This project is intended to help small and mid-sized businesses run useful data discovery, analysis, and transformation workflows without needing a large analytics team.

The target user has some technical capacity: a Snowflake warehouse, engineers or operators who know the systems, and perhaps one analyst or fractional data support. The gap is not basic technical literacy. The gap is sustained analytical throughput, reliable data discovery, documentation maintenance, and follow-through on data issues.

## Operating Model

The repo should support a long-running agent that can:

1. Discover what data exists.
2. Assess whether the data is understandable and trustworthy.
3. Identify gaps that block analysis or transformation work.
4. Recommend the next useful analyst or engineering task.
5. Preserve memory and status across runs.
6. Report progress and unresolved issues in human-readable form.

This turns the agent from a one-off SQL helper into a lightweight analytics operations assistant.

## Core Workflows

### Data Discovery

Goal: help a company understand what exists in Snowflake and where analysis should start.

Expected outputs:

- Inventory of relevant databases, schemas, tables, views, and columns.
- Table purpose and owner/context when available.
- Description coverage and description quality.
- Tables with unclear grain, unclear business meaning, or missing usage notes.
- Candidate tables for deeper sampling or profiling.

### Metadata Gap Analysis

Goal: make weak documentation visible and actionable.

Expected outputs:

- Missing table descriptions.
- Missing or weak column descriptions.
- Generic descriptions that repeat names without business meaning.
- Recommended description improvements.
- Snowflake `COMMENT` statements that are reviewable before execution.

### Analyst Backlog Generation

Goal: convert discovery findings into work a human or agent can actually execute.

Expected outputs:

- Prioritized data gaps.
- Suggested analysis tasks.
- Suggested transformation tasks.
- Questions for business stakeholders.
- Tasks that can be safely delegated to a coding agent.
- Tasks that require human review or domain judgment.

### Data Transformation Planning

Goal: help teams identify useful transformations before writing production SQL.

Expected outputs:

- Candidate staging or cleanup models.
- Reporting-table recommendations.
- Suggested joins and relationship checks.
- Transformation risks, such as missing keys or unclear grain.
- SQL or dbt model plans that remain reviewable before execution.

### Monitoring and Follow-Up

Goal: prevent findings from being discovered once and then forgotten.

Expected outputs:

- Current data quality or metadata health snapshot.
- New gaps since the last run.
- Resolved gaps since the last run.
- Regressions in description quality or schema readiness.
- Progress updates suitable for a shared Google Doc or other team-readable location.

## Target Domain Objects

Future implementation work should introduce first-class models for the SMB analytics layer:

- `DataDiscoveryRun`: one discovery pass across a configured Snowflake scope.
- `DataGap`: a missing, weak, stale, or unclear piece of metadata or context.
- `DataIssue`: a data quality, governance, freshness, or schema concern.
- `AnalysisWorkItem`: an actionable analyst or agent task.
- `TransformationCandidate`: a possible data model, view, cleanup rule, or SQL transformation.
- `MonitoringSnapshot`: a point-in-time status record for recurring checks.
- `Recommendation`: a human-readable next action with rationale and priority.

These models should sit above low-level Snowflake metadata retrieval. Metadata is the input; analyst-ready work is the output.

## Suggested Priorities

1. Add discovery report documentation and tests.
2. Add typed data gap and recommendation models.
3. Extend the harness status format to track unresolved gaps and active analysis goals.
4. Add transformation recommendation planning.
5. Add monitoring snapshots and comparison across runs.
6. Expose the highest-value methods through ChatGPT Actions and AWS deployment docs.

## Safety Boundaries

- Default to metadata-only analysis.
- Require explicit opt-in before sampling row data.
- Keep generated SQL reviewable before execution.
- Preserve Snowflake role permissions and never bypass warehouse access controls.
- Avoid storing credentials, raw customer data, or sensitive samples in harness memory.
- Mark uncertain relationships, transformation assumptions, and inferred business meaning clearly.
