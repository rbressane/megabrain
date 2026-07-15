# User-zero Product Feedback

User-zero testing runs only against an installed stable consumer runtime and a real private clone. Product development runs in the canonical public repository and never reads, copies, or patches that private data. Every product reproduction replaces private content with the smallest synthetic fixture that fails for the same reason.

For each finding record observed and expected behavior, installed version and product commit, harness and operating system, sanitized exact reproduction, measurements, privacy implications, acceptance tests, and post-release verification. Update one permanent implementation brief only while the epic remains reviewable; use a new descriptive brief when implementation or rollback boundaries diverge.

The release loop is: consumer finding; sanitized classification; product branch and tests; review and green CI; explicit merge/release approval; stable consumer update; original flow retest; report VERIFIED, PARTIAL, or FAILED with measurements.

## Post-release retrieval retest

1. On the released consumer runtime, save the user's real X-writing preference through ordinary conversation.
2. Request an X post with the explicit task. At the default limit, confirm the preference is returned and the total ordinary record count does not exceed 12.
3. In an active editing conversation, use a vague instruction equivalent to “Make this better.” Confirm the harness compiles a short `x-post` structured descriptor and retrieves the same preference without sending raw conversation history.
4. Request the complete Round 6 pricing family. Confirm every canonical relevant sibling is present, unrelated core and sensitive records are absent, and source coverage reports any canonical reference-only source not scanned.
5. Capture diagnostic cold/warm stage timings separately from model response time and Git network time.

## Post-release Vault retest

1. Set up Vault on the installed stable runtime, save the one-time recovery key, and confirm readiness.
2. Add one real sensitive structured record and one document through protected input without exposing either to product logs or screenshots.
3. Grant one test agent metadata only and confirm masked metadata works while reveal fails.
4. Add reveal scopes and confirm the broker still rejects agent reveal, including a self-asserted private context, with `PRIVATE_CONTEXT_UNATTESTED`.
5. As the owner, provide unlock material through protected input and explicitly confirm a private output context; reveal only selected fields with a purpose code.
6. Revoke the agent and confirm a new future metadata request fails. Do not claim any earlier disclosure was erased.
7. Export an encrypted backup, restore it in a clean second home with recovery material, run doctor, and verify one selected field through the owner flow.
8. Confirm Brain Git history and generated browser contain no protected value, recovery key, ciphertext, wrapper, or agent private key.

The consumer report must not include the real value. Record only outcome, stable error codes, masking shape, timing, installed version/commit, and whether the flow is VERIFIED, PARTIAL, or FAILED.
