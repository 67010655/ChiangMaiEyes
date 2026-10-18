# FireTrace: creator-source availability check

Checked: 2026-10-18, Asia/Bangkok. Scope: identify the creator's own public project, source, demo, license, model, data, and validation. No contact with the creator, app changes, or deployment.

## Finding

The supplied FireTrace / Wildfire Forensic Analysis screenshots correspond to the creator's current AI Lab entry **50, Wildfire, Interactive Science**, whose sole card link is [Dilum Sanjaya's original X post](https://x.com/DilumSanjaya/status/2108241054298415258). The [creator's AI Lab](https://dilum.dev/lab) does not attach a playable demo, repository, data specification, model description, or validation report to that entry. This check did **not find** public FireTrace source or an executable FireTrace demo in the inspected first-party surfaces. This is not proof that no source exists: private repositories, unindexed pens, replies, and later releases are outside the verified search.

The screenshot's labels (modeled spread, burn scars, wind, ignition probability, resources, and drones) are interface evidence. They do not establish that those layers are measured, that a forecasting algorithm is present, or how accurate one might be. No forecasting accuracy or real-incident provenance can be established from the inspected creator pages.

## Identity and exact link chain

1. [dilum.dev](https://dilum.dev/) identifies Dilum Sanjaya and its actual HTML contains the GitHub link `https://github.com/dilums` (twice, header/footer social links).
2. [github.com/dilums](https://github.com/dilums) links back to `https://dilum.dev`, lists the same name, and links `@DilumSanjaya` and `https://codepen.io/dilums`.
3. [dilum.dev/lab](https://dilum.dev/lab) contains the Wildfire card, visible extracted text `View on X 50 Wildfire Interactive Science`, with exactly one href within the card: `https://x.com/DilumSanjaya/status/2108241054298415258`.

Raw lab HTML fetched in this check: 519,862 bytes, SHA-256 `19becfa997bae820207eec28c049fb64ef27bd86b5f2a4411d759df79f3269a7`. HTML and repository API responses are mutable; these hashes describe only this retrieval, not a permanent release.

## Important same-name false match: 2023 shader art

The creator has a public MIT repository named [dilums/wildfire](https://github.com/dilums/wildfire), advertised with [a GitHub Pages homepage](https://dilums.github.io/wildfire/). **This is not the FireTrace screenshot app.**

- [GitHub repository API](https://api.github.com/repos/dilums/wildfire) reports creation `2023-03-24T12:56:47Z`, last push `2023-03-24T12:57:35Z`.
- Its [complete main tree](https://api.github.com/repos/dilums/wildfire/git/trees/main?recursive=1) has only `LICENSE`, `README.md`, `index.html`, `main.js`, and `style.css`, tree SHA `b4105b75f6af5e931479c17a3a438b03f1433517`, and `truncated: false`.
- The [README](https://github.com/dilums/wildfire/blob/main/README.md) links [the old CodePen mdOKpMp](https://codepen.io/dilums/pen/mdOKpMp).
- The full [main.js](https://github.com/dilums/wildfire/blob/main/main.js) is a 128-line Three.js shader animation: FBM/noise fragment shading, a time uniform, a plane geometry, and requestAnimationFrame. It contains no hotspot ingestion, geographic terrain, weather data, fire-spread solver, incident model, or predictive validation. Source blob SHA `dd6c8b0200f241b3544475fdb8fe5861e6daeb07`.
- The [index.html](https://github.com/dilums/wildfire/blob/main/index.html) imports Three.js 110 and a canvas. The [MIT license](https://github.com/dilums/wildfire/blob/main/LICENSE) applies to this shader repository; it does not establish a license for the separate FireTrace prototype.
- The creator's [handcrafted Three.js catalog](https://dilum.dev/handcrafted/threejs) also links the old Wildfire CodePen. This is a separate catalog from the current AI Lab entry.

An initial name-only match would therefore misidentify a procedural visual effect as a forecasting engine. The source inspection resolves that ambiguity.

## Exact repository search limits

Read the unauthenticated public [GitHub user repositories API, page 1](https://api.github.com/users/dilums/repos?per_page=100&page=1) and [page 2](https://api.github.com/users/dilums/repos?per_page=100&page=2): 100 + 16 = **116 public repositories** returned. Inspected each repository's **name, description, and homepage**, case-insensitively, for `firetrace`, `ridgeview`, `wildfire forensic`, `wildfire`, and `fire`.

| Term | Matching repository metadata |
| --- | --- |
| firetrace | None |
| ridgeview | None |
| wildfire forensic | None |
| wildfire | wildfire (the 2023 shader) |
| fire | wildfire; GOT-networks (description refers to A Song of Ice and Fire) |

Page-1 raw-response SHA-256: `37306cbfa174f70d31fcd37ce633cbe59b1341d5ac0c724b221a6e8cd3de02bb`.

Page-2 raw-response SHA-256: `e89a04bc6480531266ab149ee44f3fcfe90ca5772d4a465cfa7cfbeb127e23df`.

This was a metadata inventory, **not an exhaustive full-text search of every file of all 116 repositories**. Only the plausible `wildfire` repository received full tree and source inspection. A differently named repository could conceal relevant files; no claim of universal absence follows.

## Website and CodePen search limits

- Read the creator homepage, AI Lab, handcrafted catalog, handcrafted Three.js page, and sitemap. The current AI Lab entry above links only to X.
- The handcrafted Three.js HTML returned 156,266 bytes, SHA-256 `dfecea689a68f3eda6ce89e881ed800a078e349162e053742d4b0fdd34116295`. Case-insensitive literal counts in its raw HTML: FireTrace 0, Ridgeview 0, Wildfire Forensic 0, Wildfire 28. Duplicate markup/embedded page payloads mean 28 is not a project count.
- Tried [CodePen creator profile](https://codepen.io/dilums) and [public pens](https://codepen.io/dilums/pens/public). Direct HTTP requests returned 403; the web reader returned a JavaScript-required shell without the pen inventory. This prevents an exhaustive creator-pen search in this subtask.
- Tried the old linked pen `https://codepen.io/dilums/pen/mdOKpMp`; web retrieval was unavailable. Its equivalent GitHub code was directly read, so its shader-only identity is established independently.
- Index queries performed: `site:dilum.dev FireTrace wildfire`; `"Dilum Sanjaya" GitHub FireTrace`; `"FireTrace" "Dilum"`; `"2108241054298415258"`; `site:github.com/dilums "FireTrace"`; `"DilumSanjaya" "wildfire" source`; `site:codepen.io/dilums "FireTrace"`; `site:codepen.io/dilums "Ridgeview"`; `site:codepen.io/dilums "Wildfire"`. No exact creator FireTrace source was found. Some search results relaxed the requested restriction or were secondary commentary; those were not treated as primary evidence.
- Direct X web-reader access returned 403. This subtask did not inspect all original-post replies or claim they lack links. Parent-task browser inspection is separate evidence.

## Applicability to ChiangMaiEyes

### Additional parent-task browser evidence

The parent task successfully rendered the original X post in the background in-app browser. It shows the creator describing an idea/prototype, visualizing wildfire progression, drone hotspots and firefighting efforts, with “Made with Opus 5.5”. The body contains no solver/source/data/validation link. Only a few replies were publicly visible; full replies required login and were not inspected. The screenshot heading “Wildfire Forensic Analysis” and modeled layer names were inspected directly from the user attachment. This establishes the presented concept, not that the incident/terrain/measurements are real or simulated.

The parent also successfully rendered `https://codepen.io/dilums` and followed its visible All Pens link to `https://codepen.io/dilums/pens/public`. The showcase and first public page did not list FireTrace. The public page had a Next button and this check did not exhaust the complete paginated inventory. Thus CodePen was accessible through the actual browser despite the subtask HTTP/web-reader limitations; universal absence remains unproven.

Correction made during research: a preliminary message called the same-name 2023 shader repository the desired source/demo. Full source inspection disproved that identification and it was explicitly corrected to the user before this report. The final assessment does not rely on that false match.

**Use its product ideas now:** a shared time slider, consistent observed-versus-modeled overlays, terrain context, source timestamps, incident notes, and a clear path from an observation to a decision. These ideas can be implemented independently with our actual Thai data, without representing the visual prototype as proven prediction.

**Do not import it as a better prediction model on present evidence.** We have no inspected FireTrace solver, weights, forecasting input contract, backtest, or reuse license. The old MIT shader is reusable as an optional visual effect but offers no evidence of improved forecast skill and should not distract from the user's model-first scope.

If actual FireTrace source becomes available, evaluate its data ingestion, true issuance times, model equations, and uncertainty against the same frozen ChiangMaiEyes cases and metrics before any deployment. A visually similar interface can display an accurate model, an inaccurate model, a historical replay, or a scripted animation; the screenshot alone does not distinguish them.

## Integration assessment against the current checkout

This is a feasibility assessment; no new UI, app code, or deployment was produced for this research request.

- The existing [production frontend](../../frontend/index.html) already defines MapLibre `raster-dem` elevation sources near lines 5439–5440, enables terrain with `setTerrain` near line 5481, and synchronizes 3D hotspots in `_sync3DHotspots` near line 5722. Thus 3D geographic presentation has an existing foundation in our code. [MapLibre's official 3D terrain example](https://maplibre.org/maplibre-gl-js/docs/examples/3d-terrain/) confirms the supported rendering approach. This is independent of what renderer FireTrace uses, which remains unverified.
- The existing [historical workspace](../../frontend/public/hindcast-workspace.js) selects a historical case and scenario and draws scenario geometry alongside later detections. It provides a starting point for comparative playback, although its older scenario overlays must not be confused with a newly validated forecast.
- The existing [timed experiment directory](../../output/fire-perimeter-loop-20261017/) contains the experiment's acquisition times, georeferenced 100 m arrival-time grids, and 20 m optical reference masks. Parent-task inspection confirms these artifacts; their horizon, cloud/visibility limits, model selection split, and reference definition must accompany any playback.
- The most useful adaptation is therefore an **offline case replay**: a synchronized timeline with initial observations, a frozen model forecast, later satellite observations, wind, and community-forest boundaries. Show missed observed growth and predicted-but-unobserved areas explicitly. This makes errors interpretable for model development and helps the user understand a decision-support result. It does not itself increase model skill.
- In the screenshot, the 80–100% values are aligned with layer sliders in the Layers pane. **Our visual inference is that these are layer-opacity settings, not predictive accuracy.** Without the actual UI code or a creator explanation this remains an inference; they must not be quoted as an accuracy benchmark.

The feasible benefit is clearer historical comparison and explanation with our own data. An improvement to the prediction model cannot be credited to FireTrace until its model code, data provenance, reuse terms, and measured performance are available and tested.
