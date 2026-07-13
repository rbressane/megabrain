# Navigating MegaBrain

Markdown files remain the source of truth. The local browser is a disposable projection of those files and never edits memory.

From a managed clone, run:

```bash
python3 skill/megabrain/scripts/megabrain.py browse
```

The command synchronizes when possible, validates the repository, writes `.megabrain/browser/index.html`, and opens it with the operating system's default browser. When synchronization is unavailable, the catalog clearly marks the local state as potentially stale. Use `browse --no-open` to generate the same catalog without launching a browser.

The **Current** view contains active knowledge. **History** contains superseded memories and tombstones. **Conflicts** keeps every unresolved current claim visible. **Agents** shows provenance identities and contribution counts. **Imports** shows source fingerprints and batch results. Memory links open their immutable Markdown source or move between replacements and the records they supersede.

The generated catalog contains private brain content. It is ignored by Git and can be removed at any time; the next `browse` command recreates it. For direct inspection, open `brain/` in any Markdown editor or use the private GitHub repository after synchronization.
