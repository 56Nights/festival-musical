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
}

SYSTEM_PROMPT = (
    "Tu es l'assistant du PC sécurité d'un festival de musique. "
    "À partir des données structurées fournies (alertes détectées par caméra, "
    "réallocations d'équipes, prévisions d'affluence), rédige un rapport de "
    "situation bref, factuel et actionnable en français, destiné à un "
    "responsable d'exploitation non technique. Utilise des phrases courtes. "
    "Priorise les urgences. N'invente aucune information absente des données."
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
        f"- **Service FoodCourt** : {a['lost_customers']} clients perdus "
        f"contre {s['lost_customers']} — soit **~{saved} € de ventes sauvées** "
        f"en déployant les équipes volantes AVANT le pic plutôt qu'en réaction.",
    ]


def _template_fallback(alerts, reallocs, scenarios, comparison=None) -> str:
    """Rapport déterministe sans LLM — garantit une démo hors ligne."""
    lines = ["# Rapport de situation — Festival (généré automatiquement)", ""]
    if alerts:
        lines.append("## ⚠️ Alertes détectées")
        for a in alerts:
            kinds = ", ".join(TYPE_FR.get(k, k) for k in a["types"])
            lines.append(
                f"- **Pas {a['step']} — zone {a['zone']}** : {kinds} "
                f"(densité estimée {a['density']:.0%}). "
                f"Ré-allocation déclenchée : {a['response']}")
    else:
        lines.append("Aucune alerte sur la période.")
    lines += ["", "## 🔧 Activité du système",
              f"- {reallocs} ré-allocations de ressources effectuées "
              f"(périodiques + événementielles)."]
    if scenarios:
        lines += ["", "## 🧪 Évaluation de scénarios"]
        for name, k in scenarios.items():
            lines.append(
                f"- **{name}** : temps de réponse moyen "
                f"{k['mean_response_min']} min, pire p95 {k['worst_p95_min']} min, "
                f"{k['total_uncovered']} incident(s) non couvert(s) "
                f"sur {k['total_incidents']}.")
    lines += _impact_section(comparison)
    return "\n".join(lines)


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
            "lost_revenue_eur")
    return {"avec": {k: cmp["avec"][k] for k in keep},
            "sans": {k: cmp["sans"][k] for k in keep},
            "targets": cmp["targets"]}


def summarize(control_log: list, scenarios: dict | None = None,
              comparison: dict | None = None) -> str:
    if comparison is None:
        comparison = _load_comparison()
    # extraction des faits saillants du journal
    alerts = []
    for e in control_log:
        for a in e["alerts"]:
            med = {}
            if e["allocation"] and isinstance(e["allocation"].get("medical"), dict):
                raw = e["allocation"]["medical"]
                # garde-fou : valeurs CP-SAT parfois non initialisées hors solution
                total_medical = C.RESOURCES["medical"]
                med = {z: v for z, v in raw.items()
                       if isinstance(v, int) and 0 <= v <= total_medical}
                alerts.append({
                    "step": e["step"], "zone": a["zone"], "types": a["types"],
                    "density": a["density"],
                    "response": f"{med.get(a['zone'], '?')} équipe(s) médicale(s) "
                                f"positionnée(s) en zone {a['zone']}",
                })
    n_realloc = sum(e["resolved"] for e in control_log)

    provider, call = pick_provider()
    if provider == "template":
        report = _template_fallback(alerts, n_realloc, scenarios, comparison)
    else:
        facts = json.dumps({
            "alertes": alerts, "nb_reallocations": n_realloc,
            "scenarios": scenarios,
            "impact_avec_vs_sans": comparison}, ensure_ascii=False, indent=1)
        try:
            report = call(
                "Données du système pour la période écoulée :\n" + facts +
                "\n\nRédige le rapport de situation.")
        except Exception as exc:            # le LLM n'est jamais bloquant
            print(f"[narration] échec {provider} ({exc}) -> repli gabarit")
            provider = "template (repli)"
            report = _template_fallback(alerts, n_realloc, scenarios, comparison)

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
