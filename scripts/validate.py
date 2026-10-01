"""Validate every scenario under scenarios/.

A scenario is checked as data (its own shape), then against Mycelium itself:
the flow it names must parse with the hub's own `Protocol` model, and the cast
must fit the flow's roles. Run it with the backend's environment so the
protocol model is the hub's, not a copy:

    uv run --project ../mycelium/fastapi-backend python scripts/validate.py
    uv run --project ../mycelium/fastapi-backend python scripts/validate.py --emit-schema

MYCELIUM_BACKEND overrides where the backend checkout is.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ROOT = Path(__file__).resolve().parent.parent
BACKEND = Path(os.environ.get("MYCELIUM_BACKEND", ROOT.parent / "mycelium" / "fastapi-backend"))
sys.path.insert(0, str(BACKEND))

from app.services.protocols import BUILTIN_PROTOCOLS, parse_protocol  # noqa: E402

SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

#: Kinds a scenario may cast. `conductor` is implicit (the loader registers it),
#: and `human` is the person loading the scenario.
Kind = Literal["persona", "worker", "aligner", "synthesizer", "hello", "human"]

#: Kinds a flow can ask a question of.
ASKABLE = {"persona", "worker", "human"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Context(Strict):
    key: str
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def _under_context(self) -> Context:
        if not self.key.startswith("context/") or not SLUG.match(self.key.removeprefix("context/")):
            msg = f"context key {self.key!r} must be context/<slug>"
            raise ValueError(msg)
        return self


class Member(Strict):
    handle: str
    kind: Kind
    description: str = ""
    notes: str = ""

    @model_validator(mode="after")
    def _shape(self) -> Member:
        if not SLUG.match(self.handle) or self.handle == "conductor":
            msg = f"handle {self.handle!r} must be a lowercase slug and not 'conductor'"
            raise ValueError(msg)
        if self.kind in ("persona", "worker") and not self.notes.strip():
            msg = f"{self.kind} {self.handle!r} needs notes: they are its character"
            raise ValueError(msg)
        if self.kind == "human" and self.notes:
            msg = f"human {self.handle!r} takes no notes"
            raise ValueError(msg)
        return self


class Task(Strict):
    title: str = Field(min_length=1, max_length=200)
    body: str = ""


class Summon(Strict):
    flow: str
    members: list[str] = Field(min_length=1)
    ask: str = Field(min_length=1)


class Room(Strict):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=500)


class Scenario(Strict):
    pattern: str
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=300)
    room: Room
    context: list[Context] = Field(default_factory=list)
    members: list[Member] = Field(min_length=1)
    task: Task
    summon: Summon | None = None
    #: A flow file beside the scenario, installed as protocols/<summon.flow>.
    flow_file: str | None = None


def check(scenario: Scenario, folder: Path) -> list[str]:
    errors: list[str] = []
    if folder.name != scenario.pattern:
        errors.append(f"pattern {scenario.pattern!r} must match its folder {folder.name!r}")
    handles = [m.handle for m in scenario.members]
    if len(set(handles)) != len(handles):
        errors.append("member handles must be distinct")
    keys = [c.key for c in scenario.context]
    if len(set(keys)) != len(keys):
        errors.append("context keys must be distinct")
    if sum(m.kind == "human" for m in scenario.members) > 1:
        errors.append("at most one human seat: the person who loads it")

    if scenario.flow_file and scenario.summon is None:
        errors.append("flow_file is set but there is no summon to run it")
    if scenario.summon is None:
        return errors

    summon = scenario.summon
    protocol = None
    if scenario.flow_file:
        path = folder / scenario.flow_file
        if not path.is_file():
            errors.append(f"flow_file {scenario.flow_file!r} does not exist")
        else:
            try:
                protocol = parse_protocol(summon.flow, path.read_text())
            except (ValueError, ValidationError, yaml.YAMLError) as exc:
                errors.append(f"flow {scenario.flow_file}: {exc}")
    elif summon.flow in BUILTIN_PROTOCOLS:
        protocol = parse_protocol(summon.flow, yaml.safe_dump(BUILTIN_PROTOCOLS[summon.flow]))
    else:
        errors.append(
            f"summon.flow {summon.flow!r} is not built in "
            f"({', '.join(sorted(BUILTIN_PROTOCOLS))}) and no flow_file is given"
        )
    if protocol is None:
        return errors

    by_handle = {m.handle: m for m in scenario.members}
    unknown = [h for h in summon.members if h not in by_handle]
    if unknown:
        errors.append(f"summon names members the scenario does not cast: {unknown}")
        return errors
    if len(set(summon.members)) != len(summon.members):
        errors.append("summon members must be distinct")
    if len(summon.members) < len(protocol.roles):
        errors.append(f"flow {summon.flow!r} has roles {protocol.roles}; the summon names too few")
        return errors
    for role, handle in zip(protocol.roles, summon.members, strict=False):
        if by_handle[handle].kind not in ASKABLE:
            errors.append(f"role {role!r} is bound to {handle!r}, a {by_handle[handle].kind}")
    bound = set(summon.members[: len(protocol.roles)])
    asks_workers = any(s.to == "workers" for s in protocol.steps)
    if asks_workers and not [h for h in summon.members if h not in bound]:
        errors.append(f"flow {summon.flow!r} asks workers, but every named member holds a role")
    for handle in summon.members:
        if by_handle[handle].kind not in ASKABLE:
            errors.append(f"{handle!r} is a {by_handle[handle].kind}, which a flow cannot ask")
    return errors


def main() -> int:
    if "--emit-schema" in sys.argv:
        print(json.dumps(Scenario.model_json_schema(), indent=2))
        return 0
    failed = 0
    folders = sorted(p.parent for p in (ROOT / "scenarios").glob("*/scenario.yaml"))
    if not folders:
        print("no scenarios found")
        return 1
    for folder in folders:
        try:
            scenario = Scenario.model_validate(yaml.safe_load((folder / "scenario.yaml").read_text()))
            errors = check(scenario, folder)
        except (ValidationError, yaml.YAMLError) as exc:
            errors = [str(exc)]
        status = "ok  " if not errors else "FAIL"
        print(f"{status} {folder.name}")
        for error in errors:
            print(f"       {error}")
        failed += bool(errors)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
