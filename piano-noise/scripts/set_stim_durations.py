#!/usr/bin/env python3
"""Rewrite stim durations in SNIRF files (Aurora writes 10 s for every LSL marker).

Copies each input file to --out and sets the duration column of the chosen
stim groups, so a GLM (NIRWizard, cedalion, ...) models the whole block.

    python scripts/set_stim_durations.py data/*.snirf --out data/dur40 --set 20=40 --set 21=40
    python scripts/set_stim_durations.py data/*.snirf --out data/actual --actual 20,21 --until 30

--set NAME=SECONDS   fixed duration for stim group NAME (repeatable)
--actual NAMES       per-event duration = onset of the next --until marker minus onset
--until NAME         marker that ends an --actual block (default 30 = REST)

Needs h5py (pip install h5py). Only /nirs/stim*/data column 2 is touched.
"""
import argparse
import os
import shutil
import sys

import h5py
import numpy as np


def stim_groups(nirs):
    out = {}
    for k in nirs:
        if k.startswith("stim"):
            name = nirs[k]["name"][()]
            out[name.decode() if isinstance(name, bytes) else str(name)] = nirs[k]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", required=True, help="output directory (created)")
    ap.add_argument("--set", action="append", default=[], metavar="NAME=SECONDS")
    ap.add_argument("--actual", default="", metavar="NAMES", help="comma-separated stim names")
    ap.add_argument("--until", default="30", help="marker ending an --actual block")
    a = ap.parse_args()

    fixed = {}
    for s in a.set:
        name, dur = s.split("=")
        fixed[name.strip()] = float(dur)
    actual = [s.strip() for s in a.actual.split(",") if s.strip()]
    if not fixed and not actual:
        sys.exit("nothing to do: give --set and/or --actual")

    os.makedirs(a.out, exist_ok=True)
    for src in a.files:
        dst = os.path.join(a.out, os.path.basename(src))
        if os.path.abspath(dst) == os.path.abspath(src):
            sys.exit(f"{src}: output would overwrite the input")
        shutil.copyfile(src, dst)
        with h5py.File(dst, "r+") as h:
            groups = stim_groups(h["nirs"])
            print(f"{dst}")
            for name, dur in fixed.items():
                if name not in groups:
                    print(f"  {name}: not in file, skipped")
                    continue
                d = groups[name]["data"][()]
                d[:, 1] = dur
                groups[name]["data"][...] = d
                print(f"  {name}: {len(d)} events -> {dur:g} s")
            if actual:
                if a.until not in groups:
                    sys.exit(f"{dst}: --until marker {a.until} not in file")
                ends = np.sort(groups[a.until]["data"][()][:, 0])
                for name in actual:
                    if name not in groups:
                        print(f"  {name}: not in file, skipped")
                        continue
                    d = groups[name]["data"][()]
                    for i, onset in enumerate(d[:, 0]):
                        later = ends[ends > onset]
                        if len(later) == 0:
                            print(f"  {name}: event at {onset:.1f} s has no following {a.until}, left as is")
                            continue
                        d[i, 1] = later[0] - onset
                    groups[name]["data"][...] = d
                    print(f"  {name}: {len(d)} events -> " + ", ".join(f"{x:.1f}" for x in d[:, 1]) + " s")


if __name__ == "__main__":
    main()
