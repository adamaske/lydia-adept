# Piano-in-noise fNIRS pilot (LYDIA)

Acquisition tooling for the protocol in `test_protocol_Lydia.pdf`: prefrontal /
premotor / SMA / sensorimotor / temporal fNIRS (NIRSport2, 16x16) while a pianist
plays a memorised piece in quiet (QP) and in multi-talker babble (NP), in a
natural and in an acoustically adjusted room.

```
plan.md                      task description
test_protocol_Lydia.pdf      the protocol
montage/make_montage.py      builds the Aurora montage from 10-10 labels (no NIRSite needed)
montage/positions_icbm152.csv  10-10/10-5 scalp positions on NIRSite's ICBM152 head
montage/aurora_template.ncfg   Aurora config template (device settings) the .ncfg is derived from
montage/out/PianoNoise/      generated montage folder  -> Documents\NIRx\Configurations\Montages\PianoNoise\
montage/out/PianoNoise.ncfg  generated Aurora config   -> Documents\NIRx\Configurations\
scripts/run_session.py       runs one session: LSL markers, block timing, cues, babble on/off, MIDI log
scripts/triggers.py          marker code table (single source of truth)
scripts/beep.py              1 kHz cue
scripts/noise.py             looped babble playback
scripts/midi_log.py          optional MIDI keyboard logger (LSL-clock timestamps)
logs/                        per-session json + log (commit these)
data/blocks.csv              one row per block; data/sessions.csv one row per session
data/midi/                   MIDI event CSVs
```

## Montage (`PianoNoise`, 16 sources x 16 detectors, 49 channels, 30-42 mm)

| region | optodes | channels |
|---|---|---|
| prefrontal (DLPFC / VLPFC-IFG) | S: F7 AF3 AF4 F8 Fz F3 F4; D: F5 F1 AFz F2 F6 | F7-F5, AF3-F5, AF3-AFz, Fz-F1/F2/AFz, F3-F5/F1, mirrored right |
| premotor / SMA | S: FC5 FC1 FC2 FC6 Cz; D: FC3 FCz FC4 | FC-row pairs, Fz-FCz, FC1/FC2-FCz, Cz-FCz |
| sensorimotor (C3/C4) | S: C3 C4; D: C5 C1 C2 C6 | C3-C5, C3-C1, C3-FC3, FC1-C1, Cz-C1, mirrored right |
| temporal (auditory) | S: T7 T8; D: FT7 TP7 FT8 TP8 | T7-FT7, T7-TP7, T7-C5, F7-FT7, FC5-FT7, mirrored right |

![montage](montage/out/PianoNoise/montage.png)

Notes for the protocol questions:
- 16 sources on one NIRSport2 give ~5.1 Hz (the 16x16 recordings in `~/nirs` are 5.09 Hz).
  Halving the sources would give ~10 Hz but loses a region; 5 Hz is plenty for a
  40/30 s block design and still resolves the heartbeat for QC.
- No short-separation channels (as the protocol says). The `.ncfg` has the
  accelerometer enabled. Rebuild with `--biosignals` if WINGS2 is used through Aurora.

### Rebuilding or changing the montage

```sh
pip install numpy scipy matplotlib
python montage/make_montage.py                  # default PianoNoise montage
python montage/make_montage.py --list-labels    # which 10-10 labels are available
python montage/make_montage.py --name Test --sources Fz,Cz --detectors FCz,F1,C1
```

Edit `PIANO_NOISE` in `make_montage.py` to move optodes; channels are all
source-detector pairs within `min_mm..max_mm` (plus `include`/`exclude`).
The writer produces the same `Standard_probeInfo.mat` structure NIRSite 2023.9
exports (headmodel ICBM152, `probes` struct with coords/normals/labels), the
Aurora `.ncfg` (channel mask, detector plan, montage path, accelerometer) and
the NIRSite-style text files for reference. The cortex projection columns in
`Standard_Channels.txt` are approximate (15 mm below the scalp point).

## Session runner

### Setup (Windows 11 acquisition PC)

```
git clone https://github.com/adamaske/lydia-adept
cd lydia-adept\piano-noise
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt          # pylsl (+ mido, python-rtmidi for MIDI logging)
```

Copy `montage\out\PianoNoise\` to `%USERPROFILE%\Documents\NIRx\Configurations\Montages\PianoNoise\`
and `montage\out\PianoNoise.ncfg` to `%USERPROFILE%\Documents\NIRx\Configurations\`, then load it in Aurora.

Put the babble file (PCM WAV, any length; it loops) in `stimuli\babble.wav`
(not in git). Calibrate its level to ~65 dB SPL at the player's head:

```
python scripts\run_session.py --noise stimuli\babble.wav --noise-test 30
```

### Run

```
python scripts\run_session.py --list-midi
python scripts\run_session.py --subject 1 --room natural  --noise stimuli\babble.wav --midi "Keystation"
python scripts\run_session.py --subject 1 --room adjusted --noise stimuli\babble.wav --midi "Keystation"
python scripts\run_session.py --no-lsl --speed 20                 # 1-minute dry run, no LSL
python scripts\run_session.py --help
```

Start the Aurora recording first with the `Trigger` LSL stream selected as
trigger source. The session is fully timed: after ENTER it runs

```
SESSION_START, ROOM_*, BASELINE 60 s,
3 runs x [ RUN_START, 6 x ( PLAY 40+/-8 s (QP or NP)  ->  REST 30+/-5 s ) ], RUN_REST 120 s between runs,
SESSION_END                                          (~26 min)
```

QP/NP is 3/3 per run, shuffled (max two in a row), first condition alternating
across runs; everything is derived from `--seed` (printed and logged). The 1 kHz
beep marks every play onset (1 beep) and rest onset (2 beeps). During NP the
babble starts with the play marker and stops at the rest marker; without
`--noise` the console tells you to switch it by hand.

Marker codes (`python scripts/triggers.py`):

```
 1 SESSION_START   2 SESSION_END   3 ROOM_NATURAL   4 ROOM_ADJUSTED
10 BASELINE       11 RUN_START
20 PLAY_QUIET     21 PLAY_NOISE   30 REST          40 RUN_REST
99 ABORT
```

After the session commit `logs/` and `data/` and push.
