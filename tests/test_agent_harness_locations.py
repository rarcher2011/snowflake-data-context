import json
from pathlib import Path

from openai_snowflake_agent_context.agent_harness import (
    initialize_agent_session,
    load_harness_config,
)
from openai_snowflake_agent_context.agent_harness_locations import (
    LocationReaders,
    TextObject,
    parse_google_doc_id,
    parse_location_spec,
    parse_object_store_uri,
)


class FakeObjectStore:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], str] = {}
        self.listings: dict[tuple[str, str], list[TextObject]] = {}

    def read_text(self, bucket: str, key: str) -> str:
        return self.objects[(bucket, key)]

    def list_text_objects(self, bucket: str, prefix: str) -> list[TextObject]:
        return self.listings[(bucket, prefix)]


class FakeGoogleDocs:
    def __init__(self, documents: dict[str, str]) -> None:
        self.documents = documents

    def read_document_text(self, document_id: str) -> str:
        return self.documents[document_id]


def test_parse_location_spec_detects_supported_remote_backends(tmp_path: Path) -> None:
    assert parse_location_spec("s3://agent-state/memory/", tmp_path).backend == "s3"
    assert parse_location_spec("gs://agent-state/status.json", tmp_path).backend == "gcs"
    assert parse_location_spec("gdoc://doc-123", tmp_path).backend == "google_doc"
    assert parse_location_spec("local/status.json", tmp_path).backend == "local"


def test_parse_object_store_uri_validates_bucket_and_key() -> None:
    parsed = parse_object_store_uri("s3://agent-state/memory/latest.md", expected_scheme="s3")

    assert parsed.bucket == "agent-state"
    assert parsed.key == "memory/latest.md"


def test_parse_google_doc_id_accepts_raw_custom_and_share_urls() -> None:
    assert parse_google_doc_id("doc-123") == "doc-123"
    assert parse_google_doc_id("gdoc://doc-123") == "doc-123"
    assert (
        parse_google_doc_id("https://docs.google.com/document/d/doc-123/edit")
        == "doc-123"
    )


def test_harness_uses_s3_memory_and_gcs_status_locations(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    work_file = repo / ".agent_harness" / "work.md"
    work_file.parent.mkdir()
    work_file.write_text("- [ ] WORK-9: Reconcile remote memory\n", encoding="utf-8")
    config = tmp_path / "agent_harness.toml"
    config.write_text(
        f"""
[repo]
path = "{repo}"

[paths]
work_file = ".agent_harness/work.md"
session_context_file = ".agent_harness/session_context.md"

[locations]
memory = "s3://agent-state/memory/"
status = "gs://agent-state/status.json"
""",
        encoding="utf-8",
    )
    s3 = FakeObjectStore()
    s3.listings[("agent-state", "memory/")] = [
        TextObject(
            name="s3://agent-state/memory/old.md",
            text="status: completed\nwork_id: WORK-8\n",
            updated_at=1.0,
        ),
        TextObject(
            name="s3://agent-state/memory/latest.md",
            text="summary: Cloud memory loaded\nstatus: in_progress\nwork_id: WORK-9\n",
            updated_at=2.0,
        ),
    ]
    gcs = FakeObjectStore()
    gcs.objects[("agent-state", "status.json")] = json.dumps(
        {"work_id": "WORK-9", "status": "in_progress"}
    )

    report = initialize_agent_session(config, readers=LocationReaders(s3=s3, gcs=gcs))

    assert report.memory.path == "s3://agent-state/memory/latest.md"
    assert report.memory.summary == "Cloud memory loaded"
    assert report.status["work_id"] == "WORK-9"
    assert report.next_work is not None
    assert report.next_work.work_id == "WORK-9"


def test_harness_uses_google_doc_as_work_location(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = tmp_path / "agent_harness.toml"
    config.write_text(
        f"""
[repo]
path = "{repo}"

[paths]
session_context_file = ".agent_harness/session_context.md"

[locations]
work = "gdoc://doc-work"
""",
        encoding="utf-8",
    )
    docs = FakeGoogleDocs({"doc-work": "- [ ] WORK-10: Continue from shared doc\n"})

    report = initialize_agent_session(config, readers=LocationReaders(google_docs=docs))

    assert report.next_work is not None
    assert report.next_work.work_id == "WORK-10"
    assert report.next_work.description == "Continue from shared doc"


def test_config_can_declare_remote_config_location_for_bootstrap_metadata(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = tmp_path / "agent_harness.toml"
    config.write_text(
        f"""
[repo]
path = "{repo}"

[locations.config]
backend = "google_doc"
uri = "https://docs.google.com/document/d/config-doc-123/edit"
description = "Shared harness bootstrap configuration"
""",
        encoding="utf-8",
    )

    loaded = load_harness_config(config)

    assert loaded.config_location is not None
    assert loaded.config_location.backend == "google_doc"
    assert loaded.config_location.description == "Shared harness bootstrap configuration"

