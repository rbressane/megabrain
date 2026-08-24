---
version: 1
slug: "skill-megabrain-assets-browser-html"
primary_target: "skill/megabrain/assets/browser.html"
related_targets: []
---

# MegaBrain Home

Mode: Operate. Scope: the generated local browser at `skill/megabrain/assets/browser.html`.

Audience and job: A time-constrained owner inspects the current shape of their private Brain, finds a topic or memory, checks provenance and history, and opens immutable Markdown without learning repository mechanics.

Content and proof: Use only the generated memory, topic, conflict, agent, import, freshness, and provenance data. Graph relationships come only from explicit tags and supersession links. Keep the snapshot boundary and synchronization state visible.

Chosen composition: Graph First, approved from `.impeccable/mocks/decision/technical-graph-first.png`. A dim 184px rail and compact utility bar frame a dominant graph canvas with a narrow evidence inspector. Violet marks selection; coral marks conflict; everything else recedes into graphite neutrals.

Memorable interaction: Selecting a topic or memory isolates its direct relationships and turns the inspector into the fastest path from the map to evidence.

Constraints: Static, private, offline, standard-library-only, dependency-free, accessible, reduced-motion aware, responsive. Mobile becomes a ranked topic and memory list rather than a squeezed graph.

Implementation inventory:

| Visible commitment | Medium | Required behavior |
| --- | --- | --- |
| Compact top utility bar and dim navigation rail | Semantic HTML, CSS, authored inline SVG icons | Search and filters remain keyboard accessible; navigation keeps view counts and selected state. |
| Dominant clustered knowledge map | Generated inline SVG | Render every memory, up to eight leading tag topics, explicit tag edges, directional supersession edges, and conflict edges; support selection, keyboard activation, pan, zoom, and reset. |
| Persistent evidence inspector | Semantic HTML | Topic selection lists tagged memories; memory selection shows summary, state, confidence, date, history, provenance, and Markdown navigation. |
| Compact graph legend and snapshot state | Semantic HTML and CSS | Explain current, historical, supersession, shared-tag, conflict, record, subject, and freshness state without relying on color alone. |
| Ranked mobile topic view | Semantic buttons and responsive CSS | Replace the SVG canvas below 760px while preserving topic selection and evidence inspection. |

Component grammar: 3–5px radii, 1px graphite hairlines, flat surfaces without shadows, compact 10–18px sans type, 1.5px authored icon strokes, violet selection, and coral conflict. No shipping raster assets.

Unresolved: None.
