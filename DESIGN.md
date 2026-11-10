---
name: "MegaBrain Home · Console"
description: "A flat, retro-futuristic instrument panel for a private Brain: sage paper, ink outlines, bar meters, ring gauges and one dial. Today answers in sentences; Map, Explore and the evidence views keep the full shape and provenance."
colors:
  paper: "#e9eee3"
  paper-2: "#dde4d5"
  ink: "#20221f"
  ink-2: "#454942"
  ink-3: "#5d6259"
  hair: "rgba(32, 34, 31, 0.18)"
  hair-strong: "rgba(32, 34, 31, 0.45)"
  track: "rgba(32, 34, 31, 0.2)"
  signal: "#b33a08"
  night-paper: "#151714"
  night-ink: "#e2e8da"
  night-signal: "#ff8a4f"
typography:
  display:
    fontFamily: "Geist Mono"
    fontSize: "clamp(32px, 4.1vw, 60px)"
    fontWeight: 400
    lineHeight: 1.04
    letterSpacing: "-0.05em"
  readout:
    fontFamily: "Geist Mono"
    fontSize: "clamp(56px, 10.5vw, 148px)"
    fontWeight: 400
    lineHeight: 0.98
    letterSpacing: "-0.04em"
  instrument:
    fontFamily: "Geist Mono"
    fontSize: "22px"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "0.01em uppercase"
  body:
    fontFamily: "Geist Mono"
    fontSize: "15–17px"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  label:
    fontFamily: "Geist Mono"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: "0.08em uppercase"
rounded:
  control: "999px"
  card: "28px"
  inner: "22px"
  notice: "0 0 0 44px"
spacing:
  workspace: "34px 40px"
  card: "28px 30px"
  section-gap: "44px"
  stroke: "2px"
---

# Design System: MegaBrain Home · Console

## North star

**"A control panel for your memory."** On 10 November 2026 the owner replaced the earlier glowing "Synapse" direction with a retro-futuristic one, from a reference image of a home-energy control panel: pale sage background, near-black ink, a mono typeface, capsule outlines, bar meters, ring gauges, a ticked dial and a very large digital readout.

Home is a flat instrument panel printed on paper. Nothing glows, and there are no gradients, shadows or blur. Structure comes from 2px ink outlines and generous spacing. One signal orange is reserved for what needs the owner.

## Signature instruments

- **Verdict:** Today opens with two lines in display type: a muted lead-in ("Your Brain is") and the verdict ("up to date."). The verdict turns signal orange when the Brain needs the owner or may be out of date.
- **Notice:** an inverted block (ink background, paper text) hangs from the top bar, square except for a 44px bottom-left corner. It carries the time, the freshness state, one plain sentence and, when there are conflicts, one action.
- **Meters:** three outlined capsules with a solid ink bar, each with an uppercase name, a caption in words and a percentage:
  - Recall: lookups that found something this week.
  - Confirmed: current memories that are confirmed.
  - In use: current memories recalled this week. It falls back to "New", the share learned in two weeks, when activity is unavailable.
- **Gauges:** one capsule per agent with a ring. The ring's ink arc is the share of that agent's lookups that found something.
- **Dial:** the last 14 days as an arc of 57 ticks, one every six hours, with a longer tick each day. A dot marks each six-hour stretch in which a memory was learned, changed or forgotten:
  - a larger dot means more memories;
  - the newest dot is ringed;
  - a signal dot is in conflict;
  - hovering names the memory, and clicking opens it.
- **Readout:** inside the dial, a clock counts up from the last synchronization in Live Home, or shows the snapshot's age in local Home.

## Color

Day (sage paper) is the default regardless of the system setting, because it is the direction the owner chose. The toggle switches to night, which inverts paper and ink, and the choice is stored per browser.

- **Paper and ink:** every surface is paper; every outline, bar, dot and heading is ink. Secondary text is `ink-2`; captions and labels are `ink-3`.
- **Signal** (`colors.signal`): conflicts, staleness and forgotten items only, always paired with words.
- **Inversion:** the active navigation item, current and core badges, the notice and hovered buttons swap paper and ink. Inversion is the only emphasis besides signal.
- **Contrast:** all text is WCAG AA or better in both themes (captions 5.3:1 on day paper, signal 5.0:1).

## Typography

- **One family:** Geist Mono (Vercel, SIL OFL), a variable font, for everything.
- **Display and readout:** regular weight with tight tracking (-0.04em to -0.05em).
- **Instrument names:** uppercase, medium weight, 19–22px.
- **Labels:** uppercase, 12px, tracked 0.08em. Nothing is smaller than 11px, and only short uppercase status chips use 11px.
- **Reading text:** 15–17px at a 1.6 line height, in sentence case.
- **Bundling:** the font is bundled in `assets/fonts/` with its license and inlined as a `data:` URL at render time. Nothing loads from the network, and Live Home's CSP allows `font-src data:` only.

## Layout

- **Chrome:** a 64px top bar with a 2px ink rule (ticked-dial mark, pill search with a `/` hint, scope filter, sync state, theme toggle) and a 232px rail of 44px pill navigation in uppercase.
- **Content width:** content is centered at up to 1240px.
- **Today, top to bottom:**
  1. The verdict beside the hanging notice.
  2. Needs you: a card with a signal outline when something is open, or a single capsule line when clear.
  3. Meters beside agent gauges.
  4. The dial and readout.
  5. Most recalled, recent changes and current knowledge as full-width cards.
- **Below 1050px:** the notice moves above the verdict and spans the full width; meters and gauges stack.
- **Below 760px:** the rail becomes a sticky horizontal strip, and the readout sits under the dial instead of inside it.

## Surfaces

- **Cards:** a 2px ink outline, a 28px radius and no fill. Hover fills with `paper-2`.
- **Inner chips:** recall and knowledge chips use a 1px `hair-strong` outline with a 22px radius. Core knowledge gets the full 2px ink outline.
- **Attention:** conflict cards and claim panels use a signal outline. Claim panels add a faint signal wash.
- **Controls:** buttons and selects are capsules with a 2px ink outline and uppercase labels. They invert on hover.
- **Badges:** capsule chips. Current and core are inverted, conflict is signal-outlined, private and sensitive are dashed.

## Motion

- Today's first render raises each section over 640ms, staggered 70ms apart, and fills the meters over 900ms. Live refreshes never replay either.
- The freshness dot in the notice blinks slowly.
- The clock changes once a second.
- Everything else is still, and all animation stops under `prefers-reduced-motion`.

## Map and evidence views

- **Map:** topics are open ink circles with uppercase labels on a faint dot grid. Current memories are solid ink dots, historical ones are open, and conflicts are signal. The selected topic is filled.
- **Timeline:** an ink spine with solid dots for current records and open dots for history.
- **Sign-in:** one outlined card with the mark, "Welcome back.", a capsule field and an inverted capsule button.

## Accessibility

- **Never color alone:** every state has words; signal only reinforces them.
- **Focus:** a 2px ink outline with a 3px offset, in paper color on the notice.
- **Instruments:** each meter states its value in text. Each gauge and the dial have a text alternative. Everything the dial shows is also listed under "Recently learned and changed".
- **Navigation:** keyboard navigation everywhere. Headings that receive programmatic focus show no ring.
