"""
Visualisation des données synthétiques en local.

    uv run python visualize.py

Ouvre deux fenêtres dans votre navigateur :
  1. Les frames synthétiques du CNN (5 scénarios côte à côte)
  2. Les courbes d'affluence simulées + incidents injectés
"""
import sys, os, webbrowser
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from vision.synthetic_images import make_frame
import config as C


def show_frames():
    scenarios = [
        (0.2, False, False, "Foule clairsemée"),
        (0.8, False, False, "Foule dense"),
        (0.9, True,  False, "Personne au sol"),
        (0.6, False, True,  "Objet suspect"),
        (0.95, True, True,  "Tout actif"),
    ]
    fig = make_subplots(rows=1, cols=len(scenarios),
                        subplot_titles=[s[3] for s in scenarios])
    for i, (d, f, o, _) in enumerate(scenarios, 1):
        frame = make_frame(d, f, o)
        img = (frame.transpose(1, 2, 0) * 255).astype(np.uint8)
        fig.add_trace(go.Image(z=img), row=1, col=i)
    fig.update_layout(title_text="Frames synthétiques CNN (64×64)",
                      height=350, width=1100)
    fig.update_xaxes(showticklabels=False)
    fig.update_yaxes(showticklabels=False)

    path = os.path.join(C.OUT, "synthetic_frames.html")
    fig.write_html(path, include_plotlyjs="cdn")
    webbrowser.open(f"file://{os.path.abspath(path)}")
    print(f"Frames synthétiques -> {path}")


def show_attendance():
    df = pd.read_csv(C.DATA_CSV)
    events = pd.read_csv(C.EVENTS_CSV)

    fig = make_subplots(rows=2, cols=1,
                        subplot_titles=("Affluence par zone (fraction de capacité)",
                                        "Incidents injectés"),
                        row_heights=[0.7, 0.3])

    colors = ["#e41a1c", "#377eb8", "#4daf4a", "#ff7f00", "#984ea3"]
    for zone, color in zip(C.ZONES, colors):
        zdf = df[df.zone == zone].sort_values("step")
        fig.add_trace(go.Scatter(
            x=zdf.step, y=zdf.attendance / zdf.capacity,
            name=zone, line=dict(color=color, width=1.5)), row=1, col=1)

    fig.add_hline(y=C.DENSITY_ALERT_THRESHOLD, line_dash="dot",
                  line_color="red", row=1, col=1)

    type_colors = {"fallen_person": "red", "suspicious_object": "orange",
                   "crowd_surge": "purple"}
    for _, ev in events.iterrows():
        fig.add_trace(go.Scatter(
            x=[ev.step], y=[0.5], mode="markers+text",
            marker=dict(symbol="triangle-up", size=14,
                        color=type_colors.get(ev.type, "gray")),
            text=[f"{ev.zone} ({ev.type})"], textposition="top center",
            showlegend=False), row=2, col=1)

    fig.update_layout(height=700, title_text="Données simulées du festival")
    fig.update_yaxes(title_text="fraction capacité", row=1, col=1)
    fig.update_yaxes(showticklabels=False, row=2, col=1)

    path = os.path.join(C.OUT, "simulated_data.html")
    fig.write_html(path, include_plotlyjs="cdn")
    webbrowser.open(f"file://{os.path.abspath(path)}")
    print(f"Données simulées -> {path}")


if __name__ == "__main__":
    os.makedirs(C.OUT, exist_ok=True)

    if not os.path.exists(C.DATA_CSV):
        print("Données non trouvées, génération...")
        from data.generate_data import generate
        generate()

    show_frames()
    show_attendance()
    print("\nLes deux pages se sont ouvertes dans votre navigateur.")
