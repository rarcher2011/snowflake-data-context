from datetime import datetime, timezone
from io import BytesIO

from openai_snowflake_agent_context.agent_harness_cloud import (
    Boto3S3TextStore,
    GoogleCloudStorageTextStore,
    GoogleDocsTextStore,
    extract_google_doc_text,
)


class FakePaginator:
    def paginate(self, **kwargs: object) -> list[dict[str, object]]:
        assert kwargs == {"Bucket": "agent-state", "Prefix": "memory/"}
        return [
            {
                "Contents": [
                    {
                        "Key": "memory/latest.md",
                        "LastModified": datetime(2026, 7, 14, tzinfo=timezone.utc),
                    },
                    {"Key": "memory/image.png"},
                ]
            }
        ]


class FakeS3Client:
    def get_object(self, **kwargs: str) -> dict[str, BytesIO]:
        assert kwargs == {"Bucket": "agent-state", "Key": "memory/latest.md"}
        return {"Body": BytesIO(b"status: in_progress\nwork_id: WORK-11\n")}

    def get_paginator(self, name: str) -> FakePaginator:
        assert name == "list_objects_v2"
        return FakePaginator()


def test_boto3_s3_text_store_reads_and_lists_text_objects() -> None:
    store = Boto3S3TextStore(FakeS3Client())

    objects = store.list_text_objects("agent-state", "memory/")

    assert len(objects) == 1
    assert objects[0].name == "s3://agent-state/memory/latest.md"
    assert objects[0].text == "status: in_progress\nwork_id: WORK-11\n"
    assert objects[0].updated_at > 0


class FakeBlob:
    name = "memory/latest.md"
    updated = datetime(2026, 7, 14, tzinfo=timezone.utc)

    def download_as_text(self) -> str:
        return "status: blocked\nwork_id: WORK-12\n"


class FakeBucket:
    def blob(self, key: str) -> FakeBlob:
        assert key == "memory/latest.md"
        return FakeBlob()


class FakeStorageClient:
    def bucket(self, bucket: str) -> FakeBucket:
        assert bucket == "agent-state"
        return FakeBucket()

    def list_blobs(self, bucket: str, prefix: str) -> list[FakeBlob]:
        assert bucket == "agent-state"
        assert prefix == "memory/"
        return [FakeBlob()]


def test_google_cloud_storage_text_store_reads_and_lists_text_objects() -> None:
    store = GoogleCloudStorageTextStore(FakeStorageClient())

    assert store.read_text("agent-state", "memory/latest.md") == "status: blocked\nwork_id: WORK-12\n"
    objects = store.list_text_objects("agent-state", "memory/")

    assert objects[0].name == "gs://agent-state/memory/latest.md"
    assert objects[0].updated_at > 0


class FakeDocsExecute:
    def execute(self) -> dict[str, object]:
        return {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {"textRun": {"content": "status: in_progress\n"}},
                                {"textRun": {"content": "work_id: WORK-13\n"}},
                            ]
                        }
                    }
                ]
            }
        }


class FakeDocuments:
    def get(self, **kwargs: str) -> FakeDocsExecute:
        assert kwargs == {"documentId": "doc-13"}
        return FakeDocsExecute()


class FakeDocsService:
    def documents(self) -> FakeDocuments:
        return FakeDocuments()


def test_google_docs_text_store_extracts_plain_text() -> None:
    store = GoogleDocsTextStore(FakeDocsService())

    assert store.read_document_text("doc-13") == "status: in_progress\nwork_id: WORK-13\n"


def test_extract_google_doc_text_ignores_non_paragraph_content() -> None:
    text = extract_google_doc_text(
        {
            "body": {
                "content": [
                    {"sectionBreak": {}},
                    {"paragraph": {"elements": [{"textRun": {"content": "hello"}}]}},
                ]
            }
        }
    )

    assert text == "hello"
