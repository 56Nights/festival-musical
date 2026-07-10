"""
Simulation multi-agents (SimPy) — évaluation de scénarios d'organisation.

Agents :
- VisitorFlow : flux de visiteurs par zone (piloté par les courbes d'affluence)
- Incident    : générateur stochastique d'incidents (chute, mouvement de foule)
- Responder   : équipes (médicales/sécurité) positionnées par le CSP,
                temps de réponse dépendant de la distance zone->zone

Évaluation Monte-Carlo : chaque scénario est simulé N fois, on compare
des KPIs (temps de réponse moyen, incidents non couverts, saturation).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import simpy
import config as C

rng = np.random.default_rng(123)

# distance (en minutes de trajet) entre zones — matrice simplifiée
TRAVEL = {
    ("MainStage", "SecondStage"): 4, ("MainStage", "FoodCourt"): 3,
    ("MainStage", "Camping"): 8, ("MainStage", "Entrance"): 6,
    ("SecondStage", "FoodCourt"): 3, ("SecondStage", "Camping"): 6,
    ("SecondStage", "Entrance"): 5, ("FoodCourt", "Camping"): 5,
    ("FoodCourt", "Entrance"): 4, ("Camping", "Entrance"): 7,
}


def travel_time(a: str, b: str) -> float:
    if a == b:
        return 1.0
    return TRAVEL.get((a, b), TRAVEL.get((b, a), 6))


class FestivalSim:
    def __init__(self, allocation: dict, incident_rate: float = 0.08,
                 demand: dict | None = None):
        """
        allocation    : {res_type: {zone: n}} — sortie du CSP
        incident_rate : proba d'incident par zone et par pas de 15 min
        demand        : {zone: densité} — les incidents sont plus probables
                        dans les zones denses (réalisme)
        """
        self.env = simpy.Environment()
        self.allocation = allocation
        self.incident_rate = incident_rate
        d = demand or {z: 1.0 for z in C.ZONES}
        w = np.array([max(d.get(z, 0.05), 0.05) for z in C.ZONES])
        self.zone_probs = w / w.sum()
        self.medical = {
            z: simpy.Resource(self.env, capacity=max(1, allocation["medical"][z]))
            for z in C.ZONES}
        self.kpi = {"response_times": [], "uncovered": 0, "incidents": 0}

    # ---------- processus ----------
    def incident_generator(self, horizon_min: float):
        while self.env.now < horizon_min:
            yield self.env.timeout(rng.exponential(15 / self.incident_rate / C.N_ZONES))
            zone = rng.choice(C.ZONES, p=self.zone_probs)
            self.kpi["incidents"] += 1
            self.env.process(self.handle_incident(zone))

    def handle_incident(self, zone: str):
        t0 = self.env.now
        # équipe locale sinon la plus proche disposant de capacité
        best, best_t = zone, 1.0
        if self.allocation["medical"][zone] == 0:
            cands = [(z, travel_time(z, zone)) for z in C.ZONES
                     if self.allocation["medical"][z] > 0]
            if not cands:
                self.kpi["uncovered"] += 1
                return
            best, best_t = min(cands, key=lambda c: c[1])
        with self.medical[best].request() as req:
            res = yield req | self.env.timeout(30)      # abandon après 30 min
            if req not in res:
                self.kpi["uncovered"] += 1
                return
            yield self.env.timeout(best_t)              # trajet
            yield self.env.timeout(rng.uniform(5, 12))  # prise en charge
        self.kpi["response_times"].append(self.env.now - t0)

    # ---------- exécution ----------
    def run(self, horizon_min: float = 14 * 60):
        self.env.process(self.incident_generator(horizon_min))
        self.env.run(until=horizon_min)
        rt = self.kpi["response_times"]
        return {
            "incidents": self.kpi["incidents"],
            "mean_response_min": float(np.mean(rt)) if rt else None,
            "p95_response_min": float(np.percentile(rt, 95)) if rt else None,
            "uncovered": self.kpi["uncovered"],
        }


def evaluate_scenario(allocation: dict, n_runs: int = 20,
                      incident_rate: float = 0.08,
                      demand: dict | None = None) -> dict:
    """Monte-Carlo : n_runs simulations, KPIs agrégés."""
    results = [FestivalSim(allocation, incident_rate, demand).run()
               for _ in range(n_runs)]
    mean_rts = [r["mean_response_min"] for r in results if r["mean_response_min"]]
    return {
        "runs": n_runs,
        "mean_response_min": round(float(np.mean(mean_rts)), 2),
        "worst_p95_min": round(max(r["p95_response_min"] or 0 for r in results), 2),
        "total_uncovered": sum(r["uncovered"] for r in results),
        "total_incidents": sum(r["incidents"] for r in results),
    }


if __name__ == "__main__":
    from allocation.dynamic_csp import solve_allocation
    demand = {"MainStage": .8, "SecondStage": .5, "FoodCourt": .4,
              "Camping": .2, "Entrance": .3}

    print("Scénario A — allocation optimisée par CSP")
    alloc, _ = solve_allocation(demand)
    print(evaluate_scenario(alloc, demand=demand))

    print("\nScénario B — allocation uniforme naïve")
    naive = {r: {z: t // C.N_ZONES + (1 if i < t % C.N_ZONES else 0)
                 for i, z in enumerate(C.ZONES)}
             for r, t in C.RESOURCES.items()}
    print(evaluate_scenario(naive, demand=demand))
