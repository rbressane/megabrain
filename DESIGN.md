---
name: "MegaBrain Home"
description: "A compact, graph-first instrument for inspecting the shape, evidence, and provenance of a private Brain."
colors:
  canvas: "#0b0c0e"
  surface: "#111317"
  surface-raised: "#17191d"
  surface-hover: "#1c1f24"
  border: "#25282e"
  border-strong: "#343840"
  text: "#f3f4f6"
  text-secondary: "#b7bbc3"
  text-muted: "#8b9099"
  accent: "#7c6ef6"
  accent-muted: "#aaa2ff"
  success: "#69b9af"
  warning: "#d7a95f"
  danger: "#f06a6a"
typography:
  headline:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "18px"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  title:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "14px"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  body:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.58
    letterSpacing: "normal"
  label:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "10px"
    fontWeight: 400
    lineHeight: 1.8
    letterSpacing: "normal"
rounded:
  compact: "3px"
  panel: "4px"
  control: "5px"
  circle: "50%"
spacing:
  hairline-gap: "2px"
  micro: "4px"
  tight: "6px"
  control: "8px"
  compact: "10px"
  rhythm: "12px"
  section: "14px"
  panel: "16px"
  block: "18px"
  inspector: "20px"
  workspace-y: "24px"
  workspace-x: "28px"
components:
  search-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 9px"
    height: "34px"
  navigation-default:
    backgroundColor: "transparent"
    textColor: "{colors.text-muted}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 9px"
    height: "36px"
  navigation-active:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 9px"
    height: "36px"
  memory-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "14px 16px"
  evidence-row:
    backgroundColor: "transparent"
    textColor: "{colors.text-secondary}"
    typography: "{typography.body}"
    padding: "7px 9px"
    height: "42px"
  evidence-row-hover:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.text}"
  inspector-action:
    backgroundColor: "transparent"
    textColor: "{colors.accent-muted}"
    rounded: "{rounded.panel}"
    padding: "0 8px"
    height: "34px"
  badge-current:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.accent-muted}"
    rounded: "{rounded.compact}"
    padding: "0 6px"
    height: "20px"
  mobile-topic:
    backgroundColor: "transparent"
    textColor: "{colors.text-secondary}"
    typography: "{typography.body}"
    padding: "0 14px"
    height: "48px"
  graph-node-selected:
    backgroundColor: "#282442"
    textColor: "{colors.text}"
    rounded: "{rounded.circle}"
---

# Design System: MegaBrain Home

## Overview

**Creative North Star: "The Brain Itself"**

MegaBrain Home is direct visual access to the owner's knowledge, not a dashboard that summarizes it. The graph replaces hero copy, stat cards, and presentation framing: show the whole knowledge shape first, isolate direct relationships on selection, reveal evidence and history in the inspector, then provide a quiet path to immutable Markdown.

The atmosphere is precise, calm, compact, and confidence-inspiring. Warm graphite chrome recedes around the knowledge map. Violet identifies selection and current attention; coral preserves the visibility of conflict. Every surface should make ownership, provenance, uncertainty, and snapshot freshness legible without forcing the owner to learn repository mechanics.

**Key Characteristics:**

- Graph-first desktop composition with receding navigation and persistent evidence.
- Compact neutral typography, exact spacing, and 1px graphite hairlines.
- A whole shape → evidence → Markdown interaction path.
- Violet selection, coral conflict, and explicit text for every meaningful state.
- A ranked topic list on mobile, not a compressed graph.

## Colors

The palette is a warm graphite field with one cool violet signal, one coral exception, and restrained operational status colors.

### Primary

- **Selection Violet** (`colors.accent`): Marks the selected graph node, targeted records, focus within fields, and the current legend state.
- **Evidence Violet** (`colors.accent-muted`): Carries active icons, current badges, evidence dots, links, carets, and visible focus rings.

### Secondary

- **Conflict Coral** (`colors.danger`): Marks unresolved conflict nodes, edges, badges, and conflict headings. It is semantic evidence, never decoration.

### Tertiary

- **Synchronized Teal** (`colors.success`): Confirms synchronization at snapshot generation time.
- **Stale Amber** (`colors.warning`): Signals that a generated snapshot may be stale or synchronization was incomplete.

### Neutral

- **Brain Canvas** (`colors.canvas`): The dominant graph field and page background.
- **Knowledge Surface** (`colors.surface`): Search, filters, memory records, and quiet hover fills.
- **Raised Evidence** (`colors.surface-raised`): Selected navigation, selected evidence rows, badges, and active compact surfaces.
- **Hover Graphite** (`colors.surface-hover`): Interactive hover feedback for controls.
- **Graphite Hairline** (`colors.border`): Default separators, panel boundaries, and record outlines.
- **Strong Graphite Hairline** (`colors.border-strong`): Input outlines, graph controls, scrollbar thumbs, and stronger hover boundaries.
- **Primary Text** (`colors.text`): Headings, selected content, and high-priority labels.
- **Secondary Text** (`colors.text-secondary`): Summaries, evidence names, graph labels, and readable operational copy.
- **Muted Text** (`colors.text-muted`): Metadata, counts, timestamps, inactive navigation, and supporting status.

**The Selection Is Signal Rule.** Violet marks the current point of attention and current knowledge. It is not decoration.

**The Conflict Is Evidence Rule.** Coral is reserved for unresolved conflict and danger states, always paired with explicit text.

## Typography

**Display Font:** The system sans-serif stack (`typography.headline`)

**Body Font:** The system sans-serif stack (`typography.body`)

**Label Font:** The system sans-serif stack (`typography.label`)

**Character:** One neutral sans-serif family keeps the interface fast, native, and operational. Hierarchy comes from weight, size, contrast, and alignment rather than decorative type changes.

### Hierarchy

- **Headline** (`typography.headline`): Inspector titles and primary page headings. Keep it rare and left aligned.
- **Title** (`typography.title`): Product identity and compact section emphasis.
- **Body** (`typography.body`): Search, navigation, memory summaries, evidence names, and the main reading layer. Long summaries stay near 78ch.
- **Label** (`typography.label`): Metadata, counts, badges, ranks, legend labels, and snapshot notes. Use tabular numerals for counts and dates.

**The Density Must Stay Legible Rule.** Compact type may reduce size only when hierarchy, contrast, and line height preserve scanning.

## Layout

Desktop is a full-viewport instrument. A 52px utility bar spans the top. Below it, a 184px dim rail frames a graph workspace split into a fluid canvas and a persistent 304px evidence inspector; a 36px status and legend strip spans both columns. The graph uses a 900 × 820 coordinate field and owns the clear majority of usable space.

At 1050px and below, the rail contracts to 164px and the inspector to 280px. At 760px and below, the composition becomes a document flow: the rail becomes horizontally scrollable navigation, the SVG graph and zoom controls disappear, ranked 48px topic rows become the overview, and the evidence inspector follows below. At 520px and below, secondary hints and legend detail recede further.

The spacing rhythm is compact and incremental. Use 2–12px gaps inside controls and dense groups, 14–20px for record and inspector padding, and 24–28px for non-graph workspace framing. Structure should be felt through alignment and tone, not a grid of boxed cards.

**The Whole Shape First Rule.** Desktop opens on the graph; evidence follows selection in the persistent inspector.

## Elevation & Depth

This is a flat system with no shadows. Depth comes from graphite tonal steps, 1px borders, dimmed non-adjacent graph relationships, and a restrained raised surface for selected or hovered content. The canvas, chrome, inspector, and status strip remain physically quiet.

**The Flat Instrument Rule.** Surfaces stay flat. Use tonal separation and 1px hairlines to establish hierarchy; do not add shadows.

## Shapes

Controls and containers use gently compact corners: 3px for badges, 4px for evidence containers and inspector actions, and 5px for fields, navigation rows, cards, and empty states. Graph nodes and status dots are circular because their geometry carries meaning; circles do not become a general component style. Authored icons use 1.5px rounded strokes at 14–17px.

Topic nodes scale from a 20px to 34px radius according to evidence count. Memory nodes stay much smaller at a 4.5px to 7px radius, with size and outline distinguishing history, current state, conflict, and selection.

**The Curve Is Restraint Rule.** Use 3–5px corners for controls and containers; reserve circles for graph and status semantics.

## Components

Components are compact, quiet, and evidence-led. Hover and focus states clarify operation without lifting surfaces or adding decorative motion.

### Search and Filters

- **Search:** A 34px graphite field with a 5px radius, strong hairline, 13px input, inline 17px search icon, and small keyboard hint.
- **Filters:** Match the search field's height, surface, outline, and corner treatment.
- **Hover / Focus:** Hover shifts to the hover graphite; focus changes the border to violet. Keyboard focus uses a 2px evidence-violet outline with 2px offset.

### Navigation

- **Default:** A transparent 36px row with muted text, 17px authored icon, compact count, and a 5px radius.
- **Active:** Use the raised graphite surface, default hairline, primary text, and evidence-violet icon.
- **Mobile:** Convert the rail to a sticky horizontal strip. Preserve labels, counts, active state, and keyboard operation.

### Knowledge Map

- **Topics:** Large dark circular nodes with centered 12px labels; node size reflects tagged-memory count.
- **Memories:** Small neutral circles. Historical memories recede; conflict memories retain coral visibility even when unrelated nodes dim.
- **Relationships:** Shared-tag edges are faint and dotted. Supersession edges are directional. Active direct relationships shift to evidence violet.
- **Selection:** The selected node uses a dark violet fill and a strong violet outline; direct neighbors remain legible while unrelated nodes recede.
- **Controls:** Zoom in, zoom out, and reset form one flat segmented control in the lower-left corner.

### Evidence Inspector

- **Container:** A persistent flat panel separated from the graph by one hairline and padded by 20px horizontally on desktop.
- **Rows:** Evidence rows are at least 42px high, use a status dot plus name plus explicit state, and switch to raised graphite on hover or selection.
- **Facts:** Confidence, updated date, history count, agent, source, and tags remain compact but readable.
- **Actions:** Violet text actions are 34px high and use a 4px corner. They lead to topic exploration, the relevant list view, or immutable Markdown.

### Memory Cards and Tags

- **Cards:** Flat knowledge surfaces with a 5px radius, default hairline, and 14px × 16px padding. Conflict and targeted states change the border color rather than adding elevation.
- **Badges / Tags:** Compact 20px labels with a 3px radius. Use raised graphite by default, evidence violet for current knowledge, and coral for conflict or tombstone states.

### Ranked Mobile Topics

- **Rows:** Full-width 48px buttons with a two-digit rank, topic name, and tabular count.
- **State:** The selected topic uses raised graphite and primary text. Its evidence inspector follows immediately below the list.

### Status and Legend

- **Structure:** A 36px graphite strip carries the relationship legend and record/topic/conflict totals.
- **Meaning:** Pair every dot or line with a text label. Freshness language must state that synchronization is true only when the snapshot was generated.

**The Evidence Path Rule.** Every selection should lead from shape to evidence to immutable Markdown.

## Do's and Don'ts

### Do:

- **Do** let the knowledge graph dominate the desktop overview and let surrounding chrome recede.
- **Do** use violet for selection, focus, and current evidence; use coral only for conflict and danger.
- **Do** preserve provenance, history, uncertainty, and snapshot freshness in plain language.
- **Do** pair color-coded states with labels, maintain visible keyboard focus, and honor reduced motion.
- **Do** replace the graph with a ranked topic list on narrow screens while preserving selection and evidence.

### Don't:

- **Don't** turn MegaBrain Home into a hero page, KPI dashboard, bento grid, or collection of large stat cards.
- **Don't** add gradients, glassmorphism, glow, neon, shadows, decorative illustration, or presentation theater.
- **Don't** use an anatomical brain, neural-network cliché, person, or physical knowledge metaphor.
- **Don't** round every element into pills or soften the compact 3–5px form language.
- **Don't** hide conflicts, provenance, immutable Markdown access, or the local snapshot boundary.
- **Don't** imply that a generated local snapshot is continuously synchronized.
