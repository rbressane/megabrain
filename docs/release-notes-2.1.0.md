# MegaBrain 2.1.0 Graph First Home

MegaBrain Home makes the private Brain visible without exposing repository or runtime details. Run `megabrain open` to synchronize, validate, regenerate, and open a local snapshot of current memories, topics, conflicts, evidence, agents, and imports.

## What changed

- The overview is a compact graph-first workspace inspired by technical knowledge maps.
- Search and filters update the graph, history, and inspector together.
- Selecting a topic or memory reveals its current record, provenance, and immutable Markdown source.
- Keyboard navigation, visible focus, reduced motion, and responsive mobile behavior are first-class.
- Large Brains use a deterministic bounded overview while keeping the complete current dataset available in the inspector and timeline.
- The command validates the configured managed clone, Git repository, remote, and harness identity before opening it. Errors never expose the configured private path.

The generated browser remains an ignored disposable local projection. Markdown records and Git history remain authoritative. No server, daemon, database authority, hosted relay, package dependency, or personal Brain data was added.

## Verification

- The complete 59-test standard-library suite passes.
- Seed validation completes with zero errors and warnings.
- Synthetic retrieval and resource benchmarks pass at 15, 500, and 5,000 memories.
- Desktop and mobile browser checks cover navigation, focus restoration, selection semantics, pan and zoom, and mobile scrolling.
- Independent code review found the release ready to merge.

## Update and use

Install the compatible stable release:

```bash
megabrain update
```

Open MegaBrain Home:

```bash
megabrain open
```

The browser reports when its snapshot was generated. Run `megabrain open` again whenever you want a freshly synchronized view.
