#!/usr/bin/env python3
"""LYDIA piano-in-noise fNIRS session runner (LSL markers + block timing).

Protocol (test_protocol_Lydia.pdf), fully timed, no key presses during the session:

    SESSION_START -> ROOM_* -> BASELINE (60 s)
    run 1..R:  RUN_START -> R x [ PLAY (40 s +/- 8 s, QP or NP) -> REST (30 s +/- 5 s) ]
               -> RUN_REST (120 s) between runs
    SESSION_END

QP/NP is balanced within each run (half/half), shuffled with at most two
identical conditions in a row, and the first condition of a run alternates
across runs.  Durations are jittered uniformly.  The full schedule is derived
from --seed (logged), so a session can be reproduced.

Cues: a 1 kHz beep at every play onset (1 beep) and rest onset (2 beeps).
Noise: --noise babble.wav is looped during NP blocks (starts with the play
marker, stops at the rest marker).  Without --noise the console tells the
experimenter to switch the noise on/off by hand.

Markers are int32 samples on an LSL stream (name "Trigger", type "Markers"),
selected in Aurora as the trigger source.  Codes: triggers.py.

Usage:
    python scripts/run_session.py --subject 1 --room natural --noise stimuli/babble.wav
    python scripts/run_session.py --subject 1 --room adjusted --noise stimuli/babble.wav --midi "Keystation"
    python scripts/run_session.py --no-lsl --speed 20 --room natural        # 1-minute dry run
    python scripts/run_session.py --noise-test 20 --noise stimuli/babble.wav # SPL calibration
    python scripts/run_session.py --list-midi

Ctrl-C aborts (ABORT marker pushed, log still written).
"""
import argparse
import csv
import datetime as dt
import json
import logging
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from triggers import TRIGGERS, code  # noqa: E402
import beep as beep_mod  # noqa: E402
from noise import NoisePlayer  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(ROOT, "logs")
DATA_DIR = os.path.join(ROOT, "data")
MIDI_DIR = os.path.join(DATA_DIR, "midi")
BLOCKS_CSV = os.path.join(DATA_DIR, "blocks.csv")
SESSIONS_CSV = os.path.join(DATA_DIR, "sessions.csv")

MARKER_GAP_S = 1.0  # minimum spacing between two consecutive markers (Aurora frame ~0.2 s at 5 Hz)


# --------------------------------------------------------------------------- #
# Marker outlet
# --------------------------------------------------------------------------- #
class MarkerOutlet:
    def __init__(self, enabled, name, stype, source_id):
        self.enabled = enabled
        self.outlet = None
        self.lsl_clock = None
        if enabled:
            from pylsl import StreamInfo, StreamOutlet, local_clock
            info = StreamInfo(name=name, type=stype, channel_count=1,
                              nominal_srate=0, channel_format="int32", source_id=source_id)
            self.outlet = StreamOutlet(info)
            self.lsl_clock = local_clock
            logging.info(f"LSL outlet '{name}' ({stype}, int32) source_id={source_id}")
        else:
            logging.warning("LSL disabled (--no-lsl): markers are only logged")

    def clock(self):
        return self.lsl_clock() if self.lsl_clock else time.perf_counter()

    def push(self, name):
        c = code(name)
        t_wall = time.time()
        t_lsl = self.clock()
        if self.outlet is not None:
            self.outlet.push_sample([c], t_lsl)
        logging.info(f"MARKER {c:3d} {name}")
        print(f"\n  >> marker {c:3d} {name}")
        return {"code": c, "name": name, "t_wall": t_wall, "t_lsl": t_lsl}


# --------------------------------------------------------------------------- #
# Schedule
# --------------------------------------------------------------------------- #
def make_schedule(runs, blocks, play, play_jit, rest, rest_jit, seed):
    """Return a list of runs; each run is a list of blocks {cond, play_s, rest_s}."""
    rng = random.Random(seed)
    sched = []
    for r in range(runs):
        n_q = blocks // 2 + (1 if (blocks % 2 and r % 2 == 0) else 0)
        conds = ["Q"] * n_q + ["N"] * (blocks - n_q)
        first = "Q" if r % 2 == 0 else "N"   # counterbalance the starting condition across runs
        for _ in range(10000):
            rng.shuffle(conds)
            ok = conds[0] == first or conds.count(first) == 0
            ok = ok and all(not (conds[i] == conds[i - 1] == conds[i - 2]) for i in range(2, blocks))
            if ok:
                break
        run = []
        for c in conds:
            run.append({
                "cond": c,
                "play_s": round(play + rng.uniform(-play_jit, play_jit), 1),
                "rest_s": round(rest + rng.uniform(-rest_jit, rest_jit), 1),
            })
        sched.append(run)
    return sched


def schedule_duration(sched, baseline, run_rest):
    t = baseline
    for i, run in enumerate(sched):
        t += sum(b["play_s"] + b["rest_s"] for b in run)
        if i < len(sched) - 1:
            t += run_rest
    return t


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def countdown(label, seconds, next_label, speed=1.0):
    """Blocking timed block with a live countdown. Real time = seconds / speed."""
    deadline = time.perf_counter() + seconds / speed
    while True:
        remaining = (deadline - time.perf_counter()) * speed
        if remaining <= 0:
            print()
            return
        print(f"  [{label:11s}] {remaining:6.1f} s left -> {next_label}     ", end="\r", flush=True)
        time.sleep(min(0.05, max(remaining / speed, 0)))


def append_csv(path, row):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if new:
            w.writeheader()
        w.writerow(row)


def next_session_number(subject):
    n = 1
    if os.path.exists(SESSIONS_CSV):
        with open(SESSIONS_CSV) as f:
            rows = [r for r in csv.DictReader(f) if int(r["subject"]) == subject]
        if rows:
            n = max(int(r["session"]) for r in rows) + 1
    return n


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--subject", type=int, default=1)
    p.add_argument("--session", type=int, default=None, help="session number (default: auto-increment from data/sessions.csv)")
    p.add_argument("--room", choices=["natural", "adjusted"], default=None, help="room acoustics condition (required for a real session)")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--blocks", type=int, default=6, help="play/rest blocks per run (default 6)")
    p.add_argument("--play", type=float, default=40.0, help="play block length, s")
    p.add_argument("--play-jitter", type=float, default=8.0, help="uniform +/- jitter of play length, s")
    p.add_argument("--rest", type=float, default=30.0, help="rest block length, s")
    p.add_argument("--rest-jitter", type=float, default=5.0)
    p.add_argument("--baseline", type=float, default=60.0, help="baseline rest before run 1, s")
    p.add_argument("--run-rest", type=float, default=120.0, help="rest between runs, s")
    p.add_argument("--seed", type=int, default=None, help="RNG seed for the schedule (default: from timestamp)")
    p.add_argument("--noise", default=None, help="PCM WAV with multi-talker babble, looped during NP blocks")
    p.add_argument("--noise-test", type=float, default=None, metavar="SECONDS", help="play --noise for SECONDS (SPL calibration) and exit")
    p.add_argument("--midi", default=None, metavar="PORT", help="log a MIDI input port (substring of its name) to data/midi/")
    p.add_argument("--midi-lsl", action="store_true", help="also push MIDI note events on an LSL stream 'PianoMIDI'")
    p.add_argument("--list-midi", action="store_true")
    p.add_argument("--stream-name", default="Trigger")
    p.add_argument("--stream-type", default="Markers")
    p.add_argument("--source-id", default="lydia-piano-noise")
    p.add_argument("--no-lsl", action="store_true", help="dry run without pushing LSL markers")
    p.add_argument("--no-beep", action="store_true", help="disable the 1 kHz audio cue")
    p.add_argument("--speed", type=float, default=1.0, help="time scale for dry runs (20 = twenty times faster)")
    p.add_argument("--comment", default="")
    args = p.parse_args()

    if args.list_midi:
        import midi_log
        for name in midi_log.list_ports():
            print(name)
        return
    if args.noise_test is not None:
        if not args.noise:
            sys.exit("--noise-test needs --noise FILE")
        np_ = NoisePlayer(args.noise)
        print(f"Playing {args.noise} for {args.noise_test:.0f} s. Adjust the volume to ~65 dB SPL at the listening position.")
        np_.start(); countdown("NOISE TEST", args.noise_test, "stop"); np_.stop()
        return
    if args.room is None:
        if args.no_lsl:
            args.room = "natural"
        else:
            sys.exit("--room natural|adjusted is required for a recorded session")

    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    if args.session is None:
        args.session = next_session_number(args.subject)

    started = dt.datetime.now()
    stamp = started.strftime("%Y%m%d_%H%M%S")
    base = f"sub-{args.subject:02d}_ses-{args.session:02d}_{args.room}_{stamp}"
    seed = args.seed if args.seed is not None else int(started.timestamp())

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(os.path.join(LOG_DIR, base + ".log")), logging.StreamHandler()],
    )
    logging.getLogger().handlers[1].setLevel(logging.WARNING)

    sched = make_schedule(args.runs, args.blocks, args.play, args.play_jitter, args.rest, args.rest_jitter, seed)
    total = schedule_duration(sched, args.baseline, args.run_rest)

    session = {
        "subject": args.subject, "session": args.session, "room": args.room, "started": started.isoformat(),
        "params": dict(vars(args)), "seed": seed,
        "stream": {"name": args.stream_name, "type": args.stream_type, "source_id": args.source_id},
        "triggers": {c: n for c, (n, _) in TRIGGERS.items()},
        "schedule": sched, "planned_duration_s": total,
        "markers": [], "blocks": [], "completed": False,
    }

    def save():
        with open(os.path.join(LOG_DIR, base + ".json"), "w") as f:
            json.dump(session, f, indent=2)

    save()

    print("=" * 78)
    print(f" LYDIA piano-in-noise fNIRS | subject {args.subject} session {args.session} | room: {args.room.upper()} | {started:%Y-%m-%d %H:%M}")
    print(f" baseline {args.baseline:.0f} s, {args.runs} runs x {args.blocks} blocks "
          f"(play {args.play:.0f}+/-{args.play_jitter:.0f} s, rest {args.rest:.0f}+/-{args.rest_jitter:.0f} s), run rest {args.run_rest:.0f} s")
    print(f" planned duration {total / 60:.1f} min | seed {seed}")
    print(f" LSL stream: {args.stream_name} ({args.stream_type})" + ("  [DISABLED]" if args.no_lsl else ""))
    print(f" noise: {args.noise or 'MANUAL (experimenter switches babble on/off)'}")
    if args.speed != 1.0:
        print(f" SPEED x{args.speed:g} (dry run)")
    print("=" * 78)
    for r, run in enumerate(sched, 1):
        print(f"  run {r}: " + "  ".join(f"{b['cond']}P {b['play_s']:.0f}/{b['rest_s']:.0f}" for b in run))
    print()

    outlet = MarkerOutlet(not args.no_lsl, args.stream_name, args.stream_type, args.source_id)
    noise = NoisePlayer(args.noise)
    midi = None
    if args.midi:
        import midi_log
        ports = [n for n in midi_log.list_ports() if args.midi.lower() in n.lower()]
        if not ports:
            sys.exit(f"no MIDI input port matching {args.midi!r}; available: {midi_log.list_ports()}")
        os.makedirs(MIDI_DIR, exist_ok=True)
        midi_csv = os.path.join(MIDI_DIR, base + "_midi.csv")
        midi = midi_log.MidiLogger(ports[0], midi_csv, lsl_clock=outlet.clock, lsl_outlet=args.midi_lsl and not args.no_lsl,
                                   source_id=args.source_id + "-midi")
        session["midi"] = {"port": ports[0], "csv": os.path.relpath(midi_csv, ROOT)}
        print(f"MIDI logging from '{ports[0]}' -> {session['midi']['csv']}")

    def cue(times=1):
        if not args.no_beep:
            beep_mod.beep(times=times)

    def mark(name):
        m = outlet.push(name)
        session["markers"].append(m)
        save()
        return m

    def gap():
        time.sleep(MARKER_GAP_S / args.speed)

    def noise_on(on):
        if noise.enabled:
            noise.start() if on else noise.stop()
        else:
            print(f"  ***** NOISE {'ON' if on else 'OFF'} (manual) *****")

    print("Checklist: Aurora recording with 'Trigger' selected as LSL trigger; subject seated, hands on keys, eyes on the cross;"
          + (" babble level calibrated." if args.noise else " babble source ready (manual)."))
    input("Press ENTER to start the session...")

    completed_blocks = 0
    try:
        mark("SESSION_START"); gap()
        mark("ROOM_NATURAL" if args.room == "natural" else "ROOM_ADJUSTED"); gap()

        mark("BASELINE")
        countdown("BASELINE", args.baseline, "run 1", args.speed)

        for r, run in enumerate(sched, 1):
            mark("RUN_START")
            print(f"\n----- Run {r}/{args.runs} -----")
            countdown("GET READY", 3.0, "play", args.speed)

            for b, blk in enumerate(run, 1):
                rec = {"run": r, "block": b, "cond": blk["cond"], "planned_play_s": blk["play_s"], "planned_rest_s": blk["rest_s"]}
                is_noise = blk["cond"] == "N"
                print(f"\n  ===== run {r} block {b}/{args.blocks}: {'NOISE' if is_noise else 'QUIET'} PIANO {blk['play_s']:.0f} s =====")
                cue(1)
                m = mark("PLAY_NOISE" if is_noise else "PLAY_QUIET")
                rec["t_play"] = m["t_lsl"]
                if is_noise:
                    noise_on(True)
                countdown("PLAY " + ("NOISE" if is_noise else "QUIET"), blk["play_s"], "rest", args.speed)

                if is_noise:
                    noise_on(False)
                cue(2)
                m = mark("REST")
                rec["t_rest"] = m["t_lsl"]
                rec["play_s"] = round(rec["t_rest"] - rec["t_play"], 3)
                last = (b == args.blocks)
                countdown("REST", blk["rest_s"], "next block" if not last else ("run rest" if r < args.runs else "end"), args.speed)
                rec["t_rest_end"] = outlet.clock()
                rec["rest_s"] = round(rec["t_rest_end"] - rec["t_rest"], 3)
                session["blocks"].append(rec)
                completed_blocks += 1
                save()
                append_csv(BLOCKS_CSV, {
                    "subject": args.subject, "session": args.session, "room": args.room, "date": started.strftime("%Y-%m-%d"),
                    "run": r, "block": b, "cond": blk["cond"], "planned_play_s": blk["play_s"], "planned_rest_s": blk["rest_s"],
                    "play_s": rec["play_s"], "rest_s": rec["rest_s"], "t_play_lsl": round(rec["t_play"], 4), "t_rest_lsl": round(rec["t_rest"], 4),
                })

            if r < args.runs:
                mark("RUN_REST")
                print(f"\n  [RUN REST] {args.run_rest:.0f} s. Subject may relax, keep the cap still.")
                countdown("RUN REST", args.run_rest, f"run {r + 1}", args.speed)

        cue(2)
        mark("SESSION_END")
        session["completed"] = True
        print("\nSession complete. Stop the Aurora recording now.")
    except KeyboardInterrupt:
        print("\nAborted.")
        noise_on(False)
        mark("ABORT")
    finally:
        noise.stop()
        if midi is not None:
            midi.close()
            session["midi"]["events"] = midi.n
        session["ended"] = dt.datetime.now().isoformat()
        save()
        append_csv(SESSIONS_CSV, {
            "subject": args.subject, "session": args.session, "room": args.room, "date": started.strftime("%Y-%m-%d %H:%M"),
            "blocks_completed": completed_blocks, "blocks_planned": args.runs * args.blocks, "seed": seed,
            "noise_file": os.path.basename(args.noise) if args.noise else "manual",
            "midi_events": midi.n if midi else "", "completed": int(session["completed"]), "log": base, "comment": args.comment,
        })
        print(f"Log written: logs/{base}.json")


if __name__ == "__main__":
    main()
