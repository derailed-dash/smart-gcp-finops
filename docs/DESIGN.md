# Design System Document: Emerald Cyber Visual Language

## 1. Overview & Creative North Star: "The Neon Core"
This design system, **"Emerald Cyber"**, is engineered to evoke high-precision engineering, energy efficiency, and operational speed. Our Creative North Star, **"The Neon Core"**, models the interface after a advanced grid system or clean energy fusion core. We avoid muddy shadows and excessive light sources in favour of dark, high-contrast carbon surfaces separated by pure, glowing vector lines.

The aesthetic balance is strictly high-performance utility: deep dark backgrounds representing cold space, paired with vibrant, high-energy neon emerald representing optimized, active financial flow.

---

## 2. Colors & Surface Philosophy

### The Palette
The core color system is built around dark, carbon-rich surfaces punctuated by high-voltage active indicators:
*   `surface` (Base Background): `#080B0D` (deep, pure carbon black)
*   `surface_container` (Mid-ground card base): `#0F1418` (dark obsidian gray)
*   `surface_container_high` (Active/Interactive surface): `#161D22` (medium charcoal)
*   `surface_container_highest` (Tooltip/Popup overlay): `#1E272E`
*   `primary` (Cyber Emerald): `#00F59B` (high-energy, glowing cyber emerald green)
*   `on_primary`: `#040708` (deep black, for text placed on top of emerald)
*   `secondary` (Dark Emerald): `#059669` (for secondary actions and muted states)
*   `tertiary` (Cyber Teal): `#00E5FF` (neon teal, for metrics, data points, and tooltips)
*   `error`: `#EF4444` (neon cherry red, for cost spikes and critical anomalies)

### The "Subtle Glow" Rule
Borders are never pure grey. Boundaries are established using high-contrast surface changes or a semi-transparent glowing outline:
*   **Default borders**: `outline_variant` is `#00F59B0F` (6% opacity emerald green). This creates an extremely subtle, glowing green perimeter that reacts on hover.
*   **Active/Focus borders**: `#00F59B3D` (24% opacity emerald green).
*   **Glassmorphism overlays**: Use `#161D224D` (30% opacity surface) with a `backdrop-filter: blur(16px)` for floating control panels and headers.

---

## 3. Typography

*   **Display & Headlines**: Orbitron / Space Grotesk style. Wide, technical, high-precision geometry. Fits the aerospace console feel.
*   **Body & Technical Labels**: Inter / Roboto. Extremely readable, clean sans-serif optimized for numbers and multi-column tables.
*   **Typography Weights**:
    *   Technical headers: Bold, tight letter spacing (`-0.02em`).
    *   Numbers / Metrics: Monospace-style alignment, semi-bold `tertiary` (`#00E5FF`) text.

---

## 4. Components

### 1. Split-Screen Layout
*   **Left Column (Chat)**: Base background `surface` (`#080B0D`). Glassmorphic top bar containing status. Input box anchored at the bottom with a pulsing `#00F59B26` border.
*   **Right Column (Canvas)**: Surface `surface_container` (`#0F1418`). A spacious workspace designed for heavy visual payloads.

### 2. KPI Cards (Emerald Accents)
*   Background: `surface_container_high` (`#161D22`).
*   Accent: Top-border thin neon line in `primary` (`#00F59B`) for positive/optimized metrics or `error` (`#EF4444`) for active anomalies.
*   Value text: Large, glowing font in `#FFFFFF` or `#00E5FF`.

### 3. A2UI Pivot Tables
*   Headers: `surface_container_highest` (`#1E272E`), uppercase lettering, `outline_variant` bottom border.
*   Rows: Alternate background between `surface_container` and `surface_container_high`. No vertical lines.
*   Sorting icons: Neon glowing arrows when active.

### 4. Interactive Charts
*   Grid lines: Very faint `#FFFFFF08`.
*   Data curves: Neon glowing paths in `primary` (`#00F59B`) and `tertiary` (`#00E5FF`) with vertical glow gradients below.

### 5. Telemetry Syncing Loader Overlay
*   **Trigger**: Active during SSE streaming of telemetry payloads (detected when `isStreaming` is `true` and JSON block starts).
*   **Aesthetics**: Glassmorphic absolute-positioned container over the right column canvas (`background-color: rgba(8, 11, 13, 0.75)` with `backdrop-filter: blur(3px)`).
*   **Visual Elements**:
    *   Outer Spinning Ring: Glowing cyber emerald border (`3px solid rgba(0, 245, 155, 0.05)` with `borderTopColor: var(--color-primary)`) animating inline.
    *   Inner Pulsing Core: Glow-pulsed circular green dot (`box-shadow: 0 0 10px rgba(0, 245, 155, 0.4)`).
    *   Vertical Scanning Beam: Glowing linear gradient neon laser scanning downwards continuously (`animation: scan-vertical 3s linear infinite`).

### 6. Chat Starter Chips
*   **Aesthetics**: Glassmorphic dark card in the chat input sidebar (`background: var(--color-surface)` with `border: var(--border-glow-default)`).
*   **Interactivity**: Moves on hover with a smooth transition (`transition: var(--transition-fast)`), brightening boundaries to `var(--color-primary)` and applying a glowing neon background glow (`rgba(0, 245, 155, 0.04)`).
*   **Disabled State (Loading Guard)**: Opacity is restricted to `0.5` with a locked pointer indicator (`cursor: not-allowed`). All active hover scaling and background glow animations are completely suppressed to provide intuitive visual gating.

