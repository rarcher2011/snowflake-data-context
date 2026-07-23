"""File-based startup harness for long-running coding-agent sessions."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from sys import version_info
from typing import Any, cast

from .agent_harness_locations import (
    LocationReaders,
    LocationSpec,
    list_text_location,
    parse_google_doc_id,
    parse_location_spec,
    read_text_location,
)

if version_info >= (3, 11):
    import tomllib  # type: ignore[import-untyped]
else:
    import tomli as tomllib  # type: ignore[import-not-found]


STATUS_DONE_VALUES = {"done", "complete", "completed", "closed", "merged"}
STATUS_INCOMPLETE_VALUES = {
    "blocked",
    "in_progress",
    "in-progress",
    "open",
    "pending",
    "started",
    "todo",
}


@dataclass(frozen=True)
class HarnessConfig:
    """Resolved filesystem locations for a long-running agent harness."""

    repo_path: Path
    memory_dir: Path
    status_file: Path
    work_file: Path
    session_context_file: Path
    memory_location: LocationSpec | None = None
    status_location: LocationSpec | None = None
    work_location: LocationSpec | None = None
    config_location: LocationSpec | None = None
    progress_location: LocationSpec | None = None


@dataclass(frozen=True)
class MemoryRecord:
    """Latest memory file and parsed status hints."""

    path: str | None
    status: str | None
    work_id: str | None
    summary: str | None


@dataclass(frozen=True)
class WorkItem:
    """Current work item discovered from the configured work file."""

    work_id: str
    description: str
    checked: bool


@dataclass(frozen=True)
class HarnessReport:
    """Startup report used to restore context for a long-running agent."""

    repo_path: str
    config_path: str
    memory: MemoryRecord
    status: dict[str, Any]
    next_work: WorkItem | None
    incomplete_work: list[str]
    warnings: list[str]
    session_context_file: str
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary_text(self) -> str:
        sampled_table = _sampled_table_from_status(self.status)
        lines = [
            "Agent harness initialized",
            f"Repo: {self.repo_path}",
            f"Memory: {self.memory.path or 'none'}",
            f"Status: {self.status.get('status', 'unknown')}",
            f"Next work: {self.next_work.description if self.next_work else 'none'}",
            f"Session context: {self.session_context_file}",
        ]
        if sampled_table:
            lines.append(f"Sampled table: {sampled_table}")
        if self.incomplete_work:
            lines.append("Incomplete work:")
            lines.extend(f"- {item}" for item in self.incomplete_work)
        if self.warnings:
            lines.append("Warnings:")
            lines.extend(f"- {warning}" for warning in self.warnings)
        return "\n".join(lines)


@dataclass(frozen=True)
class HarnessProgressUpdate:
    """Human-readable progress update for a long-running agent run."""

    message: str
    work_id: str | None = None
    status: str | None = None
    completed: bool = False
    details: tuple[str, ...] = ()
    generated_at: str | None = None


def initialize_agent_session(
    config_path: Path | str,
    readers: LocationReaders | None = None,
) -> HarnessReport:
    """Load config, recover memory/status/work state, and write a context bundle."""

    resolved_config_path = Path(config_path)
    config = load_harness_config(resolved_config_path)
    warnings = validate_config(config)

    try:
        memory = find_latest_memory_from_location(config, readers)
    except RuntimeError as exc:
        warnings.append(str(exc))
        memory = find_latest_memory(config.memory_dir)

    try:
        status = load_status_from_location(config, readers)
    except RuntimeError as exc:
        warnings.append(str(exc))
        status = load_status(config.status_file)

    try:
        next_work = load_next_work_from_location(config, readers)
    except RuntimeError as exc:
        warnings.append(str(exc))
        next_work = load_next_work(config.work_file)

    incomplete_work = detect_incomplete_work(memory, status, next_work)
    warnings.extend(detect_status_mismatches(memory, status, next_work))

    generated_at = datetime.now(timezone.utc).isoformat()
    report = HarnessReport(
        repo_path=str(config.repo_path),
        config_path=str(resolved_config_path.resolve()),
        memory=memory,
        status=status,
        next_work=next_work,
        incomplete_work=incomplete_work,
        warnings=warnings,
        session_context_file=str(config.session_context_file),
        generated_at=generated_at,
    )
    write_session_context(config.session_context_file, report)
    return report


def load_harness_config(config_path: Path) -> HarnessConfig:
    """Load and resolve the TOML harness config."""

    resolved_config_path = config_path.resolve()
    raw = tomllib.loads(resolved_config_path.read_text(encoding="utf-8"))
    config_root = resolved_config_path.parent
    repo_path = _resolve_path(config_root, raw.get("repo", {}).get("path", "."))
    paths = raw.get("paths", {})
    locations = raw.get("locations", {})

    return HarnessConfig(
        repo_path=repo_path,
        memory_dir=_resolve_path(repo_path, paths.get("memory_dir", ".agent_harness/memory")),
        status_file=_resolve_path(repo_path, paths.get("status_file", ".agent_harness/status.json")),
        work_file=_resolve_path(repo_path, paths.get("work_file", ".agent_harness/work.md")),
        session_context_file=_resolve_path(
            repo_path,
            paths.get("session_context_file", ".agent_harness/session_context.md"),
        ),
        memory_location=_parse_optional_location(locations.get("memory"), repo_path),
        status_location=_parse_optional_location(locations.get("status"), repo_path),
        work_location=_parse_optional_location(locations.get("work"), repo_path),
        config_location=_parse_optional_location(locations.get("config"), repo_path),
        progress_location=_parse_optional_location(locations.get("progress"), repo_path),
    )


def validate_config(config: HarnessConfig) -> list[str]:
    """Return non-fatal startup warnings for missing configured resources."""

    warnings: list[str] = []
    if not config.repo_path.exists():
        warnings.append(f"Configured repo path does not exist: {config.repo_path}")
    if not config.memory_dir.exists():
        warnings.append(f"Memory directory not found: {config.memory_dir}")
    if not config.status_file.exists():
        warnings.append(f"Status file not found: {config.status_file}")
    if not config.work_file.exists():
        warnings.append(f"Work file not found: {config.work_file}")
    for label, location in (
        ("memory", config.memory_location),
        ("status", config.status_location),
        ("work", config.work_location),
        ("config", config.config_location),
        ("progress", config.progress_location),
    ):
        if location is not None and location.backend != "local":
            warnings.append(f"{label} is configured for remote backend {location.backend}: {location.uri}")
    return warnings


def publish_progress_update(
    config: HarnessConfig,
    update: HarnessProgressUpdate,
    readers: LocationReaders | None = None,
) -> None:
    """Append a human-readable progress update to the configured progress location."""

    if config.progress_location is None:
        raise RuntimeError("Progress update location is not configured.")
    if config.progress_location.backend != "google_doc":
        raise ValueError("Progress updates currently require a Google Doc location.")

    readers = readers or LocationReaders()
    progress_store = readers.google_docs_progress
    if progress_store is None:
        raise RuntimeError("Google Docs progress writer is not configured.")

    progress_store.append_document_text(
        parse_google_doc_id(config.progress_location.uri),
        format_progress_update(update),
    )


def format_progress_update(update: HarnessProgressUpdate) -> str:
    """Format one progress update for human readers in a shared Google Doc."""

    generated_at = update.generated_at or datetime.now(timezone.utc).isoformat()
    lines = [
        "",
        f"## Agent Progress Update - {generated_at}",
        "",
        f"Status: {update.status or 'in_progress'}",
    ]
    if update.work_id:
        lines.append(f"Work ID: {update.work_id}")
    lines.extend(["", update.message])
    if update.details:
        lines.extend(["", "Details:"])
        lines.extend(f"- {detail}" for detail in update.details)
    if update.completed:
        lines.extend(["", "Completion: work marked complete."])
    return "\n".join(lines) + "\n"


def find_latest_memory(memory_dir: Path) -> MemoryRecord:
    """Find the newest memory file and parse simple status hints from it."""

    if not memory_dir.exists():
        return MemoryRecord(path=None, status=None, work_id=None, summary=None)

    candidates = [
        path
        for path in memory_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".md", ".txt", ".json"}
    ]
    if not candidates:
        return MemoryRecord(path=None, status=None, work_id=None, summary=None)

    latest = max(candidates, key=lambda path: (path.stat().st_mtime, path.name))
    return parse_memory_text(str(latest), latest.read_text(encoding="utf-8"))


def find_latest_memory_from_location(
    config: HarnessConfig,
    readers: LocationReaders | None = None,
) -> MemoryRecord:
    """Find latest memory from configured local or remote location."""

    if config.memory_location is None:
        return find_latest_memory(config.memory_dir)

    objects = list_text_location(config.memory_location, readers)
    if not objects:
        return MemoryRecord(path=None, status=None, work_id=None, summary=None)
    latest = max(objects, key=lambda item: (item.updated_at, item.name))
    return parse_memory_text(latest.name, latest.text)


def parse_memory_text(name: str, text: str) -> MemoryRecord:
    """Parse status hints from one memory text payload."""

    status = _extract_labeled_value(text, "status")
    work_id = _extract_labeled_value(text, "work_id") or _extract_labeled_value(text, "work-id")
    summary = _extract_labeled_value(text, "summary")
    return MemoryRecord(path=name, status=status, work_id=work_id, summary=summary)


def load_status(status_file: Path) -> dict[str, Any]:
    """Load the last persisted status JSON file."""

    if not status_file.exists():
        return {}
    return cast(dict[str, Any], json.loads(status_file.read_text(encoding="utf-8")))


def load_status_from_location(
    config: HarnessConfig,
    readers: LocationReaders | None = None,
) -> dict[str, Any]:
    """Load status from configured local or remote location."""

    if config.status_location is None:
        return load_status(config.status_file)
    return cast(dict[str, Any], json.loads(read_text_location(config.status_location, readers)))


def load_next_work(work_file: Path) -> WorkItem | None:
    """Load the first unchecked work item from Markdown or a JSON work file."""

    if not work_file.exists():
        return None

    return parse_next_work_text(work_file.name, work_file.read_text(encoding="utf-8"))


def load_next_work_from_location(
    config: HarnessConfig,
    readers: LocationReaders | None = None,
) -> WorkItem | None:
    """Load next work from configured local or remote location."""

    if config.work_location is None:
        return load_next_work(config.work_file)
    return parse_next_work_text(
        config.work_location.uri,
        read_text_location(config.work_location, readers),
    )


def parse_next_work_text(source_name: str, text: str) -> WorkItem | None:
    """Parse first unfinished work item from Markdown or JSON text."""

    if source_name.lower().endswith(".json"):
        raw = json.loads(text)
        items = raw.get("items", raw if isinstance(raw, list) else [])
        for item in items:
            status = str(item.get("status", "pending")).lower()
            if status not in STATUS_DONE_VALUES:
                return WorkItem(
                    work_id=str(item.get("id", "work-1")),
                    description=str(item.get("description", "")),
                    checked=False,
                )
        return None

    for line in text.splitlines():
        match = re.match(r"^\s*[-*]\s+\[(?P<mark>[ xX])\]\s+(?P<body>.+?)\s*$", line)
        if not match or match.group("mark").lower() == "x":
            continue

        body = match.group("body")
        work_id, description = _split_work_item_body(body)
        return WorkItem(work_id=work_id, description=description, checked=False)

    return None


def detect_incomplete_work(
    memory: MemoryRecord,
    status: dict[str, Any],
    next_work: WorkItem | None,
) -> list[str]:
    """Describe work that appears unfinished across memory, status, and queue files."""

    incomplete: list[str] = []
    memory_status = (memory.status or "").lower()
    status_value = str(status.get("status", "")).lower()

    if memory.path and memory_status in STATUS_INCOMPLETE_VALUES:
        incomplete.append(
            f"Latest memory reports {memory.status}"
            + (f" for {memory.work_id}" if memory.work_id else "")
        )

    if status_value in STATUS_INCOMPLETE_VALUES:
        incomplete.append(
            f"Status file reports {status.get('status')}"
            + (f" for {status.get('work_id')}" if status.get("work_id") else "")
        )

    if next_work:
        incomplete.append(f"Work queue has next item {next_work.work_id}: {next_work.description}")

    return incomplete


def detect_status_mismatches(
    memory: MemoryRecord,
    status: dict[str, Any],
    next_work: WorkItem | None,
) -> list[str]:
    """Detect incoherent state between recovered files."""

    warnings: list[str] = []
    status_work_id = status.get("work_id")
    status_value = status.get("status")

    if memory.work_id and status_work_id and memory.work_id != status_work_id:
        warnings.append(
            f"Memory work_id {memory.work_id} differs from status file work_id {status_work_id}"
        )

    if memory.status and status_value and memory.status.lower() != str(status_value).lower():
        warnings.append(
            f"Memory status {memory.status} differs from status file status {status_value}"
        )

    if next_work and status_work_id and next_work.work_id != status_work_id:
        warnings.append(
            f"Next work item {next_work.work_id} differs from status file work_id {status_work_id}"
        )

    return warnings


def write_session_context(session_context_file: Path, report: HarnessReport) -> None:
    """Write a compact context bundle for the next agent context window."""

    session_context_file.parent.mkdir(parents=True, exist_ok=True)
    memory_path = str(report.memory.path) if report.memory.path else "none"
    next_work = report.next_work.description if report.next_work else "none"
    sampled_table = _sampled_table_from_status(report.status)

    lines = [
        "# Agent Session Context",
        "",
        f"Generated: {report.generated_at}",
        f"Repo: {report.repo_path}",
        f"Config: {report.config_path}",
        f"Latest memory: {memory_path}",
        f"Memory status: {report.memory.status or 'unknown'}",
        f"Memory work_id: {report.memory.work_id or 'unknown'}",
        f"Status file state: {report.status.get('status', 'unknown')}",
        f"Status file work_id: {report.status.get('work_id', 'unknown')}",
        f"Next work: {next_work}",
        f"Sampled table: {sampled_table or 'none'}",
        "",
        "## Incomplete Work",
        "",
    ]
    lines.extend(f"- {item}" for item in report.incomplete_work)
    if not report.incomplete_work:
        lines.append("- none detected")

    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in report.warnings)
    if not report.warnings:
        lines.append("- none")

    session_context_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resolve_path(base_path: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_path / path).resolve()


def _parse_optional_location(raw: object | None, base_path: Path) -> LocationSpec | None:
    if raw is None:
        return None
    return parse_location_spec(raw, base_path)


def _extract_labeled_value(text: str, label: str) -> str | None:
    pattern = re.compile(rf"^\s*{re.escape(label)}\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE)
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            return match.group("value").strip()
    return None


def _split_work_item_body(body: str) -> tuple[str, str]:
    if ":" in body:
        work_id, description = body.split(":", 1)
        return work_id.strip(), description.strip()
    words = body.split(maxsplit=1)
    if len(words) == 2 and re.match(r"^[A-Za-z]+-\d+$", words[0]):
        return words[0], words[1]
    return "work-1", body.strip()


def _sampled_table_from_status(status: dict[str, Any]) -> str | None:
    for key in (
        "sampled_table",
        "sampled_table_identifier",
        "destination_table",
        "destination_location",
    ):
        value = status.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    sample = status.get("sample")
    if isinstance(sample, dict):
        return _sampled_table_from_status(cast(dict[str, Any], sample))
    return None
