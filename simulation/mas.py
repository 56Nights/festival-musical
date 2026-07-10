"""
Simulation multi-agents (SimPy) — évaluation de scénarios d'organisation.

Agents :
- Incident   : planning d'incidents PRÉ-GÉNÉRÉ et partagé entre scénarios
- Responder  : équipes médicales positionnées par le CSP

Comparaison équitable :
  Les incidents sont générés UNE SEULE FOIS (generate_incidents) puis
  rejoués à l'identique pour chaque allocation testée. Seule la réponse
  (allocation) varie — le nombre et la localisation des incidents sont
  strictement identiques entre CSP optimisé et baseline naïve.
  Sans cela, des différences de comptage (1479 vs 1488) invalident
  toute comparaison de KPIs.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import simpy
import config as C

rng = np.random.default_rng(123)

TRAVEL = {
    ("MainStage", "SecondStage"): 4, ("MainStage", "FoodCourt"): 3,
    ("MainStage", "Camping"): 8,     ("MainStage", "Entrance"): 6,
    ("SecondStage", "FoodCourt"): 3, ("SecondStage", "Camping"): 6,
    ("SecondStage", "Entrance"): 5,  ("FoodCourt", "Camping"): 5,
    ("FoodCourt", "Entrance"): 4,    ("Camping", "Entrance"): 7,
}


def travel_time(a: str, b: str) -> float:
    if a == b:
        return 1.0
    return TRAVEL.get((a, b), TRAVEL.get((b, a), 6))


def generate_incidents(n_runs: int, incident_rate: float = 0.25,
                       demand: dict | None = None,
                       horizon_min: float = 14 * 60,
                       seed: int = 42) -> list:
    """
    Pré-génère n_runs plannings d'incidents identiques pour TOUS les scénarios.
    Chaque planning = liste de (timestamp_min, zone).

    Même seed -> même séquence -> comparaison équitable entre allocations.
    """
    local_rng = np.random.default_rng(seed)
    d = demand or {z: 1.0 for z in C.ZONES}
    w = np.array([max(d.get(z, 0.05), 0.05) for z in C.ZONES])
    zone_probs = w / w.sum()
    mean_inter = 15 / incident_rate / C.N_ZONES

    schedules = []
    for _ in range(n_runs):
        events, t = [], 0.0
        while t < horizon_min:
            t += local_rng.exponential(mean_inter)
            if t < horizon_min:
                zone = local_rng.choice(C.ZONES, p=zone_probs)
                events.append((float(t), str(zone)))
        schedules.append(events)
    return schedules


class FestivalSim:
    def __init__(self, allocation: dict, incidents: list):
        """
        allocation : {res_type: {zone: n}} sortie du CSP
        incidents  : planning pré-généré [(t_min, zone), ...]
        """
        self.env = simpy.Environment()
        self.allocation = allocation
        self.incidents = incidents
        self.medical = {
            z: simpy.Resource(self.env,
                              capacity=max(1, allocation["medical"][z]))
            for z in C.ZONES}
        self.kpi = {"response_times": [], "uncovered": 0, "incidents": 0}

    def incident_player(self):
        for timestamp, zone in self.incidents:
            yield self.env.timeout(max(0.0, timestamp - self.env.now))
            self.kpi["incidents"] += 1
            self.env.process(self.handle_incident(zone))

    def handle_incident(self, zone: str):
        t0 = self.env.now
        best, best_t = zone, 1.0
        if self.allocation["medical"][zone] == 0:
            cands = [(z, travel_time(z, zone)) for z in C.ZONES
                     if self.allocation["medical"][z] > 0]
            if not cands:
                self.kpi["uncovered"] += 1
                return
            best, best_t = min(cands, key=lambda c: c[1])
        with self.medical[best].request() as req:
            result = yield req | self.env.timeout(30)
            if req not in result:
                self.kpi["uncovered"] += 1
                return
            yield self.env.timeout(best_t)
            yield self.env.timeout(rng.uniform(5, 12))
        self.kpi["response_times"].append(self.env.now - t0)

    def run(self) -> dict:
        self.env.process(self.incident_player())
        self.env.run()
        rt = self.kpi["response_times"]
        return {
            "incidents": self.kpi["incidents"],
            "mean_response_min": float(np.mean(rt)) if rt else None,
            "p95_response_min":  float(np.percentile(rt, 95)) if rt else None,
            "uncovered": self.kpi["uncovered"],
        }


def evaluate_scenario(allocation: dict, n_runs: int = 20,
                      incident_rate: float = 0.25,
                      demand: dict | None = None,
                      schedules: list | None = None) -> dict:
    """
    Évalue une allocation sur n_runs simulations Monte-Carlo.

    schedules : plannings pré-générés (generate_incidents).
                Toujours fournir le MÊME objet schedules pour toutes les
                allocations à comparer -> nombre d'incidents identique.
    """
    if schedules is None:
        schedules = generate_incidents(n_runs, incident_rate, demand)

    results = [FestivalSim(allocation, s).run() for s in schedules]
    mean_rts = [r["mean_response_min"] for r in results
                if r["mean_response_min"] is not None]
    return {
        "runs": n_runs,
        "mean_response_min":  round(float(np.mean(mean_rts)), 2),
        "worst_p95_min":      round(max(r["p95_response_min"] or 0
                                        for r in results), 2),
        "total_uncovered":    sum(r["uncovered"]  for r in results),
        "total_incidents":    sum(r["incidents"]  for r in results),
    }


if __name__ == "__main__":
    from allocation.dynamic_csp import solve_allocation
    demand = {"MainStage": .8, "SecondStage": .5, "FoodCourt": .4,
              "Camping": .2, "Entrance": .3}

    # plannings partagés — même incidents pour les deux allocations
    shared = generate_incidents(20, demand=demand)

    alloc_csp, _ = solve_allocation(demand)
    naive = {r: {z: t // C.N_ZONES + (1 if i < t % C.N_ZONES else 0)
                 for i, z in enumerate(C.ZONES)}
             for r, t in C.RESOURCES.items()}

    r_csp   = evaluate_scenario(alloc_csp, schedules=shared, demand=demand)
    r_naive = evaluate_scenario(naive,     schedules=shared, demand=demand)

    print("CSP optimisé :", r_csp)
    print("Naïf         :", r_naive)
    assert r_csp["total_incidents"] == r_naive["total_incidents"], \
        "Les deux scénarios doivent avoir le même nombre d'incidents !"
    print("OK — nombre d'incidents identique :", r_csp["total_incidents"])
