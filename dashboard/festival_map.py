"""
Lecteur HTML de la « vue simulation ».

Injecte outputs/replay.json (état du monde image par image, produit par
`simulation/replay_sim.py`) dans le gabarit `viewer_template.html` et écrit un
fichier HTML autonome : outputs/festival_map.html.

Autonome par conception : JSON en ligne, JavaScript vanilla + Canvas 2D, aucune
dépendance réseau ni CDN — lisible hors-ligne pour la soutenance.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as C

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "viewer_template.html")
MARKER = "__REPLAY_DATA__"


def build_map(replay_path=None, out_path=None):
    replay_path = replay_path or C.REPLAY_JSON
    out_path = out_path or C.FESTIVAL_MAP_HTML

    if not os.path.exists(replay_path):
        from simulation.replay_sim import build_replay
        build_replay(replay_path)

    with open(replay_path) as fh:
        replay = fh.read()
    with open(TEMPLATE, encoding="utf-8") as fh:
        template = fh.read()

    # `</script>` dans les données casserait la balise : on l'échappe.
    replay = replay.replace("</", "<\\/")
    if MARKER not in template:
        raise RuntimeError(f"marqueur {MARKER} absent du gabarit")
    html = template.replace(MARKER, replay)

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    size_mb = os.path.getsize(out_path) / 1e6
    n_frames = len(json.loads(open(replay_path).read())["frames"])
    print(f"-> vue simulation : {out_path}  "
          f"({n_frames} frames, {size_mb:.1f} Mo, autonome)")
    return out_path


if __name__ == "__main__":
    build_map()
