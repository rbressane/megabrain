# Canonical Access Policy

Protocol 2 access policies are immutable `megabrain.access-policy.v1` JSON revisions. A policy binds one registered agent to an allow/deny effect, capabilities (`read`, `propose`, `correct`, `retire`, `administer`), collections, sensitivity ceiling, platforms, chat types, source kinds, and an optional owner-DM-only constraint. Revocation is a new revision.

General records retain normal local retrieval. Private and sensitive records default deny. Importance never grants access. An authorized read requires task relevance plus host-supplied context matching the current policy. Model payloads cannot supply destination, identity, privacy, authorization, or attestation fields.

Owner DM, group, channel, forum, delegated, cron, webhook, API, background, and unattended contexts are distinct. A group or automation read requires an exact reviewed policy; broad clone access is not implied. Agents that cannot be trusted with the full repository must receive scoped deterministic digests or submit proposals through a trusted owner agent. Runtime filtering does not make an unrestricted filesystem clone safe.

Policy decisions append only timestamp, action, allow/deny, safe reason, policy revision, sensitivity class, and an agent-ID digest to ignored mode-0600 audit state. Titles, summaries, bodies, source locators, and private values are excluded.
