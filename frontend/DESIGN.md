---
name: JuryAI
description: A legal research console where crimson is the advocate's voice and ink is the machine's reasoning, never blurred into one color.
colors:
  primary: "#6B1219"
  primary-light: "#EDE3DE"
  primary-hover: "#4A0B10"
  on-primary: "#FAF8F4"
  ink: "#2E3A5C"
  ink-hover: "#232C46"
  ink-light: "#E9EBF2"
  ink-border: "#C3C8DA"
  on-ink: "#FAF8F4"
  gold: "#B8922A"
  gold-light: "#F7F0DC"
  gold-border: "#DFC47A"
  sage: "#3B5C3A"
  sage-light: "#EBF2EB"
  sage-border: "#8FB88D"
  color-error: "#C4432A"
  color-error-bg: "#FBEAE3"
  color-error-border: "#E8B49E"
  color-info: "#2A5C8C"
  color-info-bg: "#E8F0F8"
  color-info-border: "#B9D3E8"
  bg-main: "#F5F1EB"
  bg-soft: "#EDE8DF"
  bg-card: "#FAF8F4"
  text-primary: "#1C1612"
  text-secondary: "#5C4F40"
  text-muted: "#9C8E7C"
  border-default: "#D8D0C4"
  border-input: "#C8BEB4"
typography:
  display:
    fontFamily: "Cormorant Garamond, Georgia, serif"
    fontSize: "1.35em"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "0.04em"
  body:
    fontFamily: "DM Sans, -apple-system, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  label:
    fontFamily: "DM Sans, -apple-system, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "normal"
  mono:
    fontFamily: "JetBrains Mono, monospace"
    fontSize: "0.87em"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
rounded:
  sm: "5px"
  md: "9px"
  lg: "13px"
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

# Design System: JuryAI

## Overview

**Creative North Star: "The Advocate and the Clerk"**

JuryAI stages two voices in the same room and refuses to let them blur into one. The Advocate speaks in judicial crimson — the color of an Indian Supreme Court advocate's gown — and only ever speaks when a human types, submits, or acts. The Clerk works in ink navy, the color of a ledger entry: it retrieves, reasons, ranks, and verifies, and its presence on screen is the tell that the machine is doing that work right now. Gold marks the Seal of authority — citations, source ranking, the weight of a document — and sage marks a claim that has actually been checked against evidence. Nothing here is a wash of one accent color; the palette is a cast of characters, each with one job.

The system deliberately rejects the reflex to make brand-crimson double as danger-red. A legal product that flashes its own brand color at a user during an error is confusing at best, alarming at worst — so `--color-error` is its own hue, burnt terracotta, never a re-tint of the Advocate's crimson. Surfaces stay warm and paper-like (`--bg-main`, a parchment tone, not clinical white or slate) because the product's register is a law library, not a SaaS dashboard.

**Key Characteristics:**
- Two-voice color system: crimson = human/brand action, ink = machine reasoning, never interchangeable
- Warm parchment surfaces, not white or cool gray — the room is a library, not a terminal
- Serif display type (Cormorant Garamond) only at moments of editorial weight; everything operational stays in DM Sans
- Danger is its own hue; the brand mark never has to double as a warning
- Shadows are tinted to the color of the element casting them, never flat black

## Colors

The palette reads as two protagonists (crimson, ink) plus two specialists (gold, sage) on a warm neutral stage, with a fifth hue reserved solely for things going wrong.

### Primary
- **Oxblood** (#6B1219): The Advocate's voice. Reserved for the logo mark, the primary submit CTA, and the user's own chat bubble — the three places where a human, not the model, is acting. Deepened and desaturated off a brighter crimson so it reads as leather-bound authority rather than a rosy/pink cast; its shadow is now a plain neutral card shadow, not a tinted glow, so it never haloes into "blossom" territory. Never used decoratively; if it shows up anywhere else it's a bug.
- **Oxblood Hover** (#4A0B10): Pressed/hover state for the above, always darker, never a tint shift.
- **On Oxblood** (#FAF8F4): Text/icon color sitting on an oxblood fill — a warm off-white, not pure white, so it still belongs to the parchment family.

### Secondary
- **Ledger Ink** (#2E3A5C): The Clerk's voice. Owns the assistant's avatar, the retrieval → generation reasoning timeline, the "Researching…" active state, the web-search connector toggle, and focus rings. This is what "the AI is working" looks like — it deliberately never borrows crimson to say that.
- **Ink Light** (#E9EBF2): Wash for ink-owned surfaces at rest (nav active state, timeline step backgrounds).
- **On Ink** (#FAF8F4 light theme / #15130F dark theme): Text/icon sitting on an ink fill. Unlike On Crimson, this token flips per theme because Ledger Ink itself inverts lightness between themes (dark navy in light mode, pale lavender in dark mode) — a single static foreground token would fail contrast in one theme, so this one is theme-aware by design.

### Tertiary
- **Ashoka Brass** (#B8922A): The Seal — authority and citation. Owns source-ranking steps in the reasoning timeline, the "Authoritative" source-tier badge, and the document icon in the source panel header.
- **Verified Sage** (#3B5C3A): A claim that has been checked, not just asserted. Owns the verification badge's positive state and the "grounded" signal path.

### Neutral
- **Parchment** (#F5F1EB): App background — warm, matte, library paper, not clinical white.
- **Soft Paper** (#EDE8DF): Recessed/inset surfaces (code blocks, low-tier source cards).
- **Card Paper** (#FAF8F4): Raised surfaces — message bubbles, panels, cards.
- **Ink Text** (#1C1612): Primary reading text — warm near-black, not pure black.
- **Faded Ink** (#5C4F40): Secondary text, captions, metadata.
- **Dust** (#9C8E7C): Muted/placeholder text, disabled labels.
- **Aged Paper Border** (#D8D0C4): Default hairline border between surfaces.

### True Alarm (isolated hue — not a role, a firebreak)
- **True Alarm** (#C4432A): The only red-adjacent hue permitted to mean danger. Burnt terracotta, deliberately distinct from Judicial Crimson so the two are never mistaken for each other at a glance. Owns the failed-verification state and the gate-blocked banner.
- **Open Web** (#2A5C8C): A third, cooler blue reserved for content sourced from outside the internal corpus — the web-search badge and icon family — so "this came from the open internet" reads as its own signal, not a shade of ink.

### Named Rules
**The One Red Rule.** Judicial Crimson and True Alarm are never the same token and never visually adjacent in intent. If a designer reaches for `--primary` to signal "something went wrong," that's the exact anti-pattern this system was built to prevent — brand color must never double as a danger color.

**The Working-Voice Rule.** Any UI element whose job is to say "the model is doing something right now" (reasoning steps, active indicators, streaming states) is ink, never crimson. Crimson only appears where a human just acted or is about to.

## Typography

**Display Font:** Cormorant Garamond (with Georgia, serif fallback)
**Body Font:** DM Sans (with -apple-system, sans-serif fallback)
**Label/Mono Font:** JetBrains Mono (with monospace fallback)

**Character:** A restrained serif for the handful of moments that carry editorial weight (the wordmark, prose headings inside an answer) against a plain, highly legible grotesque for every operational surface — buttons, labels, chat text, metadata. The pairing keeps 95% of the interface quiet so the serif's appearances actually register as weight rather than decoration.

### Hierarchy
- **Display** (600 weight, 1.35em, line-height 1.25, 0.04em tracking, Cormorant Garamond): The "AI" wordmark in the navbar and `<h1>` inside a rendered answer. The only two contexts serif type is allowed to appear.
- **Headline** (600 weight, 1.18em, line-height 1.25, Cormorant Garamond): `<h2>` inside rendered answers.
- **Title** (600 weight, 1.05em, line-height 1.25, Cormorant Garamond): `<h3>` inside rendered answers.
- **Body** (400 weight, 14px, line-height 1.6, DM Sans): All chat text, UI copy, panel content. The base size for the entire app.
- **Label** (600 weight, 13px, DM Sans): Buttons, badges, nav items — slightly smaller and bolder than body, never uppercase-tracked (the product's register is a library, not a dashboard, so shouting-case labels are avoided).
- **Mono** (400 weight, 0.87em, JetBrains Mono): Inline code, API-key fields, source content-hashes.

### Named Rules
**The Two-Font Ceiling Rule.** Exactly two typefaces do all operational work (DM Sans) and all editorial work (Cormorant Garamond); JetBrains Mono is a third, but only for literal code/hash/key strings. A third "UI" font is never introduced no matter how small the use case.

## Layout

The chat surface is the constant center; History (left) and Sources (right) are collapsible companions that live at the edges rather than competing panels. Both edge panels collapse to a small pill (`CollapsedPanelPill`) rather than disappearing entirely, so the user is never left wondering whether a panel exists. Density is comfortable, not compact: message bubbles, source cards, and timeline steps all carry generous internal padding (12–16px) against the plain parchment background so the reading experience stays closer to a printed brief than a dense admin console.

## Elevation & Depth

Shadows exist and are used sparingly, but every shadow is tinted to the color of the element casting it rather than a generic black — a crimson button casts a faint crimson shadow, an ink-colored avatar casts a faint ink shadow, a gold-ranked source card gets a warm gold-tinted hover shadow. This is a deliberate rejection of the generic `rgba(0,0,0,.15)` shadow that appears on every element regardless of its color role.

### Shadow Vocabulary
- **Card** (`0 1px 3px rgba(28,22,18,.06), 0 1px 2px rgba(28,22,18,.04)`): Resting elevation for cards and panels, tinted ink-black rather than pure black.
- **Card Hover** (`0 4px 18px rgba(184,146,42,.18)`): Gold-tinted lift for source cards on hover — echoes the Seal, since hovering a source is an act of checking authority.
- **Panel** (`0 4px 24px rgba(28,22,18,.14)`): Drawer/overlay elevation (Settings, mobile Sources).
- **Primary / Primary-sm** (`0 2px 8px rgba(107,18,25,.18)` / `0 1px 4px rgba(107,18,25,.15)`): Cast only by oxblood elements (submit button, Sync Data CTA) — deliberately low-alpha so it never blooms into a rosy halo around small rounded shapes. The user message bubble is the one oxblood-filled element that does *not* use this shadow: it takes the neutral Card shadow instead, since a right-aligned bubble with a warm glow around it read as "cherry blossom" rather than "advocate's gown."
- **Ink / Ink-sm** (`0 2px 8px rgba(46,58,92,.22)` / `0 1px 4px rgba(46,58,92,.18)`): Cast only by ink elements (assistant avatar).
- **Focus** (`0 0 0 3px rgba(46,58,92,.16)`): Focus ring, always ink-tinted regardless of the focused element's own color, since focus is a system-level "you are here," not a brand statement.

### Named Rules
**The Tinted Shadow Rule.** No shadow uses a generic black. A shadow's tint always matches the hue of the element casting it, so shadows read as an extension of the object rather than a bolted-on effect.

## Shapes

Corners are gently rounded but never pill-shaped or fully rectangular: `--radius-sm` (5px) for small controls and badges, `--radius-md` (9px) for buttons and cards, `--radius-lg` (13px) for panels and modals. The scale is deliberately narrow and understated — enough to soften the geometry without reading as "rounded SaaS card." Borders are thin (1px), low-contrast hairlines (`--border-default`, `--border-input`) rather than heavy strokes; weight is carried by fill and shadow, not by border thickness.

## Components

### Buttons
- **Shape:** Rounded corners (9px, `--radius-md`) for standard buttons; small icon-only toolbar buttons use the tighter 5px (`--radius-sm`).
- **Primary:** Oxblood fill (`#6B1219`), on-oxblood text, 10px/20px padding, neutral card shadow (no tinted glow). Reserved for the one submit action per surface — never duplicated as a secondary accent.
- **Ink-active toggle:** Ink-light fill with ink text/border when a toolbar toggle (e.g. web-search) is active; transparent with a neutral border at rest.
- **Disabled:** Neutral border-gray fill, muted text, no shadow — visually "off," not a dimmed crimson.

### Cards (Source Cards)
- **Corner Style:** 9px radius (`--radius-md`).
- **Background:** Card paper at rest; the tier wash lives only in the rank badge and the relevance badge, never the whole card face.
- **Tier signaling:** Two decoupled, honest signals — the numbered rank badge and the relevance badge (gold = High, ink = Moderate, neutral border-gray = Low), both driven by `chunk.score`, the one ranking number the backend actually sends. There is no fabricated "authority" tier: the API contract (`SourceChunkOut`) has no `authority_score`/`source_type`/`domain` field, so the card never claims editorial authority it can't back up. A separate sage "Verified" pill reflects `chunk.verified` (claim-level grounding match) — relevance and verification are two different real signals and are never conflated into one badge.
- **Shadow Strategy:** Card at rest; gold-tinted Card Hover shadow on interaction (a fixed accent, not tier-dependent), plus a 2px lift so the card feels physically liftable.
- **Retrieved-evidence list:** All chunks render in one unified list, ordered by retrieval rank (array position from the backend) — there is no internal-corpus/web-sources split in the UI, because the live contract does not send a `domain` field to distinguish them.

### Retrieval Summary Strip
- A single-row stat strip above the passage list, computed only from real per-turn data: total retrieved count, count where `chunk.verified === true`, and the average `chunk.score` as a percentage. When a `verification` payload is available for the turn, its verdict (`grounded` / `partially_grounded` / `unsupported`, from `lib/verdictMeta.js`) and groundedness percentage render as a trailing pill — the same verdict tokens `VerificationBadge` uses, so the two never drift into different colors for the same verdict.

### Badges
- **Relevance (High / Moderate / Low):** Gold / ink / neutral-gray background+text+border, driven by `chunk.score` tiers.
- **Verified:** Sage-light background, sage text/border, shown only when `chunk.verified` is true.

### Banners
- **Gate-blocked banner:** True-Alarm-bg background, True-Alarm text/border, persistent (not dismissible) — used only for the one case where the backend's groundedness gate withheld an answer even after a rewrite attempt. This is the system's only "hard stop" visual, and it is never reused for lesser warnings.

### Navigation
- History and Sources are peer nav buttons in the top bar; the active one takes ink-light background with ink text/border. Collapsed panels leave behind a small edge pill in the same ink family, so the affordance to reopen is always visible without permanently occupying panel width.

## Do's and Don'ts

### Do:
- **Do** keep crimson to exactly three roles: logo mark, primary CTA, user message bubble. If a fourth crimson use case appears, it needs a different token, not an exception.
- **Do** tint every shadow to the hue of the element casting it (crimson shadow under crimson elements, ink shadow under ink elements, gold shadow under source-card hovers).
- **Do** use True Alarm (`--color-error`) for every actual danger/failure state, even when it would be visually "convenient" to reuse crimson because the element is already red-adjacent in context.
- **Do** carry the theme-aware `--on-ink` token wherever text sits on an ink fill, since Ledger Ink inverts lightness between light and dark themes and `--on-primary` is not safe to reuse there.

### Don't:
- **Don't** use `--primary` (crimson) for any state that means "the AI is thinking/working" — that is Ledger Ink's job, exclusively.
- **Don't** introduce a third operational typeface. Cormorant Garamond is editorial-only (wordmark + answer headings); everything else is DM Sans.
- **Don't** tint a source card's entire face by its relevance tier, and don't invent an "authority" signal the backend doesn't send — a card colored crimson-to-gold-to-neutral by rank would read as a traffic-light dashboard, not a law library, and a fabricated authority score would misrepresent what was actually retrieved.
- **Don't** reuse the gate-blocked banner styling (True-Alarm, persistent, non-dismissible) for anything short of an actual withheld answer — it is reserved for that one backend signal so it retains its weight.
