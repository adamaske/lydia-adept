"""Trigger (event marker) table for the LYDIA piano-in-noise fNIRS protocol.

Single source of truth for the integer codes pushed on the LSL "Trigger"
stream that Aurora records alongside the fNIRS data.

Convention (same as cube-nirs): tens digit = phase, ones digit = variant.
Only one marker is ever pushed per instant, so Aurora never sees two codes in
the same frame.
"""

TRIGGERS = {
    # code : (name, meaning)
    1:  ("SESSION_START", "Session begins; Aurora must already be recording"),
    2:  ("SESSION_END",   "Session ends; stop the recording after this"),
    3:  ("ROOM_NATURAL",  "Pushed right after SESSION_START: natural (untreated) room"),
    4:  ("ROOM_ADJUSTED", "Pushed right after SESSION_START: acoustically adjusted room"),

    10: ("BASELINE",      "Baseline rest onset (60 s, before run 1; hands on keys, eyes on cross)"),

    11: ("RUN_START",     "Run onset (3 s before the first play block; a run = N play/rest blocks, ~7 min)"),

    20: ("PLAY_QUIET",    "Piano-playing block onset, quiet condition (QP)"),
    21: ("PLAY_NOISE",    "Piano-playing block onset, multi-talker babble on (NP)"),
    30: ("REST",          "Inter-block rest onset (fixation, hands still). Also ends the play block and the noise"),

    40: ("RUN_REST",      "Between-run rest onset (120 s)"),

    99: ("ABORT",         "Session aborted by the experimenter (Ctrl-C)"),
}

NAME_TO_CODE = {name: code for code, (name, _) in TRIGGERS.items()}


def code(name: str) -> int:
    return NAME_TO_CODE[name]


if __name__ == "__main__":
    for c, (n, m) in TRIGGERS.items():
        print(f"{c:3d}  {n:14s} {m}")
