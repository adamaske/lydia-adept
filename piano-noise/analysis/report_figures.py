"""ROI-level figures and tables for the report, from the NIRWizard exports.

Reads the exported tables under analysis/ (01-qc, 04-block-average, 05-glm;
ROI membership from the laterality sidecar) and writes

  report/figures/ba_roi.pdf           ROI block averages, HbO and HbR
  report/figures/glm_maps_*.pdf       on-cortex GLM t maps, HbO + HbR
  report/figures/laterality.pdf       Seghier LI per ROI pair (GLM beta)
  report/tables/*.tex                 booktabs bodies \\input by report.tex

ROI summaries average the channels the GLM export marks good (all 47 in the
current export, which was run without QC exclusions).
"""
import csv
import json
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIG = os.path.join(ROOT, "report", "figures")
TAB = os.path.join(ROOT, "report", "tables")

# Same palette as scripts/plot_block_design.py so the report reads as one set.
COL = {"QUIET": "#4878cf", "NOISE": "#c44e52"}
C_TEXT = "#333333"
PLAY_S = 40.0

plt.rcParams.update({"font.size": 8, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.edgecolor": C_TEXT,
                     "axes.labelcolor": C_TEXT, "xtick.color": C_TEXT,
                     "ytick.color": C_TEXT, "pdf.fonttype": 42})


def table(path, sep=","):
    with open(os.path.join(HERE, path), encoding="utf-8") as f:
        return list(csv.DictReader((l for l in f if not l.startswith("#")),
                                   delimiter=sep))


def chan_key(name):
    s, d = name[1:].split("-D")
    return int(s), int(d)


def write_tex(name, header, rows):
    os.makedirs(TAB, exist_ok=True)
    with open(os.path.join(TAB, name), "w", encoding="utf-8") as f:
        f.write("\\begin{tabular}{%s}\n\\toprule\n" % header[0])
        f.write(" & ".join(header[1]) + " \\\\\n\\midrule\n")
        for r in rows:
            f.write(" & ".join(r) + " \\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n")


# ---- inputs -----------------------------------------------------------------
glm = table("05-glm/glm_results_glm_channels.csv")
good = sorted({r["channel"] for r in glm if r["status"] == "good"}, key=chan_key)
bad = sorted({r["channel"] for r in glm if r["status"] == "bad"}, key=chan_key)
glm = [r for r in glm if r["status"] == "good"]

with open(os.path.join(HERE, "05-glm", "laterality_glm_beta.json"),
          encoding="utf-8") as f:
    pairs = json.load(f)["Parameters"]["Model"]["region_pairs"]
pairs = [p for p in pairs if "|" in p["label"]]  # drop the whole-hemisphere pair
ROIS = []  # (pair label, side, roi name, all channels, good channels)
for p in pairs:
    for side in ("left", "right"):
        ch = p[side + "_channels"]
        ROIS.append((p["label"], side, p[side + "_roi"], ch,
                     [c for c in ch if c in good]))


# ---- QC ---------------------------------------------------------------------
def qc():
    runs = table("01-qc/cohort_qc_cohort_qc_runs.csv")
    names = [os.path.basename(r["file"]).replace(".snirf", "") for r in runs]
    write_tex("qc_runs.tex", ("lrrrrr", ["Run", "Duration (s)", "Bad / 47",
                                         "SCI fail", "PSP fail", "GVTD median"]),
              [[n.replace("_", "\\_"),
                "%.0f" % (int(r["n_samples"]) / float(r["sampling_rate"])),
                r["n_bad"], r["sci_n_fail"], r["psp_n_fail"],
                "%.4f" % float(r["gvtd_median"])]
               for n, r in zip(names, runs)])


# ---- block averages ---------------------------------------------------------
def block_average():
    tc = {}  # (channel, signal, condition) -> [(t, mean)]
    for r in table("04-block-average/group_block_average_group_blockavg_timecourse.csv"):
        tc.setdefault((r["channel"], r["signal"], r["condition"]), []).append(
            (float(r["time_s"]), float(r["mean"])))
    tc = {k: np.array(v) for k, v in tc.items()}

    def roi_curve(chs, sig, cond):
        n = min(len(tc[(c, sig, cond)]) for c in chs)
        t = tc[(chs[0], sig, cond)][:n, 0]
        return t, np.mean([tc[(c, sig, cond)][:n, 1] for c in chs], axis=0)

    fig, axes = plt.subplots(len(pairs), 2, figsize=(7.2, 8.4), sharex=True)
    rows = []
    for k, (label, side, name, allch, chs) in enumerate(ROIS):
        ax = axes[k // 2, k % 2]
        ax.axvspan(0, PLAY_S, color="#eeeeee", lw=0)
        ax.axhline(0, color="#999999", lw=0.5)
        cells = []
        for cond in ("QUIET", "NOISE"):
            for sig, ls in (("HbO", "-"), ("HbR", "--")):
                t, y = roi_curve(chs, sig, cond)
                ax.plot(t, y, ls, color=COL[cond], lw=1.2,
                        label="%s %s" % (cond, sig))
                w = (t >= 5) & (t <= PLAY_S)
                cells.append("%.3f" % y[w].mean())
        ax.set_title("%s (%d of %d channels)" % (name, len(chs), len(allch)),
                     fontsize=8, color=C_TEXT, loc="left")
        rows.append([name, "%d/%d" % (len(chs), len(allch))] + cells)
    for ax in axes[-1]:
        ax.set_xlabel("time from play onset (s)")
    for ax in axes[:, 0]:
        ax.set_ylabel(u"\u0394conc. (\u00b5M)")
    axes[0, 1].legend(frameon=False, fontsize=6.5, ncol=2, loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "ba_roi.pdf"))
    plt.close(fig)

    write_tex("ba_roi.tex", ("llrrrr", ["ROI", "Ch.", "QUIET HbO", "QUIET HbR",
                                        "NOISE HbO", "NOISE HbR"]), rows)


# ---- GLM --------------------------------------------------------------------
def glm_roi():
    val = {(r["channel"], r["signal"], r["effect"]): r for r in glm}
    rows = []
    for label, side, name, allch, chs in ROIS:
        cells = []
        for sig in ("HbO", "HbR"):
            for cond in ("QUIET", "NOISE"):
                d = [val[(c, sig, cond)] for c in chs]
                cells.append("%.3f" % np.mean([float(r["beta"]) for r in d]))
                cells.append("%.1f" % np.mean([float(r["t"]) for r in d]))
        rows.append([name, "%d" % len(chs)] + cells)
    write_tex("glm_roi.tex", ("lr rrrr rrrr", [
        "ROI", "$n$"] + ["$\\beta$", "$t$"] * 4), rows)

    census = []
    for eff in ("QUIET", "NOISE"):
        for sig in ("HbO", "HbR"):
            d = [r for r in glm if r["effect"] == eff and r["signal"] == sig]
            t = np.array([float(r["t"]) for r in d])
            q = np.array([float(r["q"]) for r in d])
            census.append([eff, sig,
                           "%d" % ((q < .05) & (t > 0)).sum(),
                           "%d" % ((q < .05) & (t < 0)).sum(),
                           "%d" % (np.abs(t) > 20).sum(),
                           "%.3f" % np.median([float(r["beta"]) for r in d]),
                           "%.1f to %.1f" % (t.min(), t.max())])
    write_tex("glm_census.tex", ("llrrrrr", [
        "Condition", "Signal", "$q<.05$, $t>0$", "$q<.05$, $t<0$", "$|t|>20$",
        "median $\\beta$", "$t$ range"]), census)


# ---- on-cortex GLM maps -----------------------------------------------------
VIEWS = ("left", "right", "anterior", "superior")
# (chromophore, export folder under 05-glm, colour range) per figure
MAPS = {
    "unthresholded": [("HbO", "no_thresh", 26),
                      ("HbR", "hbr_glm_images/no_thresh", 15)],
    "thresholded": [("HbO", "thresh_t>20", 26),
                    ("HbR", "hbr_glm_images/thresh_t>10", 15)],
}


def cortex(path):
    """NIRWizard cortex export as RGBA: background transparent, cropped."""
    from PIL import Image, ImageDraw, ImageFilter
    im = Image.open(path).convert("RGB").crop((0, 0, 800, 735))  # drop caption
    key = (255, 0, 255)
    for xy in ((0, 0), (799, 0), (0, 734), (799, 734)):
        ImageDraw.floodfill(im, xy, key, thresh=30)
    a = np.array(im)
    alpha = Image.fromarray(((a != key).any(2) * 255).astype(np.uint8))
    alpha = alpha.filter(ImageFilter.MinFilter(3))  # shave the dark fringe
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.7))
    rgba = np.dstack([a, np.array(alpha)])
    ys, xs = np.where(rgba[..., 3] > 0)
    return rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def glm_maps():
    from matplotlib.colors import Normalize
    for name, rows in MAPS.items():
        imgs = [[cortex(os.path.join(HERE, "05-glm", folder, "GLM",
                                     "Condition_" + cond, sig,
                                     "cond-%s-%s-%s.png" % (cond, v, sig)))
                 for v in VIEWS]
                for sig, folder, _ in rows for cond in ("QUIET", "NOISE")]
        # the exports differ slightly in zoom: bring every brain of a view to
        # the height of the first row, then size the columns by pixel width
        from PIL import Image
        for r in imgs[1:]:
            for j, im in enumerate(r):
                k = imgs[0][j].shape[0] / im.shape[0]
                if abs(k - 1) > 0.01:
                    size = (round(im.shape[1] * k), imgs[0][j].shape[0])
                    r[j] = np.array(Image.fromarray(im).resize(size, Image.LANCZOS))
        wcol = [max(r[j].shape[1] for r in imgs) for j in range(4)]
        hrow = max(i.shape[0] for r in imgs for i in r)
        fig = plt.figure(figsize=(7.2, 7.6))
        gs = fig.add_gridspec(4, 5, width_ratios=wcol + [110],
                              left=0.07, right=0.95, top=0.95, bottom=0.02,
                              wspace=0.10, hspace=0.12)
        for i, r in enumerate(imgs):
            for j, im in enumerate(r):
                ax = fig.add_subplot(gs[i, j])
                ax.imshow(im, interpolation="lanczos")
                px, py = (wcol[j] - im.shape[1]) / 2, (hrow - im.shape[0]) / 2
                ax.set_xlim(-px, im.shape[1] + px)
                ax.set_ylim(im.shape[0] + py, -py)
                ax.axis("off")
                if i == 0:
                    ax.set_title(VIEWS[j].capitalize(), fontsize=9,
                                 color=C_TEXT, pad=6)
                if j == 0:
                    sig, cond = rows[i // 2][0], ("QUIET", "NOISE")[i % 2]
                    ax.text(-0.06, 0.5, cond, transform=ax.transAxes,
                            rotation=90, ha="center", va="center", fontsize=9,
                            color=COL[cond], fontweight="bold")
        for k, (sig, _, lim) in enumerate(rows):
            box = gs[2 * k:2 * k + 2, 4].get_position(fig)
            fig.text(0.015, (box.y0 + box.y1) / 2, sig, rotation=90,
                     ha="center", va="center", fontsize=11, color=C_TEXT)
            cax = fig.add_axes([box.x0 + 0.02, box.y0 + box.height * 0.22,
                                0.016, box.height * 0.56])
            cb = fig.colorbar(plt.cm.ScalarMappable(Normalize(-lim, lim), "jet"),
                              cax=cax, ticks=[-lim, 0, lim])
            cb.outline.set_visible(False)
            cb.ax.tick_params(length=2, labelsize=7.5)
            cb.ax.set_title("$t$", fontsize=9, color=C_TEXT, pad=5)
        if len(rows) > 1:  # hairline between the chromophore blocks
            y = (gs[1, 0].get_position(fig).y0 + gs[2, 0].get_position(fig).y1) / 2
            fig.add_artist(plt.Line2D([0.04, 0.99], [y, y], color="#dddddd", lw=0.6))
        fig.savefig(os.path.join(FIG, "glm_maps_%s.pdf" % name), dpi=300)
        plt.close(fig)


# ---- laterality -------------------------------------------------------------
def laterality():
    li = table("05-glm/laterality_glm_beta_laterality_subject.csv")
    fig, ax = plt.subplots(figsize=(4.6, 2.6))
    for i, cond in enumerate(("QUIET", "NOISE")):
        for k, p in enumerate(pairs):
            r = next(r for r in li if r["roi_pair"] == p["label"] and
                     r["condition"] == cond and r["signal"] == "HbO")
            ok = r["sign_case"] == "bothPositive"
            ax.bar(k + (i - 0.5) * 0.36, float(r["li"]), 0.32, color=COL[cond],
                   alpha=0.85 if ok else 0.3, hatch=None if ok else "///",
                   label=cond if k == 0 else None)
    ax.axhline(0, color="#999999", lw=0.5)
    for y in (-0.2, 0.2):
        ax.axhline(y, color="#999999", lw=0.5, ls=":")
    ax.set_xticks(range(len(pairs)),
                  [p["left_roi"].replace("Left ", "") for p in pairs])
    ax.set_ylim(-1.05, 1.05)
    ax.set_ylabel(u"LI (HbO \u03b2)   right  \u2194  left")
    ax.legend(frameon=False, fontsize=7, loc="lower left")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "laterality.pdf"))
    plt.close(fig)


if __name__ == "__main__":
    os.makedirs(FIG, exist_ok=True)
    qc()
    block_average()
    glm_roi()
    glm_maps()
    laterality()
    for _, _, name, allch, chs in ROIS:
        print("  %-15s %d/%d  %s" % (name, len(chs), len(allch), " ".join(chs)))
