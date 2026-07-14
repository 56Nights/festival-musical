# Product‑Owner Analysis — Festival Musical Intelligent (SAE S8)

**Author:** Product owner (feature-by-feature test & critique)
**Date:** 2026‑07‑13
**Method:** every feature was actually executed, its output inspected, and its behaviour compared against what it *claims* to do. Two colleagues were consulted on every user-facing feature — a **UI (visual) designer** and a **UX (experience) designer**. Nothing below is invented; every claim is backed by a run, a rendered screenshot, or a source line.

---

## 0. How this was tested (evidence base)

| Action | Result |
|---|---|
| `uv run python run_demo.py` (full pipeline, end to end) | ✅ **Succeeds in 93 s.** TimesFM downloaded (~200 MB) and ran zero-shot (`backend: timesfm-2.5-200m`). All 9 stages completed, all artefacts written. |
| Module self-checks: `generate_data`, `geometry`, `dynamic_csp`, `optical_flow`, `mas`, `replay_sim`, `kpis`, `timesfm_forecaster` | ✅ All exit 0 and pass their asserts (with important caveats below). |
| Rendered the two HTML deliverables headless (Google Chrome) at 6 states | `map_morning` (10:30), `map_rush` (20:10), `map_headliner` (21:05), `map_egress` (23:05), `map_summary` (Bilan), `dashboard`. Saved to `outputs/_shots/`. |
| Quantitative log analysis on `control_log.json`, `events.csv`, `kpi_*.json` | Numbers cited throughout. |
| UI designer + UX designer review of both HTML surfaces + report | Scores and findings folded into each section. |

**One-line verdict:** This is an **exceptionally ambitious and well-engineered student project** — the pipeline is real, runs end to end, is honestly documented, and the animated "vue simulation" is genuinely impressive craft. But it has **three systemic weaknesses that a jury will find**: (1) a CNN that fires **112 alerts for 15 real incidents**, with false positives placed in the highest-authority UI slots; (2) two flagship "intelligence" features — **optical-flow stampede detection** and the **dynamic CSP** — that don't visibly earn their keep (flow is near-inert; the CSP thrashes and its advantage is scenario-dependent); and (3) several **internal inconsistencies** between what the code claims and what it prints/shows.

---

## 1. Scoreboard (all features)

| # | Feature | Works? | Does its job / clear? | Nothing invented? | Overall |
|---|---|---|---|---|---|
| 1 | Data / population model | ✅ | ⚠️ mostly — one intent mismatch | ✅ | **B** |
| 2 | Forecasting (TimesFM zero-shot) | ✅ | ⚠️ high error, unvalidated vs baseline | ✅ | **B‑** |
| 3 | Vision CNN (density/fall/object) | ✅ | ❌ very low precision (many FPs) | ⚠️ "99%" is misleading | **C** |
| 4 | Optical-flow stampede detection | ⚠️ runs | ❌ near-inert; fails its own demo | ⚠️ oversold | **C‑** |
| 5 | CSP dynamic allocation | ✅ | ⚠️ thrashes; benefit scenario-dependent | ✅ | **B‑** |
| 6 | MAS scenario evaluation | ✅ | ⚠️ headline result not reproduced by own self-check | ✅ | **B‑** |
| 7 | KPI A/B impact evaluator + ablation | ✅ | ✅ strong, sourced | ⚠️ "complete = best" not uniform | **A‑** |
| 8 | Integration control loop | ✅ | ⚠️ "periodic + event" collapses to "every step" | ✅ | **B** |
| 9 | Narration (LLM + template) | ✅ | ❌ dumps 112 alerts; not "brief" | ✅ | **C** |
| 10 | Dashboard (Plotly) | ✅ | ❌ chaotic alloc plot, step-index axes, needs CDN | ✅ | **C** |
| 11 | Vue simulation (Canvas twin) | ✅ | ⚠️ beautiful but overloaded; legibility issues | ⚠️ "single source of truth" not quite true | **B+** |
| 12 | End-of-day "Bilan" modal | ✅ | ✅ best surface in the product | ✅ (honest footnote) | **A‑** |
| 13 | `run_demo.py` orchestration | ✅ | ⚠️ one mislabelled console figure | ✅ | **A‑** |

---

## 2. Feature-by-feature analysis

### Feature 1 — Data / population model (`data/generate_data.py`)

**Intended:** simulate a full day (10h→midnight) with a *conserved* population, arrivals as a non-homogeneous Poisson process by visitor type, an entry bottleneck (queue), compressed egress, inertia-driven internal migration; anchored on real festival studies (~50 % arrive 16h–18h; campers stay overnight).

**What it actually does (verified):** self-check passes; population peaks at **15 391 (target 16 000)** at **17:45**; queue max **1 179**; egress T90 **75 min**; midnight population **3 270 (≈ campers 3 200)**. Conservation holds. This is a genuinely sophisticated, well-conserved model — clearly the strongest of the "backend" modules.

**Problems found:**
- ❌ **Intent mismatch — arrivals do not match the stated real-world anchor.** The self-check prints `arrivées 16h-18h : 3 %` right next to the comment `ancrage étude ~50 %`. The `planner` cohort (40 % of visitors) has its log-normal mode at ~13:45, so the crowd front-loads to early afternoon, not the 16h–18h window the README leans on. The peak population *timing* (17:45) is fine, but the arrival *shape* the model advertises is not the one it produces.
- ⚠️ **Zones exceed 100 % capacity:** SecondStage **119 %** (4 771/4 000), FoodCourt **115 %** (2 867/2 500), Entrance **208 %** (1 459/700). Entrance overflow is by design (transit/queue), but SecondStage running *hotter than MainStage-scale saturation* means the crowd-aversion penalty (`CROWD_AVERSION`) isn't containing overflow. This has a downstream effect: in the evening, *many zones read >85 % simultaneously*, which is what floods the CNN with "crowd_surge" alerts.
- ⚠️ **"Le site part vide à 10h" is not literally true:** `flow.csv` step 0 shows **onsite = 3 601** (campers already present). The morning screenshot shows 4 693 on site at 10:30. This is intended (campers sleep on site) but contradicts the "starts empty" narrative in the README.

**UI colleague:** n/a (no direct surface) — but notes the over-capacity data is what the map then *fails to visualise* (see Feature 11).
**UX colleague:** n/a directly.

**Recommendation:** either re-shape the `planner` arrival curve to actually put ~50 % in 16h–18h (move the log-normal mode later) *or* stop citing the 50 % figure. Add an assert on the 16h–18h fraction so the intent is tested, not just printed. Cap zone overflow (or document why SecondStage overflows).

---

### Feature 2 — Forecasting: TimesFM zero-shot (`forecasting/timesfm_forecaster.py`)

**Intended:** 2 h-ahead per-zone attendance forecast, zero-shot (no training), with a documented seasonal-naïve fallback offline.

**What it actually does (verified):** TimesFM loads and runs. `MAE dernier jour : 0.2137 (fraction de capacité)`. The fallback path exists and is clean.

**Problems found:**
- ⚠️ **MAE 0.21 is high** for a signal used to *trip a 0.85 threshold* and pre-position teams. A ±21 %-of-capacity error means the forecast frequently mis-ranks which zone will breach.
- ⚠️ **No validation vs the fallback.** The self-check reports TimesFM's MAE but never compares it to the seasonal-naïve baseline. For a "Concevoir" justification ("more robust than training from scratch"), you want evidence TimesFM actually beats the trivial baseline on *these* data. Right now that claim is asserted, not shown.
- ⚠️ **Overshoots at turning points** (visible in dashboard panel 1: the red forecast spikes to ~1.2 while real is ~0.9). The model doesn't "know" the headliner ends, so at 21:05 it forecasts FoodCourt at **103 % for 23:05** — exactly when egress will empty it. The in-app claim "anticipe les pics de 1 h 10 (3 zones)" only holds for 3/5 zones.

**UI colleague:** the sparklines (real solid / forecast dashed / threshold) are "the clearest single artifact in the product." ✅
**UX colleague:** great for the predictive story, but "TimesFM" is unexplained jargon for a non-technical operator; rename to "Prévision d'affluence."

**Recommendation:** print `MAE(TimesFM)` vs `MAE(seasonal-naïve)` in the self-check and in the report; if TimesFM doesn't beat the baseline here, say so honestly (that's a *fine* Compétence-5 "limite"). Consider clipping/damping the forecast near known schedule end-points.

---

### Feature 3 — Vision CNN: density / fallen / object (`vision/`)

**Intended:** ResNet18 (frozen ImageNet backbone) + 3 heads; transfer learning; "chute ≈ 99 %, objet ≈ 88–99 %, densité MAE ≈ 0.10."

**What it actually does (verified):** loads, runs in the pipeline, produces the alerts. The accuracy numbers are measured on a **held-out synthetic split (`vision/train.py` `_eval`) with ~30 % positive prevalence.**

**Problems found (this is the product's biggest correctness liability):**
- ❌ **Precision collapses in the pipeline.** Over the replayed day: **112 CNN alert-instances for 15 ground-truth incidents (≈ 7:1).** Specifically **46 "fallen_person" alerts, of which 6 fire at real density < 30 %** — e.g. a "personne au sol" alert at SecondStage at **8 % density** at 10:30 (an essentially empty field). That's a false positive shown as a live incident.
- ⚠️ **"99 %" is accuracy, not precision, on in-distribution synthetic data.** With near-zero real prevalence of falls across 5 zones × 56 steps, even 95 % specificity yields ~dozens of false positives — which is exactly what happens. The headline "99 %" is technically true but operationally misleading; the README's "quelques faux positifs" undersells a 7:1 alert-to-truth ratio.
- The suspicious-object head is honestly flagged as a synthetic POC — good.

**UI colleague:** the false positives are rendered with equal visual weight to real incidents.
**UX colleague:** *"This single frame [fall @ 8 %] would destroy an ops manager's trust in the system."* Rated the alert/incident surface **3/10** — the top thing to fix.

**Recommendation:** add a **plausibility gate** (a "fallen_person" alert in a <X% density zone is physically implausible — suppress or down-rank it); report **precision/recall**, not just accuracy; and surface a **false-positive count** as an honest metric rather than hiding it in the noise.

---

### Feature 4 — Optical-flow stampede detection + 3-signal fusion (`vision/optical_flow.py`)

**Intended (a flagship Compétence-3 justification):** the CNN sees isolated frames; optical flow adds temporal motion so a surge is caught **before** people fall; three signals (flow, density, fallen) fuse at "2 of 3 → alert" to avoid false positives.

**What it actually does (verified — and this is the most damning finding):**
- ❌ **The module fails its own demonstration.** Its `__main__` prints: calm → `magnitude=3.029` (already **above** the 2.0 threshold), `coherence=0.284`, `stampede=False`; simulated stampede → `magnitude=4.267`, `coherence=0.235`, `stampede=False`. **The demo stampede is NOT detected**, and the "calm" case already exceeds the magnitude threshold. The coherence metric is swamped by background-noise vectors, so it never reaches 0.70.
- ❌ **In the real pipeline, flow contributes almost nothing.** Of **77 crowd_surge alerts, 73 come from the pure `cnn_density > 0.85` fallback** (line 183–184 of `pipeline.py`); **only 3** of 112 total alerts reached the 2-of-3 fusion with density < 0.85 (i.e. where flow could have been a deciding signal). So the "early detection before people fall" story is, empirically, delivered by a **density threshold**, not by optical flow.
- ❌ **The "2 of 3 fusion" barely gates anything:** the active-signals distribution over alerts is **{1 signal: 94, 2: 15, 0: 3}** — 94/112 alerts fire on a *single* signal via independent paths (fallen alone → fallen alert; object alone; density alone → surge fallback). The fusion rule that's sold as the anti-false-positive mechanism is bypassed by most alerts.

**UI/UX colleagues:** n/a (not directly surfaced), but the resulting alert flood is what they both flagged.

**Recommendation:** this is the feature whose *pertinence* is most questionable as-is. Either (a) fix the flow metric (compute coherence only over pixels with meaningful magnitude, calibrate thresholds on the actual `_simulate_motion` shifts) and *demonstrate* it firing before the CNN, or (b) be honest in the report that the current stampede signal is effectively "density > 85 %" and reframe optical flow as future work. Right now the architecture diagram gives it equal billing with the CNN, which the evidence doesn't support.

---

### Feature 5 — CSP dynamic allocation (`allocation/dynamic_csp.py`)

**Intended:** OR-Tools CP-SAT re-allocation; hard constraints (headcount, safety minimums), soft constraints (demand-proportional coverage, severity triage, **reassignment penalty for stability**); always feasible.

**What it actually does (verified):** solves OPTIMAL in the calm and mass-emergency stress tests; always feasible (emergencies are soft). The modelling is clean and correct. ✅

**Problems found:**
- ❌ **The allocation thrashes.** The medical allocation **changes on 34 of 55 step-transitions** (per-zone flips: SecondStage 23, Camping 19, MainStage 18, FoodCourt 17, Entrance 16). The dashboard's "Équipes médicales allouées" panel is visually a plate of spaghetti flipping 0↔2 every 15 min. The `REASSIGNMENT_PENALTY = 3` is simply overwhelmed because the coverage/emergency terms change every step (alerts fire every step). **Operationally, physically relocating medical teams across a 17-ha site every 15 minutes is unrealistic and unsafe** — and the plot meant to showcase "intelligent allocation" instead advertises instability.

**UI colleague:** the alloc plot is *"unreadable spaghetti… it actively hurts the 'intelligent allocation' claim."* Rated dashboard **3.5/10**.
**UX colleague:** *"titled as if it's a feature and reads as pure noise."* Suggests reframing it honestly as "ré-allocations fréquentes (charge de décision)."

**Recommendation:** raise the reassignment penalty and/or add **hysteresis** (don't move a team unless the improvement exceeds a margin), or re-solve less often. Then the "stability" soft constraint the docstring advertises will actually be visible.

---

### Feature 6 — MAS scenario evaluation (`simulation/mas.py`)

**Intended:** SimPy Monte-Carlo; prove CSP allocation beats a naïve uniform one on the same replayed incidents.

**What it actually does (verified):**
- In **`run_demo.py`'s peak scenario**, CSP wins clearly: mean **10.46** vs **13.14** min, uncovered **1** vs **43** (of 1 048). ✅
- ❌ **But the module's own self-check shows the opposite.** `python simulation/mas.py` runs with a *spread* demand and prints CSP **13.41** min / **44** uncovered vs naïve **12.99** / **43** — i.e. CSP is *slightly worse* on both. The only assert in that self-check checks that the incident *count* matches (1 048 == 1 048); it **does not test that the CSP actually wins**, so it "passes" while demonstrating no benefit.

**Interpretation (fair):** the CSP's advantage is real but **scenario-dependent** — it helps precisely when demand/incidents are *concentrated* (the headliner case, which is the realistic one). When demand is spread, proportional allocation ≈ uniform. That's a legitimate and defensible nuance, but as written the repo can print "CSP loses" from one entry point and "CSP wins big" from another, which an examiner will notice.

**Recommendation:** align the `mas.py` self-check with the demo scenario (concentrated peak demand) *or* add an assert + a comment explaining the scenario dependence, so the module doesn't contradict the headline. State explicitly: "CSP helps under concentrated demand; under uniform demand it ties the naïve baseline."

---

### Feature 7 — KPI A/B impact evaluator + 2×2 ablation (`simulation/kpis.py`)

**Intended:** quantify predictive vs reactive management on the *same* incidents: detection, first-aid, medic arrival, chain reaction (induced injuries, R_eff, MCE), victim outcome, FoodCourt service; plus a 2×2 ablation (forecast × vision).

**What it actually does (verified):** the strongest analytical module. Self-check passes with well-chosen monotonicity asserts. Headline (40 runs): detection **3.5/5.8**, first-aid **2.5/5.1**, medic **3.3/7.0** min (**93 %/62 %** < 8 min), MCE **0/0.20**, victim outcome **68 %/43 %**, clients lost **218/2 170**, **~€27 324 saved**. Balking model (Erlang-A) is properly sourced. This is genuinely good work.

**Problems found:**
- ⚠️ **The ablation quietly contradicts "more modules = better."** `vision seule` beats the *complete* system on **detection (2.53 vs 3.51 min)** and on **R_eff (0.36 vs 0.44)**; `p95` is tied (8.5). So adding forecasting makes detection *slightly worse* (the dynamic allocation moves "eyes" — security/logistics — around, changing human-discovery latency). The self-check asserts `complet ≤ prévision-seule` but never `complet ≤ vision-seule`, so this passes unnoticed. A jury could ask "why does your full system detect slower than vision alone?"
- ⚠️ **All FoodCourt savings come from `prévision`, none from `vision`** (lost revenue is binary: €3 055 proactive vs €30 379 reactive). Fine, but the "€27 324 saved" headline should be attributed to the *service pre-deployment*, not the whole system.

**UI colleague:** the Bilan built on this is the best-composed surface (7.5/10), only marred by "all-green reads like marketing."
**UX colleague:** rated the A/B storytelling **7/10**; the sourced, expandable, *honestly-caveated* Bilan is "rare in student projects — keep it."

**Recommendation:** add the missing `complet ≤ vision-seule` check (or acknowledge the detection regression as a finding); attribute the € figure precisely to the service module.

---

### Feature 8 — Integration control loop (`integration/pipeline.py`)

**Intended:** per-15-min loop: forecast → CNN+flow → fusion → CSP re-allocation on periodic (30 min) **or** event **or** forecast-spike trigger; write `control_log.json`.

**What it actually does (verified):** runs cleanly; writes the log; the reactive baseline (`run_reactive_loop`, static allocation) is a fair, non-strawman comparator (Hare quota + safety minimum).

**Problems found:**
- ⚠️ **"Periodic + event" degenerates to "every step."** Trigger breakdown: **periodic 1, forecast 3, event 52** — i.e. **56/56 steps re-allocate**, almost all event-driven, because the CNN alerts every step. The elegant multi-trigger design is real in code but invisible in practice (everything is an "event"). This is the upstream cause of the CSP thrashing (Feature 5).

**Recommendation:** once CNN false positives are gated (Feature 3), the event trigger will fire far less, the periodic/forecast triggers will re-appear, and the loop will look like its own architecture diagram.

---

### Feature 9 — Narration (LLM + offline template) (`narration/llm_narrator.py`)

**Intended:** convert structured facts into a **brief, factual, actionable** situation report for a non-technical manager; LLM if a key exists, deterministic template otherwise; "N'invente aucune information."

**What it actually does (verified):** the template fallback works with no API key, is deterministic, and invents nothing. ✅ The tail sections (system activity, scenario eval, predictive-value paragraph) are strong and sourced.

**Problems found:**
- ❌ **It violates its own brief.** The `SYSTEM_PROMPT` demands "phrases courtes, priorise les urgences" — but the template dumps **112 near-identical alert bullets** (`situation_report.md` is 128 lines, 112 of them "Pas N — zone Z … Ré-allocation déclenchée: X équipe(s)…"). No grouping, dedup, ranking, or summary-first. The genuinely useful summary sits *after* all 112 bullets, so no one reads it.
- ❌ **False positives are recorded as official facts** with equal weight ("personne au sol, densité 8 %").
- ⚠️ **Wrong time vocabulary** ("Pas 114" instead of 10:30) — the rest of the product speaks clock time.
- ⚠️ **Never prescriptive** — describes, never recommends ("Entrance saturated 5× — add a lane"). Many "0 équipe(s) positionnée(s)" lines (coverage failures) are buried, not flagged.

**UI colleague:** **2.5/10** — "an undifferentiated 112-line dump with visible false positives and no summary."
**UX colleague:** **2/10** — "non-actionable as delivered; invert the structure, lead with an executive summary, dedup, use HH:MM, add recommendations."

**Recommendation:** invert the document (summary first, ≤15-row confirmed-incident table, alerts collapsed to "112 caméra dont ~97 faibles"), switch to HH:MM, group/dedup, add an "Actions recommandées" section, and gate implausible alerts.

---

### Feature 10 — Dashboard système (`dashboard/build_dashboard.py`)

**Intended:** 4-panel Plotly overview (affluence real vs forecast, density heatmap, CSP allocation over time, MAS scenario bars) + an impact section (CDF, cumulative €, KPI bars, ablation).

**What it actually does (verified):** builds; covers the right variables; the heatmap and scenario-bar and CDF are good.

**Problems found:**
- ❌ **Breaks the project's offline guarantee.** `fig.to_html(..., include_plotlyjs="cdn")` → `dashboard.html` contains an `https://` reference to the Plotly CDN, so **it does not render offline** — directly contradicting the repo's headline promise ("la démo ne dépend jamais du réseau"). (The *viewer* is genuinely autonomous: **0 external references** — so fix the dashboard to match, e.g. `include_plotlyjs=True` to inline it.)
- ❌ **The allocation subplot is unreadable** (the CSP thrashing, Feature 5).
- ⚠️ **One bar chart is quantitatively misleading:** "temps de réponse moyen (min)" (~10) and "incidents non couverts" (~43) share **one 0–43 axis** — minutes and counts on the same scale.
- ⚠️ **X-axes are raw step indices (110–170)**, meaningless to an operator who thinks in clock time; the map speaks 10:30/21:05, the dashboard must too.
- ⚠️ **Palette drift:** MainStage is *blue* on the map but *purple* here; one shared legend spans two unrelated charts; the threshold line and heatmap colourbar are unlabelled.

**UI colleague:** **3.5/10.** **UX colleague:** **4/10** — "pretty, not decision-useful; convert axes to HH:MM (non-negotiable), add a takeaway per panel."

**Recommendation:** inline Plotly (offline), convert all x-axes to HH:MM, split the min/count bars onto two axes/panels, replace the alloc spaghetti with per-zone small-multiples or a team-count heatmap, adopt the map's zone palette, add one annotated takeaway per panel.

---

### Feature 11 — Vue simulation / digital-twin player (`dashboard/festival_map.py` + `viewer_template.html`)

**Intended:** an autonomous (no CDN) animated top-down replay of the decided day; crowd that enters/packs/exits, teams that move on each CSP decision, typed incidents, a real-time surveillance panel, forecast sparklines, an AVEC/SANS story, playback/scrub/keyboard/deep-links, and an end-of-day Bilan.

**What it actually does (verified):** **The standout deliverable.** Genuinely autonomous (0 external refs, 12.9 MB self-contained). Rich, complete interaction model — **verified working**: play/pause, ×1–×8 speed, scrub, keyboard (Space, ←/→, Shift+arrow = full step, 1–9 = chapters, Esc), hover tooltips (affluence/density/teams per zone), layer toggles, chapter strip, clickable event journal (click-to-seek), demo/projector mode, deep-links (`?f=`/`?theme=`/`?demo=`/`?play=`/`?summary=`), a one-time welcome overlay gated by `localStorage`, and auto-Bilan at the end. The vector "bâti" (stages, tents, food-stall awnings, hourglass gate, mown-grass texture, dispatch beams, "en concert" badge) is exceptional craft. The double-encoding of density (heat fill + dots physically clumping + halo) is smart and readable.

**Problems found:**
- ⚠️ **"Single source of truth / la vue ne peut pas contredire les KPIs" is not quite true.** The map's KPI tile shows **"2.1′ rép. moy."** (from `replay_sim`, which dispatches with no detection delay), while the **Bilan modal shows "Arrivée médecin 3.3 min"** (from `kpis.py`, which includes detection). **Two different engines, two different "response" numbers in the same HTML file.** They measure different things, but both are labelled as response/arrival time — a contradiction an examiner comparing the two panels will spot.
- ⚠️ **The replay is non-deterministic:** two consecutive builds reported **17 then 18 incidents** (module-level RNG shared across runs; induced children vary). And the crowd-conservation error can reach **15 %** (its own self-check bound is 30 %) — the on-screen crowd count can drift from the underlying data.
- **UI legibility (UI colleague, map 6/10):** density is **clamped to [0,1]** (`d = Math.max(0, Math.min(1, d))`) so 100 %, 110 % and 131 % render *identical* red — **over-capacity is invisible**; and the over-capacity % is drawn in **`#d03b3b` red text on the `#d03b3b` red fill** (confirmed in source) — red-on-red. **Colour overload:** `#d03b3b` is simultaneously *medical*, *critical*, *max-density* and *"sans-is-bad"*, so the red medical cross vanishes into a saturated red zone; security blue == MainStage crowd blue. Light theme is markedly weaker than dark.
- **UX overload (UX colleague, map+panel 5/10):** at rush, four zones are red at once with pulsing outlines/beams/pictos and **no "look here first" priority cue**; the `85% › 83% →` label syntax is never decoded on the map; panel labels are jargon ("CSP", "TimesFM", "rép. moy."); the four identical "chute induit — évité" ghost rows read as a glitch, not a win; keyboard shortcuts/deep-links are undiscoverable (one-shot, unrecoverable onboarding — no persistent "?").
- **Accessibility:** encoding is heavily colour-only (CVD risk despite the CVD-aware base palette), and the canvas has no text/ARIA alternative.

**Recommendations (highest value first):** (1) reconcile or relabel the 2.1 vs 3.3 numbers so the "single source of truth" claim holds; (2) give on-map labels a semi-opaque pill and never draw label colour == fill colour; (3) encode >100 % explicitly (hatching / intensifying outline / inverted chip); (4) split "team-role" colours from "danger" colours (this one change fixes the red-cross-on-red, blue-on-blue, amber pile-up, and dashboard palette drift at once); (5) add a single per-moment urgency anchor; (6) add a persistent Help/`?` with a shortcut sheet and collapse repeated ghost rows into "×N évités."

---

### Feature 12 — End-of-day "Bilan" modal

**Intended:** an explained, sourced with/without comparison; the payoff of the whole demo.

**What it actually does (verified):** **the best surface in the product.** Hero "27 324 € de ventes sauvées" (correctly showing **≈1 952 clients retenus** = 2 170 − 218), grouped KPI sections, **each row expandable with a definition + real-world source**, "✓ MIEUX" badges, and an explicit **honesty footnote that "sans" is a calibrated model, not a strawman**. Exactly what a sceptical jury needs.

**Problems found (cosmetic):**
- ⚠️ **All-green / all-red** (predictive wins every row, every "sans" in alarm-red) reads as marketing rather than measurement — can *lower* credibility.
- ⚠️ **Badge wrapping** breaks row alignment on "Catastrophe (MCE)" and "Attente (moy·pic)".
- ⚠️ **Leads with money, not lives** — for a *safety* audience, the € hero should follow the safety wins (0 catastrophe, better victim outcome), not precede them.

**UI colleague:** **7.5/10.** **UX colleague:** **7/10** — "keep the honesty note; lead with the safety win; add a one-line decoder above the twin timers."

**Recommendation:** neutral-ink the "sans" values (colour only the delta/winner), fix badge wrapping, and offer a safety-first hero (€ as the business kicker).

---

### Feature 13 — `run_demo.py` orchestration

**Intended:** one command runs all 9 stages and prints a readable trace.

**What it actually does (verified):** works, 93 s, clear 9-stage trace.

**Problem found:**
- ⚠️ **One mislabelled figure:** it prints `CA FoodCourt sauvé : ~27324 € (2170 clients retenus)` — but 2 170 is the number of clients *lost* in the reactive scenario, not *retained*. The retained figure is **1 952** (which the Bilan modal shows correctly). Minor, but it's a wrong number in the headline console output.

**Recommendation:** print `{s_lost - a_lost}` (=1 952) as "clients retenus," or relabel to "clients perdus sans le système."

---

## 3. Cross-cutting findings ("nothing invented?" audit)

The user asked specifically whether anything is invented/misleading. The system **does not fabricate data** — every displayed number traces to a real computation, and the docs are unusually honest (the Bilan's "calibrated model" footnote, the README's "limites assumées"). But there are **honest-model-vs-reality gaps and internal inconsistencies** a jury should be prepared for:

| Claim in code/docs | Reality (verified) | Severity |
|---|---|---|
| CNN "chute ≈ 99 %" | 99 % *accuracy on synthetic in-distribution* data; **46 fallen alerts, 6 at <30 % density** in the pipeline (low precision) | 🔴 High |
| Optical flow = early stampede detection (equal billing with CNN) | Fails its own demo; **73/77 surge alerts are just density>85 %**, flow decisive in ~3/112 | 🔴 High |
| "Vue ne peut pas contredire les KPIs" (single source of truth) | Map shows **2.1′** response, Bilan shows **3.3 min** — two engines | 🟠 Medium |
| CSP beats naïve (headline) | True in the peak scenario; **`mas.py` self-check shows CSP tie/loss** (13.41 vs 12.99) | 🟠 Medium |
| "~50 % arrive 16h–18h" (anchor) | Model produces **3 %** in that window | 🟠 Medium |
| "La démo ne dépend jamais du réseau" | Viewer ✅ autonomous; **dashboard needs the Plotly CDN** | 🟠 Medium |
| "Le site part vide à 10h" | **3 601 on site** at open (campers) | 🟡 Low |
| run_demo "2170 clients retenus" | Actually 1 952 retained (2 170 lost) | 🟡 Low |
| Narration "bref, factuel" (system prompt) | **112-bullet dump**, FPs included | 🔴 High |
| Complete system is best (implied) | `vision seule` beats `complet` on detection & R_eff | 🟡 Low |

None of these are dishonesty — they are the normal seams of an ambitious simulation — but each is a place where **what the code says and what it does diverge**, which is exactly what "compare what it does with what it should do" surfaces.

---

## 4. What is genuinely excellent (don't lose it)

- **End-to-end pipeline that actually runs** in 93 s, offline-capable per module, with real TimesFM, real OR-Tools CP-SAT, real SimPy Monte-Carlo. For a student project this integration is rare.
- **The KPI A/B evaluator** — sourced, Monte-Carlo, 2×2 ablation, with honest asserts. This is the intellectual core and it's strong.
- **The vue simulation** — autonomous, richly interactive, beautiful vector site, thoughtful demo affordances (deep-links, projector mode, chapters). The engineering here is well beyond the assignment.
- **The Bilan modal** — expandable, sourced, honestly caveated. Keep the "sans is a calibrated model" note; it's a credibility asset.
- **Documentation honesty** — the README's "limites assumées" already pre-empts several criticisms.

---

## 5. Prioritised recommendations

**P0 — trust & correctness (do before any demo):**
1. **Gate CNN false positives** with a density-plausibility rule; report **precision/recall**, not accuracy; surface a false-positive counter. (Fixes the 112:15 flood, the empty-stage "fall," the report, the banner, and — downstream — the CSP thrashing.)
2. **Resolve the optical-flow story:** fix the coherence metric and *show* it firing early, **or** honestly reframe it as "density-threshold surge detection + future work."
3. **Reconcile the internal number conflicts:** map 2.1 vs Bilan 3.3; `mas.py` self-check vs demo; "2170 retenus."

**P1 — the two weak surfaces:**
4. **Rebuild the situation report** summary-first, HH:MM, deduped, with recommendations.
5. **Fix the dashboard:** inline Plotly (offline), HH:MM axes, split the min/count bars, replace the alloc spaghetti, unify the palette.
6. **Tame the CSP thrashing** (hysteresis / higher reassignment penalty).

**P2 — polish the flagship viewer:**
7. Pill backgrounds behind on-map labels; never draw label colour == fill; encode >100 % explicitly.
8. Split "team-role" from "danger" colours (one change, many fixes).
9. Persistent Help/`?` + shortcut sheet; collapse repeated ghost rows; add a per-moment urgency anchor.
10. Bilan: neutral-ink "sans" values, fix badge wrapping, lead with safety.

**P3 — model integrity:**
11. Make the data model actually match its 16h–18h anchor (or drop the claim) and cap zone overflow.
12. Validate TimesFM against the seasonal-naïve baseline and report both MAEs.

---

## 6. Designer scorecard (colleague consultation summary)

| Surface | UI (visual) | UX (experience) |
|---|---|---|
| Simulation map | 6/10 | 5/10 |
| Right info panel | 6/10 | (folded into map) |
| Alert/incident panel | (folded) | **3/10** ← top fix |
| Timeline / playback | 6.5/10 | 7/10 |
| AVEC/SANS + Bilan | 7.5/10 | 7/10 |
| Dashboard | 3.5/10 | 4/10 |
| Situation report | 2.5/10 | 2/10 |
| Onboarding | (folded) | 6/10 |

**UI's single highest-leverage fix:** separate "role" colours (teams) from "danger" colours (load/incidents) and reuse the zone palette everywhere — resolves the red-cross-on-red, blue-on-blue, amber pile-up, legend ambiguity, and dashboard palette drift at once.

**UX's top 3:** (1) tame false positives + add triage/confidence, (2) put real clock times on the report & dashboard, (3) make every surface **prescriptive** ("look here / do this"), not just descriptive.

---

## 7. Bottom line

The project **works** — it runs end to end, nothing is fabricated, and the ambition and engineering are well above the assignment bar. Its two show-piece surfaces (the animated twin and the Bilan) are genuinely strong. The gap between "impressive demo" and "credible system" is almost entirely **three fixes**: a CNN that cries wolf 7× too often, an optical-flow feature that doesn't earn its billing, and a handful of places where the code's claims and its own outputs disagree. Fix those and this moves from an impressive student project to a genuinely defensible one.

*Screenshots referenced: `outputs/_shots/{map_morning,map_rush,map_headliner,map_egress,map_summary,dashboard}.png`. Log analysis: `outputs/control_log.json`, `outputs/kpi_*.json`, `outputs/events.csv`. All numbers reproducible via the commands in the README's "Tester / vérifier" section.*
