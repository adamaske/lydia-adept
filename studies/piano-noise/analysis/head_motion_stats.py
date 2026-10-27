#!/usr/bin/env python3
"""QUIET vs NOISE tests on the per-block head-motion metrics.

Reads report/head_motion_metrics.csv (written by accelerometer_analysis.py) and
asks two questions:

    1. does the subject move their head more while PLAYING in noise?
    2. does the subject move their head more while RESTING in a noise run?

Both are tested at the block level (12 blocks per condition) and, because
blocks within a run are not independent observations, again at the run level
(2 runs per condition). The run-level test is the honest unit of replication
and, with 2 vs 2 runs, cannot reach p < 0.05 -- that is reported rather than
hidden.

    python analysis/head_motion_stats.py

Writes report/head_motion_stats.csv and prints the summary.
"""

import itertools
import os

import numpy as np
import pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
METRICS = os.path.join(ROOT, "report", "head_motion_metrics.csv")
OUT = os.path.join(ROOT, "report", "head_motion_stats.csv")

# every motion metric in the CSV, tested as one family per epoch type
METRICS_COLS = [
    "accel_rms", "accel_p95", "ang_speed_mean", "ang_speed_p95",
    "rotation_deg", "rotation_deg_per_s", "yaw_range", "pitch_range",
    "roll_range", "pct_time_moving", "n_motion_events_per_min",
]
# the one headline metric, chosen because it is rate-normalised (blocks differ
# in length) and is the least derived of the rotation measures
PRIMARY = "rotation_deg_per_s"


def bh_fdr(pvals):
    """Benjamini-Hochberg adjusted p-values, same convention as the GLM."""
    p = np.asarray(pvals, dtype=float)
    n = len(p)
    order = np.argsort(p)
    adj = np.empty(n, dtype=float)
    prev = 1.0
    for rank, idx in enumerate(reversed(order), start=1):
        val = p[idx] * n / (n - rank + 1)
        prev = min(prev, val)
        adj[idx] = prev
    return adj


def rank_biserial(a, b):
    """Effect size for Mann-Whitney U: -1..1, 0 = no separation."""
    u = stats.mannwhitneyu(a, b, alternative="two-sided").statistic
    return 2.0 * u / (len(a) * len(b)) - 1.0


def exact_run_permutation(runs_q, runs_n):
    """Two-sided p from every way of splitting 4 runs into 2 + 2.

    With 2 runs per condition there are only C(4,2) = 6 assignments, so the
    smallest attainable two-sided p-value is 2/6 = 0.33.
    """
    values = list(runs_q) + list(runs_n)
    observed = abs(np.mean(runs_q) - np.mean(runs_n))
    idx = range(len(values))
    diffs = []
    for combo in itertools.combinations(idx, len(runs_q)):
        left = [values[i] for i in combo]
        right = [values[i] for i in idx if i not in combo]
        diffs.append(abs(np.mean(left) - np.mean(right)))
    diffs = np.asarray(diffs)
    return float(np.mean(diffs >= observed - 1e-12)), len(diffs)


def compare(df, epoch_label, quiet_mask, noise_mask):
    rows = []
    for col in METRICS_COLS:
        q = df.loc[quiet_mask, col].to_numpy(dtype=float)
        n = df.loc[noise_mask, col].to_numpy(dtype=float)

        u = stats.mannwhitneyu(q, n, alternative="two-sided")
        # run-level: mean of each run, then the exact 2-vs-2 permutation
        run_means = df.groupby(["run", "cond_group"])[col].mean().reset_index()
        rq = run_means.loc[run_means.cond_group == "QUIET", col].to_numpy()
        rn = run_means.loc[run_means.cond_group == "NOISE", col].to_numpy()
        p_run, n_perm = exact_run_permutation(rq, rn)

        rows.append({
            "epoch": epoch_label,
            "metric": col,
            "quiet_median": np.median(q), "noise_median": np.median(n),
            "quiet_mean": q.mean(), "noise_mean": n.mean(),
            "quiet_sd": q.std(ddof=1), "noise_sd": n.std(ddof=1),
            "pct_change": 100.0 * (n.mean() - q.mean()) / q.mean(),
            "U": u.statistic, "p_block": u.pvalue,
            "rank_biserial": rank_biserial(q, n),
            "p_run_exact": p_run, "n_perm": n_perm,
            "quiet_runs": ", ".join("%.4g" % v for v in rq),
            "noise_runs": ", ".join("%.4g" % v for v in rn),
        })
    out = pd.DataFrame(rows)
    out["q_block_fdr"] = bh_fdr(out["p_block"])
    return out


def main():
    df = pd.read_csv(METRICS)
    # the run a block belongs to, regardless of whether the epoch is play or rest
    df["cond_group"] = np.where(df["run"].str.startswith("noise"), "NOISE", "QUIET")
    df["epoch_type"] = np.where(df["condition"] == "rest", "rest", "play")

    parts = []
    for epoch in ("play", "rest"):
        sub = df[df.epoch_type == epoch]
        parts.append(compare(
            sub, epoch,
            sub.cond_group == "QUIET", sub.cond_group == "NOISE",
        ))
    res = pd.concat(parts, ignore_index=True)
    res.to_csv(OUT, index=False, float_format="%.6g")

    pd.set_option("display.width", 200, "display.max_columns", 50)
    for epoch in ("play", "rest"):
        sub = res[res.epoch == epoch]
        n_q = (df[(df.epoch_type == epoch) & (df.cond_group == "QUIET")]).shape[0]
        n_n = (df[(df.epoch_type == epoch) & (df.cond_group == "NOISE")]).shape[0]
        print("\n=== %s epochs (QUIET n=%d, NOISE n=%d blocks; 2 runs each) ==="
              % (epoch.upper(), n_q, n_n))
        show = sub[["metric", "quiet_median", "noise_median", "pct_change",
                    "rank_biserial", "p_block", "q_block_fdr", "p_run_exact"]]
        print(show.to_string(index=False, float_format=lambda v: "%.4g" % v))
        prim = sub[sub.metric == PRIMARY].iloc[0]
        print("  primary (%s): QUIET runs [%s] vs NOISE runs [%s]"
              % (PRIMARY, prim.quiet_runs, prim.noise_runs))
    print("\nwrote %s" % OUT)


if __name__ == "__main__":
    main()
