"""
Dashboard HTML (Plotly) — vue d'ensemble du système pour la démo.

4 panneaux :
  1. Affluence réelle vs prévue (Transformer)
  2. Heatmap de densité par zone (CNN)
  3. Allocation des ressources dans le temps (CSP)
  4. KPIs de simulation : scénario optimisé vs naïf (MAS)
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config as C


def build(scenario_results: dict):
    df = pd.read_csv(C.DATA_CSV)
    with open(os.path.join(C.OUT, "control_log.json")) as f:
        log = json.load(f)

    steps = [e["step"] for e in log]
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(
            "Affluence — dernier jour (réel vs pic prévu à 2h)",
            "Densité par zone (fraction de capacité)",
            "Équipes médicales allouées (CSP dynamique)",
            "Évaluation de scénarios (MAS, Monte-Carlo)"),
        specs=[[{}, {}], [{}, {"type": "bar"}]])

    # --- 1. réel vs prévu (MainStage) ---
    real = df[(df.zone == "MainStage") & (df.step.isin(steps))]
    fig.add_trace(go.Scatter(x=real.step, y=real.attendance / real.capacity,
                             name="MainStage réel", line=dict(width=2)), 1, 1)
    fig.add_trace(go.Scatter(
        x=steps, y=[e["forecast_peak"]["MainStage"] for e in log],
        name="pic prévu (T+2h)", line=dict(dash="dash")), 1, 1)
    fig.add_hline(y=C.DENSITY_ALERT_THRESHOLD, line_dash="dot",
                  line_color="red", row=1, col=1)

    # --- 2. heatmap densité ---
    dens = np.array([[df[(df.zone == z) & (df.step == s)].attendance.iloc[0]
                      / C.ZONE_CAPACITY[z] for s in steps] for z in C.ZONES])
    fig.add_trace(go.Heatmap(z=dens, y=C.ZONES, x=steps,
                             colorscale="YlOrRd", showscale=False), 1, 2)

    # --- 3. allocation médicale dans le temps ---
    for z in C.ZONES:
        ys = [e["allocation"]["medical"][z] if e["allocation"] else None
              for e in log]
        fig.add_trace(go.Scatter(x=steps, y=ys, name=f"med {z}",
                                 mode="lines+markers"), 2, 1)
    # marqueurs d'alerte
    for e in log:
        if e["alerts"]:
            fig.add_vline(x=e["step"], line_color="rgba(200,0,0,.35)",
                          row=2, col=1)

    # --- 4. comparaison scénarios ---
    labels = list(scenario_results.keys())
    fig.add_trace(go.Bar(
        x=labels, y=[scenario_results[k]["mean_response_min"] for k in labels],
        name="temps de réponse moyen (min)"), 2, 2)
    fig.add_trace(go.Bar(
        x=labels, y=[scenario_results[k]["total_uncovered"] for k in labels],
        name="incidents non couverts"), 2, 2)

    fig.update_layout(
        height=850, title_text="Festival Musical Intelligent — Dashboard système",
        legend=dict(orientation="h", y=-0.08), barmode="group")
    fig.write_html(C.DASHBOARD_HTML, include_plotlyjs="cdn")
    print(f"-> dashboard : {C.DASHBOARD_HTML}")


if __name__ == "__main__":
    with open(os.path.join(C.OUT, "scenarios.json")) as f:
        build(json.load(f))
