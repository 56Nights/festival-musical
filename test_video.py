"""
Test du détecteur de bousculade sur vidéo réelle.

    uv run python test_video.py --video video.mp4
    uv run python test_video.py --video video.mp4 --output annotated.mp4 --fps 5

Détection basée UNIQUEMENT sur le flux optique avancé (stampede_flow.py) :
compensation caméra + alignement des pixels mobiles + fraction mobile
+ persistance temporelle (1 s). Le CNN n'est pas utilisé ici : entraîné sur
frames synthétiques, il souffre d'un écart de domaine sur vidéo réelle
(limite documentée dans le rapport ; fine-tuning sur données réelles en
perspective).

Validation sur 3 vidéos étiquetées :
  bousculade réelle -> ALERTE | foule calme avec sursaut -> rien | danse -> rien
"""
import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np
from vision.raft_flow import RaftStampedeDetector

GREEN = (0, 200, 0)
RED   = (0, 0, 255)
GRAY  = (170, 170, 170)


def annotate(frame_bgr, result):
    vis = frame_bgr.copy()
    h, w = vis.shape[:2]
    feats = result["flow"] or {}
    alert = result["stampede_alert"]
    scale = max(0.5, w / 900)

    lines = [
        f"mag residuelle : {feats.get('res_mag', 0):.1f}",
        f"alignement     : {feats.get('alignment', 0):.2f}",
        f"fraction mobile: {feats.get('moving_frac', 0):.2f}",
        f"persistance    : {result['consecutive']}/5",
    ]
    y = int(30 * scale)
    for line in lines:
        cv2.putText(vis, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55 * scale, RED if alert else GRAY, max(1, int(scale)))
        y += int(28 * scale)

    if alert:
        cv2.rectangle(vis, (0, 0), (w - 1, h - 1), RED, max(3, int(6 * scale)))
        cv2.putText(vis, "ALERTE BOUSCULADE", (10, y + int(10 * scale)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8 * scale, RED,
                    max(2, int(2 * scale)))
    else:
        cv2.putText(vis, "Situation normale", (10, y + int(10 * scale)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6 * scale, GREEN,
                    max(1, int(scale)))
    return vis


def run(video_path, sample_fps=5, output_path=None):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Erreur : impossible d'ouvrir {video_path}")
        sys.exit(1)

    native_fps = cap.get(cv2.CAP_PROP_FPS) or 25
    skip = max(1, int(native_fps / sample_fps))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    detector = RaftStampedeDetector()
    print(f"Backend flux optique : {detector.backend}")
    writer = None
    if output_path:
        writer = cv2.VideoWriter(output_path,
                                 cv2.VideoWriter_fourcc(*"mp4v"),
                                 sample_fps, (w, h))

    frame_idx, analyzed, alert_frames = 0, 0, 0
    first_alert_t = None

    print(f"Analyse : {video_path} à {sample_fps} fps (1 frame sur {skip})")
    print("-" * 60)

    while True:
        ret, bgr = cap.read()
        if not ret:
            break
        if frame_idx % skip != 0:
            frame_idx += 1
            continue

        t = frame_idx / native_fps
        result = detector.update(bgr)
        analyzed += 1

        if result["stampede_alert"]:
            alert_frames += 1
            if first_alert_t is None:
                first_alert_t = t
            f = result["flow"]
            print(f"t={t:6.1f}s  ALERTE  mag={f['res_mag']:.1f} "
                  f"align={f['alignment']:.2f} frac={f['moving_frac']:.2f} "
                  f"persistance={result['consecutive']}")

        if writer:
            writer.write(annotate(bgr, result))
        frame_idx += 1

    cap.release()
    if writer:
        writer.release()
        print(f"\nVidéo annotée : {output_path}")

    print(f"\n{'=' * 60}")
    print(f"Frames analysées   : {analyzed}")
    print(f"Frames en alerte   : {alert_frames}")
    if first_alert_t is not None:
        print(f"Première alerte    : t={first_alert_t:.1f}s")
    else:
        print("Aucune bousculade détectée.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--video", required=True)
    p.add_argument("--fps", type=int, default=5)
    p.add_argument("--output", default=None)
    args = p.parse_args()
    run(args.video, args.fps, args.output)
