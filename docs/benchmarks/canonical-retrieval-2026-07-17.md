# Canonical Retrieval Benchmark — 2026-07-17

Synthetic mixed corpus on macOS 26.5.2 arm64, Python 3.14.6. Each size is split evenly between memories and resources. Both queries return exactly eight relevant records; unrelated `core` memories do not bypass retrieval.

| Total records | Memory/resource | Cold memory total | Cold resource index | Warm memory median | Warm resource index median | Collections |
|---:|---:|---:|---:|---:|---:|---|
| 30 | 15 / 15 | 66.191 ms | 21.235 ms | 42.443 ms | 8.787 ms | 8 / 8 complete |
| 1,000 | 500 / 500 | 231.270 ms | 256.061 ms | 47.824 ms | 8.928 ms | 8 / 8 complete |
| 10,000 | 5,000 / 5,000 | 2,198.993 ms | 2,505.662 ms | 152.635 ms | 9.642 ms | 8 / 8 complete |

Command:

```sh
MEGABRAIN_ROOT=skill/megabrain/seed python3 skill/megabrain/scripts/megabrain.py benchmark
```

Indexes are ignored, rebuildable SQLite projections created from `git archive HEAD`. Results are environment-specific and are not a service-level guarantee.
