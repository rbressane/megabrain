# MegaBrain 2.0.1 Private-Retrieval Repair

MegaBrain 2.0.0 correctly default-denied private records but ordinary installed CLI retrieval never supplied trusted harness context, and newly registered owner agents had no read policy. Exact-topic queries could therefore find candidates and still return zero private memories or protected resources.

This repair keeps default deny intact. Explicit setup or reconnect now binds Codex and Claude owner-local provenance to their secured managed clone and committed agent identity, then creates one immutable `read`-only, all-collection, `private`-ceiling policy only when that agent has no policy history. The same attested context is supplied to memory, resource-list, and resource-read operations. `sensitive` records remain denied. Existing custom or revoked policies are untouched.

Automatic policy synchronization also rechecks the fetched remote policy history after every rejected push. If another writer created or revoked a policy concurrently, the pending automatic allow is superseded by an immutable revoked revision before any retry, so setup cannot rebase a stale grant over that decision. Inconclusive fetch, history, rebase, or retry outcomes leave automatic access disabled. A remotely accepted push whose acknowledgement was lost remains valid only when the fetched policy history contains the exact provisional commit and no distinct policy decision.

Hermes does not infer owner trust from a clone, prompt, subprocess argument, or environment claim. Setup creates no Hermes read policy. A reviewed in-process host integration must supply an owner-verified `gateway_user` DM context and create an exact reviewed platform policy through the owner-local control. The upstream generic provenance seam and the separate integration remain approval gates.

Diagnostic context output adds value-free counts for candidates, relevant candidates, authorized candidates, and policy denials, plus a trusted-context availability boolean. Denied memory IDs, subjects, summaries, source locators, and values are never emitted.

## Upgrade and rollback

This is a compatible runtime repair, not a silent Brain migration. After an approved stable release is installed, rerun setup or connect once for each owner agent. The operation preserves agent IDs and memory records, upgrades only ignored local provenance state, and commits the conservative policy. Reruns are idempotent.

To remove authorization, create an immutable revocation with the owner-local policy control; future setup runs will not recreate it. Runtime rollback does not rewrite Brain history. Do not delete policy revisions or reset a managed clone.

## Verification

- The complete 55-test standard-library suite passes.
- Seed validation completes with zero errors and warnings.
- The synthetic 30 / 1,000 / 10,000 retrieval and resource benchmark returns the full 8/8 collections at every size.
- Python compilation, Ruff, skill validation, bootstrap help, dependency health, `git diff --check`, and the changed-diff secret-pattern scan pass.
- Bandit reports no medium/high findings.
- Codex Security completed the PR diff worklist and candidate ledgers with no deferred rows, open questions, or reportable findings; an independent read-only remediation review found no remaining issues.

## Post-release acceptance

- Install the stable release and explicitly rerun setup for a synthetic or owner-approved consumer.
- Run User Zero acceptance through the separate User Zero agent after the stable release is installed.
- Land and review the Hermes trusted-provenance seam and integration before enabling Hermes private retrieval.

Vault, opaque private delivery, real destinations, sensitive synchronized assets, and high-assurance security claims remain outside this repair.
