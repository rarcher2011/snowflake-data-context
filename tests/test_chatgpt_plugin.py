from openai_snowflake_agent_context.chatgpt_plugin import (
    MetadataAnalysisRequest,
    ProgressUpdateRequest,
    SampleTableRequest,
    build_ai_plugin_manifest,
    build_openapi_schema,
    execute_sample_table,
    execute_format_progress_update,
    execute_metadata_description_analysis,
)


class FakeCursor:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> object:
        self.executed_sql.append(sql)
        return self


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


def test_execute_metadata_description_analysis_returns_agent_quality_report() -> None:
    payload = MetadataAnalysisRequest.model_validate(
        {
            "tables": [
                {
                    "database": "ANALYTICS",
                    "schema": "PUBLIC",
                    "name": "ORDERS",
                    "kind": "TABLE",
                    "description": "Order fact table with one row per customer order.",
                    "columns": [
                        "ORDER_ID NUMBER -- Unique identifier for an order from the commerce system.",
                        "CUSTOMER_ID NUMBER",
                    ],
                }
            ]
        }
    )

    result = execute_metadata_description_analysis(payload)

    assert result["total_tables"] == 1
    assert result["total_columns"] == 2
    assert result["missing_column_descriptions"] == 1
    assert result["tables"][0]["table_identifier"] == "ANALYTICS.PUBLIC.ORDERS"


def test_execute_format_progress_update_returns_formatted_text() -> None:
    payload = ProgressUpdateRequest(
        work_id="WORK-20",
        status="completed",
        completed=True,
        message="Finished metadata description analysis.",
        details=["4 columns need better descriptions."],
        generated_at="2026-07-18T12:00:00+00:00",
    )

    result = execute_format_progress_update(payload)

    assert result["text"].startswith("\n## Agent Progress Update - 2026-07-18T12:00:00+00:00")
    assert "Status: completed" in result["text"]
    assert "Completion: work marked complete." in result["text"]


def test_execute_sample_table_returns_sampled_table_status_fields() -> None:
    connection = FakeConnection()
    payload = SampleTableRequest(
        table_name="ANALYTICS.PUBLIC.ORDERS",
        destination_location="ANALYTICS.PUBLIC.ORDERS_SAMPLE",
    )

    result = execute_sample_table(payload, connection)

    assert result["sampled_table"] == "ANALYTICS.PUBLIC.ORDERS_SAMPLE"
    assert result["sample_percent"] == 1.0
    assert connection.cursor_instance.executed_sql == [result["sql"]]


def test_build_openapi_schema_exposes_chatgpt_callable_operations() -> None:
    schema = build_openapi_schema("https://actions.example.com")

    assert schema["openapi"] == "3.1.0"
    assert schema["servers"] == [{"url": "https://actions.example.com"}]
    assert (
        schema["paths"]["/metadata/description-analysis"]["post"]["operationId"]
        == "analyzeMetadataDescriptions"
    )
    assert (
        schema["paths"]["/metadata/sample-table"]["post"]["operationId"]
        == "sampleSnowflakeTable"
    )
    assert (
        schema["paths"]["/harness/progress-updates/format"]["post"]["operationId"]
        == "formatHarnessProgressUpdate"
    )


def test_build_ai_plugin_manifest_points_to_openapi_schema() -> None:
    manifest = build_ai_plugin_manifest("https://actions.example.com/openapi.json")

    assert manifest["schema_version"] == "v1"
    assert manifest["name_for_model"] == "snowflake_agent_context"
    assert manifest["api"]["url"] == "https://actions.example.com/openapi.json"
