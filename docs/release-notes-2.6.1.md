# MegaBrain 2.6.1

Quieter automatic recall. Runtime protocol remains 2; no Brain migration is required.

## Receipts only when they matter

- Routine per-message recall no longer shows a `MegaBrain:` line. Claude Code renders every hook message as an alert, so a receipt on every message read as a warning when nothing was wrong.
- A message still shows a receipt when the owner may need to act: a conflict between memories, a local copy older than two minutes, an offline or unsynchronized copy, saves still uploading, a message skipped because it looks like it contains a secret, or a failure.
- The session-start status line is unchanged.
- Recall itself is unchanged. The agent still receives the relevant memories and documents as context labelled as data, and is still told to search again before saying it lacks information. Every lookup, including quiet ones, is still recorded for `megabrain activity` and the Today page in Home and Live Home.

## Upgrade

Connected agents receive 2.6.1 through the normal compatible automatic update. No hook reinstall or Codex re-trust is needed: the hook commands are unchanged, only the runtime behind them. A Live Home host pinned to 2.6.0 needs no change for this release, since Live Home does not use the hooks.

## Verification and boundaries

The unit suite and seed validation passed locally with synthetic data. The GitHub matrix covers macOS and Linux on Python 3.10, 3.11 and 3.13 plus browser verification. No personal Brain was used or connected.
