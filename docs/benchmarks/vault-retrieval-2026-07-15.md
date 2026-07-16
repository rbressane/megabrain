# Retrieval Benchmark — 2026-07-15

Command:

```text
python3 skill/megabrain/scripts/megabrain.py benchmark
```

Reference environment: Apple arm64, macOS 26.5.2, Python 3.14.6. The benchmark creates disposable synthetic Brain records only, uses a fixed local Git commit, builds the index once, then runs five warm reads. Network time is zero by construction; the `remote_synchronization` stage measures the local dirty-worktree/freshness check separately. The task requests all eight synthetic `round6.pricing.*` siblings with 20 unrelated `core` records present.

| Active memories | Cold total | Cold index refresh | Cold graph resolution | Warm median total | Warm sync | Warm index query | Warm graph | Warm rank | Warm serialize | Returned |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | 71.620 ms | 22.298 ms | 0.072 ms | 43.452 ms | 32.087 ms | 10.826 ms | 0 ms | 0.017 ms | 0.046 ms | 8/8 |
| 1,000 | 442.964 ms | 283.290 ms | 1.522 ms | 43.674 ms | 32.274 ms | 10.434 ms | 0 ms | 0.013 ms | 0.042 ms | 8/8 |
| 10,000 | 3352.229 ms | 2230.340 ms | 16.920 ms | 56.485 ms | 44.897 ms | 8.945 ms | 0 ms | 0.018 ms | 0.048 ms | 8/8 |

Warm totals at 1,000 memories were 64.811, 45.170, 42.935, 43.674, and 40.042 ms. Warm totals at 10,000 were 111.314, 54.013, 55.672, 57.186, and 56.485 ms. The 1,000-memory median is below the 500 ms acceptance threshold. Cold refresh includes creating and parsing a safe archive of the captured Git commit, so uncommitted working-tree text can never enter the index. Warm graph resolution is zero because the validated immutable graph is compiled once per Git commit; SQLite token postings load only matching compact projections. Every size respected the limit, expanded the complete pricing family, and excluded unrelated core records.

These are local helper measurements, not model-generation latency and not a network claim. Consumer Git synchronization latency remains separately dependent on the Git host and connection.

## Independent user-zero environment

Pierre independently ran the same synthetic benchmark on x86_64 macOS 14.8.3 with Python 3.14.4. Keep these measurements alongside, rather than instead of, the Apple-arm64 reference:

| Active memories | Cold total | Warm median | Returned |
|---:|---:|---:|---:|
| 30 | 227.187 ms | 143.080 ms | 8/8 |
| 1,000 | 1,525.012 ms | 148.507 ms | 8/8 |
| 10,000 | 14,600.881 ms | 192.547 ms | 8/8 |

The older x86 environment shows a materially slower one-commit cold archive/index build while preserving the warm-path target. Both environments exclude Git-host network latency. The original stable-consumer path measured roughly 2.5 seconds of remote synchronization before model generation; that real network stage must be measured again only after an approved stable release reaches user zero.
