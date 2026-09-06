# LYDIA-ADEPT — Auditory Environment, Cognitive Load & fNIRS

Literature notes and working material for the LYDIA-ADEPT sub-project:
the effect of the auditory environment (noise, soundscape, ANC, entrainment)
on mental workload and task performance, measured with mobile non-invasive
neuroimaging (primarily fNIRS, plus EEG).

## Contents

- `notes.tex` — per-paper reading notes + citable facts bank (biblatex/biber)
- `references.bib` — BibTeX library for the above
- `literature/` — PDFs of the reviewed papers (filenames match bib keys)
- `audio/` — lab soundscape recording and spectral analysis
  (`analyze_soundscape.py`, spectrogram/spectrum plots, report)
- `piano-noise/` — piano-in-noise fNIRS pilot: protocol, Aurora montage built
  from 10-10 labels (`make_montage.py`), and the LSL session runner
  (`run_session.py`) for the acquisition PC. See its README.

## Build

```sh
latexmk -pdf -bibtex- notes.tex   # then: biber notes && latexmk -pdf notes.tex
```

Moved out of the `harmonia` repository (neurofeedback project) on 2026-08-26.
