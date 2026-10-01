# mycelium-patterns

Multi-agent design patterns as scenarios Mycelium can load. Each scenario is a
small room, ready to run: a few members, some context, a task, and the flow that
sets them working. The patterns themselves come from
[ioc-app-mas-patterns](https://github.com/cisco-eti/ioc-app-mas-patterns); this
repo holds the part Mycelium can act on.

A scenario loads **paused**: the room, members, context and task are in place, and
nothing runs until the person starts it.

## Layout

```
scenarios/<pattern>/
  scenario.yaml     the room, its cast, its task and the summon that starts it
  protocol.yaml     optional: a flow of its own, installed as protocols/<flow>
```

`<pattern>` is the upstream pattern's directory name, so a scenario can always be
traced back to the pattern it shows.

## scenario.yaml

| Field | |
|---|---|
| `pattern` | The upstream pattern name. Must match the folder. |
| `title`, `summary` | What the scenario is, for a list. |
| `room.title`, `room.description` | The room it creates. |
| `context[]` | `{key: context/<slug>, text}`. Written to the room's memory. |
| `members[]` | `{handle, kind, description, notes}`. `kind` is `persona`, `worker`, `aligner`, `synthesizer`, `hello` or `human`. A persona or worker needs `notes`: its character. At most one `human`: the person who loads it. |
| `task` | `{title, body}`. The board row the flow runs in. |
| `summon` | `{flow, members, ask}`. Optional. `members` is the cast in order: the first ones fill the flow's roles, the rest are its workers. |
| `flow_file` | A flow beside the scenario. Without it, `summon.flow` must be a built-in. |

The conductor is not listed as a member: loading registers it.

## Validate

```bash
uv run --project ../mycelium/fastapi-backend python scripts/validate.py
```

Run it with the Mycelium backend's environment (`MYCELIUM_BACKEND` points at a
checkout, default `../mycelium/fastapi-backend`). A flow is parsed with the hub's
own `Protocol` model, because the hub does not check a `protocols/<name>` memory
when it is saved: a bad one is silently left out of the room's flows. The
validator also checks that the cast fits the flow: every role is filled by
something a flow can ask, and a flow that asks workers has some.

`validate.py --emit-schema` prints the scenario shape as JSON Schema.

## Scenarios

| Scenario | Flow | Members |
|---|---|---|
| `supervisor-worker` | `fan-out` (built in) | a supervisor and three specialists, all personas |
| `approval-gate-agent` | `gated` (built in) | an ops persona and you as the approver |
| `adversarial-review-agents` | `adversarial-review` (own flow) | a proposer and a critic, with you as the observer |
