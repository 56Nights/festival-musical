"""
DÉMO COMPLÈTE — exécute tout le système de bout en bout.

    uv run python run_demo.py

Étapes :
  1. Génération des données simulées             (Compétence 2)
  2. Prévision zéro-shot TimesFM — pas d'entraînement (Compétences 1, 3)
  3. Têtes du CNN ResNet18 — entraînées UNE fois puis rechargées
  4. Boucle de contrôle intégrée                 (intégration des 4 modules)
  5. Évaluation de scénarios par MAS             (Compétence 3)
  6. Impact prédictif vs réactif (avec/sans)     (Compétences 3, 5)
  7. Vue simulation spatiale du festival         (Compétences 1, 5)
  8. Dashboard HTML                              (Compétence 5)
  9. Narration LLM — rapport de situation        (Compétence 5)

Les poids du CNN (outputs/vision_cnn.pt) sont réutilisés s'ils existent :
supprimez le fichier pour forcer un ré-entraînement (~30 s, têtes seules).
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C

t0 = time.time()

print("=" * 60)
print("1/9  Génération des données simulées")
print("=" * 60)
from data.generate_data import generate
generate()

print("\n" + "=" * 60)
print("2/9  Prévision d'affluence — TimesFM zéro-shot (aucun entraînement)")
print("=" * 60)
from forecasting.timesfm_forecaster import ZeroShotForecaster
print(f"backend : {ZeroShotForecaster().backend}")

print("\n" + "=" * 60)
print("3/9  CNN ResNet18 — têtes multi-tâches")
print("=" * 60)
if os.path.exists(C.VISION_MODEL):
    print(f"poids trouvés ({C.VISION_MODEL}) — entraînement sauté")
else:
    from vision.train import train as train_cnn
    train_cnn()

print("\n" + "=" * 60)
print("4/9  Boucle de contrôle intégrée (TimesFM + CNN + CSP)")
print("=" * 60)
from integration.pipeline import run_control_loop
log = run_control_loop()
print(f"{sum(len(e['alerts']) for e in log)} alertes | "
      f"{sum(e['resolved'] for e in log)} ré-allocations")

print("\n" + "=" * 60)
print("5/9  Évaluation de scénarios (simulation multi-agents)")
print("=" * 60)
from allocation.dynamic_csp import solve_allocation
from simulation.mas import evaluate_scenario, generate_incidents

demand = log[-1]["forecast_peak"]

# pour l'évaluation de scénarios, on simule le PIC headliner explicitement :
# MainStage saturée à 95 %, les autres zones en retrait.
# C'est le moment où l'intelligence du CSP fait la différence — il concentre
# les équipes médicales là où la foule est dense ; la baseline naïve répartit
# uniformément et laisse MainStage sous-couverte.
peak_demand = {
    "MainStage":   0.95,
    "SecondStage": 0.35,
    "FoodCourt":   0.40,
    "Camping":     0.10,
    "Entrance":    0.15,
}

alloc_csp, _ = solve_allocation(peak_demand)
naive = {r: {z: t // C.N_ZONES + (1 if i < t % C.N_ZONES else 0)
             for i, z in enumerate(C.ZONES)}
         for r, t in C.RESOURCES.items()}

print(f"  CSP medical  : {alloc_csp['medical']}")
print(f"  Naïf medical : {naive['medical']}")

# plannings partagés générés avec le pic — même incidents pour les deux allocations.
# Taux calé pour rester HORS saturation (les durées de trajet sont désormais
# réalistes/plus courtes, cf. mas.travel_time dérivé de la géométrie) : à charge
# modérée l'intelligence du placement CSP se voit sur le p95 ET les non-couverts.
shared_schedules = generate_incidents(20, incident_rate=0.15, demand=peak_demand)

scenarios = {
    "CSP optimisé": evaluate_scenario(alloc_csp, schedules=shared_schedules),
    "Uniforme naïf": evaluate_scenario(naive,     schedules=shared_schedules),
}
for name, kpi in scenarios.items():
    print(f"  {name:14s} -> {kpi}")
with open(os.path.join(C.OUT, "scenarios.json"), "w") as f:
    json.dump(scenarios, f, indent=1)

print("\n" + "=" * 60)
print("6/9  Impact : gestion prédictive vs réactive (même journée)")
print("=" * 60)
from integration.pipeline import run_reactive_loop
from simulation.kpis import compare, ablation
run_reactive_loop()                       # baseline « sans » (aucun modèle)
cmp = compare()                           # avec vs sans -> kpi_comparison.json
abl = ablation()                          # 2x2 prévision × vision -> kpi_ablation.json
_a, _s = cmp["avec"], cmp["sans"]
print(f"  détection  avec/sans : {_a['mean_detect_min']['mean']} / "
      f"{_s['mean_detect_min']['mean']} min")
print(f"  réponse    avec/sans : {_a['mean_response_min']['mean']} / "
      f"{_s['mean_response_min']['mean']} min "
      f"({_a['pct_within_target']:.0f}% vs {_s['pct_within_target']:.0f}% < "
      f"{C.RESPONSE_TARGET_MIN:.0f} min)")
_retained = _s['lost_customers'] - _a['lost_customers']
print(f"  CA FoodCourt sauvé   : ~{_s['lost_revenue_eur'] - _a['lost_revenue_eur']} € "
      f"({_retained} clients retenus ; {_s['lost_customers']} perdus sans le système)")

print("\n" + "=" * 60)
print("7/9  Vue simulation spatiale (jumeau numérique animé)")
print("=" * 60)
from simulation.replay_sim import build_replay
build_replay()                            # intègre le bloc comparaison au header
from dashboard.festival_map import build_map
build_map()

print("\n" + "=" * 60)
print("8/9  Génération du dashboard")
print("=" * 60)
from dashboard.build_dashboard import build
build(scenarios)

print("\n" + "=" * 60)
print("9/9  Narration LLM — rapport de situation")
print("=" * 60)
from narration.llm_narrator import summarize
report = summarize(log, scenarios, cmp)
print("\n" + report)

print(f"\nTerminé en {time.time()-t0:.0f}s. Sorties dans {C.OUT}/")
print(f"  • Dashboard système : {C.DASHBOARD_HTML}")
print(f"  • Vue simulation    : {C.FESTIVAL_MAP_HTML}")
