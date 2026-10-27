#!/usr/bin/env python3
"""LYDIA piano-in-noise fNIRS session, PsychoPy version of run_session.py.

Same protocol, schedule, LSL markers (triggers.py) and data/blocks.csv + data/sessions.csv
rows as run_session.py; differences:
  - start dialog for every session setting (remembered between runs), so PsychoPy Studio's
    Runner needs no command-line flags
  - start screen shows whether Aurora is listening on the LSL stream; N plays the babble
    for level calibration (~65 dB SPL), SPACE starts
  - pilot runs (Studio's pilot toggle / --pilot) go to data/pilot/ (logs in data/pilot/logs/)
  - small conductor window (phase, run/block, countdown, session clock) to keep next to Aurora;
    the player is at the piano and only hears the cues, so there is no participant display
  - cues and babble through psychopy.sound; markers are pushed on the screen flip
  - Escape aborts (ABORT marker, logs still written)

    SESSION_START -> [ROOM_*] -> BASELINE
    run 1..R:  RUN_START -> N x [ PLAY (40 +/- 8 s) -> REST (30 +/- 5 s) ] -> RUN_REST between runs
    SESSION_END

In Studio, install pylsl (and mido + python-rtmidi for MIDI) via Tools > Plugins/Packages.
Run with the PsychoPy venv (Python 3.10, see requirements-psychopy.txt):
    .venv-psychopy/bin/python scripts/piano-noise-experiment.py
    .venv-psychopy/bin/python scripts/piano-noise-experiment.py --no-lsl --speed 20   # dry run
PsychoPy Studio: add this file in the Runner; the pilot toggle (orange) = the dry run above.
"""
import argparse
import datetime as dt
import json
import os
import sys

import numpy as np
from psychopy import core, event, gui, prefs, visual

# PTB on the Windows acquisition PC; on Linux PTB rejects PipeWire's 128-channel default device
prefs.hardware["audioLib"] = ["ptb"] if sys.platform == "win32" else ["sounddevice"]
from psychopy import sound  # noqa: E402  (after prefs)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from triggers import TRIGGERS, code  # noqa: E402
from run_session import (DATA_DIR, LOG_DIR, MIDI_DIR, ROOT,  # noqa: E402
                         append_csv, make_schedule, next_session_number, schedule_duration)

MARKER_GAP_S = 1.0
LAST_DIALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".last_dialog.json")  # git-ignored


class Abort(Exception):
    pass


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--blocks", type=int, default=6)
    p.add_argument("--play", type=float, default=40.0)
    p.add_argument("--play-jitter", type=float, default=8.0)
    p.add_argument("--rest", type=float, default=30.0)
    p.add_argument("--rest-jitter", type=float, default=5.0)
    p.add_argument("--baseline", type=float, default=60.0)
    p.add_argument("--run-rest", type=float, default=120.0)
    p.add_argument("--noise", default=None, help="babble WAV, looped during play blocks of noise sessions")
    p.add_argument("--noise-volume", type=float, default=1.0, help="0-1; calibrate to ~65 dB SPL with the OS volume")
    p.add_argument("--midi", default=None, metavar="PORT", help="log a MIDI input port (substring of its name)")
    p.add_argument("--stream-name", default="Trigger")
    p.add_argument("--no-lsl", action="store_true")
    p.add_argument("--speed", type=float, default=1.0, help="time scale for dry runs")
    p.add_argument("--pilot", action="store_true", help="PsychoPy Studio pilot mode = dry run (no LSL, x20)")
    args, _ = p.parse_known_args()  # Studio's Runner also passes --prefs-json etc.
    if args.pilot:
        args.speed = 20.0

    try:
        with open(LAST_DIALOG) as f:
            last = json.load(f)
    except (OSError, ValueError):
        last = {}
    rooms, conds = ["", "natural", "adjusted"], ["quiet", "noise"]
    info = {
        "subject": last.get("subject", 1),
        "session": 0,
        "condition": sorted(conds, key=lambda c: c != last.get("condition")),
        "room": sorted(rooms, key=lambda r: r != last.get("room", "")),
        "noise file": args.noise or last.get("noise file", ""),
        "noise volume": args.noise_volume if args.noise_volume != 1.0 else last.get("noise volume", 1.0),
        "MIDI port": args.midi or last.get("MIDI port", ""),
        "send LSL": not (args.no_lsl or args.pilot),
        "seed": 0,
        "comment": "pilot" if args.pilot else "",
    }
    dlg = gui.DlgFromDict(info, title="LYDIA piano-noise" + (" [PILOT]" if args.pilot else ""), order=list(info),
                          tip={"session": "0 = next free number",
                               "noise file": "babble WAV (path relative to piano-noise/), looped during play blocks "
                                             "of noise sessions; empty = noise comes from the room",
                               "noise volume": "0-1, fine level on top of the OS volume",
                               "MIDI port": "part of the MIDI input name; empty = no MIDI log",
                               "seed": "0 = from timestamp"})
    if not dlg.OK:
        core.quit()
    with open(LAST_DIALOG, "w") as f:
        json.dump({k: info[k] for k in ("subject", "condition", "room", "noise file", "noise volume", "MIDI port")}, f)

    subject = int(info["subject"])
    session_n = int(info["session"]) or next_session_number(subject)
    condition, room = info["condition"], info["room"]
    args.noise = info["noise file"].strip() or None
    if args.noise and not os.path.isabs(args.noise):
        args.noise = os.path.join(ROOT, args.noise)
    if args.noise and not os.path.exists(args.noise):
        sys.exit(f"noise file not found: {args.noise}")
    args.noise_volume = float(info["noise volume"])
    args.midi = info["MIDI port"].strip() or None
    args.no_lsl = not info["send LSL"]
    if condition == "noise" and not args.noise:
        print("noise session without a noise file: babble assumed to come from the room (markers only)")

    # pilot runs never touch the real logs/CSVs
    log_dir = os.path.join(DATA_DIR, "pilot", "logs") if args.pilot else LOG_DIR
    data_dir = os.path.join(DATA_DIR, "pilot") if args.pilot else DATA_DIR
    blocks_csv, sessions_csv = os.path.join(data_dir, "blocks.csv"), os.path.join(data_dir, "sessions.csv")
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)
    started = dt.datetime.now()
    seed = int(info["seed"]) or int(started.timestamp())
    cond = "Q" if condition == "quiet" else "N"
    base = f"sub-{subject:02d}_ses-{session_n:02d}_{condition}_{started:%Y%m%d_%H%M%S}"

    sched = make_schedule(args.runs, args.blocks, args.play, args.play_jitter, args.rest, args.rest_jitter, seed, cond)
    session = {
        "subject": subject, "session": session_n, "condition": condition, "room": room, "started": started.isoformat(),
        "runner": "psychopy", "params": vars(args), "seed": seed, "comment": info["comment"],
        "triggers": {c: n for c, (n, _) in TRIGGERS.items()}, "schedule": sched,
        "planned_duration_s": schedule_duration(sched, args.baseline, args.run_rest),
        "markers": [], "blocks": [], "completed": False,
    }

    def save():
        with open(os.path.join(log_dir, base + ".json"), "w") as f:
            json.dump(session, f, indent=2)

    # --- LSL ---------------------------------------------------------------
    if args.no_lsl:
        outlet, clock = None, core.getTime
    else:
        try:
            from pylsl import StreamInfo, StreamOutlet, local_clock
        except ImportError:
            sys.exit("pylsl is not installed in this Python. In PsychoPy Studio: Tools > Plugins/Packages > "
                     "Packages, install pylsl. Or untick 'send LSL' for a run without markers.")
        outlet = StreamOutlet(StreamInfo(args.stream_name, "Markers", 1, 0, "int32", "lydia-piano-noise"))
        clock = local_clock

    def push(name):
        t = clock()
        if outlet is not None:
            outlet.push_sample([code(name)], t)
        session["markers"].append({"code": code(name), "name": name, "t_wall": dt.datetime.now().timestamp(), "t_lsl": t})
        print(f"  >> marker {code(name):3d} {name}")
        return t

    # --- MIDI (optional, fail-soft like run_session.py) --------------------
    midi = None
    if args.midi:
        try:
            import midi_log
            ports = [n for n in midi_log.list_ports() if args.midi.lower() in n.lower()]
            if not ports:
                raise RuntimeError(f"no MIDI port matching {args.midi!r}")
            midi_dir = os.path.join(data_dir, "midi") if args.pilot else MIDI_DIR
            os.makedirs(midi_dir, exist_ok=True)
            midi = midi_log.MidiLogger(ports[0], os.path.join(midi_dir, base + "_midi.csv"), lsl_clock=clock)
            session["midi"] = {"port": ports[0]}
        except Exception as e:
            print(f"(MIDI logging disabled: {e})")
            session["midi"] = {"error": str(e)}

    # --- display + sound ----------------------------------------------------
    win = visual.Window(size=(560, 320), pos=(40, 40), color=(-0.8, -0.8, -0.8), units="height", allowGUI=True,
                        title="Piano-noise conductor" + (" [PILOT]" if args.pilot else ""))
    text = lambda y, h, **kw: visual.TextStim(win, "", pos=(0, y), height=h, wrapWidth=1.7, **kw)
    title, where, left, clock_txt = text(0.3, 0.13, bold=True), text(0.13, 0.065), text(-0.06, 0.11), text(-0.36, 0.045)
    session_t0 = [None]
    def beeps(n, rate=44100):
        """n x 150 ms 1 kHz beeps, 120 ms apart, as one sound so it can start on a flip without blocking."""
        t = np.arange(int(0.15 * rate)) / rate
        tone = 0.5 * np.sin(2 * np.pi * 1000 * t) * np.minimum(1, np.minimum(t, t[::-1]) / 0.005)  # 5 ms ramps
        mono = np.concatenate([np.concatenate([tone, np.zeros(int(0.12 * rate))])] * n)
        return sound.Sound(np.column_stack([mono, mono]), sampleRate=rate, stereo=True)

    play_cue, rest_cue = beeps(1), beeps(2)
    babble = sound.Sound(args.noise, loops=-1, volume=args.noise_volume) if (args.noise and cond == "N") else None

    total_s = session["planned_duration_s"] / args.speed

    def draw(remaining):
        left.text = f"{remaining:.0f} s left"
        if session_t0[0] is not None:
            m, sec = divmod(int(core.getTime() - session_t0[0]), 60)
            tm, tsec = divmod(int(total_s), 60)
            clock_txt.text = f"session {m:02d}:{sec:02d} / {tm:02d}:{tsec:02d}    ESC: abort (click here first)"
        for t in (title, where, left, clock_txt):
            t.draw()

    def phase(name, marker, seconds, sounds=(), info="", color="white"):
        """Show the phase in the conductor window; marker and sounds start on the same flip.
        Hold for seconds/speed. Returns the marker's LSL time."""
        title.text, title.color, where.text = name, color, info
        hold = seconds / args.speed
        ts = []
        draw(hold)
        if marker:  # first on the flip, so the timestamp is not delayed by the sound start-up
            win.callOnFlip(lambda: ts.append(push(marker)))
        for snd in sounds:
            win.callOnFlip(snd.play)
        t0 = win.flip()  # block duration counts from the marker flip
        if session_t0[0] is None:
            session_t0[0] = t0
        save()
        shown = None
        while core.getTime() - t0 < hold:
            if event.getKeys(["escape"]):
                raise Abort
            remaining = int(hold - (core.getTime() - t0) + 0.999)
            if remaining != shown:  # re-render text once a second, not every frame
                shown = remaining
                draw(remaining)
            else:
                for t in (title, where, left, clock_txt):
                    t.draw()
            win.flip()
        over = core.getTime() - t0 - hold
        if over > 0.1:  # one frame is ~17 ms; more means the window was minimised/throttled
            print(f"  !! {marker or 'phase'} held {over:.2f} s too long: keep the conductor window visible (not minimised)")
        return ts[0] if ts else None

    # --- run ----------------------------------------------------------------
    save()
    status = text(-0.12, 0.05)
    title.text = f"sub-{subject:02d} ses-{session_n:02d} {condition.upper()}"
    where.text = f"{args.runs} runs x {args.blocks} blocks, ~{total_s / 60:.0f} min"
    calib = sound.Sound(args.noise, loops=-1, volume=args.noise_volume) if args.noise else None
    calib_on = False
    event.clearEvents()
    while True:
        listening = outlet is None or outlet.have_consumers()
        if outlet is None:
            status.text, status.color = "LSL OFF - no markers will be sent", "orange"
        elif listening:
            status.text, status.color = f"Aurora is listening on '{args.stream_name}'", "lightgreen"
        else:
            status.text, status.color = (f"Nobody is listening on '{args.stream_name}' - start the Aurora recording\n"
                                         "(F: start anyway, markers are lost)"), "red"
        status.text += ("\nN: babble " + ("ON" if calib_on else "off") + " (level check)" if calib else "") + \
            "\nSPACE: start    ESC: quit"
        title.draw(); where.draw(); status.draw(); win.flip()
        keys = event.getKeys(["space", "escape", "n", "f"])
        if "space" in keys and not listening:
            keys.remove("space")
        if "f" in keys:
            keys.append("space")
        if "n" in keys and calib:
            calib_on = not calib_on
            calib.play() if calib_on else calib.stop()
        if "escape" in keys:
            if calib:
                calib.stop()
            win.close(); core.quit()
        if "space" in keys:
            break
    if calib:
        calib.stop()

    done = 0
    try:
        phase("STARTING", "SESSION_START", MARKER_GAP_S)
        if room:
            phase("STARTING", "ROOM_NATURAL" if room == "natural" else "ROOM_ADJUSTED", MARKER_GAP_S)
        phase("BASELINE", "BASELINE", args.baseline, info="player still, hands on the keys")
        for r, run in enumerate(sched, 1):
            phase("GET READY", "RUN_START", 3.0, info=f"run {r}/{len(sched)}")
            for b, blk in enumerate(run, 1):
                print(f"run {r} block {b}/{args.blocks}: {condition.upper()} play {blk['play_s']:.0f} s")
                where_txt = f"run {r}/{len(sched)}   block {b}/{args.blocks}   {condition.upper()}"
                t_play = phase("PLAY", "PLAY_NOISE" if cond == "N" else "PLAY_QUIET", blk["play_s"],
                               [play_cue] + ([babble] if babble else []), info=where_txt, color="lightgreen")
                if babble:
                    babble.stop()
                t_rest = phase("REST", "REST", blk["rest_s"], [rest_cue], info=where_txt, color="lightskyblue")
                t_end = clock()
                rec = {"run": r, "block": b, "cond": cond, "planned_play_s": blk["play_s"], "planned_rest_s": blk["rest_s"],
                       "play_s": round(t_rest - t_play, 3), "rest_s": round(t_end - t_rest, 3),
                       "t_play_lsl": round(t_play, 4), "t_rest_lsl": round(t_rest, 4)}
                session["blocks"].append(rec)
                done += 1
                append_csv(blocks_csv, {"subject": subject, "session": session_n, "condition": condition, "room": room,
                                        "date": f"{started:%Y-%m-%d}", **rec})
            if r < len(sched):
                phase("RUN BREAK", "RUN_REST", args.run_rest, info=f"after run {r}/{len(sched)} - keep the cap still",
                      color="khaki")
        phase("FINISHED", "SESSION_END", MARKER_GAP_S, [rest_cue], info="stop the Aurora recording")
        session["completed"] = True
        print("Session complete. Stop the Aurora recording now.")
    except Abort:
        print("Aborted.")
        push("ABORT")
    finally:
        if babble:
            babble.stop()
        if midi is not None:
            try:
                midi.close()
                session["midi"]["events"] = midi.n
            except Exception as e:
                print(f"MIDI close failed: {e}")
        session["ended"] = dt.datetime.now().isoformat()
        save()
        append_csv(sessions_csv, {
            "subject": subject, "session": session_n, "condition": condition, "room": room,
            "date": f"{started:%Y-%m-%d %H:%M}", "blocks_completed": done, "blocks_planned": args.runs * args.blocks,
            "seed": seed, "noise_file": os.path.basename(args.noise) if args.noise else "manual",
            "midi_events": midi.n if midi is not None else "", "completed": int(session["completed"]),
            "log": base, "comment": info["comment"],
        })
        print(f"Log written: {os.path.relpath(os.path.join(log_dir, base + '.json'), ROOT)}")
        win.close()
        core.quit()


if __name__ == "__main__":
    main()
