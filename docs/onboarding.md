# Consumer Onboarding

MegaBrain's normal setup surface is conversation, not Git or the terminal.

## Set Up

The user says `Set up my MegaBrain.` The active skill requests GitHub approval when needed and runs the bootstrap for its own harness. Bootstrap then:

1. verifies Python, Git, GitHub authentication, and private-repository access;
2. creates `OWNER/megabrain` as a private repository when it does not exist;
3. seeds an empty brain and validation workflow when the repository is empty;
4. creates the active agent's hidden managed clone;
5. creates and registers a stable agent identity;
6. installs idempotent harness instructions;
7. validates and synchronizes the result;
8. opens the generated local browser; and
9. reports `MegaBrain is ready.`

The user does not choose a filesystem path, harness, branch, or Git configuration. GitHub authorization is the only unavoidable consent boundary.

## Connect Another Agent

After the skill is available in another harness, the user says `Connect this agent to my MegaBrain.` Bootstrap reuses the locally configured private repository, creates a separate managed clone, registers the new provenance identity, and validates cross-agent synchronization.

## Other Actions

- `Open my MegaBrain` regenerates and opens the private local catalog.
- `Check MegaBrain` synchronizes and reports user-relevant health.
- `Disconnect this agent` removes managed harness instructions and links while retaining the private repository and synchronized local clone to prevent accidental data loss.

Manual clone and installer commands remain documented only for development, recovery, and environments where a skill marketplace is unavailable.
