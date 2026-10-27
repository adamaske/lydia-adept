# LYDIA-ADEPT — Auditory Environment, Cognitive Load & fNIRS

The effect of the auditory environment (noise, soundscape, ANC, entrainment) on
mental workload and task performance, measured with mobile non-invasive
neuroimaging (primarily fNIRS, plus EEG).

```
literature/        reading notes (notes.tex, biblatex/biber) + references.bib; paper PDFs stay local
audio/             lab soundscape recording and spectral analysis
studies/<study>/   one folder per study, layout below
report/            the Overleaf project (own git repo, not tracked here): main.tex is the
                   LYDIA-ADEPT report, report/<study>/<study>.tex one chapter per study
```

## Studies

| study | what |
|---|---|
| [`piano-noise`](studies/piano-noise/README.md) | fNIRS while a pianist plays in quiet and in noise |

Every study folder has the same layout (leave out what a study doesn't need):

```
README.md      how to run it
docs/          protocol, plans, notes
montage/       probe layout / cap files
stimuli/       audio etc. (large files not in git)
scripts/       acquisition: experiment, triggers, checks
data/          raw/ recordings, logs/ per-session logs, *.csv session tables, pilot/ dry runs;
               processed/ is regenerable and not in git
analysis/      analysis code and exports for the current cohort
archive/       finished reports with the exact analysis they were built from
```

## Report (Overleaf)

```sh
git clone https://git.overleaf.com/6a32fa664f35f5909d3e4fda report
cd report && latexmk -pdf -outdir=build main.tex
```

## Notes

```sh
cd literature && latexmk -pdf notes.tex   # biber runs via latexmk
```

Moved out of the `harmonia` repository (neurofeedback project) on 2026-08-26.
