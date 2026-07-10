"""
Prévision d'affluence par Transformer (encoder-only).

Justification (Compétence 3) :
- dépendances temporelles longues (l'affluence du soir dépend des arrivées
  du matin) -> attention plutôt que convolutions 1D
- covariables connues à l'avance (headliner programmé, heure, météo)
  injectées dans chaque pas, dans l'esprit du Temporal Fusion Transformer
- sortie multi-horizon : 8 pas (2h) prédits d'un coup
"""
import math
import torch
import torch.nn as nn


class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 512):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        pos = torch.arange(max_len).unsqueeze(1).float()
        div = torch.exp(torch.arange(0, d_model, 2).float()
                        * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe.unsqueeze(0))

    def forward(self, x):
        return x + self.pe[:, : x.size(1)]


class AttendanceTransformer(nn.Module):
    """
    Entrée : (batch, SEQ_LEN, n_features) — features par pas :
      [affluence normalisée, tod, headliner, weather, one-hot zone...]
    Sortie : (batch, HORIZON) — affluence normalisée future.
    """

    def __init__(self, n_features: int, d_model: int = 64, n_heads: int = 4,
                 n_layers: int = 2, horizon: int = 8, dropout: float = 0.1):
        super().__init__()
        self.input_proj = nn.Linear(n_features, d_model)
        self.pos = PositionalEncoding(d_model)
        layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=n_heads, dim_feedforward=d_model * 4,
            dropout=dropout, batch_first=True, activation="gelu")
        self.encoder = nn.TransformerEncoder(layer, num_layers=n_layers)
        self.head = nn.Sequential(
            nn.Linear(d_model, d_model), nn.GELU(),
            nn.Linear(d_model, horizon))

    def forward(self, x):
        h = self.encoder(self.pos(self.input_proj(x)))
        return self.head(h[:, -1])          # dernier token -> multi-horizon
