#!/usr/bin/env python3
"""Listen on the LSL "Trigger" stream the way Aurora does and print every marker.

Run it next to the experiment (or instead of Aurora) to check the triggers arrive:
    python scripts/check_triggers.py                                  # until SESSION_END / ABORT
    python scripts/check_triggers.py --log data/pilot/logs   # then compare with the newest session log there

With --log, the received codes must equal the logged ones in order, and the LSL timestamps
must match within --tol seconds. Exit code 0 = all good.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from triggers import TRIGGERS  # noqa: E402

END = {2, 99}  # SESSION_END, ABORT


def compare(got, logged, tol):
    """got/logged: lists of (code, t_lsl). Returns a list of problems (empty = match)."""
    problems = []
    if [c for c, _ in got] != [c for c, _ in logged]:
        problems.append(f"codes differ:\n  received {[c for c, _ in got]}\n  logged   {[c for c, _ in logged]}")
    for i, ((c, t), (_, tl)) in enumerate(zip(got, logged)):
        if abs(t - tl) > tol:
            problems.append(f"marker {i} ({c}): received t={t:.4f}, logged t={tl:.4f} ({1000 * (t - tl):+.1f} ms)")
    return problems


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--stream-name", default="Trigger")
    p.add_argument("--wait", type=float, default=60.0, help="seconds to wait for the stream to appear")
    p.add_argument("--timeout", type=float, default=3600.0, help="stop after this many seconds")
    p.add_argument("--log", help="session JSON to compare against once the session ends")
    p.add_argument("--tol", type=float, default=0.002, help="max |received - logged| timestamp, s")
    args = p.parse_args()

    from pylsl import StreamInlet, resolve_byprop
    print(f"waiting for LSL stream '{args.stream_name}' ...")
    found = resolve_byprop("name", args.stream_name, timeout=args.wait)
    if not found:
        sys.exit(f"no LSL stream named '{args.stream_name}' within {args.wait:.0f} s")
    info = found[0]
    print(f"connected: {info.name()} type={info.type()} format={info.channel_format()} "
          f"source_id={info.source_id()} host={info.hostname()}")
    inlet = StreamInlet(info)
    inlet.open_stream()  # subscribe now, so the experiment's have_consumers() turns true

    got, t_stop = [], time.time() + args.timeout
    while time.time() < t_stop:
        sample, t = inlet.pull_sample(timeout=0.5)
        if sample is None:
            continue
        t += inlet.time_correction()  # sender's clock (0 on one machine)
        c = int(sample[0])
        got.append((c, t))
        print(f"{t:12.4f}  {c:3d}  {TRIGGERS.get(c, ('UNKNOWN',))[0]}")
        if c in END:
            break
    print(f"{len(got)} markers received")

    if args.log:
        if os.path.isdir(args.log):  # newest session log in that folder
            args.log = max((os.path.join(args.log, n) for n in os.listdir(args.log) if n.endswith(".json")),
                           key=os.path.getmtime)
        for _ in range(50):  # the experiment rewrites the log after the last marker; wait for "ended"
            try:
                with open(args.log) as f:
                    session = json.load(f)
                if "ended" in session:
                    break
            except ValueError:
                pass
            time.sleep(0.2)
        logged = [(m["code"], m["t_lsl"]) for m in session["markers"]]
        problems = compare(got, logged, args.tol)
        print("\n".join(problems) if problems else f"OK: matches {os.path.basename(args.log)}")
        sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
