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
    fig.add_annotation(
        xref="paper", yref="paper", x=1, y=1.06, showarrow=False,
        xanchor="right", font=dict(size=13, color="#2a78d6"),
        text="<a href='festival_map.html' style='color:#2a78d6'>"
             "▶ Vue simulation en direct (jumeau numérique animé) →</a>")

    # section COMPARAISON avec / sans (si l'évaluateur a tourné)
    cmp_div = _comparison_section(log)

    main_div = fig.to_html(full_html=False, include_plotlyjs="cdn")
    html = ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>Festival — Dashboard système</title></head>"
            "<body style='font-family:-apple-system,sans-serif;margin:0'>"
            + main_div + cmp_div + "</body></html>")
    with open(C.DASHBOARD_HTML, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"-> dashboard : {C.DASHBOARD_HTML}")


A_COL, S_COL = "#0ca30c", "#d03b3b"          # avec (vert) / sans (rouge)


def _comparison_section(log):
    """Figure comparative « avec / sans gestion prédictive » + ablation.
    Retourne un div HTML (vide si kpi_comparison.json absent)."""
    path = os.path.join(C.OUT, "kpi_comparison.json")
    if not os.path.exists(path):
        return ""
    with open(path) as fh:
        cmp = json.load(fh)
    a, s = cmp["avec"], cmp["sans"]
    def _clock(step):
        m = (step % C.STEPS_PER_DAY) * C.STEP_MINUTES
        return f"{10 + m // 60:02d}:{m % 60:02d}"
    clocks = [_clock(e["step"]) for e in log]

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(
            "Temps de réponse — fonction de répartition (CDF)",
            "CA perdu au FoodCourt (cumulé sur la journée)",
            "KPIs de sécurité — avec vs sans",
            "Ablation : temps de réponse par configuration"),
        specs=[[{}, {}], [{"type": "bar"}, {"type": "bar"}]])

    # 1. CDF des temps de réponse
    for side, col, name in ((a, A_COL, "avec"), (s, S_COL, "sans")):
        xs = side["response_samples"]
        if xs:
            ys = [100 * (i + 1) / len(xs) for i in range(len(xs))]
            fig.add_trace(go.Scatter(x=xs, y=ys, name=name, mode="lines",
                                     line=dict(color=col, width=2)), 1, 1)
    fig.add_vline(x=cmp["targets"]["response_target_min"], line_dash="dot",
                  line_color="#888", row=1, col=1)
    fig.update_xaxes(title_text="minutes", row=1, col=1)
    fig.update_yaxes(title_text="% incidents", row=1, col=1)

    # 2. CA perdu cumulé
    n = min(len(clocks), len(a["step_series"]), len(s["step_series"]))
    fig.add_trace(go.Scatter(x=clocks[:n], y=[a["step_series"][i]["cum_rev"] for i in range(n)],
                             name="avec €", line=dict(color=A_COL, width=2)), 1, 2)
    fig.add_trace(go.Scatter(x=clocks[:n], y=[s["step_series"][i]["cum_rev"] for i in range(n)],
                             name="sans €", line=dict(color=S_COL, width=2),
                             fill="tonexty", fillcolor="rgba(208,59,59,.12)"), 1, 2)
    fig.update_yaxes(title_text="€ perdus", row=1, col=2)

    # 3. KPIs de sécurité (barres groupées) : chaîne de secours + réaction en chaîne
    labels = ["détection", "premiers gestes", "arrivée médic",
              "blessés induits", "R_eff ×10", "MCE ×10"]
    av = [a["mean_detect_min"]["mean"], a["mean_first_aid_min"]["mean"],
          a["mean_response_min"]["mean"], a["mean_induced"],
          a["r_eff"] * 10, a["mean_mce"] * 10]
    sv = [s["mean_detect_min"]["mean"], s["mean_first_aid_min"]["mean"],
          s["mean_response_min"]["mean"], s["mean_induced"],
          s["r_eff"] * 10, s["mean_mce"] * 10]
    fig.add_trace(go.Bar(x=labels, y=av, name="avec", marker_color=A_COL), 2, 1)
    fig.add_trace(go.Bar(x=labels, y=sv, name="sans", marker_color=S_COL), 2, 1)

    # 4. ablation (temps de réponse + CA perdu en annotation)
    ab_path = os.path.join(C.OUT, "kpi_ablation.json")
    if os.path.exists(ab_path):
        abl = json.load(open(ab_path))
        names = list(abl.keys())
        resp = [abl[k]["mean_response_min"]["mean"] for k in names]
        cols = [A_COL if "complet" in k else S_COL if "aucun" in k else "#eda100"
                for k in names]
        fig.add_trace(go.Bar(x=names, y=resp, marker_color=cols,
                             text=[f"{abl[k]['lost_revenue_eur']} € perdus" for k in names],
                             textposition="outside", name="réponse (min)"), 2, 2)
        fig.update_yaxes(title_text="réponse (min)", row=2, col=2)

    fig.update_layout(
        height=780, barmode="group", showlegend=True,
        legend=dict(orientation="h", y=-0.08),
        title_text="Impact de la gestion prédictive — même journée, avec vs sans "
                   f"(→ {s['lost_revenue_eur'] - a['lost_revenue_eur']} € sauvés, "
                   f"réponse {a['mean_response_min']['mean']} vs "
                   f"{s['mean_response_min']['mean']} min)")
    return ("<hr style='margin:24px 40px;border:none;border-top:1px solid #ddd'>"
            + fig.to_html(full_html=False, include_plotlyjs=False))


if __name__ == "__main__":
    with open(os.path.join(C.OUT, "scenarios.json")) as f:
        build(json.load(f))
