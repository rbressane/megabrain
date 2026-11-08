# Automatic Recall Benchmark · 2026-11-08

Synthetic memory-only Brains on Linux, Intel Core i5-4258U (2 cores, 4 threads), Python 3.14.8, Git 2.56.0. Each Brain has eight relevant memories, and the rest are unrelated. "Before" is `main` at `4a6f797`. "After" is the automatic-recall change. Times are whole helper processes, including Python startup, measured against a local bare remote, so they exclude network latency. Network operations are counted separately with `GIT_TRACE`. Each warm figure is the median of six runs after one cold run.

| Memories | Lookup | Before: local time | Before: network round trips | After: local time | After: network round trips |
|---:|---|---:|---:|---:|---:|
| 300 | Explicit `context` | 272 ms | 2 (fetch + push) | 241 ms | 1 (fetch) |
| 300 | Explicit `search` | 272 ms | 2 | 258 ms | 1 |
| 300 | Automatic recall, copy under 10 min old | not available | not available | 197 ms | 0 |
| 300 | Automatic recall, copy older than 10 min | not available | not available | 215 ms | 1 |
| 300 | Session start | not available | not available | 220 ms | 1 |
| 3,000 | Explicit `context` | 805 ms | 2 | 222 ms | 1 |
| 3,000 | Explicit `search` | 800 ms | 2 | 227 ms | 1 |
| 3,000 | Automatic recall, copy under 10 min old | not available | not available | 200 ms | 0 |
| 3,000 | Automatic recall, copy older than 10 min | not available | not available | 223 ms | 1 |
| 3,000 | Session start | not available | not available | 230 ms | 1 |

Before this change, every read re-validated the whole Brain, which took 55 ms at 300 memories and 559 ms at 3,000. It also pushed even when there was nothing to send. Reads now validate a committed tree once per runtime and push only pending commits. The first read after a new commit still pays one full validation and index refresh: 1.56 s cold at 3,000 memories, compared with 1.38 s before.

## With a real remote

On the measurement machine, a GitHub `git fetch` or `git ls-remote` took 477–533 ms. Adding about 0.5 s per round trip gives these totals:

| Memories | Before, every lookup | After, explicit lookup | After, automatic recall |
|---:|---:|---:|---:|
| 300 | about 1.3 s | about 0.75 s | about 0.2 s, or about 0.7 s when the copy is over 10 min old |
| 3,000 | about 1.8 s | about 0.7 s | about 0.2 s, or about 0.7 s when the copy is over 10 min old |

Before this change, a lookup also needed the agent to spend one or two model steps of its own to run it. Automatic recall runs before the model sees the message, so that step disappears whenever the hook's result is enough.

These are synthetic, environment-specific measurements, not a service-level guarantee. The comparison script lives outside the repository. It builds Brains with `benchmark_memory`, runs both checkouts' helpers as subprocesses, and counts `git fetch` and `git push` in `GIT_TRACE` output.
