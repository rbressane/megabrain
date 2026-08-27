# Retrieval Activation Benchmark · 2026-08-27

Synthetic mixed corpus on macOS 26.5.2 arm64, Python 3.14.6. Each size is split evenly between memories and resources. Memory ranking includes field weighting and inverse document frequency. The resource index includes heading-scoped sections and term frequencies. Both exact collection queries return all eight expected records.

| Total records | Memory/resource | Cold memory total | Cold resource index | Warm memory median | Warm resource index median | Collections |
|---:|---:|---:|---:|---:|---:|---|
| 30 | 15 / 15 | 53.346 ms | 18.557 ms | 36.421 ms | 9.191 ms | 8 / 8 complete |
| 1,000 | 500 / 500 | 203.834 ms | 269.526 ms | 45.616 ms | 8.728 ms | 8 / 8 complete |
| 10,000 | 5,000 / 5,000 | 2,327.656 ms | 2,751.025 ms | 149.654 ms | 9.435 ms | 8 / 8 complete |

Command:

```sh
MEGABRAIN_ROOT=skill/megabrain/seed python3 skill/megabrain/scripts/megabrain.py benchmark
```

Separate synthetic acceptance tests verify unified memory and resource evidence, immutable citations, rare-term score contribution, adjacent-section recovery, conflict expansion, authority-domain narrowing, and default-deny private resource behavior. The benchmark does not claim semantic paraphrase quality and is not a service-level guarantee.
