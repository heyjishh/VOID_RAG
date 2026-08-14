---
name: JuryAI
description: A legal research workspace in frosted glass — a white canvas washed with fixed radial pastels, translucent surfaces with blur, and one violet voice for the action.
colors:
  primary: "#7c3aed"
  primary-light: "#f3effe"
  primary-hover: "#6d28d9"
  on-primary: "#FFFFFF"
  ink: "#6366f1"
  ink-hover: "#4f46e5"
  ink-light: "#eef0ff"
  ink-border: "#c7ccff"
  on-ink: "#FFFFFF"
  gold: "#d97706"
  gold-light: "#fef3c7"
  gold-border: "#fcd34d"
  sage: "#059669"
  sage-light: "#d1fae5"
  sage-border: "#a7f3d0"
  color-error: "#dc2626"
  color-error-bg: "#fee2e2"
  color-error-border: "#fecaca"
  color-info: "#2563eb"
  color-info-bg: "#dbeafe"
  color-info-border: "#bfdbfe"
  bg-main: "#fafaff"
  bg-card: "rgba(255,255,255,0.6)"
  bg-soft: "rgba(255,255,255,0.85)"
  text-primary: "#0f0f14"
  text-secondary: "#4e4e5c"
  text-muted: "#86868f"
  border-default: "rgba(15,15,20,0.08)"
  border-input: "rgba(15,15,20,0.14)"
typography:
  display:
    fontFamily: "Inter, -apple-system, sans-serif"
    fontSize: "1.35em"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.015em"
  body:
    fontFamily: "Inter, -apple-system, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.65
    letterSpacing: "normal"
  label:
    fontFamily: "Inter, -apple-system, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "normal"
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "0.87em"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
rounded:
  sm: "8px"
  md: "12px"
  lg: "16px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: "10px 20px"
  button-primary-disabled:
    backgroundColor: "{colors.border-default}"
    textColor: "{colors.text-muted}"
    rounded: "{rounded.md}"
    padding: "10px 20px"
  button-ink-active:
    backgroundColor: "{colors.ink-light}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0"
    size: "36px"
  card-source:
    backgroundColor: "{colors.bg-card}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.md}"
    padding: "12px 14px"
  badge-authoritative:
    backgroundColor: "{colors.gold-light}"
    textColor: "{colors.gold}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  badge-web:
    backgroundColor: "{colors.color-info-bg}"
    textColor: "{colors.color-info}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  banner-blocked:
    backgroundColor: "{colors.color-error-bg}"
    textColor: "{colors.color-error}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
---

# Design System: JuryAI — Arc Glass

## Overview

**Creative North Star: "A brief that reads like morning light through a window."**

JuryAI is a legal research workspace for advocates and their clerks. Its surfaces are frosted glass: the canvas is white washed with fixed radial pastels — blush at the top-left, ice blue at the right, lavender at the base — and every panel floats above it as translucent glass, `backdrop-filter: blur(20–28px) saturate(160%)`, defined by a white glow edge rather than a dark stroke. The register follows Arc (the browser) and Figma: a luminous white world, soft violet action, earned familiarity, the tool disappearing into the task.

The palette is a cast of characters, each with one job: **violet** is the action (the Advocate's pen), **indigo ink** is the machine's reasoning (the Clerk), **amber** marks the Seal of citation authority, **emerald** marks what has been checked, and **red** is its own hue for danger — the brand mark never doubles as a warning.

**Key Characteristics:**
- Frosted light canvas: `#fafaff` + three fixed radial washes (`#ffe0f0`, `#d4e4ff`, `#e0d4ff`) painted on `body`, `background-attachment: fixed`
- Glass materials: translucent white surfaces (`rgba(255,255,255,.6)` surface / `.85` strong), blur + saturate, white glow edges (`--border-glass: rgba(255,255,255,.65)`), inset top highlight
- Definition by soft violet-tinted shadow, never dark hairlines; inputs use hairline graphite `rgba(15,15,20,.08–.14)`
- Inter for everything; JetBrains Mono for evidence numerals and citation badges
- Motion is fast, ease-out, physical — `scale(0.97)` presses, 160–320ms, information-bearing only
- Dark is a night-courtroom variant: graphite `#0e0e13` with violet/indigo/magenta glows, glass at 5–9% white

## Colors

### Primary — Violet (Arc accent)
- **Violet** (#7c3aed light / #8b5cf6 dark): The one action color. Logo mark, primary CTA, evidence-count badge. Light value tuned for AA with white text; dark uses a lifted violet for the same contrast on graphite.
- **Violet Light** (#f3effe light / rgba(139,92,246,.16) dark): Wash for violet-owned states.
- **On Violet** (#FFFFFF): Text on a violet fill, both themes.

### Secondary — Indigo Ink (the Clerk)
- **Ledger Ink** (#6366f1 light / #818cf8 dark): The AI's reasoning voice. Owns the assistant's presence, the reasoning timeline, web-search connector, focus rings, and active toolbar toggles. "The AI is working" is always ink, never violet.
- **Ink Light** (#eef0ff light / rgba(99,102,241,.18) dark): Wash for ink-owned surfaces at rest (nav active, timeline steps).

### Tertiary
- **Seal Amber** (#d97706 light / #fbbf24 dark): Authority and citations — source rank, inline `[N]` markers, the source-flash ring.
- **Verified Emerald** (#059669 light / #34d399 dark): A claim that has been checked. Owns the verified signal and "Draft ready" states.

### Neutral — the glass ladder
- **Canvas** (#fafaff light / #0e0e13 dark): App background, painted with the fixed radial washes.
- **Surface** (rgba(255,255,255,.6) light / rgba(255,255,255,.055) dark): Frosted glass — cards, panels, message bubbles. Always used with backdrop blur.
- **Strong** (rgba(255,255,255,.85) light / rgba(255,255,255,.09) dark): Sidebars, drawers, popovers — the more-read surface.
- **Text** (#0f0f14 / #4e4e5c / #86868f light; #f2f2f7 / #b0b0bd / #71717d dark): Primary / secondary / muted.
- **Border** (rgba(15,15,20,.08) default / .14 input light; rgba(255,255,255,.14/.22) dark): Hairline graphite definition for dividers and inputs — the only place dark strokes are allowed.
- **Glass Edge** (rgba(255,255,255,.65) light / rgba(255,255,255,.16) dark): The white glow edge of frosted surfaces.

### True Alarm (isolated hue — not a role, a firebreak)
- **True Alarm** (#dc2626 light / #f87171 dark): The only red-adjacent hue permitted to mean danger. Owns failed-verification and gate-blocked states.
- **Open Web** (#2563eb light / #60a5fa dark): Cool blue for content from outside the internal corpus.

### Named Rules
**The One Red Rule.** Violet and True Alarm are never the same token and never visually adjacent in intent. Brand color must never double as a danger color.

**The Working-Voice Rule.** Any element whose job is to say "the model is doing something right now" is ink, never violet. Violet appears only where a human just acted or is about to.

**The Glass-Before-Fill Rule.** A translucent surface without `backdrop-filter` is a bug — it reads as a flat tint over the washes instead of frosted glass. Panels blur; the canvas does not.

## Typography

**UI/Display Font:** Inter (with -apple-system fallback)
**Mono Font:** JetBrains Mono (with ui-monospace fallback)

**Character:** A neutral grotesque for every surface; weight and tight tracking carry editorial moments instead of a serif. JetBrains Mono owns everything that is *evidence* — citation badges, page numbers, confidence figures — so the eye learns that monospace = verifiable.

### Hierarchy
- **Display** (600 weight, 1.35em, line-height 1.3, -0.015em): The wordmark and answer headings. Never italic.
- **Body** (400 weight, 14px, line-height 1.65): All chat text, UI copy, panel content.
- **Label** (600 weight, 13px): Buttons, badges, nav items.
- **Mono** (400 weight, 0.87em): Evidence numerals, citation badges, API keys. Tabular numerals on by default.

### Named Rules
**The Two-Font Ceiling Rule.** Exactly two typefaces do all work: Inter (all reading, UI, editorial) and JetBrains Mono (evidence and code only).

## Layout

The chat surface is the constant center on the open pastel canvas — its message area carries no background at all, so the washes remain visible behind the conversation. Matters (left) and Evidence (right) are collapsible floating glass panels at the edges; the rail and top bar are frosted glass, and the top bar reads as a floating pill above the canvas. Density is comfortable: 12–16px internal padding, 14px base text, 5px scrollbars.

## Elevation & Depth

Elevation is drawn with soft, violet-neutral shadows under translucent glass — the register has ambient light, so floating layers earn real depth, while resting cards stay nearly flat. Definition on the canvas comes from the white glow edge (`--border-glass`), never a dark ring.

### Shadow Vocabulary
- **Card** (`0 1px 2px rgba(15,15,20,.03), 0 4px 16px rgba(15,15,20,.05)`): Resting definition for frosted cards.
- **Card Hover** (`0 2px 4px …, 0 12px 32px rgba(15,15,20,.09)`): The card lifts slightly — the one place hover changes depth.
- **Panel** (`0 8px 24px rgba(15,15,20,.07), 0 24px 64px rgba(15,15,20,.12)`): Floating layers — drawers, modals, popovers.
- **Primary / Ink** (colored glow rings at 25–35%): Buttons and avatar outlines echo their owner's hue at soft alpha.
- **Focus** (`0 0 0 3px` ink-tinted): Focus ring, always ink — "you are here" is a system statement, not a brand statement.

### Named Rules
**The Glow-Edge Rule.** Glass surfaces are edged in white (`--border-glass`), never graphite. Graphite hairlines are reserved for dividers and input fields, where they give the eye something crisp to rest on.

## Shapes

Corners follow the 8 / 12 / 16 scale: `--radius-sm` (8px) for badges, chips and small controls, `--radius-md` (12px) for inputs and buttons, `--radius-lg` (16px) for cards, panels and the auth form card. Borders are 1px; glass edges are the border-glass tone.

## Motion

Motion follows a discipline: fast, ease-out, and only where it carries information. Shared tokens: `--dur-fast` (160ms), `--dur-base` (240ms), `--dur-slow` (320ms), `--ease-out: cubic-bezier(0.23,1,0.32,1)`.

- **Press states:** every enabled button compresses to `scale(0.97)` on `:active` — physical feedback under 200ms.
- **Reveals:** timeline steps, cards, and messages enter with a short opacity + 6px shift; staggered 30–80ms where several appear together; nothing scales up from 0.
- **Feedback loops:** pulsing indicators use opacity/scale on ink, never color flashes.
- **Transitions, not keyframes:** hover, focus, theme switch, and panel collapse use `transition` so they are interruptible.
- **Reduced motion:** `prefers-reduced-motion` collapses all animation to near-zero, except progress feedback which slows instead of freezing.

### Named Rules
**The Motivated Motion Rule.** If a motion does not help the eye track *what changed* or *where to look next*, it is removed.

## Components

### Buttons
- **Shape:** 12px radius (`--radius-md`); icon-only toolbar buttons use 8px (`--radius-sm`).
- **Primary:** Violet fill, white text, soft violet glow ring. Reserved for the one submit action per surface.
- **Ink-active toggle:** Ink-light fill with ink text/border when a toolbar toggle is active; transparent with a hairline at rest.
- **Disabled:** Faded hairline fill, muted text — visually "off," not a dimmed violet.

### Cards (Source Cards)
- **Corner Style:** 12px radius (`--radius-md`), frosted glass face (`--bg-card` + blur).
- **Tier signaling:** Two decoupled, honest signals — the numbered rank badge and the relevance badge (amber = High, ink = Moderate, neutral = Low), driven by `chunk.score`. A separate emerald "Verified" pill reflects `chunk.verified` — relevance and verification are two different real signals and are never conflated.
- **Shadow Strategy:** Soft card shadow at rest; the shadow deepens slightly on hover.
- **Retrieved-evidence list:** One unified list ordered by retrieval rank.

### Retrieval Summary Strip
- A single-row stat strip above the passage list, computed only from real per-turn data: total retrieved, count where `chunk.verified === true`, average `chunk.score` as a percentage. When a `verification` payload is present, its verdict (`grounded` / `partially_grounded` / `unsupported`, from `lib/verdictMeta.js`) and groundedness percentage render as a trailing pill.

### Badges
- **Relevance (High / Moderate / Low):** Amber / ink / neutral wash background+text+border, driven by `chunk.score` tiers.
- **Verified:** Emerald-light background, emerald text/border, only when `chunk.verified` is true.
- **Draft ready:** Emerald pill in the Drafting workspace toolbar, only when a draft exists.

### Banners
- **Gate-blocked banner:** True-Alarm-bg background, True-Alarm text/border, persistent — used only when the backend's groundedness gate withheld an answer even after a rewrite attempt. Never reused for lesser warnings.

### Navigation
- The nav rail is a full-height frosted glass strip with a white glow edge; the active item takes ink-light fill with an ink ring. The top bar is frosted glass with the breadcrumb on the left and the web-search toggle, corpus status, and evidence toggle on the right. The wordmark is Inter 600 with tight tracking — a mark, not a serif flourish.

## Do's and Don'ts

### Do:
- **Do** keep violet to exactly three roles: logo mark, primary CTA, evidence-count badge. A fourth use case needs a new token, not an exception.
- **Do** pair every translucent white surface with `backdrop-filter: blur(...) saturate(160%)` — that pairing is what the register is made of.
- **Do** use True Alarm (`--color-error`) for every actual danger/failure state.
- **Do** edge glass surfaces with `--border-glass`, and reserve graphite hairlines for dividers and inputs.
- **Do** give every press state physical feedback (`scale(0.97)` under 200ms) and keep all motion under 320ms with `--ease-out`.

### Don't:
- **Don't** use `--primary` (violet) for any state that means "the AI is thinking/working" — that is Ledger Ink's job, exclusively.
- **Don't** paint opaque `--bg-main` over the canvas inside panels — the pastel washes must show through everywhere.
- **Don't** introduce a third typeface, a serif display, or italic headings.
- **Don't** tint a source card's entire face by its relevance tier, and don't invent an "authority" signal the backend doesn't send.
- **Don't** reuse the gate-blocked banner styling for anything short of an actual withheld answer.
- **Don't** animate for animation's sake — no shimmer, bounce, or scale-from-zero entrances; if it doesn't help the eye track a change, it doesn't ship.
