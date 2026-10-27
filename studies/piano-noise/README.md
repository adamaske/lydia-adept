# Piano-noise (LYDIA-ADEPT study)

fNIRS (NIRSport2, Aurora) over prefrontal / premotor / SMA / sensorimotor /
temporal cortex while a pianist plays a memorised piece in quiet (QP) and in
noise (NP). Protocol: `docs/test_protocol_Lydia.pdf`. Write-up: the
`piano-noise/` chapter of the Overleaf report.

```
docs/                        protocol, plan.md, notes.md
montage/cap_56 … cap_62/     WizardHat exports of montage PianoNoise_62 (16 S x 16 D, 49 ch), one per head size:
                             nirsite/ (the folder Aurora loads), panels/*.stl (print), .snirf/.nirwmontage, cap.yaml
montage/PianoNoise-Montage*  montage drawings
stimuli/                     babble/noise WAVs (not in git)
scripts/piano-noise-experiment.py  the experiment (PsychoPy): dialog, conductor window, cues, LSL markers
scripts/check_triggers.py    listens on the LSL "Trigger" stream like Aurora; checks markers against the session log
scripts/triggers.py          marker code table (single source of truth)
scripts/run_session.py       terminal-only runner (first round); also holds the schedule/CSV helpers the PsychoPy script uses
scripts/beep.py noise.py midi_log.py   cue, babble and optional MIDI logger used by run_session.py
scripts/set_stim_durations.py  .snirf copies with the real play-block durations (Aurora writes 10 s)
scripts/plot_block_design.py   block-design figure
data/raw/sub_XX/             Aurora .snirf recordings
data/logs/                   per-session JSON (+ .log for run_session.py) — commit these
data/blocks.csv, sessions.csv  one row per block / per session
data/pilot/                  dry runs: same files, never mixed with real data
data/processed/              NIRWizard output (not in git)
analysis/                    accelerometer / head-motion analysis
archive/                     finished reports + the exports they were built from (see archive/README.md)
```

## Markers (LSL stream `Trigger`, int32)

| code | marker | | code | marker |
|---|---|---|---|---|
| 1 | SESSION_START | | 20 | PLAY_QUIET |
| 2 | SESSION_END | | 21 | PLAY_NOISE |
| 3 / 4 | ROOM_NATURAL / ROOM_ADJUSTED | | 30 | REST (ends play block and noise) |
| 10 | BASELINE (60 s) | | 40 | RUN_REST (120 s) |
| 11 | RUN_START | | 99 | ABORT (Esc) |

```
SESSION_START, [ROOM_*], BASELINE 60 s,
3 runs x [ RUN_START, 6 x ( PLAY 40+/-8 s -> REST 30+/-5 s ) ], RUN_REST 120 s between runs,
SESSION_END                                          (~26 min)
```

Each marker is pushed right after the screen flip that shows PLAY/REST, before
the cue beep starts, and its LSL timestamp is in the session JSON.

## Acquisition PC (Windows 11)

Once, in a terminal (needs git and uv; uv fetches Python 3.10 itself):

```bat
git clone https://github.com/adamaske/lydia-adept "%USERPROFILE%\Desktop\LYDIA-ADEPT"
```

Then in `Desktop\LYDIA-ADEPT`:

- `run-piano-noise.bat`: double-click to run a session. The first run builds
  `.venv-psychopy` (a few minutes, needs internet). If anything fails, the window stays open with the error.
- `check-piano-noise-triggers.bat`: trigger check without Aurora (see below). Run it once after setup.

Before a session day, `git pull` there. After it, commit `data/` and push.

## Setup (other machines)

PsychoPy needs Python 3.10:

```sh
uv venv --python 3.10 .venv-psychopy
uv pip install -p .venv-psychopy -r requirements-psychopy.txt
```

On Windows, `.venv-psychopy\Scripts\python` instead of `.venv-psychopy/bin/python`. Or use
PsychoPy Studio: install `pylsl` under Tools > Plugins/Packages, then add the script in the Runner.

Aurora: copy `montage/cap_<size>/nirsite/` to
`Documents\NIRx\Configurations\Montages\PianoNoise_62\` and select the `Trigger`
LSL stream as the trigger source.

## Session

1. Fit the cap for the participant's head size, check signal quality in Aurora.
2. Start the experiment:
   ```sh
   .venv-psychopy/bin/python scripts/piano-noise-experiment.py
   ```
   Fill in the dialog (subject, condition, room, noise file). The next free session number is used by default.
3. **Start the Aurora recording.** The start screen turns green ("Aurora is listening on
   'Trigger'"). SPACE does nothing while it is red; F starts anyway, but then the markers are lost.
   With a noise file, N toggles the babble to set the level (~65 dB SPL at the head).
4. SPACE. The session runs by itself. Esc aborts (ABORT marker, logs are still written).
   The player only hears the cues (1 beep = play, 2 = rest), so there is no participant screen. A small
   conductor window (top left) shows the phase, run/block, the countdown and the session clock. Keep it
   next to Aurora's signal view. For Esc, click the window first. Don't minimise it: a minimised window can
   be redrawn slowly and phases then run long. The console prints `!! … held … too long` when that happens.
5. Stop the Aurora recording after SESSION_END. Commit `data/logs/`, `data/*.csv`, `data/raw/`.

Dry run, no participant: Studio's pilot toggle, or `--pilot` (no LSL, x20 speed, writes to `data/pilot/`).

### Checking the triggers

Before the first session on a machine, run the listener in a second terminal and a short pilot with LSL on.
The listener connects like Aurora (so the start screen turns green). It prints every marker and compares
them with the session log when the session ends:

```sh
.venv-psychopy/bin/python scripts/check_triggers.py --log data/pilot/logs
.venv-psychopy/bin/python scripts/piano-noise-experiment.py --pilot     # tick "send LSL" in the dialog
```

`OK: matches <log>.json` means all codes arrived in order with timestamps within 2 ms of the log.
Exit code 1 lists the differences.

## Stim durations for the GLM

Aurora stores every LSL marker with a 10 s duration. Make copies with the real block length before NIRWizard:

```sh
python scripts/set_stim_durations.py data/raw/sub_01/*.snirf --out data/processed/dur40 --set 20=40 --set 21=40   # planned 40 s
python scripts/set_stim_durations.py data/raw/sub_01/*.snirf --out data/processed/actual --actual 20,21 --until 30 # onset to next REST
```

## First round (2026-09)

Subject 01, sessions 2026-09-07 (`quiet_1`/`quiet_2` = ses-08/ses-10, `noise_1`/`noise_2` = ses-09/ses-11),
recorded with `run_session.py` on the 47-channel `PianoNoise` montage (built with `make_montage.py`,
which is in git history before the WizardHat caps). Reports: `archive/report-2026-09-08/` (HbO only) and
`archive/sub-01-2026-09/` (HbO + HbR).
