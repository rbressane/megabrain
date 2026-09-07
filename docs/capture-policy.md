# Capture Policy

Capture information that will materially reduce future re-explanation:

- directly stated durable facts and preferences;
- decisions and commitments;
- current project state that will matter in another session;
- recurring constraints and pitfalls;
- corrections to existing knowledge;
- document and secret-manager locations without secret values.

Do not capture routine questions, raw transcripts, temporary task progress, debugging output, ephemeral TODOs, unverified guesses as facts, or content that merely repeats current memory.

Honor an explicit don't-remember request by skipping capture. Owner-local Codex/Claude can pause automatic capture per agent/device; an explicit owner remember request remains distinct. A review queue derives conflicts, uncertainty, duplicates and freshness reminders without changing canonical truth. See [owner workflows](owner-workflows.md).

Direct user statements are `confirmed`. Agent conclusions are `inferred`. Ambiguous imports are `unconfirmed`. When a task produces multiple related memories, save them as separate entries and report only the count to the user.
