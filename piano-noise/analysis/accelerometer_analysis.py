#!/usr/bin/env python3
"""Head-motion analysis from the Aurora IMU (aux) channels of the SNIRF files.

The NIRSport2 writes a 6-axis IMU alongside the fNIRS data: ACCEL_X/Y/Z (m/s^2)
and GYRO_X/Y/Z (rad/s), sampled at ~99 Hz (the fNIRS itself is 12.2 Hz). This
script turns those six channels into head-motion measures, epochs them on the
block markers (20 = PLAY_QUIET, 21 = PLAY_NOISE, 30 = REST) and asks the
question the piano-in-noise design cares about: does the subject move their
head more while playing in NOISE (pink noise from a loudspeaker behind and to
the left of the player) than in QUIET?

    python analysis/accelerometer_analysis.py                 # all four runs
    python analysis/accelerometer_analysis.py --format pdf png
    python analysis/accelerometer_analysis.py --files data/noise_1.snirf
    python analysis/accelerometer_analysis.py --show          # interactive

Outputs (into report/figures/ and report/, override with --outdir/--figdir):
    head_motion_timeline.pdf      motion index + head angles per run, blocks shaded
    head_motion_orientation.pdf   3D path through orientation space, whole run
    head_motion_epoch_paths.pdf   the same path cut into one panel per block
    head_motion_epochs.pdf        onset-locked average + per-block metric spread
    head_motion_metrics.csv       one row per epoch (the numbers behind the plots)

What is and is not trustworthy
------------------------------
Orientation is tracked with a complementary filter: gyro integration for the
fast changes, gravity from the accelerometer as a slow tilt reference. Pitch
and roll are therefore drift-free (gravity pins them). Yaw is not observable
without a magnetometer, so it is gyro-only: the bias is removed up front from
the still samples, but slow yaw drift over a 10-minute run is expected and yaw
should be read for its fast excursions, not its absolute value.

There is deliberately no x/y/z position track here. Double-integrating a 1 mm/s^2
accelerometer gives metres of drift within a block, so a "head path" in space
would be a picture of the integration error, not of the head. The path plotted
instead is the genuine one the IMU can measure: the trajectory through
orientation space (yaw, pitch, roll).
"""

import argparse
import os

import h5py
import numpy as np
from scipy import signal, stats

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEFAULT_FILES = ["quiet_1.snirf", "quiet_2.snirf", "noise_1.snirf", "noise_2.snirf"]

# Trigger codes (scripts/triggers.py)
PLAY_QUIET, PLAY_NOISE, REST, RUN_START, RUN_REST = "20", "21", "30", "11", "40"

# Same palette as scripts/plot_block_design.py so the report reads as one set.
C_QUIET = "#4878cf"
C_NOISE = "#c44e52"
C_REST = "#9a9a9a"
C_TEXT = "#333333"
COND_COLOUR = {"QUIET": C_QUIET, "NOISE": C_NOISE, "rest": C_REST}
COND_LABEL = {"QUIET": "play (QUIET)", "NOISE": "play (NOISE)", "rest": "rest"}

G = 9.80665
HP_HZ = 0.3      # below this is posture/drift, not movement
SMOOTH_S = 0.5   # envelope smoothing for the displayed motion index
TAU_TILT = 3.0   # complementary-filter time constant, s


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def _aux_by_name(nirs):
    out = {}
    for key in nirs:
        if not key.startswith("aux"):
            continue
        name = nirs[key]["name"][()]
        name = name.decode() if isinstance(name, bytes) else str(name)
        out[name.strip()] = nirs[key]
    return out


def _stim_by_name(nirs):
    out = {}
    for key in nirs:
        if not key.startswith("stim"):
            continue
        name = nirs[key]["name"][()]
        name = name.decode() if isinstance(name, bytes) else str(name)
        onsets = np.asarray(nirs[key]["data"])[:, 0]
        out[name.strip()] = np.sort(onsets)
    return out


def load_run(path):
    """Read one SNIRF into {name, t, accel, gyro, fs, stim, epochs}."""
    with h5py.File(path, "r") as f:
        nirs = f["nirs"]
        aux = _aux_by_name(nirs)
        missing = [c for c in ("ACCEL_X", "ACCEL_Y", "ACCEL_Z",
                               "GYRO_X", "GYRO_Y", "GYRO_Z") if c not in aux]
        if missing:
            raise ValueError(f"{os.path.basename(path)}: no IMU aux channels ({missing})")
        t = np.asarray(aux["ACCEL_X"]["time"], float)
        accel = np.stack([np.asarray(aux[f"ACCEL_{a}"]["dataTimeSeries"])[:, 0]
                          for a in "XYZ"], axis=1)
        gyro = np.stack([np.asarray(aux[f"GYRO_{a}"]["dataTimeSeries"])[:, 0]
                         for a in "XYZ"], axis=1)
        stim = _stim_by_name(nirs)

    run = {
        "name": os.path.splitext(os.path.basename(path))[0],
        "path": path,
        "t": t,
        "accel": accel,
        "gyro": gyro,
        "fs": 1.0 / float(np.median(np.diff(t))),
        "stim": stim,
        "t0": float(stim[RUN_START][0]) if RUN_START in stim else float(t[0]),
    }
    run["epochs"] = build_epochs(stim)
    return run


def build_epochs(stim):
    """Play and rest epochs with their real durations (Aurora writes 10 s for all).

    A play block runs from its 20/21 marker to the next REST marker; a rest
    block runs from its REST marker to the next play marker, or to RUN_REST /
    the end of the last rest if it is the final one.
    """
    plays = [(float(o), "QUIET") for o in stim.get(PLAY_QUIET, [])]
    plays += [(float(o), "NOISE") for o in stim.get(PLAY_NOISE, [])]
    plays.sort()
    rests = [float(o) for o in stim.get(REST, [])]
    ends = sorted(rests + [float(o) for o in stim.get(RUN_REST, [])])

    epochs = []
    for i, (onset, cond) in enumerate(plays):
        after = [r for r in rests if r > onset]
        if not after:
            continue
        epochs.append({"cond": cond, "block": i + 1,
                       "onset": onset, "offset": after[0]})
    for i, onset in enumerate(rests):
        after = [p for p, _ in plays if p > onset] + [e for e in ends if e > onset]
        if not after:
            continue
        epochs.append({"cond": "rest", "block": i + 1,
                       "onset": onset, "offset": min(after)})
    epochs.sort(key=lambda e: e["onset"])
    for e in epochs:
        e["duration"] = e["offset"] - e["onset"]
    return epochs


# --------------------------------------------------------------------------- #
# motion measures
# --------------------------------------------------------------------------- #
def gyro_bias(accel, gyro, fs):
    """Per-axis gyro offset, taken as the median over the still samples.

    Still = gravity-only accelerometer reading and angular speed in the lowest
    quartile. Removing this matters: an uncorrected 0.01 rad/s offset is 0.6
    deg/s, i.e. hundreds of degrees of phantom yaw over a 10-minute run.
    """
    speed = np.linalg.norm(gyro, axis=1)
    still = (np.abs(np.linalg.norm(accel, axis=1) - G) < 0.3) & \
            (speed < np.percentile(speed, 25))
    if still.sum() < fs:  # pathological run: fall back to the whole recording
        still = np.ones(len(gyro), bool)
    return np.median(gyro[still], axis=0)


def motion_index(accel, fs):
    """Movement energy in m/s^2: norm of the high-passed accelerometer, smoothed.

    High-passing at HP_HZ removes gravity and slow posture changes, so what is
    left is the head actually accelerating.
    """
    sos = signal.butter(4, HP_HZ, "highpass", fs=fs, output="sos")
    hp = signal.sosfiltfilt(sos, accel, axis=0)
    mag = np.linalg.norm(hp, axis=1)
    win = max(3, int(round(SMOOTH_S * fs)) | 1)
    kernel = np.ones(win) / win
    return np.convolve(mag, kernel, mode="same"), mag


def _rodrigues(w, dt):
    """Rotation matrix for turning at angular velocity w (rad/s) for dt seconds."""
    theta = np.linalg.norm(w) * dt
    if theta < 1e-12:
        return np.eye(3)
    k = w / np.linalg.norm(w)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(theta) * K + (1 - np.cos(theta)) * (K @ K)


def orientation(t, accel, gyro, fs, tau=TAU_TILT):
    """Complementary filter -> sensor-to-world rotation per sample.

    World z is up. Gyro integration carries the fast rotation; the gravity
    direction from a low-passed accelerometer is folded back in with time
    constant `tau` to keep pitch and roll from drifting.
    """
    sos = signal.butter(2, 0.5, "lowpass", fs=fs, output="sos")
    a_lp = signal.sosfiltfilt(sos, accel, axis=0)
    up_meas = a_lp / np.linalg.norm(a_lp, axis=1, keepdims=True)

    # Initial pose: only the tilt is known, so rotate the measured up onto world z.
    R = _align(up_meas[0], np.array([0.0, 0.0, 1.0]))
    out = np.empty((len(t), 3, 3))
    out[0] = R
    dts = np.diff(t)
    for i, dt in enumerate(dts, start=1):
        R = R @ _rodrigues(gyro[i], dt)
        up_pred = R.T @ np.array([0.0, 0.0, 1.0])      # where "up" should be, sensor frame
        corr = _align(up_meas[i], up_pred)             # error between measured and predicted
        R = R @ _slerp_to_identity(corr, min(1.0, dt / tau))
        out[i] = _orthonormalise(R)
    return out


def _align(v_from, v_to):
    """Smallest rotation taking unit vector v_from onto unit vector v_to."""
    v = np.cross(v_from, v_to)
    c = float(np.dot(v_from, v_to))
    s = float(np.linalg.norm(v))
    if s < 1e-12:
        return np.eye(3) if c > 0 else -np.eye(3)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K * ((1 - c) / (s ** 2))


def _slerp_to_identity(R, frac):
    """A fraction `frac` of the rotation R (frac=0 -> identity, 1 -> R)."""
    c = (np.trace(R) - 1) / 2
    theta = np.arccos(np.clip(c, -1, 1))
    if theta < 1e-9:
        return np.eye(3)
    axis = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    axis /= (2 * np.sin(theta))
    return _rodrigues(axis, theta * frac)


def _orthonormalise(R):
    u, _, vt = np.linalg.svd(R)
    return u @ vt


def euler_yxz(R):
    """Yaw / pitch / roll in degrees, relative to the first sample.

    Angles are only used for display and for peak-to-peak ranges, so the exact
    convention matters less than that they are continuous and small.
    """
    R0 = R[0].T
    Rr = np.einsum("ij,njk->nik", R0, R)
    yaw = np.degrees(np.arctan2(Rr[:, 1, 0], Rr[:, 0, 0]))
    pitch = np.degrees(-np.arcsin(np.clip(Rr[:, 2, 0], -1, 1)))
    roll = np.degrees(np.arctan2(Rr[:, 2, 1], Rr[:, 2, 2]))
    return (np.degrees(np.unwrap(np.radians(yaw))),
            np.degrees(np.unwrap(np.radians(pitch))),
            np.degrees(np.unwrap(np.radians(roll))))


def analyse(run):
    """Add derived traces to a loaded run, in place."""
    fs, t = run["fs"], run["t"]
    bias = gyro_bias(run["accel"], run["gyro"], fs)
    gyro = run["gyro"] - bias
    run["gyro_corrected"] = gyro
    run["gyro_bias_dps"] = np.degrees(bias)
    run["ang_speed"] = np.degrees(np.linalg.norm(gyro, axis=1))
    run["motion"], run["motion_raw"] = motion_index(run["accel"], fs)
    R = orientation(t, run["accel"], gyro, fs)
    run["R"] = R
    run["yaw"], run["pitch"], run["roll"] = euler_yxz(R)
    run["thresh"] = rest_threshold(run)
    return run


def rest_threshold(run, k=5.0):
    """"Moving" means: above what this subject does while resting in this run.

    Taken from the rest epochs rather than the whole run, so the play blocks --
    which are most of the interesting signal -- do not raise their own bar.
    """
    t = run["t"]
    m = np.zeros(len(t), bool)
    for e in run["epochs"]:
        if e["cond"] == "rest":
            m |= (t >= e["onset"]) & (t < e["offset"])
    if m.sum() < run["fs"]:
        m = np.ones(len(t), bool)
    ref = run["motion"][m]
    med = np.median(ref)
    return float(med + k * 1.4826 * np.median(np.abs(ref - med)))


# --------------------------------------------------------------------------- #
# per-epoch metrics
# --------------------------------------------------------------------------- #
def epoch_metrics(run):
    t, fs = run["t"], run["fs"]
    rows = []
    for e in run["epochs"]:
        m = (t >= e["onset"]) & (t < e["offset"])
        if m.sum() < fs:
            continue
        motion = run["motion"][m]
        above = motion > run["thresh"]
        # count contiguous supra-threshold runs as one movement event each
        n_events = int(np.sum(np.diff(above.astype(int)) == 1) + (1 if above[0] else 0))
        rows.append({
            "run": run["name"],
            "condition": e["cond"],
            "block": e["block"],
            "onset_s": round(e["onset"], 2),
            "duration_s": round(e["duration"], 2),
            "accel_rms": float(np.sqrt(np.mean(run["motion_raw"][m] ** 2))),
            "accel_p95": float(np.percentile(motion, 95)),
            "ang_speed_mean": float(np.mean(run["ang_speed"][m])),
            "ang_speed_p95": float(np.percentile(run["ang_speed"][m], 95)),
            "rotation_deg": float(np.trapezoid(run["ang_speed"][m], t[m])),
            "rotation_deg_per_s": float(np.trapezoid(run["ang_speed"][m], t[m]) / e["duration"]),
            "yaw_range": float(np.ptp(run["yaw"][m])),
            "pitch_range": float(np.ptp(run["pitch"][m])),
            "roll_range": float(np.ptp(run["roll"][m])),
            "pct_time_moving": float(100 * above.mean()),
            "n_motion_events_per_min": float(60 * n_events / e["duration"]),
        })
    return rows


METRICS = [
    ("accel_rms", "accel. RMS (m/s$^2$)"),
    ("ang_speed_mean", "angular speed (deg/s)"),
    ("n_motion_events_per_min", "motion events (/min)"),
    ("pitch_range", "pitch range (deg)"),
    ("yaw_range", "yaw range (deg)"),
    ("pct_time_moving", "time moving (%)"),
]


def compare(rows, a="QUIET", b="NOISE"):
    """Mann-Whitney U per metric between two conditions (blocks are the unit)."""
    out = []
    for key, label in METRICS:
        xa = np.array([r[key] for r in rows if r["condition"] == a])
        xb = np.array([r[key] for r in rows if r["condition"] == b])
        if len(xa) < 3 or len(xb) < 3:
            continue
        u, p = stats.mannwhitneyu(xa, xb, alternative="two-sided")
        # rank-biserial: +1 means b always larger
        rbc = 2 * u / (len(xa) * len(xb)) - 1
        out.append({"metric": key, "label": label,
                    "n_a": len(xa), "n_b": len(xb),
                    "median_a": float(np.median(xa)), "median_b": float(np.median(xb)),
                    "U": float(u), "p": float(p), "rank_biserial": float(-rbc)})
    return out


# --------------------------------------------------------------------------- #
# plotting
# --------------------------------------------------------------------------- #
def _style():
    plt.rcParams.update({
        "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8.5,
        "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7.5,
        "axes.edgecolor": "#999999", "axes.labelcolor": C_TEXT,
        "text.color": C_TEXT, "xtick.color": "#666666", "ytick.color": "#666666",
        "axes.spines.top": False, "axes.spines.right": False,
        "figure.facecolor": "white", "savefig.facecolor": "white",
    })


def _shade_blocks(ax, run, t0):
    for e in run["epochs"]:
        if e["cond"] == "rest":
            continue
        ax.axvspan(e["onset"] - t0, e["offset"] - t0,
                   color=COND_COLOUR[e["cond"]], alpha=0.16, lw=0)


ANGLE_TRACES = (("pitch", "pitch", "#333333"),
                ("roll", "roll", "#7f7f7f"),
                ("yaw", "yaw (gyro only, drifts)", "#c0c0c0"))


def _legend(fig, conds=("QUIET", "NOISE", "rest"), extra=()):
    handles = [Line2D([], [], color=COND_COLOUR[c], lw=3, alpha=0.85,
                      label=COND_LABEL[c]) for c in conds]
    handles += list(extra)
    if fig.get_layout_engine() is not None:  # constrained layout reserves the room
        fig.legend(handles=handles, loc="outside lower center",
                   ncol=len(handles), frameon=False)
    else:
        fig.legend(handles=handles, loc="lower center", ncol=len(handles),
                   frameon=False, bbox_to_anchor=(0.5, 0.0))


def fig_timeline(runs, path):
    """Motion index and head angles over each whole run, with blocks shaded."""
    _style()
    fig, axes = plt.subplots(2 * len(runs), 1, figsize=(7.4, 2.05 * len(runs)),
                             layout="constrained")
    for i, run in enumerate(runs):
        t0 = run["t0"]
        t = run["t"] - t0
        ax = axes[2 * i]
        _shade_blocks(ax, run, t0)
        ax.plot(t, run["motion"], color="#333333", lw=0.5)
        ax.axhline(run["thresh"], color="#c44e52", lw=0.6, ls=(0, (3, 2)))
        ax.set_ylabel("motion\n(m/s$^2$)")
        ax.set_title(f"{run['name']}  ({run['fs']:.0f} Hz IMU, "
                     f"{len([e for e in run['epochs'] if e['cond'] != 'rest'])} blocks)",
                     loc="left", pad=2)
        ax.set_xlim(t[0], t[-1])

        ax = axes[2 * i + 1]
        _shade_blocks(ax, run, t0)
        for trace, _, colour in ANGLE_TRACES:
            ax.plot(t, run[trace], color=colour, lw=0.7)
        ax.set_ylabel("angle\n(deg)")
        ax.set_xlim(t[0], t[-1])
    for ax in axes[:-1]:
        ax.tick_params(labelbottom=False)
    axes[-1].set_xlabel("time from run start (s)")
    _legend(fig, ("QUIET", "NOISE"),
            extra=[Line2D([], [], color=c, lw=1.2, label=lab)
                   for _, lab, c in ANGLE_TRACES])
    fig.suptitle("Head motion over the run; shaded = piano-playing blocks. "
                 "Dashed line = this run's resting motion threshold.",
                 fontsize=9)
    _save(fig, path)


def _smooth_path(run, mask, seconds=0.4):
    """Yaw/pitch/roll over a mask, lightly smoothed so the path reads as a path.

    Without this the plot is a scribble of 99 Hz sensor noise on top of the
    movement; the smoothing is short enough to keep every real excursion.
    """
    win = max(1, int(round(seconds * run["fs"])) | 1)
    kernel = np.ones(win) / win
    return [np.convolve(run[k][mask], kernel, mode="valid")
            for k in ("yaw", "pitch", "roll")]


def _time_coloured_path(ax, x, y, z, colour, lw=0.7):
    """Draw a 3D path that fades from pale to saturated as the block progresses."""
    from mpl_toolkits.mplot3d.art3d import Line3DCollection
    pts = np.stack([x, y, z], axis=1).reshape(-1, 1, 3)
    segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
    rgb = np.array(matplotlib.colors.to_rgb(colour))
    frac = np.linspace(0.25, 1.0, len(segs))[:, None]
    colours = np.hstack([1 - frac * (1 - rgb[None, :]), np.full((len(segs), 1), 0.9)])
    ax.add_collection(Line3DCollection(segs, colors=colours, linewidths=lw))


def _orientation_axes(ax):
    ax.set_xlabel("yaw (deg)", labelpad=-2)
    ax.set_ylabel("pitch (deg)", labelpad=-2)
    ax.set_zlabel("roll (deg)", labelpad=-4)
    ax.tick_params(pad=-1)
    ax.grid(True, color="#dddddd", lw=0.4)
    for pane in (ax.xaxis, ax.yaxis, ax.zaxis):
        pane.pane.set_facecolor("white")
        pane.pane.set_edgecolor("#dddddd")


def fig_orientation(runs, path):
    """The whole-run trajectory through orientation space, coloured by block."""
    _style()
    fig = plt.figure(figsize=(7.4, 6.6))
    for i, run in enumerate(runs):
        ax = fig.add_subplot(2, 2, i + 1, projection="3d")
        t = run["t"]
        whole = _smooth_path(run, np.ones(len(t), bool))
        ax.plot(*whole, color="#e0e0e0", lw=0.4, zorder=1)
        for e in run["epochs"]:
            m = (t >= e["onset"]) & (t < e["offset"])
            ax.plot(*_smooth_path(run, m), color=COND_COLOUR[e["cond"]], lw=0.6,
                    alpha=0.5 if e["cond"] == "rest" else 0.9, zorder=2)
        ax.scatter(run["yaw"][0], run["pitch"][0], run["roll"][0],
                   s=18, color="#222222", zorder=3)
        ax.set_title(run["name"], loc="left", pad=0)
        _orientation_axes(ax)
        ax.view_init(elev=22, azim=-58)
    _legend(fig)
    fig.suptitle("Head path through orientation space (yaw drifts; pitch/roll are gravity-referenced)",
                 y=0.985, fontsize=9)
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    _save(fig, path)


def fig_epoch_paths(runs, path):
    """The same 3D path, cut into one panel per play block, onset at the origin."""
    _style()
    ncol = max(len([e for e in r["epochs"] if e["cond"] != "rest"]) for r in runs)
    fig = plt.figure(figsize=(1.45 * ncol, 1.75 * len(runs)))
    for i, run in enumerate(runs):
        t = run["t"]
        plays = [e for e in run["epochs"] if e["cond"] != "rest"]
        for j, e in enumerate(plays):
            ax = fig.add_subplot(len(runs), ncol, i * ncol + j + 1, projection="3d")
            m = (t >= e["onset"]) & (t < e["offset"])
            y, p, r = _smooth_path(run, m)
            y, p, r = y - y[0], p - p[0], r - r[0]
            _time_coloured_path(ax, y, p, r, COND_COLOUR[e["cond"]])
            ax.scatter([0], [0], [0], s=8, color="#222222")
            lim = max(3.0, np.abs(np.concatenate([y, p, r])).max() * 1.05)
            ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_zlim(-lim, lim)
            ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])
            ax.set_title(f"block {e['block']}  ±{lim:.0f}°" if i == 0 else f"±{lim:.0f}°",
                         fontsize=6.5, pad=-6)
            for pane in (ax.xaxis, ax.yaxis, ax.zaxis):
                pane.pane.set_facecolor("white")
                pane.pane.set_edgecolor("#e4e4e4")
            ax.grid(True, color="#eeeeee", lw=0.3)
            ax.view_init(elev=22, azim=-58)
            if j == 0:
                ax.text2D(-0.12, 0.5, run["name"], transform=ax.transAxes,
                          rotation=90, va="center", ha="center", fontsize=7.5)
    _legend(fig, ("QUIET", "NOISE"))
    fig.suptitle("Per-block head path (yaw / pitch / roll, recentred on block onset; "
                 "colour fades in from block start to block end)", y=0.99, fontsize=9)
    fig.tight_layout(rect=(0.01, 0.045, 1, 0.965))
    _save(fig, path)


def fig_epochs(runs, rows, path, pre=10.0, post=50.0):
    """Onset-locked average motion, and the per-block metric spread by condition."""
    _style()
    fig = plt.figure(figsize=(7.4, 5.4))
    gs = fig.add_gridspec(3, 3, height_ratios=[1.35, 1, 1], hspace=0.62, wspace=0.34)

    # -- onset-locked mean motion index ------------------------------------- #
    ax = fig.add_subplot(gs[0, :])
    fs_common = 50.0
    grid = np.arange(-pre, post, 1 / fs_common)
    stacks = {"QUIET": [], "NOISE": []}
    for run in runs:
        for e in run["epochs"]:
            if e["cond"] == "rest":
                continue
            trace = np.interp(e["onset"] + grid, run["t"], run["motion"],
                              left=np.nan, right=np.nan)
            stacks[e["cond"]].append(trace)
    handles = []
    for cond in ("QUIET", "NOISE"):
        traces = stacks[cond]
        if not traces:
            continue
        arr = np.vstack(traces)
        mean = np.nanmean(arr, axis=0)
        sem = np.nanstd(arr, axis=0) / np.sqrt(np.sum(~np.isnan(arr), axis=0))
        ax.fill_between(grid, mean - sem, mean + sem,
                        color=COND_COLOUR[cond], alpha=0.2, lw=0)
        ax.plot(grid, mean, color=COND_COLOUR[cond], lw=1.2)
        handles.append(Line2D([], [], color=COND_COLOUR[cond], lw=1.6,
                              label=f"{COND_LABEL[cond]} (n={len(traces)})"))
    durations = [e["duration"] for run in runs for e in run["epochs"]
                 if e["cond"] != "rest"]
    ax.axvspan(min(durations), max(durations), color="#ededed", lw=0, zorder=0)
    ax.axvline(0, color=C_TEXT, lw=0.7, ls=(0, (3, 2)))
    ax.text(np.mean(durations), ax.get_ylim()[0], "blocks end (jittered)",
            ha="center", va="bottom", fontsize=6.5, color="#888888")
    ax.set_xlim(-pre, post)
    ax.set_xlabel("time from play-block onset (s)")
    ax.set_ylabel("motion index (m/s$^2$)")
    ax.set_title("Onset-locked head motion, mean ± SEM over blocks", loc="left")
    ax.legend(handles=handles, frameon=False, loc="upper right")

    # -- per-block metric spread -------------------------------------------- #
    conds = ["rest", "QUIET", "NOISE"]
    for k, (key, label) in enumerate(METRICS):
        ax = fig.add_subplot(gs[1 + k // 3, k % 3])
        for x, cond in enumerate(conds):
            vals = np.array([r[key] for r in rows if r["condition"] == cond])
            if not len(vals):
                continue
            jitter = (np.random.default_rng(0).random(len(vals)) - 0.5) * 0.24
            ax.scatter(x + jitter, vals, s=9, color=COND_COLOUR[cond],
                       alpha=0.75, lw=0)
            ax.hlines(np.median(vals), x - 0.26, x + 0.26,
                      color=COND_COLOUR[cond], lw=1.6)
        ax.set_xticks(range(len(conds)))
        ax.set_xticklabels([COND_LABEL[c].replace(" (", "\n(") for c in conds])
        ax.set_ylabel(label)
        ax.set_xlim(-0.5, len(conds) - 0.5)
    fig.suptitle("Head motion by block type (each dot is one block, bar = median)",
                 y=0.99, fontsize=9)
    fig.subplots_adjust(top=0.90, bottom=0.08, left=0.085, right=0.98)
    _save(fig, path)


FORMATS = ["pdf"]  # set from --format; PDF for the report, PNG to look at
DPI = 200


def _save(fig, path):
    """Write the figure once per requested format (`path` carries the stem)."""
    stem = os.path.splitext(path)[0]
    os.makedirs(os.path.dirname(stem), exist_ok=True)
    for ext in FORMATS:
        out = f"{stem}.{ext}"
        fig.savefig(out, bbox_inches="tight", dpi=DPI)
        print(f"  wrote {os.path.relpath(out, ROOT)}")


# --------------------------------------------------------------------------- #
def write_csv(rows, path):
    import csv
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v)
                        for k, v in r.items()})
    print(f"  wrote {os.path.relpath(path, ROOT)}")


def report(runs, rows):
    print("\nPer-run summary")
    print(f"  {'run':10s} {'dur':>7s} {'blocks':>7s} {'gyro bias (deg/s)':>26s} "
          f"{'moving':>8s}")
    for run in runs:
        pct = 100 * np.mean(run["motion"] > run["thresh"])
        bias = "  ".join(f"{b:+.2f}" for b in run["gyro_bias_dps"])
        n = len([e for e in run["epochs"] if e["cond"] != "rest"])
        print(f"  {run['name']:10s} {run['t'][-1]:6.0f}s {n:7d} {bias:>26s} {pct:7.1f}%")

    print("\nPer-condition medians (blocks pooled over runs)")
    conds = ["rest", "QUIET", "NOISE"]
    head = f"  {'metric':22s}" + "".join(f"{COND_LABEL[c]:>16s}" for c in conds)
    print(head)
    for key, label in METRICS:
        line = f"  {key:22s}"
        for c in conds:
            v = [r[key] for r in rows if r["condition"] == c]
            line += f"{np.median(v):16.3f}" if v else f"{'-':>16s}"
        print(line)

    print("\nQUIET vs NOISE play blocks (Mann-Whitney U on blocks)")
    print(f"  {'metric':22s} {'QUIET':>9s} {'NOISE':>9s} {'U':>7s} "
          f"{'p':>8s} {'effect':>8s}")
    for c in compare(rows, "QUIET", "NOISE"):
        star = "*" if c["p"] < 0.05 else " "
        print(f"  {c['metric']:22s} {c['median_a']:9.3f} {c['median_b']:9.3f} "
              f"{c['U']:7.1f} {c['p']:8.3f}{star} {c['rank_biserial']:+8.2f}")
    print("  effect = rank-biserial correlation, positive means more motion in NOISE")
    print("  n is small (6 blocks per run); read this as a QC/covariate check,")
    print("  not as a hypothesis test the study is powered for.")


def main():
    global FORMATS, DPI
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--files", nargs="+", default=None,
                    help="SNIRF files (default: the four session runs in data/)")
    ap.add_argument("--figdir", default=os.path.join(ROOT, "report", "figures"))
    ap.add_argument("--outdir", default=os.path.join(ROOT, "report"))
    ap.add_argument("--format", nargs="+", default=["pdf"], choices=["pdf", "png", "svg"],
                    help="figure formats to write (default: pdf)")
    ap.add_argument("--dpi", type=int, default=DPI, help="raster resolution for png")
    ap.add_argument("--show", action="store_true", help="open the figures instead of only writing them")
    args = ap.parse_args()

    FORMATS, DPI = args.format, args.dpi

    if not args.show:
        matplotlib.use("Agg")

    files = args.files or [os.path.join(ROOT, "data", f) for f in DEFAULT_FILES]
    runs = []
    for path in files:
        if not os.path.exists(path):
            print(f"  skipping {path} (not found)")
            continue
        print(f"loading {os.path.relpath(path, ROOT)} ...")
        runs.append(analyse(load_run(path)))
    if not runs:
        raise SystemExit("no input files")

    rows = [r for run in runs for r in epoch_metrics(run)]
    write_csv(rows, os.path.join(args.outdir, "head_motion_metrics.csv"))
    fig_timeline(runs, os.path.join(args.figdir, "head_motion_timeline.pdf"))
    fig_orientation(runs, os.path.join(args.figdir, "head_motion_orientation.pdf"))
    fig_epoch_paths(runs, os.path.join(args.figdir, "head_motion_epoch_paths.pdf"))
    fig_epochs(runs, rows, os.path.join(args.figdir, "head_motion_epochs.pdf"))
    report(runs, rows)
    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
