"""Cloud client adapters for the long-running agent harness."""

from __future__ import annotations

from typing import Any, cast

from .agent_harness_locations import TextObject


class Boto3S3TextStore:
    """S3 text store backed by a boto3 S3 client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def read_text(self, bucket: str, key: str) -> str:
        response = self._client.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read()
        if isinstance(body, str):
            return body
        return cast(str, body.decode("utf-8"))

    def list_text_objects(self, bucket: str, prefix: str) -> list[TextObject]:
        objects: list[TextObject] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item["Key"]
                if not _is_text_name(key):
                    continue
                objects.append(
                    TextObject(
                        name=f"s3://{bucket}/{key}",
                        text=self.read_text(bucket, key),
                        updated_at=_timestamp_or_zero(item.get("LastModified")),
                    )
                )
        return objects


class GoogleCloudStorageTextStore:
    """Google Cloud Storage text store backed by a google-cloud-storage client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def read_text(self, bucket: str, key: str) -> str:
        return str(self._client.bucket(bucket).blob(key).download_as_text())

    def list_text_objects(self, bucket: str, prefix: str) -> list[TextObject]:
        objects: list[TextObject] = []
        for blob in self._client.list_blobs(bucket, prefix=prefix):
            if not _is_text_name(blob.name):
                continue
            objects.append(
                TextObject(
                    name=f"gs://{bucket}/{blob.name}",
                    text=str(blob.download_as_text()),
                    updated_at=_timestamp_or_zero(getattr(blob, "updated", None)),
                )
            )
        return objects


class GoogleDocsTextStore:
    """Google Docs text store backed by a Google Docs API service object."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def read_document_text(self, document_id: str) -> str:
        document = self._service.documents().get(documentId=document_id).execute()
        return extract_google_doc_text(document)

    def append_document_text(self, document_id: str, text: str) -> None:
        document = self._service.documents().get(documentId=document_id).execute()
        insert_index = _append_index(document)
        self._service.documents().batchUpdate(
            documentId=document_id,
            body={
                "requests": [
                    {
                        "insertText": {
                            "location": {"index": insert_index},
                            "text": text,
                        }
                    }
                ]
            },
        ).execute()


def build_boto3_s3_text_store(**client_kwargs: Any) -> Boto3S3TextStore:
    """Build an S3 text store using boto3, imported only when requested."""

    import boto3  # type: ignore[import-untyped]

    return Boto3S3TextStore(boto3.client("s3", **client_kwargs))


def build_google_cloud_storage_text_store(**client_kwargs: Any) -> GoogleCloudStorageTextStore:
    """Build a GCS text store using google-cloud-storage, imported only when requested."""

    from google.cloud import storage  # type: ignore[import-not-found]

    return GoogleCloudStorageTextStore(storage.Client(**client_kwargs))


def build_google_docs_text_store(service: Any) -> GoogleDocsTextStore:
    """Build a Google Docs text store from an authenticated Docs API service."""

    return GoogleDocsTextStore(service)


def extract_google_doc_text(document: dict[str, Any]) -> str:
    """Extract plain text from a Google Docs API document response."""

    chunks: list[str] = []
    for content in document.get("body", {}).get("content", []):
        paragraph = content.get("paragraph")
        if not paragraph:
            continue
        for element in paragraph.get("elements", []):
            text_run = element.get("textRun")
            if text_run and "content" in text_run:
                chunks.append(str(text_run["content"]))
    return "".join(chunks)


def _append_index(document: dict[str, Any]) -> int:
    content = document.get("body", {}).get("content", [])
    if not content:
        return 1
    last = content[-1]
    end_index = last.get("endIndex")
    if isinstance(end_index, int) and end_index > 1:
        return end_index - 1
    return 1


def _is_text_name(name: str) -> bool:
    return name.lower().endswith((".md", ".txt", ".json"))


def _timestamp_or_zero(value: Any) -> float:
    if value is None:
        return 0.0
    timestamp = getattr(value, "timestamp", None)
    if callable(timestamp):
        return float(timestamp())
    return 0.0
