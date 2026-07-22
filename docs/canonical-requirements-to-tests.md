# Canonical Repository Requirements To Tests

| Requirement | Implementation | Synthetic verification |
|---|---|---|
| Real retrieval budget; unrelated `core` excluded | Bounded committed-snapshot memory index | `test_conflicts_core_relevance_and_unrelated_omission`; `test_retrieval_budget_collection_sensitive_policy_and_committed_index` |
| Eight-item collection; corrections/conflicts retained | Collection/conflict expansion counters and immutable graph | retrieval test above; existing correction/conflict tests |
| Sensitive relevance plus policy; no importance bypass | `authorize_memory_read` default deny | `test_scoped_policy_denies_default_group_internal_and_revoked_access` |
| Dirty canary never returned/persisted | `git archive HEAD` memory/resource indexes | retrieval committed-index test |
| Stable URI, immutable revisions, supersession/retirement | `megabrain.resource.v1` | `test_immutable_resource_revision_retirement_and_deterministic_export` |
| Deterministic Markdown round trip | canonical export parser/renderer | same resource revision test |
| Archived evidence and resource pointers resolve | archive/resource search and read | `test_user_zero_questions_resolve_canonical_resources_and_archived_evidence` |
| Attachment manifest and complete-object integrity | SHA-256 object layout and validation | `test_content_addressed_attachment_and_sensitive_sync_gate` |
| Review-first import, exact fingerprint, one batch | ignored stage plus owner-local approval lock | reviewed import and concurrent approval tests |
| Changed source, dirty clone, secrets, size limits fail closed | source fingerprint replay and validators | `test_stale_source_secret_oversize_and_dirty_clone_fail_without_echo` |
| Traversal, symlink, Unicode/confusable, frontmatter, count/expanded limits | separate owner allowlist preparer | `test_preparer_rejects_symlink_confusables_bad_frontmatter_and_secret_without_echo` |
| Instruction text remains inert data | resource-only instruction candidate and read label | reviewed import test |
| Scoped agent/channel capabilities and revocation | immutable policy revisions | scoped policy test |
| Existing v2 owner with no policy can recover private retrieval explicitly | setup provenance migration plus one conservative immutable policy | `test_setup_migrates_registered_v2_agent_without_policy_or_provenance`; `test_installed_owner_local_cli_retrieves_private_but_not_sensitive_memory`; `test_claude_owner_local_cli_uses_its_exact_harness_policy` |
| Setup is idempotent; revocation/deletion history is sticky | current-policy and Git-history guards | `test_setup_provisions_one_idempotent_owner_read_policy`; `test_setup_never_recreates_a_revoked_owner_policy`; `test_setup_never_recreates_policy_removed_from_current_tree` |
| Model input and unsafe local state cannot assert trust | installed-path, mode, clone, identity, and committed-agent checks | private retrieval test with forged input; `test_insecure_local_identity_and_unbound_hermes_fail_closed` |
| Zero-result diagnostics reveal no private values | value-free authorization counters | `test_diagnostics_count_policy_denials_without_private_values` |
| Hermes without trusted in-process provenance remains denied and unprovisioned | `trusted_host` provenance gate; no setup policy | `test_insecure_local_identity_and_unbound_hermes_fail_closed` |
| Derived cache has no write-back; watcher state external | deterministic cache and external state ledger | `test_derived_cache_external_intake_state_and_drift_are_non_authoritative` |
| Explicit resumable migration and rollback boundary | v1→v2 commit and guarded Git revert | `test_explicit_v1_migration_and_git_revert_rollback_preserve_memory` |
| Normal-language user-zero questions | memory/resource acceptance fixture | user-zero question test plus eight-price retrieval test |
| Cold/warm behavior at 30/1k/10k records | synthetic mixed-corpus benchmark | `megabrain.py benchmark`; [benchmark report](benchmarks/canonical-retrieval-2026-07-17.md) |
| Sensitive synchronized assets do not overclaim | runtime rejection and design gate | attachment test; [sensitive sync design](sensitive-sync-design.md) |

The full suite, seed/skill validation, lint, compile, dependency, and security scans remain release-gate evidence rather than substitutes for independent security review.
