"""
Pipeline intégré — le cœur du système intelligent.

Boucle de contrôle (par pas de 15 min) :

  1. Transformer  -> prévision d'affluence à 2h par zone
  2. CNN          -> analyse des frames (densité, chute, objet suspect)
  3. File d'événements (priorisée)
  4. CSP dynamique -> ré-allocation si déclencheur périodique OU événement
  5. Journal complet -> dashboard

C'est cette boucle qui matérialise l'intégration des 4 modules.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import numpy as np
import pandas as pd
import torch

import config as C
from forecasting.timesfm_forecaster import ZeroShotForecaster
from vision.model import MultiTaskCrowdCNN
from vision.synthetic_images import make_frame
from allocation.dynamic_csp import solve_allocation


def load_models():
    forecaster = ZeroShotForecaster()

    cnn = MultiTaskCrowdCNN(pretrained=True)
    cnn.load_state_dict(torch.load(C.VISION_MODEL, weights_only=True))
    cnn.eval()
    return forecaster, cnn


def run_control_loop(start_step: int = None, n_steps: int = 24):
    """Rejoue n_steps pas de 15 min du dernier jour du festival."""
    df = pd.read_csv(C.DATA_CSV)
    events = pd.read_csv(C.EVENTS_CSV)
    forecaster, cnn = load_models()

    # séries d'affluence normalisée par zone (fraction de capacité)
    series = {z: (df[df.zone == z].sort_values("step").attendance
                  / C.ZONE_CAPACITY[z]).to_numpy() for z in C.ZONES}

    if start_step is None:
        start_step = C.TOTAL_STEPS - C.STEPS_PER_DAY + C.SEQ_LEN  # dernier jour

    log = []
    prev_alloc = None

    for step in range(start_step, min(start_step + n_steps, C.TOTAL_STEPS)):
        entry = {"step": step, "alerts": [], "resolved": False}

        # ---- 1. prévision par zone (TimesFM zéro-shot) ----
        forecasts = {}
        for z in C.ZONES:
            pred = forecaster.forecast(series[z][:step])
            forecasts[z] = float(np.max(pred))       # pic à horizon 2h
        entry["forecast_peak"] = {z: round(v, 3) for z, v in forecasts.items()}

        # ---- 2. vision (CNN) : une frame simulée par zone ----
        truth = events[events["step"] == step]
        emergencies = {}
        with torch.no_grad():
            for z in C.ZONES:
                real_density = series[z][step]
                inc = truth[truth["zone"] == z]["type"].tolist()
                frame = torch.tensor(make_frame(
                    density=float(np.clip(real_density, 0, 1)),
                    fallen="fallen_person" in inc or "crowd_surge" in inc,
                    obj="suspicious_object" in inc)).unsqueeze(0)
                out = cnn(frame)
                kinds = []
                if torch.sigmoid(out["fallen"]).item() > 0.5:
                    kinds.append("fallen_person")
                if torch.sigmoid(out["object"]).item() > 0.5:
                    kinds.append("suspicious_object")
                if out["density"].item() > C.DENSITY_ALERT_THRESHOLD:
                    kinds.append("crowd_surge")
                if kinds:
                    emergencies[z] = kinds
                    entry["alerts"].append({"zone": z, "types": kinds,
                                            "density": round(out["density"].item(), 2)})

        # ---- 3+4. déclencheurs -> CSP dynamique ----
        periodic = (step - start_step) % C.RESOLVE_EVERY_STEPS == 0
        forecast_spike = any(v > C.DENSITY_ALERT_THRESHOLD for v in forecasts.values())
        if periodic or emergencies or forecast_spike:
            alloc, status = solve_allocation(forecasts, emergencies, prev_alloc)
            entry["resolved"] = True
            entry["trigger"] = ("event" if emergencies else
                                "forecast" if forecast_spike else "periodic")
            entry["allocation"] = alloc
            entry["solver_status"] = status
            prev_alloc = alloc
        else:
            entry["allocation"] = prev_alloc

        log.append(entry)

    with open(os.path.join(C.OUT, "control_log.json"), "w") as f:
        json.dump(log, f, indent=1)
    return log


if __name__ == "__main__":
    log = run_control_loop()
    n_alerts = sum(len(e["alerts"]) for e in log)
    n_resolves = sum(e["resolved"] for e in log)
    print(f"{len(log)} pas simulés | {n_alerts} alertes CNN | "
          f"{n_resolves} ré-allocations CSP")
    for e in log:
        if e["alerts"]:
            print(f"  step {e['step']} [{e.get('trigger')}] -> {e['alerts']}")
