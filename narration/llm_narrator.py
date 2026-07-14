"""
Module de narration LLM — dernier maillon du pipeline.

Convertit les sorties structurées du système (alertes CNN, ré-allocations CSP,
KPIs de simulation) en rapports de situation lisibles par un opérateur
non technique (Compétence 5 — Formaliser).

Fournisseurs supportés (auto-détection par variable d'environnement) :
  - GEMINI_API_KEY  -> Google Gemini 1.5 Flash (tier gratuit)
  - GROQ_API_KEY    -> Groq (Llama 3.1, tier gratuit)
  - OLLAMA          -> instance locale Ollama (OLLAMA=1)
  - aucun           -> repli sur gabarits déterministes (la démo fonctionne
                       toujours, même hors ligne)

Le repli gabarit garantit que la soutenance ne dépend jamais du réseau —
le LLM améliore la qualité rédactionnelle mais n'est pas un point de défaillance.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import urllib.request
import config as C

TYPE_FR = {
    "fallen_person": "personne au sol",
    "suspicious_object": "objet suspect",
    "crowd_surge": "mouvement de foule / densité critique",
    "fight": "bagarre",
}

SYSTEM_PROMPT = (
    "Tu es l'assistant du PC sécurité d'un festival de musique. "
    "À partir des données structurées fournies, rédige un rapport de situation "
    "bref, factuel et actionnable en français, pour un responsable d'exploitation "
    "non technique. STRUCTURE IMPOSÉE : (1) une SYNTHÈSE de 2-3 phrases en tête "
    "(nombre d'incidents, pire moment, résultat clé) ; (2) la liste des incidents "
    "en HEURE HORLOGE (HH:MM), jamais en numéro de pas ; (3) des ACTIONS "
    "RECOMMANDÉES. Phrases courtes, priorise les urgences confirmées, distingue "
    "les incidents confirmés des veilles densité. N'invente aucune information."
)


# ---------------------------------------------------------------- providers
def _call_gemini(prompt: str) -> str:
    key = os.environ["GEMINI_API_KEY"]
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-1.5-flash:generateContent?key={key}")
    body = json.dumps({
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 500},
    }).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_groq(prompt: str) -> str:
    key = os.environ["GROQ_API_KEY"]
    body = json.dumps({
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": prompt}],
        "temperature": 0.3, "max_tokens": 500,
    }).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return data["choices"][0]["message"]["content"]


def _call_ollama(prompt: str) -> str:
    body = json.dumps({
        "model": os.environ.get("OLLAMA_MODEL", "mistral"),
        "system": SYSTEM_PROMPT, "prompt": prompt, "stream": False,
    }).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/generate", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["response"]


def _impact_section(cmp) -> list:
    """Section « apport de la gestion prédictive » (avec vs sans)."""
    if not cmp:
        return []
    a, s = cmp["avec"], cmp["sans"]
    saved = s["lost_revenue_eur"] - a["lost_revenue_eur"]
    induced = s["mean_induced"] - a["mean_induced"]
    outcome_gain = a["mean_outcome"] - s["mean_outcome"]
    return [
        "", "## 💡 Apport de la gestion prédictive (même journée, avec vs sans)",
        f"- **Détection des incidents** : {a['mean_detect_min']['mean']} min en "
        f"moyenne (caméra + flux optique) contre {s['mean_detect_min']['mean']} min "
        f"pour des agents seuls.",
        f"- **Chaîne de secours** : premiers gestes en "
        f"{a['mean_first_aid_min']['mean']} min (staff formé sur place) puis "
        f"médecin en {a['mean_response_min']['mean']} min — contre "
        f"{s['mean_first_aid_min']['mean']} / {s['mean_response_min']['mean']} min "
        f"sans le système ({a['pct_within_target']:.0f}% des cas sous la cible de "
        f"{cmp['targets']['response_target_min']:.0f} min, contre "
        f"{s['pct_within_target']:.0f}%).",
        f"- **Réaction en chaîne maîtrisée** : ~{induced:.1f} blessés induits "
        f"évités ; taux de reproduction R = {a['r_eff']} (avec) contre "
        f"{s['r_eff']} (sans) — sous 1, les incidents s'éteignent au lieu de "
        f"cascader. {a['mean_mce']:.2f} « mass casualty » contre {s['mean_mce']:.2f}.",
        f"- **Issue des victimes** : score moyen {a['mean_outcome']:.0%} contre "
        f"{s['mean_outcome']:.0%} (les premiers gestes précoces gèlent la "
        f"dégradation), soit ~{outcome_gain*a.get('n_casualties',0):.0f} issues "
        f"défavorables évitées.",
        f"- **Service FoodCourt (rush)** : file au-delà du seuil de renoncement "
        f"(10 min) pendant {a.get('wait_over_balk_min', '?')} min cumulées contre "
        f"{s.get('wait_over_balk_min', '?')} min — {a['lost_customers']} clients "
        f"perdus contre {s['lost_customers']}, soit **~{saved} € de ventes "
        f"sauvées** en ajustant les équipes volantes à la demande RÉELLE du jour "
        f"plutôt qu'au planning historique.",
        f"- **Charge opérationnelle** : {a.get('urgent_repositioning', '?')} courses "
        f"en urgence vers un incident hors zone contre "
        f"{s.get('urgent_repositioning', '?')} (pré-positionnement) ; "
        f"{a.get('alloc_moves_alert', 0) + a.get('alloc_moves_anticipated', 0)} "
        f"redéploiements commandés contre {s.get('alloc_moves_anticipated', '?')} "
        f"rotations planifiées du planning.",
    ]


def _episodes(control_log) -> list:
    """Regroupe les alertes d'INCIDENT (hors veille densité) en ÉPISODES :
    alertes consécutives (≤ 2 pas d'écart) de même zone/type fusionnées. Évite
    le dump de 100+ lignes quasi identiques. Trié par heure."""
    raw = []
    for e in control_log:
        alloc = e.get("allocation") or {}
        med = alloc.get("medical", {}) if isinstance(alloc.get("medical"), dict) else {}
        for a in e["alerts"]:
            if a.get("watch"):
                continue
            m = med.get(a["zone"], 0)
            raw.append({
                "step": e["step"], "zone": a["zone"],
                "types": tuple(sorted(a["types"])),
                "confidence": a.get("confidence", "à vérifier"),
                "density": a.get("density", 0.0),
                "med": m if isinstance(m, int) else 0,
            })
    raw.sort(key=lambda r: r["step"])
    episodes, openep = [], {}
    for r in raw:
        key = (r["zone"], r["types"])
        ep = openep.get(key)
        if ep is not None and r["step"] - ep["end_step"] <= 2:
            ep["end_step"] = r["step"]
            ep["density"] = max(ep["density"], r["density"])
            ep["med"] = max(ep["med"], r["med"])
            if r["confidence"] == "confirmé":
                ep["confidence"] = "confirmé"
        else:
            ep = {"start_step": r["step"], "end_step": r["step"], "zone": r["zone"],
                  "types": r["types"], "confidence": r["confidence"],
                  "density": r["density"], "med": r["med"]}
            episodes.append(ep)
            openep[key] = ep
    episodes.sort(key=lambda e: e["start_step"])
    return episodes


def _actions(control_log, episodes) -> list:
    """Recommandations ACTIONNABLES dérivées des données (pas seulement descriptif)."""
    import collections
    acts = []
    for ep in [e for e in episodes if e["med"] == 0][:4]:
        acts.append(f"Couverture médicale nulle en zone {ep['zone']} à "
                    f"{C.step_to_hhmm(ep['start_step'])} — dépêcher une équipe.")
    watch_by_zone = collections.Counter()
    for e in control_log:
        for a in e["alerts"]:
            if a.get("watch"):
                watch_by_zone[a["zone"]] += 1
    for zone, n in watch_by_zone.most_common(2):
        if n >= 5:
            acts.append(f"Zone {zone} sous tension densité prolongée ({n} veilles) — "
                        f"renforcer la gestion de flux / ouvrir un accès.")
    if not acts:
        acts.append("Aucune action corrective prioritaire : la couverture a suivi "
                    "les incidents.")
    return acts


def _template_fallback(episodes, counts, reallocs, actions,
                       scenarios, comparison=None) -> str:
    """Rapport déterministe sans LLM — SOMMAIRE D'ABORD, HH:MM, dédupliqué,
    avec actions recommandées. Garantit une démo hors ligne."""
    L = ["# Rapport de situation — Festival", ""]

    # 1) Synthèse en tête (ce que l'opérateur lit en premier)
    n_inc = len(episodes)
    n_conf = sum(1 for ep in episodes if ep["confidence"] == "confirmé")
    worst = max(episodes, key=lambda ep: ep["density"], default=None)
    L.append("## Synthèse")
    s1 = (f"- **{n_inc} épisode(s) d'incident** détecté(s) — {n_conf} confirmé(s), "
          f"{n_inc - n_conf} à vérifier")
    if worst:
        s1 += (f" ; pic de tension en zone **{worst['zone']}** vers "
               f"**{C.step_to_hhmm(worst['start_step'])}**")
    L.append(s1 + ".")
    L.append(f"- **{reallocs} ré-allocations** d'équipes déclenchées sur la journée.")
    L.append(f"- Flot caméra : **{counts['incident_alerts']} affirmations d'incident** "
             f"+ {counts['watches']} veilles densité (basse priorité), sur "
             f"{counts['total']} alertes brutes.")
    if comparison:
        a, s = comparison["avec"], comparison["sans"]
        saved = s["lost_revenue_eur"] - a["lost_revenue_eur"]
        L.append(f"- Gestion prédictive vs planning pré-établi : arrivée médecin "
                 f"{a['mean_response_min']['mean']} vs {s['mean_response_min']['mean']} min, "
                 f"~{saved} € de ventes sauvées.")

    # 2) Table d'incidents (≤ 15 lignes, heure horloge)
    L += ["", "## Incidents (heure · zone · type · confiance · équipes méd.)"]
    if episodes:
        L += ["| Heure | Zone | Type | Confiance | Équipes méd. |",
              "|---|---|---|---|---|"]
        for ep in episodes[:15]:
            hhmm = C.step_to_hhmm(ep["start_step"])
            if ep["end_step"] != ep["start_step"]:
                hhmm += f"–{C.step_to_hhmm(ep['end_step'])}"
            types = ", ".join(TYPE_FR.get(t, t) for t in ep["types"])
            L.append(f"| {hhmm} | {ep['zone']} | {types} | {ep['confidence']} "
                     f"| {ep['med']} |")
        if len(episodes) > 15:
            L.append(f"| … | | | | +{len(episodes) - 15} épisode(s) |")
    else:
        L.append("Aucun incident caméra confirmé sur la période.")

    # 3) Actions recommandées (prescriptif)
    L += ["", "## Actions recommandées"]
    L += [f"- {act}" for act in actions]

    # 4) Détail système / scénarios / impact (en fin, pour qui veut creuser)
    L += ["", "## Activité du système",
          f"- {reallocs} ré-allocations (périodiques + prévision + événement)."]
    if scenarios:
        L += ["", "## Évaluation de scénarios"]
        for name, k in scenarios.items():
            L.append(f"- **{name}** : réponse moy. {k['mean_response_min']} min, "
                     f"pire p95 {k['worst_p95_min']} min, {k['total_uncovered']} "
                     f"non couvert(s)/{k['total_incidents']}.")
    L += _impact_section(comparison)
    return "\n".join(L)


def pick_provider():
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini", _call_gemini
    if os.environ.get("GROQ_API_KEY"):
        return "groq", _call_groq
    if os.environ.get("OLLAMA"):
        return "ollama", _call_ollama
    return "template", None


# ---------------------------------------------------------------- pipeline
def _load_comparison() -> dict | None:
    p = os.path.join(C.OUT, "kpi_comparison.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        cmp = json.load(f)
    # on ne garde que les agrégats (pas les séries) pour le prompt / gabarit
    keep = ("mean_response_min", "mean_detect_min", "mean_first_aid_min",
            "pct_within_target", "mean_uncovered", "mean_induced", "r_eff",
            "mean_mce", "mean_outcome", "n_casualties", "lost_customers",
            "lost_revenue_eur", "wait_over_balk_min", "urgent_repositioning",
            "alloc_moves_alert", "alloc_moves_anticipated")
    return {"avec": {k: cmp["avec"][k] for k in keep},
            "sans": {k: cmp["sans"][k] for k in keep},
            "targets": cmp["targets"]}


def summarize(control_log: list, scenarios: dict | None = None,
              comparison: dict | None = None) -> str:
    if comparison is None:
        comparison = _load_comparison()

    # faits saillants : épisodes d'incident (dédupliqués) + comptes honnêtes
    episodes = _episodes(control_log)
    actions = _actions(control_log, episodes)
    total = sum(len(e["alerts"]) for e in control_log)
    watches = sum(1 for e in control_log for a in e["alerts"] if a.get("watch"))
    counts = {"total": total, "watches": watches,
              "incident_alerts": total - watches}
    n_realloc = sum(e["resolved"] for e in control_log)

    # faits pour le LLM : épisodes en HH:MM (pas le dump brut d'alertes)
    ep_facts = [{"heure": C.step_to_hhmm(ep["start_step"]),
                 "fin": C.step_to_hhmm(ep["end_step"]), "zone": ep["zone"],
                 "types": [TYPE_FR.get(t, t) for t in ep["types"]],
                 "confiance": ep["confidence"], "equipes_medicales": ep["med"]}
                for ep in episodes]

    provider, call = pick_provider()
    if provider == "template":
        report = _template_fallback(episodes, counts, n_realloc, actions,
                                    scenarios, comparison)
    else:
        facts = json.dumps({
            "synthese": counts, "episodes_incident": ep_facts,
            "actions_recommandees": actions, "nb_reallocations": n_realloc,
            "scenarios": scenarios,
            "impact_avec_vs_sans": comparison}, ensure_ascii=False, indent=1)
        try:
            report = call(
                "Données du système pour la période écoulée :\n" + facts +
                "\n\nRédige le rapport : SOMMAIRE d'abord (2-3 phrases), puis la "
                "liste des incidents en HH:MM, puis les actions recommandées.")
        except Exception as exc:            # le LLM n'est jamais bloquant
            print(f"[narration] échec {provider} ({exc}) -> repli gabarit")
            provider = "template (repli)"
            report = _template_fallback(episodes, counts, n_realloc, actions,
                                        scenarios, comparison)

    path = os.path.join(C.OUT, "situation_report.md")
    with open(path, "w") as f:
        f.write(report)
    print(f"[narration] fournisseur : {provider} -> {path}")
    return report


if __name__ == "__main__":
    with open(os.path.join(C.OUT, "control_log.json")) as f:
        log = json.load(f)
    scen = None
    sp = os.path.join(C.OUT, "scenarios.json")
    if os.path.exists(sp):
        scen = json.load(open(sp))
    print("\n" + summarize(log, scen))
