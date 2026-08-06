"""Run deterministic evaluations for the orchestrator layer."""

from __future__ import annotations

import argparse
import json

from openai_snowflake_agent_context import run_orchestrator_evaluation


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate deterministic orchestrator routing and planning behavior."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args()

    result = run_orchestrator_evaluation()
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(result.to_markdown())
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
