---
name: ChiangMaiEyes
description: Public environmental intelligence dashboard for Chiang Mai smoke, PM2.5, hotspots, wind, and risk.
colors:
  civic-green: "#16a34a"
  civic-green-deep: "#0f6b54"
  forest-ink: "#10231d"
  mist-bg: "#eef3ef"
  paper: "#ffffff"
  soft-paper: "#f6faf7"
  border-mist: "#e3ece6"
  muted-leaf: "#5a6d63"
  warning-amber: "#eab308"
  hotspot-red: "#dc2626"
  wind-blue: "#3b82f6"
  smoke-orange: "#f97316"
  severe-purple: "#7c3aed"
typography:
  display:
    fontFamily: "Inter, Noto Sans Thai, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.9rem"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "0"
  headline:
    fontFamily: "Inter, Noto Sans Thai, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.35rem"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "0"
  title:
    fontFamily: "Inter, Noto Sans Thai, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "0"
  body:
    fontFamily: "Inter, Noto Sans Thai, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.9rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "0"
  label:
    fontFamily: "Inter, Noto Sans Thai, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.78rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0"
rounded:
  xs: "3px"
  sm: "8px"
  md: "12px"
  lg: "18px"
  pill: "999px"
spacing:
  xs: "6px"
  sm: "10px"
  md: "16px"
  lg: "20px"
  xl: "32px"
components:
  button-icon:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.civic-green-deep}"
    rounded: "{rounded.md}"
    width: "42px"
    height: "42px"
  button-filled:
    backgroundColor: "{colors.forest-ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.md}"
    width: "42px"
    height: "42px"
  filter-pill-active:
    backgroundColor: "{colors.civic-green}"
    textColor: "{colors.paper}"
    rounded: "{rounded.pill}"
    padding: "7px 14px"
  card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.forest-ink}"
    rounded: "{rounded.lg}"
    padding: "18px"
---

# Design System: ChiangMaiEyes

## 1. Overview

**Creative North Star: "Calm Civic Control Room"**

ChiangMaiEyes should feel like a public-interest control room that has been made humane: trustworthy, modern, and calm enough for daily use, but precise enough to support decisions during smoke season. The existing system uses a restrained green civic palette, white cards, soft mist backgrounds, and compact data modules to make environmental signals readable without turning the page into an emergency siren.

This is product UI, so design serves the task. The interface should feel familiar, fast, and dependable: clear labels, visible source freshness, predictable controls, and map-first situational awareness. Decoration is allowed only when it improves comprehension or gives local environmental context.

The system explicitly rejects stiff government portals, crypto-trading dashboards, alarmist red-heavy emergency screens, dense expert-only GIS controls, decorative complexity, vague AI-style marketing copy, and layouts that make the current situation hard to find.

**Key Characteristics:**
- Restrained civic green identity with semantic risk colors used only for state.
- White card surfaces over a pale mist background for calm public readability.
- Single sans typography tuned for Thai and English scanning.
- Map-first dashboard structure with compact panels for PM2.5, hotspots, wind, and advice.
- Soft elevation and clear borders instead of heavy drama.

## 2. Colors

The palette is a restrained civic green system with semantic environmental accents. Green carries identity and safe/current states; amber, orange, red, purple, and blue carry data meaning only.

### Primary
- **Civic Green** (`civic-green`): The primary action, selection, live status, PM2.5-good, and brand accent color. Use it sparingly so it stays meaningful.
- **Deep Civic Green** (`civic-green-deep`): The brand mark gradient endpoint, icon color, map boundary, and high-trust text accent.

### Secondary
- **Wind Blue** (`wind-blue`): Wind direction, wind field, and weather movement. Do not use it as generic decoration.

### Tertiary
- **Warning Amber** (`warning-amber`): Medium risk and watch states.
- **Smoke Orange** (`smoke-orange`): Elevated smoke or hotspot-adjacent warning.
- **Hotspot Red** (`hotspot-red`): High risk, hotspot cores, and genuinely severe public-health signals.
- **Severe Purple** (`severe-purple`): Extreme PM2.5 severity only.

### Neutral
- **Forest Ink** (`forest-ink`): Main text and dense data labels.
- **Mist Background** (`mist-bg`): App background and environmental field.
- **Paper** (`paper`): Main card and toolbar surface.
- **Soft Paper** (`soft-paper`): Pills, quiet status chips, and secondary surface fill.
- **Border Mist** (`border-mist`): Card borders, dividers, toolbar outlines.
- **Muted Leaf** (`muted-leaf`): Supporting labels, timestamps, source text, and low-emphasis metadata.

### Named Rules

**The Semantic Color Rule.** Amber, orange, red, purple, and blue are data-state colors. Never use them as decorative accents unrelated to PM2.5, hotspots, risk, or wind.

**The Red Earns Its Place Rule.** Red is reserved for high-risk and hotspot meaning. A screen covered in red is prohibited because it becomes alarmist and unreadable.

## 3. Typography

**Display Font:** Inter with Noto Sans Thai and system sans fallback
**Body Font:** Inter with Noto Sans Thai and system sans fallback
**Label/Mono Font:** Same sans stack

**Character:** The type system is utilitarian, calm, and data-literate. It should make Thai labels, numbers, and mixed English source names fit naturally in the same dashboard without needing a display face.

### Hierarchy
- **Display** (800, `1.9rem`, 1.1): Product name and top-level identity only.
- **Headline** (800, `1.35rem`, 1.2): Map title and major section titles.
- **Title** (700, `0.95rem`, 1.3): Card titles and compact panel headings.
- **Body** (400, `0.9rem`, 1.6): Advice copy, public explanations, and supporting text.
- **Label** (700, `0.78rem`, 1.2): Pills, timestamps, controls, badges, stats, and compact metadata.

### Named Rules

**The Thai Scan Rule.** Thai text must wrap cleanly, stay at practical UI sizes, and never rely on compressed letter spacing or decorative font choices.

**The Number Priority Rule.** Numbers such as PM2.5, hotspot count, wind speed, and risk score may be large and bold; explanatory prose should stay quiet and legible.

## 4. Elevation

The system uses soft ambient elevation plus borders. Cards and controls are readable because of tonal separation first, then shadows. Shadows should feel like soft daylight on paper, not floating SaaS glass.

### Shadow Vocabulary
- **Small Ambient** (`0 6px 18px rgba(20, 52, 38, 0.06), 0 1px 2px rgba(20, 52, 38, 0.04)`): Resting cards, topbar, map stage, and compact controls.
- **Panel Lift** (`0 18px 44px rgba(20, 52, 38, 0.1), 0 2px 6px rgba(20, 52, 38, 0.04)`): Hovered cards or panels that need focus.
- **Inspector Lift** (`0 18px 46px rgba(15, 54, 39, 0.16)`): Map inspector overlays and floating contextual panels.
- **Strong Lift** (`0 28px 64px rgba(16, 46, 34, 0.16)`): Rare, high-priority overlays only.

### Named Rules

**The Paper First Rule.** Use border, background, and spacing before adding shadow. If the shadow is the only reason a surface is readable, the layout is too weak.

## 5. Components

### Buttons
- **Shape:** Gently rounded product controls (`12px`) for icon buttons; fully rounded pills (`999px`) for filter chips.
- **Primary:** Active filter pills use Civic Green background with Paper text and `7px 14px` padding.
- **Hover / Focus:** Hover shifts to Soft Paper or a slightly deeper fill in 150-200 ms. Focus states must be visible and should use the green identity, not browser-default blue where possible.
- **Filled Icon:** Filled icon buttons use Forest Ink background with Paper icons for global commands such as menu.

### Chips
- **Style:** Status and filter chips are rounded pills with bold label typography.
- **State:** Selected chips use Civic Green. PM2.5 category badges use the semantic AQI color, paired with text so color is not the only signal.

### Cards / Containers
- **Corner Style:** Main dashboard cards use `18px` radius; overlays use tighter `8px` radius when they need to feel denser and map-native.
- **Background:** Main cards use Paper; secondary pills and quiet surfaces use Soft Paper.
- **Shadow Strategy:** Cards rest on Small Ambient elevation and may lift to Panel Lift on hover.
- **Border:** Use Border Mist consistently; avoid colored side stripes.
- **Internal Padding:** Main cards use `18px`; compact status pills use `8px 14px`.

### Inputs / Fields
- **Style:** There are no full text inputs in the current dashboard. Future fields should follow the button and card vocabulary: Paper background, Border Mist stroke, `12px` radius, and clear focus outline.
- **Focus:** Focus should increase border contrast and add a subtle Civic Green ring.
- **Error / Disabled:** Error uses Hotspot Red only for the actual error affordance; disabled states use muted text and low-contrast neutral fill.

### Navigation
- **Style, typography, default/hover/active states, mobile treatment.** Navigation is currently a compact topbar with brand lockup, live update pill, refresh action, and menu action. Mobile stacks the topbar and keeps actions reachable. Future navigation should preserve this compact, task-first structure.

### Map Stage

The map is the signature component. It should remain full, direct, and data-forward: soft geographic fills, clear Chiang Mai boundary, semantic PM2.5 and hotspot markers, wind field motion that respects reduced-motion preferences, compact inspector cards, and filter pills that do not obscure the map.

## 6. Do's and Don'ts

### Do:
- **Do** keep the current situation visible first: map, PM2.5, hotspots, wind direction, and risk score must be reachable without scrolling on desktop.
- **Do** use Civic Green for identity, current selection, safe status, and primary action only.
- **Do** pair every risk color with text labels, icons, or numbers so the interface works for color-blind users.
- **Do** show source names, update times, fallback notices, and formula logic in quiet but findable metadata.
- **Do** keep Thai labels short, scannable, and readable on mobile.
- **Do** use soft elevation and borders to separate surfaces.

### Don't:
- **Don't** make the interface feel like a stiff government portal.
- **Don't** make it look like a crypto trading dashboard.
- **Don't** create an alarmist emergency screen covered in red.
- **Don't** add dense expert-only GIS controls unless they are progressively disclosed.
- **Don't** add decorative complexity that does not help users understand smoke, PM2.5, hotspots, wind, or risk.
- **Don't** write vague AI-style marketing copy.
- **Don't** hide the current situation behind layout complexity or oversized decorative sections.
