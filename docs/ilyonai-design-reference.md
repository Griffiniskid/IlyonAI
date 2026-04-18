# IlyonAI Design Reference

This document captures the current IlyonAI visual system so another agent can extend the second part of the project on another device without drifting from the existing product language.

## 1. Design Intent

IlyonAI should feel like a premium, high-signal crypto intelligence product:

- dark, calm, and technical rather than loud or playful
- polished and glassy, with soft blur and subtle glow
- dense with information, but still readable and structured
- security-first and analytical, not meme-driven
- AI-enhanced, but not sci-fi for its own sake

The product sits between a DeFi terminal, a risk engine, and an AI assistant. The UI should always communicate trust, clarity, and market awareness.

## 2. Brand Personality

- Primary mood: dark intelligence dashboard
- Secondary mood: emerald-lit security tooling
- Tertiary mood: AI system overlays in purple/blue

If a new screen feels like a generic SaaS admin panel, a neon cyberpunk toy, or a bright exchange UI, it is off-brand.

## 3. Core Color System

### Base theme

IlyonAI is dark mode first. The baseline palette from `web/app/globals.css` is:

- Background: `hsl(222 47% 4%)`
- Card: `hsl(222 47% 7%)`
- Secondary / muted surfaces: `hsl(217 33% 17%)`
- Foreground text: `hsl(210 40% 98%)`
- Muted text: `hsl(215 20% 65%)`
- Border: `hsl(217 33% 17%)`

In plain terms:

- page background is near-black with a navy cast
- cards are slightly lifted from the background, never flat pure black
- borders are soft and low-contrast
- most depth comes from blur, transparency, and glow rather than hard outlines

### Primary accent

The main Ilyon accent is emerald. This is the default accent unless there is an explicit rebrand decision.

- Primary / accent: `hsl(160 84% 39%)`
- Common hex equivalent used in gradients and strokes: `#10b981`
- Supporting emeralds: `#34d399`, `#6ee7b7`, `#065f46`

Use emerald for:

- primary actions
- active navigation state
- important positive metrics
- selected controls
- hero glow and brand emphasis
- wallet / security / trusted system states

### AI / system accent

Purple and blue are intentionally reserved for AI/system framing, especially in the agent surfaces.

- Reasoning panels: purple tints like `bg-purple-500/5`, `border-purple-500/20`, `text-purple-300`
- Routing / system integrations: purple or blue monospace labels
- Chain pills: chain-specific blue / violet / sky / indigo tints

Use purple/blue for:

- AI reasoning accordions
- system-generated structured cards
- chain/router indicators
- secondary technical highlights

Do not replace the overall emerald brand with purple. Purple is a subsystem accent, not the main brand.

### Semantic colors

- Positive / safe: emerald / green
- Caution: yellow / amber
- Elevated risk: orange
- Dangerous / error: red
- Informational chain/system accents: sky / blue / violet / indigo

Examples already encoded in the UI:

- `.score-safe` -> emerald
- `.score-caution` -> yellow
- `.score-risky` -> orange
- `.score-dangerous` / `.score-scam` -> red

## 4. Surface Language

The dominant surface style is translucent glass.

### Card treatment

Most cards use some version of:

- rounded corners: `rounded-2xl`
- translucent fill: `bg-card/50`, `bg-card/60`, or `bg-card/80`
- subtle border: `border-white/10` or `border-border`
- backdrop blur: `backdrop-blur` or `backdrop-blur-xl`
- soft shadow: dark, diffuse, sometimes with emerald glow on hover

Typical visual recipe:

- dark navy card
- 5% to 10% white border
- blur behind the panel
- optional glow or color tint for emphasis

### Hover treatment

Hover states should feel refined, not jumpy:

- light border brightening
- subtle upward translation (`translateY` style lift)
- mild shadow increase
- occasional emerald halo

Avoid aggressive scale effects or flashy animated borders except for special hero/feature moments.

## 5. Typography

Fonts are defined in `web/app/layout.tsx`:

- Primary sans: `Inter`
- Monospace / data font: `JetBrains Mono`

### Usage rules

- Use Inter for headings, body copy, labels, and most UI controls.
- Use JetBrains Mono for numeric values, codes, addresses, router names, chain-specific technical metadata, and score-like readouts.

### Tone of type

- Headings are clean, bold, and compact.
- Supporting copy is muted and concise.
- Labels often use uppercase tracking for system metadata.
- Numeric and market-heavy values should feel terminal-like via monospace treatment.

Common patterns:

- page titles: `text-2xl` to `text-4xl`, bold
- card titles: `text-lg` to `text-2xl`, semibold or bold
- metadata labels: `text-[10px]` to `text-xs`, uppercase, tracked wider
- support copy: `text-sm` / `text-xs`, muted foreground

## 6. Layout Structure

The app uses a persistent shell, not isolated full-page marketing sections.

### App shell

- Desktop: left sidebar navigation, content on the right
- Mobile: bottom navigation and stacked content
- Main content uses centered containers with generous horizontal padding
- Background hero glow is global and fixed behind content

### Sidebar behavior

- Sidebar is semi-transparent dark background with a subtle right border
- Nav groups are separated by small section labels in uppercase muted text
- Active nav item uses emerald tint on a soft brand background
- Inactive nav stays low contrast until hover

### Page composition

Most screens follow this shape:

1. Page heading and short explanatory subtitle
2. Filters, actions, or status controls near the top
3. Grid or stacked glass cards below
4. Dense data inside cards, broken into readable blocks

## 7. Spacing, Shape, and Rhythm

### Radius

- Global radius token: `0.75rem`
- Common practical radii:
  - buttons / pills: `rounded-xl` or `rounded-full`
  - cards / panels: `rounded-2xl`
  - avatars / token marks: `rounded-full`

### Spacing feel

- Prefer roomy outer spacing with denser inner data layout
- Cards usually use `p-4`, `p-5`, or `p-6`
- Major page sections often separate with `mb-6`, `mb-8`, or `mb-12`
- Tight metadata stacks can use `text-xs` with compact line spacing, but never become cramped

## 8. Motion and Interaction

Motion is subtle and informative.

Existing motion vocabulary from `web/app/globals.css` includes:

- `fadeIn`
- `fadeInUp`
- `fadeInDown`
- `slideUp`
- `scaleIn`
- `float`
- `pulseGlow`
- `gradient-shift`
- shimmer loading

### Motion rules

- Use motion to suggest polish and status, not entertainment
- Entry animations should be soft and short
- Hover transitions should feel responsive but calm
- Glow pulses should be used sparingly on high-value items
- Reasoning / system areas can animate slightly more than standard analytics cards

Avoid long theatrical animations, large parallax moves, or anything that competes with the data.

## 9. Component Patterns

### Buttons

Buttons are rounded and clean, with a strong emerald primary state.

Key variants in `web/components/ui/button.tsx`:

- `default`: primary emerald
- `outline`: dark surface with border
- `secondary`: muted dark fill
- `ghost`: very low-emphasis hover surface
- `glow`: stronger emerald CTA with luminous shadow

Use:

- primary emerald buttons for the main task on the page
- outline buttons for filters and secondary actions
- ghost buttons for lightweight shell navigation or icon controls

### Badges and pills

Badges are common and important.

They should be:

- small
- rounded-full or softly rounded
- border-backed
- color-coded semantically
- often uppercase or dense utility labels

Use badges for:

- risk verdicts
- chain labels
- router/provider labels
- status chips
- preview / coming soon labels

### Glass cards

Glass cards are the main reusable container. They should remain consistent across new surfaces:

- translucent dark fill
- subtle white border
- blur
- rounded-2xl
- optional emerald hover border or glow

### Data rows

Table-like or list rows should not feel like traditional HTML tables unless needed. Prefer card-like row strips with:

- rounded corners
- low-contrast background
- hover tint
- clear left/right data grouping
- monospace for numerical fields

## 10. Iconography

The product uses Lucide icons. Icons should remain:

- simple
- outline-based
- consistent in stroke weight
- usually `h-4 w-4` to `h-6 w-6`

Color rules:

- emerald for primary meaning or security-positive actions
- purple for AI/system intelligence
- muted foreground for neutral utility
- red / yellow only for semantic alerts

## 11. Imagery and Background Effects

The background is not flat. It uses soft atmospheric effects:

- fixed emerald hero glow
- blurred floating orbs in hero areas
- radial and mesh gradients
- subtle grid overlay for technical feel

These should remain faint. They exist to give depth and identity, not to reduce legibility.

## 12. Page-Specific Guidance

### Marketing / landing surfaces

The homepage is the most expressive surface:

- stronger glow
- more decorative gradient work
- animated hero typography
- feature cards with lifted hover states
- stat cards with emerald-tinted fills

This is the upper bound of visual intensity.

### Analytics pages

Dashboard, Trending, Portfolio, Token, Pool, and Smart Money pages should be more restrained:

- cleaner grid layouts
- glass panels with clearer data hierarchy
- less decorative animation
- stronger emphasis on numbers, labels, and signal

### Agent pages

The agent pages are the bridge between Ilyon branding and the external agent platform patterns.

For `/agent/chat` and `/agent/swap`:

- keep Ilyon's emerald as the overall brand accent
- use purple for AI reasoning and structured system elements
- retain glass cards and dark shell so these pages feel native to Ilyon
- use monospace for routes, scores, and technical execution metadata
- preserve chat polarity: assistant/system uses neutral or purple framing, user uses emerald framing

## 13. Agent Surface Rules

This matters for the second part of the project.

### Chat

The AI chat page should look like a premium crypto copilot, not a generic support chat.

Required cues:

- large dark content area inside the standard shell
- emerald preview/status banner when applicable
- assistant bubble: neutral dark glass bubble
- assistant avatar/system marker: purple tint
- user bubble: emerald-tinted bubble
- reasoning accordion: purple-tinted bordered panel with technical metadata styling
- structured cards: dark glass containers with labeled stats, badges, and small technical chips

### Swap

The AI swap page should feel like a guided pre-composer that hands off to the chat.

Required cues:

- large centered composer card
- token inputs inside nested dark rounded panels
- side rail with explanatory glass cards
- emerald CTA for the handoff action
- purple or blue accents for routing/provider metadata
- technical estimate strip using small monospace values

## 14. Information Hierarchy Rules

When designing new sections, prioritize in this order:

1. Primary task or conclusion
2. Key numeric signal
3. Supporting metadata
4. Deep technical detail

In practice:

- the title or main action should be visually obvious first
- the main score, price, APY, or route should be second
- badges, timestamps, and providers should be third
- explanatory paragraphs should not dominate the screen

## 15. Copy Style

Copy should be:

- concise
- direct
- technical but still readable
- confident without hype

Good examples:

- "Multi-chain token and pool intelligence"
- "Preview of the AI Agent Chat layout"
- "Final route, simulation, and wallet signature happen inside the Agent Chat"

Avoid:

- meme language
- overly promotional crypto copy
- long marketing paragraphs inside dense product screens
- vague labels like "Insights" when a more specific label is possible

## 16. Implementation Do / Don't

### Do

- keep the app dark-first
- use emerald as the main brand and interaction accent
- reserve purple/blue for AI/system contexts
- use translucent glass cards with blur and soft borders
- use Inter for normal UI and JetBrains Mono for numeric/technical data
- use rounded-xl and rounded-2xl shapes consistently
- keep hover effects subtle and premium
- structure dense information into small grouped blocks

### Don't

- switch the product into a bright light theme
- introduce unrelated accent colors as primary branding
- use flat white cards or sharp-corner enterprise styling
- make the design look like a meme coin dashboard
- over-animate every component
- use giant gradients behind important text
- turn the agent views into a generic chatbot aesthetic

## 17. Practical Token / Chain / Risk Styling Rules

When a screen contains token, chain, or protocol metadata:

- chain-specific labels can use blue, violet, sky, or indigo chip colors
- safety-positive outcomes should still resolve back to emerald
- warnings should use amber before red when the condition is cautionary rather than catastrophic
- numbers, APYs, rates, router names, and tx metadata should often use monospace styling

## 18. Recommended Default for Part Two

If the second part of the project needs new screens and the other agent has to make judgment calls, this is the default direction to follow:

- use the current Ilyon shell
- use glass cards with dark translucent fills
- keep emerald as the brand/action accent
- use purple only for AI reasoning, router/system intelligence, or structured machine output
- favor compact, high-signal layouts over decorative marketing composition
- make every panel feel credible for crypto risk analysis

## 19. Ground-Truth Files

These files are the best source of truth for the current visual language:

- `web/app/globals.css`
- `web/app/layout.tsx`
- `web/app/page.tsx`
- `web/components/layout/sidebar.tsx`
- `web/components/layout/nav-config.ts`
- `web/components/ui/button.tsx`
- `web/components/ui/card.tsx`
- `web/components/ui/badge.tsx`
- `web/app/dashboard/page.tsx`
- `web/app/trending/page.tsx`
- `web/app/agent/chat/page.tsx`
- `web/app/agent/swap/page.tsx`
- `docs/ai-agent-integration.md`

## 20. Final Summary for the Other Agent

Replicate IlyonAI as a dark, glassy, emerald-branded crypto intelligence interface. Keep the core shell, spacing, rounded surfaces, and translucent cards. Use emerald for brand/action/safe states, and use purple/blue only for AI reasoning or system-level technical framing. Favor crisp typography, monospace numbers, compact data grouping, and subtle premium motion.
