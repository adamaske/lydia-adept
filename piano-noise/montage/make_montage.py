#!/usr/bin/env python3
"""Build a NIRx Aurora montage (probeInfo.mat + .ncfg) directly from 10-10 labels.

Replaces the NIRSite click-through: you name the sources and detectors by
10-10 label, the script places them on the ICBM152 head (positions harvested
from NIRSite exports, see positions_icbm152.csv), derives the channels, and
writes everything Aurora needs:

    out/<name>/Standard_probeInfo.mat   what Aurora loads (montage_path in the .ncfg)
    out/<name>/Standard_Optodes.txt     optode positions, mm (NIRSite-style)
    out/<name>/Standard_Channels.txt    channel list, mm (NIRSite-style)
    out/<name>/digpts.txt               fiducials + optodes, mm (NIRSite-style)
    out/<name>/montage.png              top-view + 3-D figure (see view_montage.py for an interactive viewer)
    out/<name>.ncfg                     Aurora configuration referencing the montage

Usage:
    python make_montage.py                  # build the default PianoNoise montage
    python make_montage.py --name X --sources Fz,Cz --detectors FCz,F1  # ad hoc
    python make_montage.py --list-labels
    python make_montage.py --spec my_montage.json          # spec saved from the browser editor (editor.py)

Install on the acquisition PC: copy out/<name>/ to
    C:\\Users\\<user>\\Documents\\NIRx\\Configurations\\Montages\\<name>\\
and out/<name>.ncfg to
    C:\\Users\\<user>\\Documents\\NIRx\\Configurations\\
then open it in Aurora (Configuration -> Load).

Requires numpy, scipy (matplotlib optional, for the figure).
"""
import argparse
import csv
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
POSITIONS_CSV = os.path.join(HERE, "positions_icbm152.csv")
NCFG_TEMPLATE = os.path.join(HERE, "aurora_template.ncfg")

# Fiducials on the ICBM152 head used by NIRSite (mm), copied from its digpts.txt.
FIDUCIALS = {
    "nz": (0.400, 85.900, -47.600),
    "ar": (83.900, -16.600, -56.700),
    "al": (-83.800, -18.600, -57.200),
    "cz": (-0.461, -8.416, 101.365),
    "iz": (0.200, -120.500, -25.800),
}

# --------------------------------------------------------------------------- #
# The LYDIA piano-in-noise montage (NIRSport2, 16 sources x 16 detectors)
#
# Priorities: dense bilateral prefrontal coverage (frontal pole, VLPFC, DLPFC,
# joined across the midline via AFz/Fz/FCz), premotor FC row and SMA (Fz-FCz),
# a few sensorimotor channels (C3/C4) and the temporal lobe (T7/T8 with
# FT7/TP7, FT8/TP8). Motor and temporal regions are NOT bridged across the
# hemispheres (no Cz/C1/C2): those optodes were spent on the frontal pole.
# Every channel is an adjacent 10-10 pair, 30-42 mm on the ICBM152 template.
# --------------------------------------------------------------------------- #
PIANO_NOISE = {
    "name": "PianoNoise",
    "sources": [
        "Fpz", "AF7", "AF3", "AF4", "AF8",   # S01-S05  frontal pole / VLPFC / DLPFC
        "Fz", "F3", "F4",                    # S06-S08  DLPFC + pre-SMA midline
        "FC5", "FC1", "FC2", "FC6",          # S09-S12  premotor row
        "C3", "C4",                          # S13-S14  sensorimotor
        "T7", "T8",                          # S15-S16  temporal (auditory)
    ],
    "detectors": [
        "Fp1", "Fp2", "AFz",                 # D01-D03  frontal pole
        "F5", "F1", "F2", "F6",              # D04-D07  DLPFC
        "FC3", "FCz", "FC4",                 # D08-D10  premotor / SMA
        "C5", "C6",                          # D11-D12  sensorimotor (lateral)
        "FT7", "TP7", "FT8", "TP8",          # D13-D16  temporal
    ],
    # Channels are every source-detector pair within [min_mm, max_mm].
    "min_mm": 20.0,
    "max_mm": 42.0,
    "exclude": [],   # e.g. ["Fz-AFz"] to drop an auto channel
    "include": [],   # e.g. ["T7-CP5"] to force a longer pair
}


def load_positions(path=POSITIONS_CSV):
    pos = {}
    with open(path) as f:
        for r in csv.DictReader(l for l in f if not l.startswith("#")):
            pos[r["label"]] = {
                "c3": np.array([float(r["x"]), float(r["y"]), float(r["z"])]),   # cm
                "c2": np.array([float(r["u"]), float(r["v"])]),
                "n": np.array([float(r["nx"]), float(r["ny"]), float(r["nz"])]),
            }
    return pos


def build(spec, pos):
    """Return a dict describing the montage (all coordinates in cm)."""
    src, det = spec["sources"], spec["detectors"]
    for l in src + det:
        if l not in pos:
            sys.exit(f"unknown label {l!r} (see --list-labels)")
    if len(set(src + det)) != len(src + det):
        sys.exit("a label is used twice")
    s3 = np.array([pos[l]["c3"] for l in src]); d3 = np.array([pos[l]["c3"] for l in det])
    s2 = np.array([pos[l]["c2"] for l in src]); d2 = np.array([pos[l]["c2"] for l in det])
    sn = np.array([pos[l]["n"] for l in src]); dn = np.array([pos[l]["n"] for l in det])

    excl = {tuple(x.split("-")) for x in spec.get("exclude", [])}
    incl = {tuple(x.split("-")) for x in spec.get("include", [])}
    chans = []
    for i, sl in enumerate(src):
        for j, dl in enumerate(det):
            d_mm = np.linalg.norm(s3[i] - d3[j]) * 10
            auto = spec["min_mm"] <= d_mm <= spec["max_mm"]
            if ((auto and (sl, dl) not in excl) or (sl, dl) in incl):
                chans.append((i, j, d_mm))
    if not chans:
        sys.exit("no channels")
    idx = np.array([[i + 1, j + 1] for i, j, _ in chans], dtype=float)
    c3 = np.array([(s3[i] + d3[j]) / 2 for i, j, _ in chans])
    c2 = np.array([(s2[i] + d2[j]) / 2 for i, j, _ in chans])
    cn = np.array([sn[i] + dn[j] for i, j, _ in chans])
    cn /= np.linalg.norm(cn, axis=1, keepdims=True)
    # NIRSite puts the channel point on the scalp, not on the chord: push the
    # midpoint outward by the sagitta of a ~9 cm sphere (display only).
    dist = np.array([d for _, _, d in chans]) / 10
    sag = 9.0 - np.sqrt(np.maximum(9.0 ** 2 - (dist / 2) ** 2, 0))
    c3 = c3 + cn * sag[:, None]
    return {
        "name": spec["name"], "sources": src, "detectors": det,
        "s3": s3, "d3": d3, "s2": s2, "d2": d2, "sn": sn, "dn": dn,
        "index_c": idx, "c3": c3, "c2": c2, "cn": cn, "dist_mm": dist * 10,
    }


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def _cell(labels):
    a = np.empty((1, len(labels)), dtype=object)
    for i, l in enumerate(labels):
        a[0, i] = l
    return a


def write_probeinfo_mat(m, path):
    from scipy.io import savemat
    probes = {
        "nSource0": float(len(m["sources"])),
        "nDetector0": float(len(m["detectors"])),
        "nChannel0": float(len(m["index_c"])),
        "index_c": m["index_c"],
        "coords_s2": m["s2"], "coords_s3": m["s3"], "normals_s": m["sn"], "labels_s": _cell(m["sources"]),
        "coords_d3": m["d3"], "coords_d2": m["d2"], "normals_d": m["dn"], "labels_d": _cell(m["detectors"]),
        "coords_o3": np.zeros((0, 3)), "coords_o2": np.zeros((0, 2)), "normals_o": np.zeros((0, 3)),
        "labels_o": np.empty((0, 0), dtype=object),
        "coords_c3": m["c3"], "coords_c2": m["c2"], "normals_c": m["cn"],
    }
    savemat(path, {"probeInfo": {"headmodel": "ICBM152", "probes": probes}}, format="5", oned_as="row")


def write_nirsite_txt(m, outdir):
    with open(os.path.join(outdir, "Standard_Optodes.txt"), "w") as f:
        for i, p in enumerate(m["s3"]):
            f.write(f"S{i + 1:02d},{p[0] * 10:.3f},{p[1] * 10:.3f},{p[2] * 10:.3f}\n")
        for i, p in enumerate(m["d3"]):
            f.write(f"D{i + 1:02d},{p[0] * 10:.3f},{p[1] * 10:.3f},{p[2] * 10:.3f}\n")
    with open(os.path.join(outdir, "digpts.txt"), "w") as f:
        for k, v in FIDUCIALS.items():
            f.write(f"{k}: {v[0]:.3f} {v[1]:.3f} {v[2]:.3f} \n")
        for i, p in enumerate(m["s3"]):
            f.write(f"s{i + 1}: {p[0] * 10:.3f} {p[1] * 10:.3f} {p[2] * 10:.3f} \n")
        for i, p in enumerate(m["d3"]):
            f.write(f"d{i + 1}: {p[0] * 10:.3f} {p[1] * 10:.3f} {p[2] * 10:.3f} \n")
    # NIRSite columns: idx, src, det, scalp x y z (mm), length (mm), cortex x y z (mm).
    # The cortex point is approximated here as 15 mm below the scalp point along the normal.
    with open(os.path.join(outdir, "Standard_Channels.txt"), "w") as f:
        for k, (i, j) in enumerate(m["index_c"].astype(int)):
            p = m["c3"][k] * 10; q = p - 15.0 * m["cn"][k]
            f.write(f"{k + 1},{i},{j},{p[0]:.3f},{p[1]:.3f},{p[2]:.3f},{m['dist_mm'][k]:.1f},{q[0]:.3f},{q[1]:.3f},{q[2]:.3f}\n")
    with open(os.path.join(outdir, "Standard_probeInfo.aux"), "w") as f:
        json.dump({"disabled_auto_channels": [], "manual_channels": [], "channel_min_distance": 0.0,
                   "channel_max_distance": 45.0, "version": "make_montage.py"}, f)
    with open(os.path.join(outdir, "channels.csv"), "w") as f:
        f.write("channel,source,detector,source_label,detector_label,length_mm\n")
        for k, (i, j) in enumerate(m["index_c"].astype(int)):
            f.write(f"{k + 1},S{i},D{j},{m['sources'][i - 1]},{m['detectors'][j - 1]},{m['dist_mm'][k]:.1f}\n")


def write_ncfg(m, path, accelerometer=True, biosignals=False, origin_dir=r"C:\Users\ADEPT OsloMet\Documents\NIRx\Configurations"):
    with open(NCFG_TEMPLATE) as f:
        cfg = json.load(f)
    nS, nD = len(m["sources"]), len(m["detectors"])
    if nS > 16 or nD > 16:
        sys.exit("template is for one NIRSport2 (max 16x16)")
    mask = [["0"] * nD for _ in range(nS)]
    for i, j in m["index_c"].astype(int):
        mask[i - 1][j - 1] = "1"
    cfg["tag"] = m["name"]
    cfg["channel_mask"] = ["".join(r) for r in mask]
    cfg["det_plan"] = [["1" * nD + "0" * (16 - nD)] for _ in range(16)]
    cfg["det_split"] = ["0" * j + "1" + "0" * (15 - j) for j in range(nD)]
    cfg["src_split"] = ["0" * i + "1" + "0" * (15 - i) for i in range(16)]
    cfg["montage_path"] = f"Montages\\{m['name']}\\Standard_probeInfo.mat"
    cfg["use_accelerometer"] = bool(accelerometer)
    cfg["use_biosignals"] = bool(biosignals)
    cfg["_origin_path"] = f"{origin_dir}\\{m['name']}.ncfg"
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)


def write_figure(m, path):
    try:
        import view_montage
    except ImportError:
        print("matplotlib not installed, skipping figure")
        return
    view_montage.save_png(view_montage.from_build(m), path)


def write_spec(spec, path):
    """The montage as the editor / --spec understand it (round-trips through editor.py)."""
    keys = ("name", "sources", "detectors", "min_mm", "max_mm", "exclude", "include")
    with open(path, "w") as f:
        json.dump({k: spec[k] for k in keys if k in spec}, f, indent=2)


def print_summary(m):
    print(f"{m['name']}: {len(m['sources'])} sources, {len(m['detectors'])} detectors, {len(m['index_c'])} channels")
    for k, (i, j) in enumerate(m["index_c"].astype(int)):
        print(f"  ch{k + 1:2d}  S{i:02d}-D{j:02d}  {m['sources'][i - 1]:>4s}-{m['detectors'][j - 1]:<4s} {m['dist_mm'][k]:5.1f} mm")
    unused = [f"S{i + 1}" for i in range(len(m['sources'])) if i + 1 not in m['index_c'][:, 0]] + \
             [f"D{j + 1}" for j in range(len(m['detectors'])) if j + 1 not in m['index_c'][:, 1]]
    if unused:
        print("  WARNING optodes without channels:", ", ".join(unused))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", default=None)
    p.add_argument("--spec", default=None, help="JSON file with name/sources/detectors/min_mm/max_mm/include/exclude")
    p.add_argument("--sources", default=None, help="comma-separated 10-10 labels (default: PianoNoise montage)")
    p.add_argument("--detectors", default=None)
    p.add_argument("--min-mm", type=float, default=None)
    p.add_argument("--max-mm", type=float, default=None)
    p.add_argument("--exclude", default="", help="comma-separated Src-Det label pairs to drop, e.g. Fz-AFz")
    p.add_argument("--include", default="", help="comma-separated Src-Det label pairs to force")
    p.add_argument("--out", default=os.path.join(HERE, "out"))
    p.add_argument("--no-accelerometer", action="store_true")
    p.add_argument("--biosignals", action="store_true", help="enable WINGS biosignals in the .ncfg")
    p.add_argument("--list-labels", action="store_true")
    a = p.parse_args()

    pos = load_positions()
    if a.list_labels:
        print(" ".join(sorted(pos)))
        return
    spec = dict(PIANO_NOISE)
    if a.spec:
        with open(a.spec) as f:
            spec.update(json.load(f))
    if a.sources or a.detectors:
        if not (a.sources and a.detectors):
            sys.exit("give both --sources and --detectors")
        spec["sources"] = a.sources.split(","); spec["detectors"] = a.detectors.split(",")
        spec["name"] = a.name or "Custom"
    if a.name: spec["name"] = a.name
    if a.min_mm is not None: spec["min_mm"] = a.min_mm
    if a.max_mm is not None: spec["max_mm"] = a.max_mm
    if a.exclude: spec["exclude"] = a.exclude.split(",")
    if a.include: spec["include"] = a.include.split(",")

    m = build(spec, pos)
    outdir = os.path.join(a.out, m["name"])
    os.makedirs(outdir, exist_ok=True)
    write_probeinfo_mat(m, os.path.join(outdir, "Standard_probeInfo.mat"))
    write_nirsite_txt(m, outdir)
    write_ncfg(m, os.path.join(a.out, m["name"] + ".ncfg"), accelerometer=not a.no_accelerometer, biosignals=a.biosignals)
    write_figure(m, os.path.join(outdir, "montage.png"))
    write_spec(spec, os.path.join(outdir, "spec.json"))
    print_summary(m)
    print(f"\nwritten to {outdir}/ and {os.path.join(a.out, m['name'] + '.ncfg')}")


if __name__ == "__main__":
    main()
