---
name: "MegaBrain Home · Synapse"
description: "A luminous instrument for a private Brain. Today answers in sentences around a living constellation of the owner's memories; Map, Explore and the evidence views keep the full shape and provenance."
colors:
  void: "#05060b"
  void-raised: "#0b0d16"
  glass: "rgba(16, 19, 32, 0.66)"
  line: "rgba(160, 180, 255, 0.11)"
  line-strong: "rgba(170, 190, 255, 0.22)"
  ink: "#eef1ff"
  ink-2: "#b9c0dc"
  ink-3: "#848cab"
  ion: "#7ce7ff"
  plasma: "#a68bff"
  flare: "#ff7ab8"
  mint: "#5ff2c4"
  amber: "#ffc56b"
  coral: "#ff6b81"
typography:
  display:
    fontFamily: "Mona Sans (width 110–125%)"
    fontSize: "clamp(40px, 5.2vw, 72px)"
    fontWeight: 640
    lineHeight: 0.98
    letterSpacing: "-0.035em"
  heading:
    fontFamily: "Mona Sans (width 115%)"
    fontSize: "24px"
    fontWeight: 640
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Mona Sans"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  numeral:
    fontFamily: "Mona Sans (width 125%)"
    fontSize: "48px"
    fontWeight: 280
    lineHeight: 1.05
    letterSpacing: "-0.02em"
  data:
    fontFamily: "Martian Mono"
    fontSize: "11px"
    fontWeight: 500
    lineHeight: 1.6
    letterSpacing: "0.14em uppercase"
rounded:
  chip: "999px"
  control: "999px"
  card: "22px"
  inner: "16–18px"
spacing:
  workspace: "34px 40px"
  card: "26px 28px"
  grid-gap: "18px"
  section-gap: "28px"
---

# Design System: MegaBrain Home · Synapse

## North star

**"The Brain, Answered."** Approved by the owner on 9 November 2026, asking for an interface that looks like it comes from the future while staying readable.

Home is a luminous instrument. Light is signal, not decoration: ice-cyan marks what is current and recent, coral marks conflict, violet marks agents. Everything else is ink on deep glass.

Today opens with plain sentences ("Your Brain is up to date." or "Your Brain needs you.") beside a living constellation of the owner's actual memories.

The graph-first landing of earlier releases proved hard to read and process. The graph now lives under **Map**.

## Signature: the constellation

Each current memory is a point of light on a slowly turning sphere:
- **Layout:** points are placed on a golden-angle spiral, grouped by topic, so clusters form naturally. Close neighbors are linked by faint neural lines.
- **Neural dust:** a fixed lattice of dim points keeps the sphere legible for a Brain of any size.
- **Point colors:** memories created in the last two weeks glow ion; conflicts glow and pulse coral; core items are larger.
- **Agents:** each agent active this week orbits as a violet satellite on one of two tilted rings.
- **Interaction:** hovering shows the memory, clicking opens it, and the pointer tilts the sphere.
- **Accessibility:** the canvas has a full text label. The same information is available in the cards below.
- **Motion:** with reduced motion it renders once and stays still. It pauses when hidden and is drawn at up to 2× device pixel ratio.

## Color

Dark ("void") is the default; light ("porcelain") follows the system preference, and the viewer can toggle it. The choice is stored per browser.

Both themes define the same tokens in `assets/browser.html`. The light values (ion `#0b84a8`, plasma `#6a4fe0`, coral `#cf3554`, ink `#0b0e1c`) keep text at WCAG AA or better.

- **Ion** (`colors.ion`): the active view, focus, links, current and recent knowledge. It glows.
- **Plasma** (`colors.plasma`): agents and private evidence.
- **Coral** (`colors.coral`): conflict and destructive states, always paired with words.
- **Amber** (`colors.amber`): staleness and changed wording.
- **Spectrum** (ion → plasma → flare): reserved for the headline verdict, the tile hairlines, core knowledge edges and the primary sign-in action in dark mode.
- **Atmosphere:** a slow, blurred aurora (ion, plasma, flare) and a faint 26px dot grid, masked toward the top. Both disappear with reduced transparency; the aurora's motion stops with reduced motion.

## Typography

- **Display and body:** Mona Sans (GitHub, SIL OFL), a variable font. The expanded widths (110–125%) carry headlines and the light, wide numerals; normal width carries reading text.
- **Data:** Martian Mono (Evil Martians, SIL OFL) for overlines, counts, timestamps, IDs and status chips, always uppercase with wide tracking.
- **Bundling:** both fonts are bundled in `assets/fonts/` with their licenses and inlined as `data:` URLs at render time. Nothing loads from the network, and Live Home's CSP allows `font-src data:` only.
- **Legibility floors:** reading text 17px on Today and at least 15px elsewhere. Data labels may go to 10–11px only in Martian Mono uppercase with tracking at 0.08em or more, and never for content.

## Layout

- **Chrome:** a 64px glass top bar (orbit mark, pill search with a `/` hint, scope filter, sync pill, theme toggle) and a 232px rail of 44px pill navigation. The active item gets an ion glow bar.
- **Content width:** content is centered at up to 1240px.
- **Today, top to bottom:**
  1. A hero: the verdict headline, a sentence, a freshness pill and a legend, with the constellation beside it.
  2. Four telemetry tiles.
  3. A grid of named areas: `needs agents`, then `recalled` and `recent` full width, then `knows` full width. Variable content never leaves holes.
- **Below 1050px:** the hero stacks.
- **Below 900px:** cards become one column.
- **Below 760px:** the rail becomes a sticky horizontal strip, and labels collapse to icons where words would not fit.

## Surfaces and depth

- **Glass:** a 22px radius, a 1px translucent hairline, a soft top sheen and a long, low shadow. Backdrop blur is reserved for the top bar, sidebar, inspector, controls and tooltips, so long pages stay smooth on modest hardware.
- **Attention cards:** cards that need the owner gain a coral hairline and an outer glow, not a filled background.
- **Chips:** status chips and tags are pill outlines in Martian Mono. Current knowledge is ion, conflict coral, private plasma.
- **Inner chips:** knowledge and recall chips are recessed (void at 35%) and lift 2px on hover.

## Motion

- Today's first render reveals sections with a 760ms rise, staggered 70ms apart. Live refreshes never replay it.
- Links nudge their arrow on hover, and the freshness dot breathes.
- Everything stops under `prefers-reduced-motion`.

## Components worth keeping consistent

- **Verdict headline:** a small ink-2 lead-in, then the verdict in the spectrum, or amber to coral when attention is needed.
- **Telemetry tile:** a mono overline, a wide light numeral and a plain caption, with a spectrum hairline on the top edge.
- **Claim panels:** each side of a conflict appears as Claim A, Claim B and so on, in coral-tinted panels side by side. The owner always sees every claim.
- **Agent ring:** a conic ring whose ion share is the agent's found-something rate, around its initials.
- **Timeline:** glowing node rings on a gradient spine. Changed items are amber and show the previous wording struck through; forgotten items are coral.
- **Map:** topic orbs with a spectrum stroke, glowing ion memory points, coral conflicts, and an inspector with evidence rows.

## Accessibility

- **Contrast:** AA contrast for all text in both themes. Focus is a 2px ion outline plus a soft ion ring.
- **Never color alone:** every state has words.
- **Navigation and labels:** keyboard navigation everywhere. Headings that receive programmatic focus show no ring. The constellation has a text alternative.
- **User preferences:** reduced motion and reduced transparency are both honored.
