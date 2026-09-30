# API Endpoints Todo

## Planned Endpoints

- [ ] `POST /api/snowflake/data-gaps` — identify tables or columns with missing, weak, or inconsistent data based on schema metadata and sampled content
- [ ] `POST /api/snowflake/transformation-candidates` — surface tables that are good candidates for transformation or modelling based on structure, relationships, and description coverage
- [ ] `POST /api/snowflake/monitoring-snapshot` — generate a point-in-time snapshot of schema health: row count trends, description coverage, and data quality indicators

## Claude and ChatGPT Integration

- [ ] `GET /api/context/schema-summary` — return a compact, token-efficient summary of the selected schema (table names, row counts, column counts, description coverage) suitable for injecting into a Claude or ChatGPT system prompt or tool result
- [ ] `GET /api/context/table-detail` — return full column metadata, relationships, and description coverage for a single table in a flat format ready for an LLM context window; replaces the need for callers to chain `/table-metadata` and `/description-analysis` themselves
