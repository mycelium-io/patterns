"""Validate every scenario under scenarios/ with the hub's own checks.

The hub decides what a scenario is and what fits (`app/services/patterns.py`),
so this loads each one through that same code rather than a copy of it: the
scenario's shape, the flow it runs parsed with the hub's `Protocol` model, and
the cast fitted to the flow's roles. A scenario that passes here loads on a hub.

It also says which scenarios a public hub can offer. A hub set to
`patterns.personas_only` refuses any member that is not a persona or a person.

Run it with the backend's environment so the hub's code is what checks:

    uv run --project ../mycelium/fastapi-backend python scripts/validate.py
    uv run --project ../mycelium/fastapi-backend python scripts/validate.py --emit-schema

MYCELIUM_BACKEND overrides where the backend checkout is.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BACKEND = Path(os.environ.get("MYCELIUM_BACKEND", ROOT.parent / "mycelium" / "fastapi-backend"))
sys.path.insert(0, str(BACKEND))

from app.services import patterns  # noqa: E402


def check(folder: Path) -> tuple[list[str], bool]:
    """Why a scenario does not load, and whether a personas-only hub would take it."""
    try:
        data = yaml.safe_load((folder / "scenario.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return [f"scenario.yaml cannot be read: {exc}"], False
    if not isinstance(data, dict):
        return ["scenario.yaml is not a mapping"], False
    problems: list[str] = []
    if data.get("pattern") != folder.name:
        problems.append(f"pattern {data.get('pattern')!r} must match its folder {folder.name!r}")

    flow_body = None
    flow_file = data.get("flow_file")
    if isinstance(flow_file, str):
        flow_path = (folder / flow_file).resolve()
        if folder.resolve() not in flow_path.parents or not flow_path.is_file():
            problems.append(f"flow_file {flow_file!r} is not a file in the scenario's folder")
        else:
            flow_body = flow_path.read_text(encoding="utf-8")

    try:
        patterns.parse(data, flow_body, personas_only=False)
    except patterns.PatternInvalid as exc:
        problems += exc.problems
    if problems:
        return problems, False
    try:
        patterns.parse(data, flow_body, personas_only=True)
    except patterns.PatternInvalid:
        return [], False
    return [], True


def main() -> int:
    if "--emit-schema" in sys.argv:
        print(json.dumps(patterns.Scenario.model_json_schema(), indent=2))
        return 0
    folders = sorted(p.parent for p in (ROOT / "scenarios").glob("*/scenario.yaml"))
    if not folders:
        print("no scenarios found")
        return 1
    failed = 0
    for folder in folders:
        problems, public = check(folder)
        if problems:
            failed += 1
            print(f"FAIL {folder.name}")
            for problem in problems:
                print(f"       {problem}")
        else:
            print(f"ok   {folder.name}" + ("" if public else "   (not for a personas-only hub)"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
