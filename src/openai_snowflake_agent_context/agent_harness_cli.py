"""Console entrypoint for the long-running agent harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent_harness import initialize_agent_session


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recover long-running agent memory, status, and next work context."
    )
    parser.add_argument(
        "--config",
        default="agent_harness.toml",
        help="Path to the harness TOML config. Defaults to agent_harness.toml.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full session report as JSON.",
    )
    args = parser.parse_args()

    report = initialize_agent_session(Path(args.config))
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(report.summary_text())
    return 0

