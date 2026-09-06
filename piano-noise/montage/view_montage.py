#!/usr/bin/env python3
"""Visualise a NIRx montage (Standard_probeInfo.mat) in 2-D and 3-D.

Works on montages built by make_montage.py and on NIRSite exports, e.g.
    python view_montage.py out/PianoNoise/Standard_probeInfo.mat
    python view_montage.py "~/nirs/Configurations/Montages/DLPFCACC/Standard_probeInfo.mat"
    python view_montage.py out/PianoNoise/Standard_probeInfo.mat --save montage.png
    python view_montage.py a.mat b.mat            # several montages side by side

Left panel: NIRSite-style top view with unused 10-10 labels greyed out.
Right panel: 3-D scalp view (drag to rotate, scroll to zoom); --view sets the
initial elevation,azimuth. Channel colour encodes source-detector distance.

Requires numpy, scipy, matplotlib.
"""
import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def load_mat(path):
    """Read a Standard_probeInfo.mat into a plain dict (cm units, as stored)."""
    from scipy.io import loadmat
    p = loadmat(path)["probeInfo"][0, 0]["probes"][0, 0]

    def labels(key, n):
        arr = p[key]
        out = [str(x[0]) if getattr(x, "size", 0) else "" for x in arr.flat] if arr.size else []
        return out if len(out) == n else [f"{key[-1].upper()}{i + 1}" for i in range(n)]

    nS, nD = int(p["nSource0"].item()), int(p["nDetector0"].item())
    return {
        "name": os.path.basename(os.path.dirname(os.path.abspath(path))) or path,
        "sources": labels("labels_s", nS), "detectors": labels("labels_d", nD),
        "s3": p["coords_s3"], "d3": p["coords_d3"], "s2": p["coords_s2"], "d2": p["coords_d2"],
        "index_c": p["index_c"].astype(int),
    }


def from_build(m):
    """Adapter for the dict returned by make_montage.build()."""
    return {k: m[k] for k in ("name", "sources", "detectors", "s3", "d3", "s2", "d2")} | {"index_c": m["index_c"].astype(int)}


def _distances(m):
    return np.array([np.linalg.norm(m["s3"][i - 1] - m["d3"][j - 1]) * 10 for i, j in m["index_c"]])


def _background_labels():
    try:
        import make_montage
        return make_montage.load_positions()
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
def draw_2d(ax, m, show_numbers=True):
    import matplotlib.pyplot as plt
    from matplotlib import cm
    dist = _distances(m)
    norm = plt.Normalize(25, 45)
    ax.add_patch(plt.Circle((0, 0), 1.0, fill=False, color="0.6"))
    ax.plot([0, -0.08, 0.08, 0], [1.0, 1.06, 1.06, 1.0], color="0.6")
    ax.plot([-1.0, -1.06, -1.0], [0.08, 0, -0.08], color="0.6"); ax.plot([1.0, 1.06, 1.0], [0.08, 0, -0.08], color="0.6")
    used = set(m["sources"]) | set(m["detectors"])
    used_xy = np.vstack([m["s2"], m["d2"]])
    for l, p in _background_labels().items():
        if l not in used and np.linalg.norm(p["c2"]) < 1.02 and np.linalg.norm(used_xy - p["c2"], axis=1).min() > 0.09:
            ax.text(p["c2"][0], p["c2"][1], l, ha="center", va="center", fontsize=6, color="0.6")
    for k, (i, j) in enumerate(m["index_c"]):
        a, b = m["s2"][i - 1], m["d2"][j - 1]
        ax.plot([a[0], b[0]], [a[1], b[1]], color=cm.viridis(norm(dist[k])), lw=3, zorder=1)
        if show_numbers:
            ax.text(*((a + b) / 2), str(k + 1), fontsize=6, ha="center", va="center", color="#333", zorder=2,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))
    for i, (p, l) in enumerate(zip(m["s2"], m["sources"])):
        ax.add_patch(plt.Circle(p, 0.045, color="#d62728", zorder=3))
        ax.text(p[0], p[1], f"S{i + 1}\n{l}", ha="center", va="center", fontsize=6.5, color="white", zorder=4)
    for j, (p, l) in enumerate(zip(m["d2"], m["detectors"])):
        ax.add_patch(plt.Circle(p, 0.045, color="#1f77b4", zorder=3))
        ax.text(p[0], p[1], f"D{j + 1}\n{l}", ha="center", va="center", fontsize=6.5, color="white", zorder=4)
    ax.set_aspect("equal"); ax.set_xlim(-1.15, 1.15); ax.set_ylim(-1.15, 1.15); ax.axis("off")
    ax.set_title(f"{m['name']}: {len(m['sources'])}S x {len(m['detectors'])}D, {len(m['index_c'])} channels "
                 f"({dist.min():.0f}-{dist.max():.0f} mm)", fontsize=10)


def draw_3d(ax, m, view=(35, -60)):
    import matplotlib.pyplot as plt
    from matplotlib import cm
    dist = _distances(m)
    norm = plt.Normalize(25, 45)
    # head: sphere least-squares fitted to the 10-10 positions (cm)
    bg = _background_labels()
    pts = np.array([p["c3"] for p in bg.values()]) if bg else np.vstack([m["s3"], m["d3"]])
    A = np.column_stack([2 * pts, np.ones(len(pts))])
    coef, *_ = np.linalg.lstsq(A, (pts ** 2).sum(1), rcond=None)   # 2c.x + (r^2 - |c|^2) = |x|^2
    center = coef[:3]
    radii = np.full(3, np.sqrt(coef[3] + center @ center))
    u, v = np.mgrid[0:2 * np.pi:40j, 0:np.pi:20j]
    hx = center[0] + radii[0] * np.cos(u) * np.sin(v)
    hy = center[1] + radii[1] * np.sin(u) * np.sin(v)
    hz = center[2] + radii[2] * np.cos(v)
    ax.plot_surface(hx, hy, hz, color="0.92", alpha=0.3, linewidth=0, shade=True)
    ax.plot_wireframe(hx, hy, hz, color="0.8", linewidth=0.3, rstride=4, cstride=4, alpha=0.5)
    if bg:
        ax.scatter(pts[:, 0], pts[:, 1], pts[:, 2], s=3, color="0.6", alpha=0.6, depthshade=False)
    for k, (i, j) in enumerate(m["index_c"]):
        a, b = m["s3"][i - 1], m["d3"][j - 1]
        ax.plot([a[0], b[0]], [a[1], b[1]], [a[2], b[2]], color=cm.viridis(norm(dist[k])), lw=2.5)
    s, d = m["s3"], m["d3"]
    ax.scatter(s[:, 0], s[:, 1], s[:, 2], s=70, color="#d62728", depthshade=False, label="source")
    ax.scatter(d[:, 0], d[:, 1], d[:, 2], s=70, color="#1f77b4", depthshade=False, label="detector")
    for i, (p, l) in enumerate(zip(s, m["sources"])):
        ax.text(p[0], p[1], p[2] + 0.4, l, fontsize=6, ha="center", color="#7a1010")
    for j, (p, l) in enumerate(zip(d, m["detectors"])):
        ax.text(p[0], p[1], p[2] + 0.4, l, fontsize=6, ha="center", color="#0d4a7a")
    ax.set_box_aspect((1, 1.2, 1)); ax.set_xlim(-10, 10); ax.set_ylim(-11, 11); ax.set_zlim(-8, 12)
    ax.set_xlabel("x (cm, right)"); ax.set_ylabel("y (anterior)"); ax.set_zlabel("z")
    ax.view_init(elev=view[0], azim=view[1]); ax.legend(loc="upper left", fontsize=7)
    ax.set_title("3-D (drag to rotate)", fontsize=10)


def figure(montages, view=(35, -60), numbers=True):
    import matplotlib.pyplot as plt
    n = len(montages)
    fig = plt.figure(figsize=(15, 7 * n))
    for r, m in enumerate(montages):
        draw_2d(fig.add_subplot(n, 2, 2 * r + 1), m, show_numbers=numbers)
        draw_3d(fig.add_subplot(n, 2, 2 * r + 2, projection="3d"), m, view=view)
    fig.tight_layout()
    return fig


def save_png(m, path, dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = figure([m])
    fig.savefig(path, dpi=dpi); plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mat", nargs="+", help="Standard_probeInfo.mat file(s)")
    p.add_argument("--save", default=None, help="write a PNG instead of opening a window")
    p.add_argument("--view", default="35,-60", help="initial 3-D elevation,azimuth")
    p.add_argument("--no-numbers", action="store_true", help="hide channel numbers in the 2-D view")
    p.add_argument("--table", action="store_true", help="also print the channel table")
    a = p.parse_args()
    view = tuple(float(x) for x in a.view.split(","))
    montages = [load_mat(os.path.expanduser(f)) for f in a.mat]
    if a.table:
        for m in montages:
            dist = _distances(m)
            print(m["name"])
            for k, (i, j) in enumerate(m["index_c"]):
                print(f"  ch{k + 1:2d}  S{i:02d}-D{j:02d}  {m['sources'][i - 1]:>4s}-{m['detectors'][j - 1]:<4s} {dist[k]:5.1f} mm")
    if a.save:
        import matplotlib
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = figure(montages, view=view, numbers=not a.no_numbers)
    if a.save:
        fig.savefig(a.save, dpi=150); print(f"saved {a.save}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
