import json
from pathlib import Path

from openai_snowflake_agent_context.agent_harness import (
    HarnessProgressUpdate,
    detect_status_mismatches,
    format_progress_update,
    find_latest_memory,
    initialize_agent_session,
    load_harness_config,
    load_next_work,
    load_status,
    publish_progress_update,
)
from openai_snowflake_agent_context.agent_harness_locations import LocationReaders


class FakeGoogleDocsProgress:
    def __init__(self) -> None:
        self.appended: list[tuple[str, str]] = []

    def append_document_text(self, document_id: str, text: str) -> None:
        self.appended.append((document_id, text))


def test_load_harness_config_resolves_paths_from_repo_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = tmp_path / "agent_harness.toml"
    config.write_text(
        f"""
[repo]
path = "{repo}"

[paths]
memory_dir = ".agent_harness/memory"
status_file = ".agent_harness/status.json"
work_file = ".agent_harness/work.md"
session_context_file = ".agent_harness/session_context.md"
""",
        encoding="utf-8",
    )

    loaded = load_harness_config(config)

    assert loaded.repo_path == repo.resolve()
    assert loaded.memory_dir == repo / ".agent_harness" / "memory"
    assert loaded.status_file == repo / ".agent_harness" / "status.json"
    assert loaded.work_file == repo / ".agent_harness" / "work.md"


def test_find_latest_memory_parses_status_and_work_id(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    old_memory = memory_dir / "2026-07-13.md"
    new_memory = memory_dir / "2026-07-14.md"
    old_memory.write_text("status: completed\nwork_id: WORK-1\n", encoding="utf-8")
    new_memory.write_text(
        "summary: Formatter implementation started\nstatus: in_progress\nwork_id: WORK-2\n",
        encoding="utf-8",
    )

    memory = find_latest_memory(memory_dir)

    assert memory.path == str(new_memory)
    assert memory.status == "in_progress"
    assert memory.work_id == "WORK-2"
    assert memory.summary == "Formatter implementation started"


def test_load_status_reads_json_status_file(tmp_path: Path) -> None:
    status_file = tmp_path / "status.json"
    status_file.write_text(
        json.dumps({"work_id": "WORK-2", "status": "blocked", "summary": "Waiting on schema"}),
        encoding="utf-8",
    )

    status = load_status(status_file)

    assert status["work_id"] == "WORK-2"
    assert status["status"] == "blocked"


def test_load_next_work_reads_first_unchecked_markdown_item(tmp_path: Path) -> None:
    work_file = tmp_path / "work.md"
    work_file.write_text(
        """
# Work Queue

- [x] WORK-1: Build initial scaffold
- [ ] WORK-2: Add formatter tests
- [ ] WORK-3: Implement formatter
""",
        encoding="utf-8",
    )

    next_work = load_next_work(work_file)

    assert next_work is not None
    assert next_work.work_id == "WORK-2"
    assert next_work.description == "Add formatter tests"


def test_detect_status_mismatches_flags_memory_status_and_work_queue_drift(
    tmp_path: Path,
) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    memory_file = memory_dir / "latest.md"
    memory_file.write_text("status: in_progress\nwork_id: WORK-2\n", encoding="utf-8")
    memory = find_latest_memory(memory_dir)
    next_work = load_next_work(_write_work_file(tmp_path, "- [ ] WORK-3: Add redaction tests\n"))

    warnings = detect_status_mismatches(
        memory,
        {"work_id": "WORK-4", "status": "blocked"},
        next_work,
    )

    assert "Memory work_id WORK-2 differs from status file work_id WORK-4" in warnings
    assert "Memory status in_progress differs from status file status blocked" in warnings
    assert "Next work item WORK-3 differs from status file work_id WORK-4" in warnings


def test_initialize_agent_session_writes_context_bundle(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    memory_dir = repo / ".agent_harness" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "latest.md").write_text(
        "summary: Query builder tests started\nstatus: in_progress\nwork_id: WORK-7\n",
        encoding="utf-8",
    )
    (repo / ".agent_harness" / "status.json").write_text(
        json.dumps({"work_id": "WORK-7", "status": "in_progress"}),
        encoding="utf-8",
    )
    (repo / ".agent_harness" / "work.md").write_text(
        "- [ ] WORK-7: Finish Snowflake query builder tests\n",
        encoding="utf-8",
    )
    config = tmp_path / "agent_harness.toml"
    config.write_text(
        f"""
[repo]
path = "{repo}"

[paths]
memory_dir = ".agent_harness/memory"
status_file = ".agent_harness/status.json"
work_file = ".agent_harness/work.md"
session_context_file = ".agent_harness/session_context.md"
""",
        encoding="utf-8",
    )

    report = initialize_agent_session(config)
    session_context = repo / ".agent_harness" / "session_context.md"

    assert report.next_work is not None
    assert report.next_work.work_id == "WORK-7"
    assert "Latest memory reports in_progress for WORK-7" in report.incomplete_work
    assert session_context.exists()
    assert "Finish Snowflake query builder tests" in session_context.read_text(encoding="utf-8")


def test_initialize_agent_session_references_sampled_table_from_status(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    harness_dir = repo / ".agent_harness"
    harness_dir.mkdir(parents=True)
    (harness_dir / "status.json").write_text(
        json.dumps(
            {
                "work_id": "WORK-8",
                "status": "in_progress",
                "sampled_table": "ANALYTICS.PUBLIC.ORDERS_SAMPLE",
            }
        ),
        encoding="utf-8",
    )
    (harness_dir / "work.md").write_text("", encoding="utf-8")
    config = tmp_path / "agent_harness.toml"
    config.write_text(
        f"""
[repo]
path = "{repo}"

[paths]
memory_dir = ".agent_harness/memory"
status_file = ".agent_harness/status.json"
work_file = ".agent_harness/work.md"
session_context_file = ".agent_harness/session_context.md"
""",
        encoding="utf-8",
    )

    report = initialize_agent_session(config)
    session_context = harness_dir / "session_context.md"

    assert "Sampled table: ANALYTICS.PUBLIC.ORDERS_SAMPLE" in report.summary_text()
    assert (
        "Sampled table: ANALYTICS.PUBLIC.ORDERS_SAMPLE"
        in session_context.read_text(encoding="utf-8")
    )


def test_format_progress_update_is_human_readable() -> None:
    text = format_progress_update(
        HarnessProgressUpdate(
            work_id="WORK-14",
            status="in_progress",
            message="Pulled metadata for 12 tables and started scoring descriptions.",
            details=(
                "7 columns are missing descriptions.",
                "3 descriptions are too generic for reliable agent analysis.",
            ),
            generated_at="2026-07-17T12:00:00+00:00",
        )
    )

    assert "## Agent Progress Update - 2026-07-17T12:00:00+00:00" in text
    assert "Status: in_progress" in text
    assert "Work ID: WORK-14" in text
    assert "- 7 columns are missing descriptions." in text


def test_publish_progress_update_appends_to_configured_google_doc(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = tmp_path / "agent_harness.toml"
    config.write_text(
        f"""
[repo]
path = "{repo}"

[locations]
progress = "gdoc://progress-doc"
""",
        encoding="utf-8",
    )
    loaded = load_harness_config(config)
    progress = FakeGoogleDocsProgress()

    publish_progress_update(
        loaded,
        HarnessProgressUpdate(
            work_id="WORK-15",
            status="completed",
            completed=True,
            message="Metadata description analysis completed.",
            generated_at="2026-07-17T12:30:00+00:00",
        ),
        readers=LocationReaders(google_docs_progress=progress),
    )

    assert progress.appended == [
        (
            "progress-doc",
            "\n".join(
                [
                    "",
                    "## Agent Progress Update - 2026-07-17T12:30:00+00:00",
                    "",
                    "Status: completed",
                    "Work ID: WORK-15",
                    "",
                    "Metadata description analysis completed.",
                    "",
                    "Completion: work marked complete.",
                    "",
                ]
            ),
        )
    ]


def test_publish_progress_update_requires_google_doc_location(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = tmp_path / "agent_harness.toml"
    config.write_text(
        f"""
[repo]
path = "{repo}"

[locations]
progress = ".agent_harness/progress.md"
""",
        encoding="utf-8",
    )
    loaded = load_harness_config(config)

    try:
        publish_progress_update(loaded, HarnessProgressUpdate(message="Started."))
    except ValueError as exc:
        assert "Google Doc" in str(exc)
    else:
        raise AssertionError("Expected ValueError for non-Google Doc progress location.")


def _write_work_file(tmp_path: Path, content: str) -> Path:
    work_file = tmp_path / "work.md"
    work_file.write_text(content, encoding="utf-8")
    return work_file
