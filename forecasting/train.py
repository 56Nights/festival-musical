"""Entraînement du Transformer de prévision d'affluence."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

import config as C
from forecasting.model import AttendanceTransformer

torch.manual_seed(0)


def build_features(df: pd.DataFrame):
    """Matrice (steps, zones, features) + cible normalisée par capacité."""
    zones = C.ZONES
    zid = {z: i for i, z in enumerate(zones)}
    steps = df["step"].max() + 1
    n_feat = 4 + len(zones)                     # att, tod, headliner, weather, one-hot
    X = np.zeros((steps, len(zones), n_feat), dtype=np.float32)
    for _, r in df.iterrows():
        z = zid[r["zone"]]
        X[int(r["step"]), z, 0] = r["attendance"] / r["capacity"]
        X[int(r["step"]), z, 1] = r["tod"]
        X[int(r["step"]), z, 2] = r["headliner"]
        X[int(r["step"]), z, 3] = r["weather"]
        X[int(r["step"]), z, 4 + z] = 1.0
    return X


def make_windows(X):
    xs, ys = [], []
    steps = X.shape[0]
    for z in range(X.shape[1]):
        series = X[:, z, :]
        for t in range(C.SEQ_LEN, steps - C.HORIZON):
            xs.append(series[t - C.SEQ_LEN: t])
            ys.append(series[t: t + C.HORIZON, 0])
    return (torch.tensor(np.array(xs)), torch.tensor(np.array(ys)))


def train():
    df = pd.read_csv(C.DATA_CSV)
    X = build_features(df)
    xs, ys = make_windows(X)

    # split temporel (pas aléatoire : éviter la fuite de données)
    n = len(xs)
    cut = int(n * 0.85)
    train_dl = DataLoader(TensorDataset(xs[:cut], ys[:cut]),
                          batch_size=64, shuffle=True)
    val_x, val_y = xs[cut:], ys[cut:]

    model = AttendanceTransformer(
        n_features=xs.shape[-1], d_model=C.D_MODEL, n_heads=C.N_HEADS,
        n_layers=C.N_LAYERS, horizon=C.HORIZON)
    opt = torch.optim.AdamW(model.parameters(), lr=C.LR)
    loss_fn = nn.SmoothL1Loss()

    for epoch in range(C.EPOCHS_FORECAST):
        model.train()
        tot = 0.0
        for xb, yb in train_dl:
            opt.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            opt.step()
            tot += loss.item() * len(xb)
        model.eval()
        with torch.no_grad():
            val_mae = (model(val_x) - val_y).abs().mean().item()
        print(f"epoch {epoch+1:02d}  train_loss={tot/cut:.4f}  val_MAE={val_mae:.4f}")

    torch.save({"state": model.state_dict(), "n_features": xs.shape[-1]},
               C.FORECAST_MODEL)
    print(f"-> modèle sauvegardé : {C.FORECAST_MODEL}")
    print(f"   val_MAE = {val_mae:.4f} (en fraction de capacité, "
          f"~{val_mae*100:.1f}% d'erreur moyenne)")
    return val_mae


if __name__ == "__main__":
    train()
