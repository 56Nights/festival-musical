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
from simulation import geometry as G

# palette de zone UNIFIÉE avec la vue simulation (source : geometry.ZONE_COLORS)
# -> plus de « MainStage bleu sur la carte, violet ici ».
ZCOL = {z: G.ZONE_COLORS[z]["light"] for z in C.ZONES}


def _takeaway(fig, row, col, text):
    """Annote un panneau d'une phrase de lecture (« à retenir »)."""
    ref_x = "x domain" if (row, col) == (1, 1) else None
    fig.add_annotation(
        xref=f"x{_axis_idx(row, col)} domain", yref=f"y{_axis_idx(row, col)} domain",
        x=0.5, y=1.14, showarrow=False, xanchor="center",
        font=dict(size=11, color="#555"), text=text, row=row, col=col)


def _axis_idx(row, col):
    return {(1, 1): "", (1, 2): "2", (2, 1): "3", (2, 2): "4"}[(row, col)]


def build(scenario_results: dict):
    df = pd.read_csv(C.DATA_CSV)
    with open(os.path.join(C.OUT, "control_log.json")) as f:
        log = json.load(f)

    steps = [e["step"] for e in log]
    clocks = [C.step_to_hhmm(s) for s in steps]   # axes en HH:MM (pas d'indices bruts)
    fig = make_subplots(
        rows=2, cols=2, vertical_spacing=0.16, horizontal_spacing=0.09,
        subplot_titles=(
            "Affluence MainStage — réel vs pic prévu à 2h",
            "Densité par zone (fraction de capacité)",
            "Équipes médicales allouées — carte de charge (CSP)",
            "Évaluation de scénarios (MAS, Monte-Carlo)"),
        specs=[[{}, {}], [{}, {"secondary_y": True}]])

    # --- 1. réel vs prévu (MainStage), axe horloge ---
    real = df[(df.zone == "MainStage") & (df.step.isin(steps))].sort_values("step")
    fig.add_trace(go.Scatter(x=clocks, y=real.attendance / real.capacity,
                             name="MainStage réel",
                             line=dict(width=2, color=ZCOL["MainStage"])), 1, 1)
    fig.add_trace(go.Scatter(
        x=clocks, y=[e["forecast_peak"]["MainStage"] for e in log],
        name="pic prévu (T+2h)",
        line=dict(dash="dash", color=ZCOL["MainStage"])), 1, 1)
    fig.add_hline(y=C.DENSITY_ALERT_THRESHOLD, line_dash="dot", line_color="red",
                  annotation_text="seuil d'alerte 85 %", annotation_position="top left",
                  annotation_font_color="red", row=1, col=1)
    fig.update_yaxes(title_text="densité (frac. capacité)", row=1, col=1)

    # --- 2. heatmap densité (colourbar étiquetée) ---
    dens = np.array([[df[(df.zone == z) & (df.step == s)].attendance.iloc[0]
                      / C.ZONE_CAPACITY[z] for s in steps] for z in C.ZONES])
    fig.add_trace(go.Heatmap(
        z=dens, y=C.ZONES, x=clocks, colorscale="YlOrRd",
        colorbar=dict(title="densité", len=0.42, y=0.79, thickness=12)), 1, 2)

    # --- 3. allocation médicale : carte de charge zone × temps (ex-spaghetti) ---
    med = np.array([[(e["allocation"]["medical"][z] if e["allocation"] else 0)
                     for e in log] for z in C.ZONES])
    fig.add_trace(go.Heatmap(
        z=med, y=C.ZONES, x=clocks, colorscale="Blues", zmin=0,
        colorbar=dict(title="équipes", len=0.42, y=0.21, thickness=12),
        hovertemplate="%{y} — %{x}<br>%{z} équipe(s) médicale(s)<extra></extra>"), 2, 1)

    # --- 4. comparaison scénarios : minutes (axe gauche) vs comptes (axe droit) ---
    labels = list(scenario_results.keys())
    fig.add_trace(go.Bar(
        x=labels, y=[scenario_results[k]["mean_response_min"] for k in labels],
        name="réponse moy. (min)", marker_color="#2a78d6"), 2, 2, secondary_y=False)
    fig.add_trace(go.Bar(
        x=labels, y=[scenario_results[k]["total_uncovered"] for k in labels],
        name="incidents non couverts", marker_color="#d03b3b"), 2, 2, secondary_y=True)
    fig.update_yaxes(title_text="minutes", row=2, col=2, secondary_y=False)
    fig.update_yaxes(title_text="incidents", row=2, col=2, secondary_y=True)

    # takeaways (une phrase par panneau)
    _takeaway(fig, 1, 1, "La prévision anticipe la montée vers la tête d'affiche.")
    _takeaway(fig, 1, 2, "Plusieurs zones dépassent 85 % en soirée (rouge foncé).")
    _takeaway(fig, 2, 1, "Le CSP concentre les équipes sur les zones chaudes du moment.")
    _takeaway(fig, 2, 2, "Minutes (bleu, gauche) et non-couverts (rouge, droite) — échelles séparées.")

    fig.update_layout(
        height=880, title_text="Festival Musical Intelligent — Dashboard système",
        legend=dict(orientation="h", y=-0.08), barmode="group")
    fig.add_annotation(
        xref="paper", yref="paper", x=1, y=1.08, showarrow=False,
        xanchor="right", font=dict(size=13, color="#2a78d6"),
        text="<a href='festival_map.html' style='color:#2a78d6'>"
             "▶ Vue simulation en direct (jumeau numérique animé) →</a>")

    # section COMPARAISON avec / sans (si l'évaluateur a tourné)
    cmp_div = _comparison_section(log)

    # include_plotlyjs=True -> bibliothèque INLINE : le dashboard rend HORS-LIGNE
    # (garantie « la démo ne dépend jamais du réseau », comme la vue simulation).
    main_div = fig.to_html(full_html=False, include_plotlyjs=True)
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
    clocks = [C.step_to_hhmm(e["step"]) for e in log]

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
