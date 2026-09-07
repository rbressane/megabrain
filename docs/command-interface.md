# One command interface

The installed `megabrain` executable dispatches data operations to the existing installed helper. There is no second retrieval implementation. The installed helper retains the exact harness path, clone binding and policy checks used by the skill.

| Task | Command |
| --- | --- |
| Open the current private snapshot | `megabrain open` |
| Check health or inspect problems | `megabrain status`, `megabrain doctor` |
| Synchronize local commits | `megabrain sync` |
| Retrieve evidence | `megabrain search --stdin` |
| Retrieve memory-only context | `megabrain context --stdin` |
| Capture a durable item | `megabrain remember --stdin` |
| Correct or forget a current item | `megabrain correct ID --stdin`, `megabrain forget ID --stdin` |
| Discover or open resources | `megabrain resources --stdin`, `megabrain resource-read URI` |
| Stage a reviewed import | `megabrain import-stage --stdin` |
| Inspect import coverage | `megabrain coverage` |
| Update the runtime | `megabrain update`, `megabrain update --check` |

Use each command's `--help` without setup. Content is JSON on stdin, never command-line arguments. Data command success responses use `megabrain.result.v1`; validation failures exit nonzero. Update retains its existing `megabrain.update.v1` report. The CLI does not accept owner-local policy, resource-write, backup or approval commands.

With multiple configured agents and no detectable active harness, data commands fail rather than silently selecting another agent's identity. Ask a connected agent to run the action. The owner's explicit `open` action retains its documented local snapshot selection behavior.

## Scope and completeness

`search` accepts an `authority_domain` that narrows BOTH memories and resources. A `resource_type` narrows results to resources only. New memories may declare `authority_domain`; legacy unscoped memories are excluded from scoped searches. Reclassify through an explicit immutable correction, never by editing older entries. Corrections preserve scope unless explicitly changed.

`query_status` distinguishes matched queries, no matches, and queries with no searchable terms. `truncated` says additional authorized evidence exists beyond the budget. `conflicts_incomplete` says a selected conflict could not be fully represented, including policy filtering or the expansion ceiling. Neither a limit nor an access restriction authorizes silently choosing one conflicting claim.

New optional `verified_at` and `review_after` memory timestamps retain the protocol-1 memory schema and protocol-2 Brain compatibility. Old records are not rewritten. These fields describe evidence, not automatic truth expiration or permission.
