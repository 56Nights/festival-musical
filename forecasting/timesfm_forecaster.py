"""
Prévision d'affluence — TimesFM (zéro-shot).

Justification (Compétence 3) :
- TimesFM (Google) est un modèle de fondation pour séries temporelles,
  pré-entraîné sur ~100 milliards de points réels. En zéro-shot, il rivalise
  avec des modèles supervisés entraînés sur les données cibles — plus robuste
  qu'un entraînement from scratch sur des données simulées limitées.
- Aucun entraînement local : un simple forward pass CPU suffit.

Repli : si le checkpoint TimesFM n'est pas disponible (pas de réseau,
machine légère), une baseline saisonnière-naïve documentée prend le relais.
La démo ne dépend donc jamais du téléchargement du modèle.

Limite à mentionner dans le rapport : TimesFM est univarié — les covariables
(headliner, météo) ne sont pas injectées explicitement ; le modèle infère la
saisonnalité depuis l'historique. Une extension possible : TimesFM + résidus
corrigés par covariables (modèle hybride).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import config as C

_TIMESFM_REPO = "google/timesfm-2.5-200m-pytorch"


class ZeroShotForecaster:
    """Interface unique : .forecast(history: 1D array) -> array[HORIZON]."""

    def __init__(self, horizon: int = C.HORIZON, context: int = None):
        self.horizon = horizon
        self.context = context or C.SEQ_LEN * 2
        self.backend = "seasonal-naive"
        self.model = None
        self._try_load_timesfm()

    def _try_load_timesfm(self):
        try:
            import timesfm
            model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(_TIMESFM_REPO)
            model.compile(timesfm.ForecastConfig(
                max_context=max(self.context, 64),
                max_horizon=max(self.horizon, 16),
                normalize_inputs=True,
                use_continuous_quantile_head=True,
            ))
            self.model = model
            self.backend = "timesfm-2.5-200m (zero-shot)"
        except Exception as exc:
            print(f"[forecast] TimesFM indisponible ({type(exc).__name__}) "
                  f"-> repli saisonnier-naïf")

    # ------------------------------------------------------------------
    def forecast(self, history: np.ndarray, at_step: int = None) -> np.ndarray:
        """history : série 1D (fraction de capacité). Retourne HORIZON pas.

        at_step : pas courant (optionnel). Fourni -> amortissement dérivé du
        PROGRAMME connu (le modèle univarié ignore la fin de la tête d'affiche
        et surestime l'affluence post-concert ; on corrige avec la covariable
        « egress » — hybride suggéré dans la limite du module)."""
        history = np.asarray(history, dtype=np.float32)[-self.context:]
        if self.model is not None:
            point, _ = self.model.forecast(
                horizon=self.horizon, inputs=[history])
            pred = np.clip(np.asarray(point[0], dtype=np.float32), 0, 1.2)
        else:
            pred = self._seasonal_naive(history)
        if at_step is not None:
            pred = self._schedule_damping(pred, at_step)
        return pred

    def _schedule_damping(self, pred: np.ndarray, at_step: int) -> np.ndarray:
        """Amortit les positions d'horizon qui tombent APRÈS la fin de la tête
        d'affiche (egress) : décroissance douce (les gens partent), bornée."""
        out = np.asarray(pred, dtype=np.float32).copy()
        for h in range(len(out)):
            minute = ((at_step + h + 1) % C.STEPS_PER_DAY) * C.STEP_MINUTES
            if minute > C.HEADLINER_END_MIN:
                hours_after = (minute - C.HEADLINER_END_MIN) / 60.0
                out[h] *= max(0.35, 1.0 - 0.5 * hours_after)
        return out

    def _seasonal_naive(self, history: np.ndarray) -> np.ndarray:
        """Baseline : dernière valeur + tendance locale, bornée [0, 1.2].
        Période saisonnière = 1 journée si assez d'historique."""
        period = C.STEPS_PER_DAY
        if len(history) > period + self.horizon:
            # même heure la veille, ajustée du niveau actuel
            season = history[-period: -period + self.horizon]
            level = history[-1] - history[-period - 1]
            return np.clip(season + level, 0, 1.2)
        # sinon : persistance avec tendance sur les 4 derniers pas
        trend = (history[-1] - history[-4]) / 3 if len(history) >= 4 else 0.0
        return np.clip(history[-1] + trend * np.arange(1, self.horizon + 1),
                       0, 1.2)


if __name__ == "__main__":
    import pandas as pd
    df = pd.read_csv(C.DATA_CSV)
    fc = ZeroShotForecaster()
    print(f"backend : {fc.backend}")

    # mini-évaluation : MAE sur le dernier jour, TimesFM vs baseline saisonnière.
    # On COMPARE explicitement au repli naïf : un « Concevoir » honnête montre que
    # le modèle de fondation bat (ou non) la baseline triviale sur CES données.
    maes_model, maes_naive = [], []
    for z in C.ZONES:
        s = (df[df.zone == z].sort_values("step").attendance
             / C.ZONE_CAPACITY[z]).to_numpy()
        t0 = C.TOTAL_STEPS - C.STEPS_PER_DAY
        for t in range(t0, C.TOTAL_STEPS - C.HORIZON, 4):
            truth = s[t:t + C.HORIZON]
            maes_model.append(np.abs(fc.forecast(s[:t]) - truth).mean())
            maes_naive.append(np.abs(fc._seasonal_naive(
                np.asarray(s[:t], dtype=np.float32)[-fc.context:]) - truth).mean())
    m_model, m_naive = float(np.mean(maes_model)), float(np.mean(maes_naive))
    print(f"MAE dernier jour — {fc.backend:28s} : {m_model:.4f} (frac. capacité)")
    print(f"MAE dernier jour — baseline saisonnière-naïve : {m_naive:.4f}")
    if fc.model is not None:
        verdict = ("TimesFM BAT la baseline" if m_model < m_naive - 1e-4 else
                   "TimesFM ≈ baseline (pas d'avantage net sur ces données — "
                   "limite honnête à mentionner)")
        print(f"-> {verdict}  (écart {m_naive - m_model:+.4f})")
