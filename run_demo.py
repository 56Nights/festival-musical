"""
DÉMO COMPLÈTE — exécute tout le système de bout en bout.

    uv run python run_demo.py

Étapes :
  1. Génération des données simulées             (Compétence 2)
  2. Prévision zéro-shot TimesFM — pas d'entraînement (Compétences 1, 3)
  3. Têtes du CNN ResNet18 — entraînées UNE fois puis rechargées
  4. Boucle de contrôle intégrée                 (intégration des 4 modules)
  5. Évaluation de scénarios par MAS             (Compétence 3)
  6. Dashboard HTML                              (Compétence 5)
  7. Narration LLM — rapport de situation        (Compétence 5)

Les poids du CNN (outputs/vision_cnn.pt) sont réutilisés s'ils existent :
supprimez le fichier pour forcer un ré-entraînement (~30 s, têtes seules).
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C

t0 = time.time()

print("=" * 60)
print("1/7  Génération des données simulées")
print("=" * 60)
from data.generate_data import generate
generate()

print("\n" + "=" * 60)
print("2/7  Prévision d'affluence — TimesFM zéro-shot (aucun entraînement)")
print("=" * 60)
from forecasting.timesfm_forecaster import ZeroShotForecaster
print(f"backend : {ZeroShotForecaster().backend}")

print("\n" + "=" * 60)
print("3/7  CNN ResNet18 — têtes multi-tâches")
print("=" * 60)
if os.path.exists(C.VISION_MODEL):
    print(f"poids trouvés ({C.VISION_MODEL}) — entraînement sauté")
else:
    from vision.train import train as train_cnn
    train_cnn()

print("\n" + "=" * 60)
print("4/7  Boucle de contrôle intégrée (TimesFM + CNN + CSP)")
print("=" * 60)
from integration.pipeline import run_control_loop
log = run_control_loop()
print(f"{sum(len(e['alerts']) for e in log)} alertes | "
      f"{sum(e['resolved'] for e in log)} ré-allocations")

print("\n" + "=" * 60)
print("5/7  Évaluation de scénarios (simulation multi-agents)")
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

# plannings partagés générés avec le pic — même incidents pour les deux allocations
shared_schedules = generate_incidents(20, incident_rate=0.25, demand=peak_demand)

scenarios = {
    "CSP optimisé": evaluate_scenario(alloc_csp, schedules=shared_schedules),
    "Uniforme naïf": evaluate_scenario(naive,     schedules=shared_schedules),
}
for name, kpi in scenarios.items():
    print(f"  {name:14s} -> {kpi}")
with open(os.path.join(C.OUT, "scenarios.json"), "w") as f:
    json.dump(scenarios, f, indent=1)

print("\n" + "=" * 60)
print("6/7  Génération du dashboard")
print("=" * 60)
from dashboard.build_dashboard import build
build(scenarios)

print("\n" + "=" * 60)
print("7/7  Narration LLM — rapport de situation")
print("=" * 60)
from narration.llm_narrator import summarize
report = summarize(log, scenarios)
print("\n" + report)

print(f"\nTerminé en {time.time()-t0:.0f}s. Sorties dans {C.OUT}/")
