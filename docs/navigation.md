# Navigating MegaBrain

Markdown files remain the source of truth. The local browser is a disposable projection of those files and never edits memory.

From a managed clone, run:

```bash
python3 skill/megabrain/scripts/megabrain.py browse
```

The command synchronizes when possible, validates the repository, writes `.megabrain/browser/index.html`, and opens it with the operating system's default browser. Owners can invoke the same workflow naturally by saying `Synchronize and open my MegaBrain` or `Open my MegaBrain`.

The page is a private local snapshot, not a continuously live view. It reports when the snapshot was generated, the newest memory timestamp in that validated snapshot, and whether synchronization succeeded at generation time. The unqualified word `Synchronized` is never used as a perpetual status. When synchronization is unavailable, offline generation still works from valid local state while the catalog clearly marks possible staleness and a safe reason. Use `browse --no-open` to generate the same catalog without launching a browser.

The **Current** view contains active knowledge. **History** contains superseded memories and tombstones. **Conflicts** keeps every unresolved current claim visible. **Agents** shows provenance identities and contribution counts. **Imports** shows source fingerprints and batch results. Memory links open their immutable Markdown source or move between replacements and the records they supersede.

The generated catalog contains private brain content. It is ignored by Git and can be removed at any time; the next synchronized-open action recreates it. Filters affect visible cards but not the global snapshot generation or newest-memory indicators. For direct inspection, open `brain/` in any Markdown editor or use the private GitHub repository after synchronization.
