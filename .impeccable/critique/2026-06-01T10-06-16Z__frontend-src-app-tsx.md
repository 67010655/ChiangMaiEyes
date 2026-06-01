---
target: dashboard
total_score: 29
p0_count: 0
p1_count: 3
timestamp: 2026-06-01T10-06-16Z
slug: frontend-src-app-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Loading only swaps the pill label; no skeletons, refresh has no spinner, 5-min auto-refresh is invisible |
| 2 | Match System / Real World | 3 | Strong Thai-first domain language; raw `สมการ` formula string and English "Confidence" leak through |
| 3 | User Control and Freedom | 3 | Map reset/zoom/layers are good; hamburger menu is a dead control; inspector can't be dismissed |
| 4 | Consistency and Standards | 3 | Mostly cohesive; inert Info icons and dead menu break the "interactive = does something" contract |
| 5 | Error Prevention | 3 | Read-only surface; snapshot fallback is good prevention; little to get wrong |
| 6 | Recognition Rather Than Recall | 3 | Legend, labels, map-help all present; inactive layer state is only weakly signalled |
| 7 | Flexibility and Efficiency | 3 | Wheel + buttons + keyboard-focusable markers; no shortcuts or deep-linkable state |
| 8 | Aesthetic and Minimalist Design | 3 | Clean base; fabricated sparkline, placeholder gradients, and dense map layers add noise (visual density source-inferred, not rendered) |
| 9 | Error Recovery | 3 | Plain-Thai fallback notice is clear; no retry affordance inside the banner |
| 10 | Help and Documentation | 2 | Info icons promise help and deliver none; risk formula shown raw with no plain explanation |
| **Total** | | **29/40** | **Good — solid foundation, address the weak areas** |

## Anti-Patterns Verdict

**Does this look AI-generated?** No, not in the damning sense. It has earned identity: a disciplined civic-green system, a hand-built interactive SVG map of Chiang Mai, semantic-only use of amber/red/blue. A user fluent in good dashboards would mostly trust it. The tells that remain are placeholder content and a few inert affordances, not generic composition.

**LLM assessment:** The aesthetic is calm and on-brief. The failures are specific, not systemic: (1) a hardcoded "24h trend" sparkline rendered under real-looking time-axis labels; (2) CSS-gradient placeholder imagery in the map inspector; (3) controls that look interactive but do nothing (hamburger, three Info icons); (4) muted/light-gray text below WCAG AA.

**Deterministic scan:** `detect.mjs` returned 2 warnings on `frontend/index.html` — `overused-font` (Inter) and `single-font` (Inter only). For this **product** register both are register-appropriate, not defects: `product.md` explicitly permits Inter/system stacks and states "one family is often right." Treat as optional identity polish, not a fix. No structural slop (no gradient text, no side-stripe borders, no glassmorphism-as-default, no over-rounding) was found.

**Visual overlays:** No browser visualization available this session (no running dev server, no browser-automation tool). Browser leg of Assessment B is **degraded**; findings below are source-inferred from App.tsx / DashboardMap.tsx / global.css. Items tagged "to verify" need a render to confirm.

## Overall Impression

This is a competent, genuinely caring civic dashboard that already clears the "is it AI slop" bar. The single biggest opportunity is **trust**: the product's stated spine is "trust through traceability," yet the most prominent quick-read widgets show fabricated or placeholder content, and the one piece of real traceability (the risk formula) is rendered too light to read. Fix the credibility leaks and the contrast, and this jumps from "good" to "shippable with confidence."

## What's Working

1. **Disciplined, on-brief color system.** Civic green carries identity; amber/red/blue appear only where they map to PM2.5, hotspot, risk, and wind. Exactly the "Calm Civic Control Room" intent.
2. **A genuinely accessible custom SVG map.** Districts and markers are keyboard-focusable with `role`/`aria-label`/`<title>`, `keySelect` handles Enter/Space, the inspector is `aria-live="polite"`, and the wind field is `aria-hidden` with a `prefers-reduced-motion` fallback. Hand-built accessible map interaction is rare and well done.
3. **Honest failure handling.** When the live API is down, the app falls back to a snapshot and says so in plain Thai. Color is never the sole signal (bubbles carry the number, badges/donut pair color with text).

## Priority Issues

- **[P1] Muted and light-gray text fail WCAG AA.** `--muted #6b7d74` measures ~4.37:1 on white — under the 4.5:1 floor for small/non-bold text, which is exactly where it is used (`.topbar p`, `.live-pill span`, `.pm-card__value` unit, station metadata). Lighter grays fail outright: `#9aaaa1` on `.risk-card__formula`, `.risk-donut__max`; `#a9b8b0` on `.pm-card__axis`. The irony: the risk formula is the literal traceability artifact, rendered too light to read.
  - **Why it matters:** PRODUCT.md targets WCAG AA and calls out small data labels specifically. Low-vision and bright-outdoor mobile users lose the metadata that builds trust.
  - **Fix:** Darken `--muted` toward the ink end (e.g. `#51635a`/`#4a5d54`, both already in use) to clear 4.5:1; reserve the lightest grays for non-text decoration only; bump formula/axis text to a readable tone.
  - **Suggested command:** `$impeccable audit` (then `clarify` for the formula copy)

- **[P1] Inert affordances that look interactive.** The hamburger `Menu` button has no handler; the three `Info` (ⓘ) icons have no tooltip, no popover, no `onClick`, and sit at `#b3c2ba` (near-invisible). They promise function and fail on recall.
  - **Why it matters:** A first-timer or community worker taps "ⓘ" expecting an explanation of PM2.5 / the risk score / the formula and gets nothing. Dead controls erode trust faster than missing ones.
  - **Fix:** Wire them (menu → a real drawer or remove; Info → a popover explaining the metric and the risk formula in plain Thai) or remove them entirely. If kept, raise contrast and make them real `<button>`s.
  - **Suggested command:** `$impeccable harden` (or `clarify` for the explanatory copy)

- **[P1] Fabricated 24h trend presented as real data.** `Sparkline()` renders hardcoded points `[10,9,11,8,...]` *under axis labels `00:00 / 08:00 / 16:00`*. The code comment admits it is a placeholder; the axis labels make it read as a real measured series.
  - **Why it matters:** This is the sharpest violation of "trust through traceability." A resident reading a smooth fake line could misjudge whether conditions are improving.
  - **Fix:** Either wire a real 24h series, or until the backend exposes one, drop the time-axis labels and render it as an explicitly illustrative element (or remove it). Never pair fabricated data with a real-looking axis.
  - **Suggested command:** `$impeccable harden` (or `distill` to remove)

- **[P2] Mobile hierarchy buries the answer.** In the single-column collapse, `.side-panel { order: 2 }` pushes the PM2.5 value, risk score, and public advice *below* a 500–560px interactive map. A resident asking "is it safe to go outside today?" must scroll past a full screen of map to reach the actionable summary.
  - **Why it matters:** Directly contradicts "make the current situation obvious first," and most acutely for the on-the-go mobile resident the product is built for.
  - **Fix:** On mobile, surface a compact PM2.5 + risk + advice summary above the map (reorder, or a condensed status strip), keeping the full map below.
  - **Suggested command:** `$impeccable adapt`

- **[P2] Placeholder imagery reads as unfinished.** The inspector's `map-inspector__photo--*` blocks are CSS `linear-gradient`s captioned with real place names ("Chiang Mai province", "Bhubing"…). No one mistakes a gradient for a photo, but the captioned abstract blocks read as scaffolding in an otherwise finished panel.
  - **Why it matters:** Undercuts the polished, credible feel exactly where the user has drilled into a specific place.
  - **Fix:** Ship real imagery (station/landmark photos or a small map thumbnail), or drop the photo block and let the data + label stand.
  - **Suggested command:** `$impeccable harden` (or `distill` to drop)

- **[P3] Decorative advice-card scene adds nothing.** The advice card ends with a small SVG of hills/sun/trees (4 clean geometric paths — not a doodle). It is purely decorative on a high-stakes public-health message and mildly undercuts the calm-authority tone.
  - **Why it matters:** Low impact, but the advice card is where calm credibility matters most.
  - **Fix:** Remove it, or replace with a single restrained tonal band keyed to the current PM2.5 color.
  - **Suggested command:** `$impeccable distill`

## Persona Red Flags

**Sam (Accessibility-dependent):** Muted/light-gray text fails 4.5:1 across metadata (the most consequential a11y issue). The three Info icons are non-interactive `<svg>`s, not buttons, so a keyboard/screen-reader user can't reach the "help" they imply. *Working in his favour:* map markers and districts are properly focusable and labelled, the inspector announces via `aria-live`, focus-visible styles exist, and color is never the sole signal — genuinely above average.

**Alex (Power user):** No keyboard shortcuts for zoom/refresh/layer toggles; refresh is click-only with no feedback; selection state isn't deep-linkable. Minor for a glance dashboard, but a daily local operator would want a hotkey to refresh and a shareable view.

**Project persona — "Community worker explaining to others" (first-timer-adjacent):** Taps "ⓘ" to explain the risk score to a resident and gets nothing. The raw `สมการ` formula string is shown but not translated into plain meaning. The fake sparkline could lead them to narrate a trend that isn't real.

## Minor Observations

- Emoji in chrome (🕒 on every `.card__foot`, 🔥 markers + legend) is readable but slightly informal for a civic-trust product; lucide icons would match the rest of the icon set.
- The big centered "เชียงใหม่" map label duplicates the titlebar "แผนที่จังหวัดเชียงใหม่" — consider muting one.
- `live-dot` is static (no pulse). Fine for "calm," but combined with the label-only loading state, "live" is asserted more than shown.
- Map visual density (neighbour labels + district labels + center label + wind + plumes + bubbles + emoji + legend + scale + help + chip + inspector) may read busy — **to verify in a render**.

## Questions to Consider

- What if the mobile view opened with a single honest sentence — "PM2.5 32, ปานกลาง, ออกกำลังกลางแจ้งได้" — before any map?
- Does a dashboard whose value is *trust* earn anything from a sparkline and gradient "photos" it has to fake?
- What would the most confident version of the risk card look like if the formula were a plain-Thai explanation a resident could repeat out loud?
