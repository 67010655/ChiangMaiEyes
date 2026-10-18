# Scope agreed with user, 17 October 2026

Find the strongest justified fire-prediction model for ChiangMaiEyes using publicly accessible hotspot, wind speed/direction and PM2.5 inputs. Work offline. No deployment, production-data export, new website sections or UI changes without a later explicit user request to publish.

First controlled experiment: identical historical observation target, dates, training samples, alert-area budgets and hyperparameter budgets for hotspot/static/calendar, hotspot+wind, hotspot+PM, hotspot+wind+PM. Fit2024, select2025, then evaluate the frozen selected candidate per group on2026. 2026 has already been inspected in earlier work: describe it as retrospective comparison, not a pristine future test. Do not tune further from2026 results.

Add direction-relative features at each candidate cell and near past hotspots, rather than just a single province wind-speed value. PM must precede issue time; never use smoke observed after a future hotspot as an input. PM is potentially useful context, not a physical force that drives fire spread. Compare with and without it rather than presuming benefit.

Primary observable target remains subsequent nominal/high VIIRS detections in500m cells over12h. Also report later cells at least500m from prior24h hotspots to expose persistence-only performance. Neither target is verified fire perimeter/arrival-time truth. Preserve this boundary while researching better time-resolved burn labels in a later phase.

Report paired coverage at125/250/500km2, selected-cell detection fraction, missed target cells, month breakdown and paired moving-block uncertainty. Rank candidates with validation2025 only. Save all outputs here and keep prior35% result unchanged.
