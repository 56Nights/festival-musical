"""
Génération de données simulées du festival (Compétence 2 — Gérer).

Produit :
- attendance.csv : affluence par zone / pas de 15 min, avec covariables
  (jour, heure, headliner programmé, météo simulée)
- events.csv     : incidents injectés (chutes, densité critique, objet suspect)

Les courbes sont construites à partir de motifs réalistes :
montée progressive, pic pendant les têtes d'affiche, migration
entre zones (concert -> food court), bruit stochastique.
"""
import numpy as np
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as C

rng = np.random.default_rng(42)


def _base_curve(steps_per_day: int) -> np.ndarray:
    """Courbe journalière en cloche asymétrique (pic en soirée)."""
    t = np.linspace(0, 1, steps_per_day)
    return np.exp(-((t - 0.72) ** 2) / 0.045)  # pic ~ 20h


def generate() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    headliner_steps = set()

    for day in range(C.FESTIVAL_DAYS):
        base = _base_curve(C.STEPS_PER_DAY)
        # une tête d'affiche par soir sur MainStage (fenêtre de 1h30)
        h_start = int(C.STEPS_PER_DAY * 0.70) + rng.integers(-3, 3)
        h_window = range(h_start, h_start + 6)
        headliner_steps.update(day * C.STEPS_PER_DAY + s for s in h_window)

        weather = rng.uniform(0.7, 1.0)  # facteur météo journalier

        for step in range(C.STEPS_PER_DAY):
            g = day * C.STEPS_PER_DAY + step
            is_head = step in h_window
            for zone in C.ZONES:
                cap = C.ZONE_CAPACITY[zone]
                level = base[step]
                if zone == "MainStage":
                    level *= 1.5 if is_head else 0.9
                elif zone == "SecondStage":
                    level *= 0.55 if is_head else 0.85  # migration vers MainStage
                elif zone == "FoodCourt":
                    # pic décalé après les concerts
                    level = 0.6 * base[max(0, step - 6)] + 0.25
                elif zone == "Camping":
                    level = 0.55 - 0.35 * base[step]     # inverse des concerts
                elif zone == "Entrance":
                    level = 0.9 * base[max(0, step - int(C.STEPS_PER_DAY*0.3))] \
                            if step < C.STEPS_PER_DAY * 0.5 else 0.15

                att = cap * np.clip(level * weather, 0, 1.15)
                att *= 1 + rng.normal(0, 0.05)           # bruit
                rows.append({
                    "step": g, "day": day, "tod": step / C.STEPS_PER_DAY,
                    "zone": zone, "attendance": max(0, round(att)),
                    "capacity": cap, "headliner": int(is_head),
                    "weather": round(weather, 3),
                })

    df = pd.DataFrame(rows)

    # ---- incidents injectés (vérité terrain pour la détection) ----
    ev = []
    for _ in range(10):
        step = int(rng.integers(C.STEPS_PER_DAY // 2, C.TOTAL_STEPS))
        zone = rng.choice(C.ZONES[:3])
        kind = rng.choice(["fallen_person", "suspicious_object", "crowd_surge"],
                          p=[0.4, 0.2, 0.4])
        ev.append({"step": step, "zone": zone, "type": kind})

    # incidents garantis dans la fenêtre rejouée par la boucle de contrôle
    # (dernier jour, après SEQ_LEN pas d'historique) — pour la démo
    w0 = C.TOTAL_STEPS - C.STEPS_PER_DAY + C.SEQ_LEN
    ev += [
        {"step": w0 + 5,  "zone": "MainStage",   "type": "fallen_person"},
        {"step": w0 + 11, "zone": "FoodCourt",   "type": "suspicious_object"},
        {"step": w0 + 17, "zone": "SecondStage", "type": "crowd_surge"},
    ]
    events = pd.DataFrame(ev).sort_values("step").reset_index(drop=True)

    os.makedirs(C.OUT, exist_ok=True)
    df.to_csv(C.DATA_CSV, index=False)
    events.to_csv(C.EVENTS_CSV, index=False)
    return df, events


if __name__ == "__main__":
    df, events = generate()
    print(f"attendance.csv : {len(df)} lignes ({C.TOTAL_STEPS} pas x {C.N_ZONES} zones)")
    print(f"events.csv     : {len(events)} incidents injectés")
    print(events.to_string(index=False))
