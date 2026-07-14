"""File-based startup harness for long-running coding-agent sessions."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from sys import version_info
from typing import Any, cast

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


@dataclass(frozen=True)
class MemoryRecord:
    """Latest memory file and parsed status hints."""

    path: Path | None
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
        lines = [
            "Agent harness initialized",
            f"Repo: {self.repo_path}",
            f"Memory: {self.memory.path or 'none'}",
            f"Status: {self.status.get('status', 'unknown')}",
            f"Next work: {self.next_work.description if self.next_work else 'none'}",
            f"Session context: {self.session_context_file}",
        ]
        if self.incomplete_work:
            lines.append("Incomplete work:")
            lines.extend(f"- {item}" for item in self.incomplete_work)
        if self.warnings:
            lines.append("Warnings:")
            lines.extend(f"- {warning}" for warning in self.warnings)
        return "\n".join(lines)


def initialize_agent_session(config_path: Path) -> HarnessReport:
    """Load config, recover memory/status/work state, and write a context bundle."""

    config = load_harness_config(config_path)
    warnings = validate_config(config)
    memory = find_latest_memory(config.memory_dir)
    status = load_status(config.status_file)
    next_work = load_next_work(config.work_file)
    incomplete_work = detect_incomplete_work(memory, status, next_work)
    warnings.extend(detect_status_mismatches(memory, status, next_work))

    generated_at = datetime.now(timezone.utc).isoformat()
    report = HarnessReport(
        repo_path=str(config.repo_path),
        config_path=str(config_path.resolve()),
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

    return HarnessConfig(
        repo_path=repo_path,
        memory_dir=_resolve_path(repo_path, paths.get("memory_dir", ".agent_harness/memory")),
        status_file=_resolve_path(repo_path, paths.get("status_file", ".agent_harness/status.json")),
        work_file=_resolve_path(repo_path, paths.get("work_file", ".agent_harness/work.md")),
        session_context_file=_resolve_path(
            repo_path,
            paths.get("session_context_file", ".agent_harness/session_context.md"),
        ),
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
    return warnings


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
    text = latest.read_text(encoding="utf-8")
    status = _extract_labeled_value(text, "status")
    work_id = _extract_labeled_value(text, "work_id") or _extract_labeled_value(text, "work-id")
    summary = _extract_labeled_value(text, "summary")
    return MemoryRecord(path=latest, status=status, work_id=work_id, summary=summary)


def load_status(status_file: Path) -> dict[str, Any]:
    """Load the last persisted status JSON file."""

    if not status_file.exists():
        return {}
    return cast(dict[str, Any], json.loads(status_file.read_text(encoding="utf-8")))


def load_next_work(work_file: Path) -> WorkItem | None:
    """Load the first unchecked work item from Markdown or a JSON work file."""

    if not work_file.exists():
        return None

    if work_file.suffix.lower() == ".json":
        raw = json.loads(work_file.read_text(encoding="utf-8"))
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

    for line in work_file.read_text(encoding="utf-8").splitlines():
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
