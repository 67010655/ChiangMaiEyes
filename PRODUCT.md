# Product

## Register

product

## Users

ChiangMaiEyes is for people in Chiang Mai and nearby local teams who need to understand smoke, PM2.5, hotspot, and wind conditions quickly. Users may be residents checking whether it is safe to go outside, community workers explaining conditions to others, or local operators looking for a fast situation read on mobile and desktop.

## Product Purpose

ChiangMaiEyes shows fire and smoke in Chiang Mai in a way people can trust, from satellites and from people on the ground. Anyone can open it and look without an account; community-forest representatives log in to receive alerts, coordinate and record incidents. Community-verified incidents are what other fire dashboards do not have. Two layers, one site: the public layer answers "is there fire or bad air near me, how old is this, whom do I call" in plain Thai; the logged-in layer answers "is my forest at risk, which way could it spread, who is responsible, record what happened in under a minute". Expert detail (statistics, formulas, model validation) lives behind Analysis and Sources, never on the first screen. Current heuristic projections must be labelled experimental; they are not measured fire perimeters or validated dispatch instructions.

Scope for the current round, the eight acceptance tasks that define "done", and what is explicitly out of scope are in `docs/PRODUCT_BRIEF.md`. Any new work must say which of those eight tasks it helps pass.

## Brand Personality

น่าเชื่อถือ, เข้าถึงง่าย, อ่านงานชัดเจน, ทันสมัย. The product voice should feel calm, public-minded, factual, and useful under pressure. It should explain risk plainly without panic, avoid hype, and make data feel approachable for non-specialists.

## Anti-references

Do not make the interface feel like a stiff government portal, a crypto trading dashboard, or an alarmist emergency screen covered in red. Avoid dense expert-only GIS controls, decorative complexity, vague AI-style marketing copy, and layouts that make the user work hard to find the current situation.

## Design Principles

Make the current situation obvious first: the map, measured PM2.5, hotspots, and wind direction should answer "what is happening now?" at a glance. Show unavailable combined risk honestly until fuel inputs and model validation exist.

Trust comes from traceability: show sources, update times, fallback states, and formula logic clearly enough that users know what they are seeing.

Design for Thai public reading: labels, advice, and hierarchy should be easy to scan in Thai, especially on mobile.

Reduce anxiety without hiding risk: use calm language and measured visual emphasis, escalating only when the data calls for it.

Keep the MVP practical: prefer dependable free-tier data, cached fallbacks, and clear next steps over complex infrastructure or overbuilt interactions.

## Accessibility & Inclusion

Target WCAG AA as the baseline. Preserve readable contrast for map overlays, status badges, and small data labels. Do not rely on color alone for PM2.5 or risk categories; pair color with text, icons, or labels. Support mobile browsers, keyboard interaction for map controls and filters, reduced motion preferences, and Thai text that wraps cleanly without clipping.
