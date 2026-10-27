"""Block-design schematic for the report.

Draws the nominal protocol -- a 60 s baseline followed by 6 alternations of a
play block and a rest block -- for a QUIET and a NOISE run. This is a
schematic of the design, not the executed timings: the real play blocks were
jittered (40 +/- 8 s, executed 32.1-46.1 s) and are reported in the text.

    python scripts/plot_block_design.py

Writes report/figures/block_design.pdf.
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "report", "figures", "block_design.pdf")

BASELINE_S = 60.0
PLAY_S = 40.0
REST_S = 30.0
N_BLOCKS = 6

RUNS = [("QUIET", "#4878cf"), ("NOISE", "#c44e52")]

C_REST = "#e4e4e4"
C_BASE = "#c4c4c4"
C_TEXT = "#333333"
HEIGHT = 0.52
PAD = 0.018  # rounding radius, in data units of the y axis


def block(ax, x, width, y, colour, label=None, textcolour="white"):
    """A rounded bar centred on y, plus an optional label inside it."""
    ax.add_patch(FancyBboxPatch(
        (x, y - HEIGHT / 2), width, HEIGHT,
        boxstyle="round,pad=0,rounding_size=%f" % (PAD * 260),
        facecolor=colour, edgecolor="none", mutation_aspect=1 / 260,
    ))
    if label:
        ax.text(x + width / 2, y, label, ha="center", va="center",
                fontsize=7.5, color=textcolour, fontweight="medium")


def brace(ax, x0, x1, y, label):
    """A dimension line under a block, annotating its duration."""
    ax.annotate("", xy=(x0, y), xytext=(x1, y),
                arrowprops=dict(arrowstyle="<->", color=C_TEXT, lw=0.7,
                                shrinkA=0, shrinkB=0))
    ax.text((x0 + x1) / 2, y - 0.13, label, ha="center", va="top",
            fontsize=7.5, color=C_TEXT)


def main():
    fig, ax = plt.subplots(figsize=(7.2, 2.0))

    for i, (name, colour) in enumerate(RUNS):
        y = len(RUNS) - 1 - i
        first = i == 0  # name the block types once, on the top run only
        block(ax, 0, BASELINE_S, y, C_BASE,
              "baseline" if first else None, C_TEXT)
        t = BASELINE_S
        for j in range(N_BLOCKS):
            block(ax, t, PLAY_S, y, colour,
                  "play" if first and j == 0 else None)
            t += PLAY_S
            block(ax, t, REST_S, y, C_REST,
                  "rest" if first and j == 0 else None, C_TEXT)
            t += REST_S
    total = BASELINE_S + N_BLOCKS * (PLAY_S + REST_S)

    # duration annotations under the lower run
    y_dim = -0.62
    brace(ax, 0, BASELINE_S, y_dim, "60 s")
    brace(ax, BASELINE_S, BASELINE_S + PLAY_S, y_dim, "40 s")
    brace(ax, BASELINE_S + PLAY_S, BASELINE_S + PLAY_S + REST_S, y_dim,
          "30 s")
    ax.text(total, y_dim - 0.13, "× 6 blocks", ha="right", va="top",
            fontsize=7.5, color=C_TEXT, style="italic")

    for i, (name, _) in enumerate(RUNS):
        ax.text(-14, len(RUNS) - 1 - i, name, ha="right", va="center",
                fontsize=9, color=C_TEXT)

    ax.set_xlim(-16, total + 2)
    ax.set_ylim(-1.15, len(RUNS) - 0.4)
    ax.axis("off")

    fig.tight_layout()
    fig.savefig(OUT, bbox_inches="tight")
    print("wrote %s" % OUT)


if __name__ == "__main__":
    main()
