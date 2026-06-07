---
timestamp: 2026-06-06T19-06-23Z
slug: frontend-src-app-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Live-dot pulse + update timestamps present; no loading skeletons for data fetch |
| 2 | Match System / Real World | 3 | Thai labels well-matched to audience; some English jargon leaks ("PM2.5", "AQI", "ROS") |
| 3 | User Control and Freedom | 1 | Fullscreen map traps users: controls disappear behind z-index layers, no reliable Esc exit |
| 4 | Consistency and Standards | 2 | CSS has 3+ competing rule blocks for the same components (sidebar, map-stage); `!important` overrides cascade unpredictably |
| 5 | Error Prevention | 2 | Sidebar collapse/expand relies on negative margins + transforms simultaneously; can leave sidebar in half-state |
| 6 | Recognition Rather Than Recall | 3 | Layer selector is visible; sidebar tabs have icons + text labels |
| 7 | Flexibility and Efficiency | 1 | No keyboard shortcuts; no Esc to close fullscreen; no bulk layer toggle shortcut |
| 8 | Aesthetic and Minimalist Design | 1 | 15,894-line App.tsx, 6,305-line CSS with massive duplication; community-command-strip, action-grid, zone-pills all rendered simultaneously creating visual overload |
| 9 | Error Recovery | 2 | Fallback snapshot for API failures exists; no user-facing error messages when fetch fails |
| 10 | Help and Documentation | 1 | No contextual help; no tooltips on map controls; no onboarding for first-time users |
| **Total** | | **19/40** | **Poor: Major UX overhaul required** |

## Anti-Patterns Verdict

**LLM Assessment**: The interface presents several AI-generated tells:
- **Visual overload**: Every data point is rendered on-screen simultaneously with no progressive disclosure. The sidebar has 5+ tabs but the content in each tab is itself dense enough to warrant sub-sections.
- **CSS specificity wars**: The stylesheet contains 3 distinct "redesign" passes layered on top of each other (original, "Tabbed Collapsible Sidebar Layout Redesign", "Perfected V2 UX/UI Design"), all fighting via `!important`. This creates unpredictable rendering.
- **Monolith architecture**: A 15,894-line single component file is unmaintainable and causes HMR invalidation issues (visible in dev server logs).

**Deterministic Scan** (10 findings):
- 1× **side-tab accent border** (line 530): `border-left: 5px solid #16a34a` on community-zone-pill. Classic AI card tell.
- 1× **border-accent-on-rounded** (line 3586): `border-top: 3px solid` on a rounded element.
- 1× **overused-font**: Inter is the default AI font.
- 3× **bounce-easing**: `cubic-bezier(0.34, 1.56, 0.64, 1)` and `cubic-bezier(0.175, 0.885, 0.32, 1.275)` on sidebar and popup animations.
- 4× **layout-transition**: Animating `height`, `margin-left`, and `width` directly causes layout thrash.

## Overall Impression

The dashboard has strong foundational data architecture: real PM2.5, hotspot, wind, fire risk, and community forest data are all present and properly sourced. The map with Leaflet is functional and the layer system is logical. However, the UX is overwhelmed by visual noise, CSS debt, and interaction traps. The single biggest opportunity is **radical simplification**: strip the monolith into focused views, eliminate the CSS specificity wars, and make the map the hero that it should be without burying users in simultaneous data panels.

## What's Working

1. **Data richness and sourcing**: The dashboard pulls real-time PM2.5, hotspot, wind, and community forest data with proper Thai-language attribution. The fallback-to-snapshot strategy is solid.
2. **Map layer system**: The floating layer selector panel with color-coded dots is intuitive and well-labeled in Thai.
3. **Sidebar tab architecture**: The vertical ribbon tabs with icons + labels is a good structural decision for organizing the dense data categories.

## Priority Issues

### [P0] Fullscreen map traps users with no exit
**What**: When entering fullscreen map mode, UI controls (layer selector, zoom, basemap switcher) become unreachable or invisible. The user cannot exit reliably.
**Why it matters**: Users who enter fullscreen are stuck; this breaks the fundamental "User Control and Freedom" heuristic. The z-index is forced to `10000 !important` which fights with the fullscreen fixed-position overlay.
**Fix**: Remove the `!important` z-index escalation. Use a proper stacking context with `isolation: isolate` on the map container. Ensure the fullscreen toggle button and Esc key always work.
**Suggested command**: `$impeccable harden`

### [P1] CSS specificity wars create visual inconsistency
**What**: The stylesheet has 3 competing design passes:
- Lines 5305-5734: "Tabbed Collapsible Sidebar Layout Redesign"
- Lines 5736-5826: "Perfected V2 UX/UI Design" (overrides previous with `!important`)
- Lines 6151-6305: "Detail Bar & Overlay Layout Fixes" (more `!important`)
**Why it matters**: Earlier rules set `sidebar-container width: 420px`, then later rules override to `412px !important`. The sidebar collapse uses `margin-left: -420px` and `transform: translateX(-100%)` simultaneously (double-translating). This causes the sidebar to visually jump or render in half-states.
**Fix**: Consolidate into a single authoritative sidebar section. Remove all `!important` declarations. Use CSS custom properties for sidebar width so collapse/expand can reference a single value.
**Suggested command**: `$impeccable layout`

### [P1] Cognitive overload from simultaneous data display
**What**: The sidebar body renders PM2.5 card, mini-cards (hotspot count, wind, fire spread, weather), risk card, hourly forecast, daily forecast, community command strip with 4 metrics and zone pills, action grid with ranking/reporting/data-connector panels, and an AI advisor — all visible in one scrollable column.
**Why it matters**: Users cannot find the information they need because everything competes equally. The Cognitive Load Checklist fails on "Single focus", "Chunking", "Minimal choices", and "Progressive disclosure" — 4+ failures = critical.
**Fix**: Collapse secondary data behind expandable sections. Lead with the 3 highest-priority metrics (PM2.5, hotspots, risk score) and let users drill into forecasts, community data, and connectors on demand.
**Suggested command**: `$impeccable distill`

### [P1] 15,894-line monolith App.tsx causes performance and maintainability issues
**What**: The entire dashboard is a single React component file. Every edit triggers full HMR invalidation (visible in dev server logs: "Could not Fast Refresh"). The file is ~85% blank lines from successive code edits.
**Why it matters**: Development velocity is destroyed. Users experience slow reloads. The blank-line bloat makes the file 3-4× longer than its actual logic.
**Fix**: Strip blank lines first (immediate 60% reduction). Then extract sidebar tab content into separate components: `SidebarOverview.tsx`, `SidebarForecast.tsx`, `SidebarCommunity.tsx`, `SidebarContact.tsx`.
**Suggested command**: `$impeccable optimize`

### [P2] Bounce/elastic easing feels dated
**What**: Popup entrance uses `cubic-bezier(0.175, 0.885, 0.32, 1.275)` (bounce), sidebar collapse uses `cubic-bezier(0.34, 1.56, 0.64, 1)` (elastic overshoot).
**Why it matters**: Bounce and elastic easing is a dated aesthetic that makes the interface feel like a template. Product UIs should use smooth exponential deceleration.
**Fix**: Replace all bounce beziers with `cubic-bezier(0.16, 1, 0.3, 1)` (expo-out) which is already used elsewhere in the codebase.
**Suggested command**: `$impeccable animate`

## Persona Red Flags

**Alex (Power User / Fire Management Officer)**:
- No keyboard shortcuts for any map interaction (layer toggle, zoom, fullscreen, pan).
- Cannot bulk-toggle layers (e.g., "show only PM2.5 and hotspots").
- Sidebar tab switching requires mouse clicks; no keyboard tab navigation.
- The dense data in the sidebar has no search or filter capability.
- Fullscreen map has no keyboard exit (Esc key not wired).

**Jordan (First-Timer / Concerned Citizen)**:
- "PM2.5", "AQI", "ROS" (Rate of Spread), and "µg/m³" are never explained.
- The community-command-strip metrics (52 แห่ง, 6,800 ไร่) have no context — a citizen doesn't know if these numbers are good or bad.
- No visible help option, tooltips, or introductory guidance.
- The risk score donut chart has no legend explaining what 0-10 means.
- Layer selector assumes the user knows what "เชื้อเพลิง" (fuel risk) means on a map.

**Sam (Accessibility-Dependent User)**:
- Sidebar toggle button has aria-label but no focus indicator visible in the CSS.
- Color-coded risk states (green/yellow/red) rely on color alone in several places.
- The community-zone-pill uses only `border-left` color to indicate health status — invisible to screen readers and color-blind users.
- Map markers (emoji-based) have no alt text or ARIA description.
- Layer selector buttons lack `aria-pressed` attribute.

## Minor Observations

1. **Sidebar width inconsistency**: `420px` in line 5351, `412px !important` in line 5742. The collapsed state uses `margin-left: -420px` but the expanded width is forced to `412px`, creating an 8px gap.
2. **`map-detail-bar` is hidden then shown**: Line 5678 sets `display: none !important` then line 6175 tries to override with `flex-shrink: 0 !important` but doesn't remove the `display: none`. Dead code.
3. **Leaflet popup width is hardcoded** to `320px !important` (line 5962) which may clip on mobile screens.
4. **Dark theme variables** are sprinkled throughout as one-off `[data-theme='dark']` selectors rather than using CSS custom properties, making theme switching fragile.
5. **Missing `prefers-reduced-motion`** on the pulsing selection animation, popup entrance animation, and tab fade-in animation.

## Questions to Consider

- What if the sidebar only showed 3 key numbers (PM2.5, hotspots, risk) by default and everything else was behind a "ดูเพิ่มเติม" (see more) toggle?
- Does the community forest data need to live in the same view as the real-time air quality dashboard, or could it be a separate route/tab?
- What would this dashboard look like if the map took 85% of the viewport and the sidebar was a thin, collapsible inspector that only showed data for the selected feature?
