"""Location adapters for long-running agent harness state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar
from urllib.parse import urlparse


SUPPORTED_REMOTE_BACKENDS = {"s3", "gcs", "google_doc"}
ReaderT = TypeVar("ReaderT")


@dataclass(frozen=True)
class LocationSpec:
    """Configured location for harness memory, status, work, or config data."""

    backend: str
    uri: str
    description: str | None = None


@dataclass(frozen=True)
class TextObject:
    """Text content with a stable name used for latest-memory selection."""

    name: str
    text: str
    updated_at: float = 0.0


@dataclass(frozen=True)
class ParsedCloudUri:
    """Bucket and key/prefix parts from an object-store URI."""

    bucket: str
    key: str


class TextObjectStore(Protocol):
    """Minimal protocol implemented by S3 and Google Cloud Storage adapters."""

    def read_text(self, bucket: str, key: str) -> str:
        """Read one UTF-8 text object."""

    def list_text_objects(self, bucket: str, prefix: str) -> list[TextObject]:
        """List text objects under a prefix."""


class GoogleDocStore(Protocol):
    """Minimal protocol for reading Google Docs as plain text."""

    def read_document_text(self, document_id: str) -> str:
        """Read one Google Doc as text."""


class GoogleDocProgressStore(Protocol):
    """Minimal protocol for appending human-readable Google Doc progress updates."""

    def append_document_text(self, document_id: str, text: str) -> None:
        """Append text to one Google Doc."""


@dataclass(frozen=True)
class LocationReaders:
    """Optional remote readers supplied by the caller or integration layer."""

    s3: TextObjectStore | None = None
    gcs: TextObjectStore | None = None
    google_docs: GoogleDocStore | None = None
    google_docs_progress: GoogleDocProgressStore | None = None


def parse_location_spec(raw: object, base_path: Path) -> LocationSpec:
    """Parse a TOML location value into a normalized `LocationSpec`."""

    if isinstance(raw, str):
        return _location_from_uri(raw, base_path)

    if not isinstance(raw, dict):
        raise TypeError("Location config must be a string URI or table.")

    backend = str(raw.get("backend", "")).strip().lower()
    uri = str(raw.get("uri", "")).strip()
    description = raw.get("description")
    if not backend and uri:
        return _location_from_uri(uri, base_path)
    if backend == "local":
        return LocationSpec(backend="local", uri=str(_resolve_local(base_path, uri)))
    if backend not in SUPPORTED_REMOTE_BACKENDS:
        raise ValueError(f"Unsupported harness location backend: {backend}")
    if not uri:
        raise ValueError(f"Harness location for backend {backend} requires a uri.")
    return LocationSpec(
        backend=backend,
        uri=uri,
        description=str(description) if description is not None else None,
    )


def read_text_location(location: LocationSpec, readers: LocationReaders | None = None) -> str:
    """Read one configured text location."""

    readers = readers or LocationReaders()
    if location.backend == "local":
        return Path(location.uri).read_text(encoding="utf-8")
    if location.backend == "s3":
        store = _require_reader(readers.s3, "S3")
        parsed = parse_object_store_uri(location.uri, expected_scheme="s3")
        return store.read_text(parsed.bucket, parsed.key)
    if location.backend == "gcs":
        gcs_store = _require_reader(readers.gcs, "Google Cloud Storage")
        parsed = parse_object_store_uri(location.uri, expected_scheme="gs")
        return gcs_store.read_text(parsed.bucket, parsed.key)
    if location.backend == "google_doc":
        docs_store = _require_reader(readers.google_docs, "Google Docs")
        return docs_store.read_document_text(parse_google_doc_id(location.uri))
    raise ValueError(f"Unsupported harness location backend: {location.backend}")


def list_text_location(location: LocationSpec, readers: LocationReaders | None = None) -> list[TextObject]:
    """List text objects for a configured memory directory/prefix location."""

    readers = readers or LocationReaders()
    if location.backend == "local":
        path = Path(location.uri)
        if not path.exists():
            return []
        return [
            TextObject(name=str(candidate), text=candidate.read_text(encoding="utf-8"), updated_at=0.0)
            for candidate in sorted(path.iterdir())
            if candidate.is_file() and candidate.suffix.lower() in {".md", ".txt", ".json"}
        ]
    if location.backend == "s3":
        store = _require_reader(readers.s3, "S3")
        parsed = parse_object_store_uri(location.uri, expected_scheme="s3")
        return store.list_text_objects(parsed.bucket, parsed.key)
    if location.backend == "gcs":
        store = _require_reader(readers.gcs, "Google Cloud Storage")
        parsed = parse_object_store_uri(location.uri, expected_scheme="gs")
        return store.list_text_objects(parsed.bucket, parsed.key)
    if location.backend == "google_doc":
        return [
            TextObject(
                name=location.uri,
                text=read_text_location(location, readers),
                updated_at=0.0,
            )
        ]
    raise ValueError(f"Unsupported harness location backend: {location.backend}")


def parse_object_store_uri(uri: str, expected_scheme: str) -> ParsedCloudUri:
    """Parse an S3 or GCS URI into bucket and key/prefix."""

    parsed = urlparse(uri)
    if parsed.scheme != expected_scheme:
        raise ValueError(f"Expected {expected_scheme} URI, got: {uri}")
    if not parsed.netloc:
        raise ValueError(f"Object-store URI requires a bucket: {uri}")
    key = parsed.path.lstrip("/")
    if not key:
        raise ValueError(f"Object-store URI requires a key or prefix: {uri}")
    return ParsedCloudUri(bucket=parsed.netloc, key=key)


def parse_google_doc_id(uri: str) -> str:
    """Extract a Google Doc ID from a document URI or raw document ID."""

    if uri.startswith("gdoc://"):
        return uri.removeprefix("gdoc://").strip("/")
    if uri.startswith("google-doc://"):
        return uri.removeprefix("google-doc://").strip("/")
    if "docs.google.com/document/d/" in uri:
        after_marker = uri.split("docs.google.com/document/d/", 1)[1]
        return after_marker.split("/", 1)[0]
    return uri


def _location_from_uri(uri: str, base_path: Path) -> LocationSpec:
    if uri.startswith("s3://"):
        return LocationSpec(backend="s3", uri=uri)
    if uri.startswith("gs://"):
        return LocationSpec(backend="gcs", uri=uri)
    if uri.startswith(("gdoc://", "google-doc://")) or "docs.google.com/document/d/" in uri:
        return LocationSpec(backend="google_doc", uri=uri)
    return LocationSpec(backend="local", uri=str(_resolve_local(base_path, uri)))


def _resolve_local(base_path: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_path / path).resolve()


def _require_reader(reader: ReaderT | None, name: str) -> ReaderT:
    if reader is None:
        raise RuntimeError(f"{name} reader is not configured for this harness location.")
    return reader
