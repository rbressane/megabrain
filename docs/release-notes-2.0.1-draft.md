# MegaBrain 2.0.1 Private-Retrieval Repair Draft

MegaBrain 2.0.0 correctly default-denied private records but ordinary installed CLI retrieval never supplied trusted harness context, and newly registered owner agents had no read policy. Exact-topic queries could therefore find candidates and still return zero private memories.

This repair keeps default deny intact. Explicit setup or reconnect now binds Codex and Claude owner-local provenance to their secured managed clone and committed agent identity, then creates one immutable `read`-only, all-collection, `private`-ceiling policy only when that agent has no policy history. `sensitive` records remain denied. Existing custom or revoked policies are untouched.

Hermes does not infer owner trust from a clone, prompt, subprocess argument, or environment claim. Setup creates no Hermes read policy. A reviewed in-process host integration must supply an owner-verified `gateway_user` DM context and create an exact reviewed platform policy through the owner-local control. The upstream generic provenance seam and the separate integration remain approval gates.

Diagnostic context output adds value-free counts for candidates, relevant candidates, authorized candidates, and policy denials, plus a trusted-context availability boolean. Denied memory IDs, subjects, summaries, source locators, and values are never emitted.

## Upgrade and rollback

This is a compatible runtime repair, not a silent Brain migration. After an approved stable release is installed, rerun setup or connect once for each owner agent. The operation preserves agent IDs and memory records, upgrades only ignored local provenance state, and commits the conservative policy. Reruns are idempotent.

To remove authorization, create an immutable revocation with the owner-local policy control; future setup runs will not recreate it. Runtime rollback does not rewrite Brain history. Do not delete policy revisions or reset a managed clone.

## Remaining gates

- publish the branch and open a review PR;
- complete independent diff/security review;
- merge and create an approved stable tag/release;
- install the stable release and explicitly rerun setup for a synthetic or owner-approved consumer;
- land/review the Hermes trusted-provenance seam and integration before Hermes private retrieval;
- run User Zero acceptance only after the stable release and integration gates pass.

Vault, opaque private delivery, real destinations, sensitive synchronized assets, and high-assurance security claims remain outside this repair.
