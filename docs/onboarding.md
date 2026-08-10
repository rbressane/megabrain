# Consumer Onboarding

## First Contact

An unfamiliar agent does not understand `Set up my MegaBrain` until the skill exists. The product repository is therefore the first-contact instruction surface. The user only needs to say `Install this: https://github.com/rbressane/megabrain`. The root README tells the agent to treat that as the complete setup request and follow [INSTALL.md](../INSTALL.md) end to end.

The installing agent selects the latest stable tag, inspects it, runs the repository installer, and requests approval only when GitHub authorization is needed.

## Setup

Bootstrap then:

1. verifies Python, Git, GitHub authentication, and private-repository access;
2. installs a versioned runtime separate from personal data;
3. creates `OWNER/megabrain-data` as a private repository when needed;
4. seeds an empty, data-only brain with compatibility metadata and no GitHub Actions workflow;
5. creates the active agent's hidden managed clone and stable identity;
6. creates one immutable, read-only, private-ceiling owner policy for an eligible owner-local harness when the agent has no policy history;
7. installs the skill link, first-class `megabrain` command and marker-delimited harness instructions;
8. reports a one-line `PATH` correction when required without editing shell profiles;
9. validates and synchronizes the result;
10. opens the local browser on the machine running the agent and reports that host explicitly; and
11. reports `MegaBrain is ready.` and teaches `Synchronize and open my MegaBrain` as the normal return action.

The user does not choose a filesystem path, repository, harness, branch, or Git configuration. GitHub authorization is the only unavoidable consent boundary.

The local browser is a private generated snapshot, not a continuously live page. On every later `Synchronize and open my MegaBrain` action, the agent synchronizes the active managed clone, validates it, regenerates the snapshot, opens it on that host, and returns a value-free freshness receipt. Another connected computer or agent has its own clone and local snapshot.

If setup is interrupted after creating the private repository or committing the local seed, rerunning setup converges on the same private repository. A clean local seed is pushed to an empty remote once authorization is fixed. Setup can safely remove the legacy workflow from an exact, pristine v1.0.0 seed before its first push; any other committed or uncommitted change is left untouched and blocks automatic recovery.

## Later Agents And Updates

The same repository setup message connects another agent or computer through the authenticated GitHub account. Installed users can ask to open, check, update, or disconnect MegaBrain naturally.

Compatible stable updates activate automatically at most once per day. `megabrain update --check` checks immediately without mutation and `megabrain update` installs the latest compatible stable tag. Major or protocol-version changes request approval. Disconnect removes managed harness links and instructions while retaining the command, runtime, private repository, and synchronized clone to prevent data loss.

The private-retrieval repair is intentionally not an automatic data migration. After installing a compatible runtime that contains it, the owner reruns setup or connect once. That explicit action upgrades the ignored local identity provenance and creates the conservative policy only for a Codex or Claude agent with no policy history. Existing custom or revoked policies are never replaced. Hermes setup creates no read policy and remains private-read-disabled until its reviewed in-process trusted-provenance integration is installed, bound to the owner DM, and given an exact reviewed policy.

An activated runtime updates command and skill symlinks immediately. New sessions load the updated skill instructions normally. A session that already loaded the previous skill may need to reread it or start a new session before new Product Bake Candidate completion behavior is reliable.
