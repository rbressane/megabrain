# Consumer Onboarding

## First Contact

An unfamiliar agent does not understand `Set up my MegaBrain` until the skill exists. The product repository is therefore the first-contact instruction surface. The user only needs to say `Install this: https://github.com/rbressane/megabrain`. The root README tells the agent to treat that as the complete setup request and follow [INSTALL.md](../INSTALL.md) end to end.

The installing agent selects the latest stable tag, inspects it, runs the repository installer, and requests approval only when GitHub authorization is needed.

## Setup

Bootstrap then:

1. verifies Python, Git, GitHub authentication, and private-repository access;
2. installs a versioned runtime separate from personal data;
3. creates `OWNER/megabrain-data` as a private repository when needed;
4. seeds an empty, data-only brain with compatibility metadata;
5. creates the active agent's hidden managed clone and stable identity;
6. installs the skill link and marker-delimited harness instructions;
7. validates and synchronizes the result;
8. opens the local browser; and
9. reports `MegaBrain is ready.`

The user does not choose a filesystem path, repository, harness, branch, or Git configuration. GitHub authorization is the only unavoidable consent boundary.

## Later Agents And Updates

The same repository setup message connects another agent or computer through the authenticated GitHub account. Installed users can ask to open, check, update, or disconnect MegaBrain naturally.

Compatible stable updates activate automatically at most once per day. Major updates request approval. Disconnect removes managed links and instructions while retaining the runtime, private repository, and synchronized clone to prevent data loss.
